"""Restore the rolling research ledger; fail closed on API/expiry/corruption errors."""
import io
import json
import os
from pathlib import Path
import zipfile

import requests


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GH_API_TOKEN"]
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    api = f"https://api.github.com/repos/{repo}"
    response = requests.get(f"{api}/actions/artifacts", headers=headers,
                            params={"name": "research-ledger-v1", "per_page": 100}, timeout=30)
    response.raise_for_status()
    artifacts = [a for a in response.json()["artifacts"]
                 if a["name"] == "research-ledger-v1" and a.get("workflow_run", {}).get("head_branch") == "main"]
    if not artifacts:
        # Explicit bootstrap prevents silently resetting missing/expired history.
        print("No research ledger found. Bootstrap requires RESEARCH_ALLOW_BOOTSTRAP=true.")
        if os.getenv("RESEARCH_ALLOW_BOOTSTRAP") != "true":
            raise RuntimeError("Research history missing; explicitly authorize first-run bootstrap")
        return
    latest = max(artifacts, key=lambda a: a["created_at"])
    if latest["expired"]:
        raise RuntimeError("Latest research ledger expired; restore a backup instead of resetting history")
    response = requests.get(f"{api}/actions/artifacts/{latest['id']}/zip", headers=headers, timeout=60)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        payload = archive.read("state.json")
    state = json.loads(payload)
    if state.get("schema_version") != 1 or not isinstance(state.get("records"), list):
        raise ValueError("Invalid research ledger")
    path = Path("research-state/state.json")
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(payload)
    print(f"Restored {len(state['records'])} research records")


if __name__ == "__main__":
    main()

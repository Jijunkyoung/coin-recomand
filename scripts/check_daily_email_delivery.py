"""Skip the fallback mail run when today's successful delivery marker exists."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone


KST = timezone(timedelta(hours=9))


def marker_name(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    return f"daily-email-kst-{current.astimezone(KST):%Y-%m-%d}"


def has_active_marker(payload: dict, expected_name: str) -> bool:
    return any(
        item.get("name") == expected_name and not item.get("expired", False)
        for item in payload.get("artifacts", [])
    )


def main() -> None:
    name = marker_name()
    force = os.getenv("FORCE_SEND", "").lower() in {"1", "true", "yes"}
    exists = False
    token, repository = os.getenv("GH_API_TOKEN", "").strip(), os.getenv("GH_REPOSITORY", "").strip()
    if not force and token and repository:
        query = urllib.parse.urlencode({"name": name, "per_page": 10})
        request = urllib.request.Request(
            f"https://api.github.com/repos/{repository}/actions/artifacts?{query}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "User-Agent": "coin-recomand"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            exists = has_active_marker(json.load(response), name)
    output_path = os.getenv("GITHUB_OUTPUT")
    lines = f"marker_name={name}\nshould_send={'false' if exists else 'true'}\n"
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            output.write(lines)
    print("오늘 발송 완료 기록이 있어 예비 발송을 건너뜁니다." if exists else "오늘 보고서 발송을 진행합니다.")


if __name__ == "__main__":
    main()

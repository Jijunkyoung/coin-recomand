"""Resolve the only confirmed Supabase user without exposing account details."""
from __future__ import annotations

import json
import os
import urllib.parse
from pathlib import Path
from urllib.request import Request, urlopen


def _required(name: str, environ: dict[str, str]) -> str:
    value = environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def resolve_owner_id(environ: dict[str, str] | None = None) -> str:
    env = dict(os.environ if environ is None else environ)
    url = _required("SUPABASE_URL", env).rstrip("/")
    secret = _required("SUPABASE_SERVICE_ROLE_KEY", env)
    query = urllib.parse.urlencode({"page": 1, "per_page": 1000})
    request = Request(
        f"{url}/auth/v1/admin/users?{query}",
        headers={"apikey": secret, "Authorization": f"Bearer {secret}"},
    )
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    users = payload.get("users", []) if isinstance(payload, dict) else []
    confirmed = [
        user for user in users
        if isinstance(user, dict) and user.get("email_confirmed_at") and user.get("id")
    ]
    if len(users) != 1 or len(confirmed) != 1:
        raise RuntimeError(
            "Owner binding requires exactly one confirmed account "
            f"(total users: {len(users)}, confirmed users: {len(confirmed)})"
        )
    return str(confirmed[0]["id"]).strip()


def main() -> None:
    owner_id = resolve_owner_id()
    github_env = Path(_required("GITHUB_ENV", dict(os.environ)))
    print(f"::add-mask::{owner_id}")
    with github_env.open("a", encoding="utf-8") as stream:
        stream.write(f"BOUND_KIS_OWNER_USER_ID={owner_id}\n")
    print("Resolved the sole confirmed account for owner-only KIS access.")


if __name__ == "__main__":
    main()

"""Confirm only the preconfigured owner's existing Supabase account."""
from __future__ import annotations

import json
import os
import re
import urllib.parse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


EMAIL_PATTERN = re.compile(r"^[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+$")


def _required(name: str, environ: dict[str, str]) -> str:
    value = environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} secret is missing")
    return value


def _request_json(request: Request, email: str, secret: str) -> dict:
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        detail = ""
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            candidate = payload.get("message") or payload.get("msg") or payload.get("error")
            if isinstance(candidate, str):
                detail = candidate
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            pass
        for value in (email, secret):
            detail = re.sub(re.escape(value), "[redacted]", detail, flags=re.IGNORECASE)
        suffix = f": {detail[:300]}" if detail else ""
        raise RuntimeError(f"Supabase owner confirmation failed (HTTP {exc.code}){suffix}") from exc
    except URLError as exc:
        raise RuntimeError("Supabase owner confirmation request failed") from exc


def confirm_owner(environ: dict[str, str] | None = None) -> str:
    env = dict(os.environ if environ is None else environ)
    supabase_url = _required("SUPABASE_URL", env).rstrip("/")
    secret = _required("SUPABASE_SERVICE_ROLE_KEY", env)
    owner_email = _required("KIS_OWNER_EMAIL_CANDIDATE", env).lower()
    if not EMAIL_PATTERN.fullmatch(owner_email):
        raise ValueError("KIS owner email must contain exactly one valid address")

    headers = {
        "apikey": secret,
        "Authorization": f"Bearer {secret}",
        "Content-Type": "application/json",
    }
    query = urllib.parse.urlencode({"page": 1, "per_page": 1000})
    users_payload = _request_json(
        Request(f"{supabase_url}/auth/v1/admin/users?{query}", headers=headers),
        owner_email,
        secret,
    )
    users = users_payload.get("users", []) if isinstance(users_payload, dict) else []
    matches = [
        user
        for user in users
        if isinstance(user, dict) and str(user.get("email") or "").strip().lower() == owner_email
    ]
    if len(matches) != 1:
        unconfirmed_count = sum(
            1
            for user in users
            if isinstance(user, dict) and not user.get("email_confirmed_at")
        )
        raise RuntimeError(
            "Expected exactly one existing owner account; "
            f"found {len(matches)} (total users: {len(users)}, unconfirmed users: {unconfirmed_count})"
        )

    user = matches[0]
    user_id = str(user.get("id") or "").strip()
    if not user_id:
        raise RuntimeError("Owner account has no user id")
    if user.get("email_confirmed_at"):
        return "already-confirmed"

    confirmed = _request_json(
        Request(
            f"{supabase_url}/auth/v1/admin/users/{urllib.parse.quote(user_id, safe='')}",
            data=json.dumps({"email_confirm": True}).encode("utf-8"),
            headers=headers,
            method="PUT",
        ),
        owner_email,
        secret,
    )
    confirmed_user = confirmed.get("user", confirmed) if isinstance(confirmed, dict) else {}
    if str(confirmed_user.get("email") or "").strip().lower() != owner_email:
        raise RuntimeError("Supabase confirmed a different account than the configured owner")
    if not confirmed_user.get("email_confirmed_at"):
        raise RuntimeError("Supabase did not confirm the owner's email")
    return "confirmed"


def main() -> None:
    result = confirm_owner()
    print("The configured owner account is email-confirmed." if result == "confirmed" else "The configured owner account was already email-confirmed.")


if __name__ == "__main__":
    main()

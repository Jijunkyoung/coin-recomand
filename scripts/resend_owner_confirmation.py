"""Resend the owner's pending Supabase signup confirmation without logging secrets."""
from __future__ import annotations

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


EMAIL_PATTERN = re.compile(r"^[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+$")
DEFAULT_REDIRECT_URL = "https://jijunkyoung.github.io/coin-recomand/"


def _required(name: str, environ: dict[str, str]) -> str:
    value = environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} secret is missing")
    return value


def _safe_error(exc: HTTPError, email: str, secrets: list[str]) -> str:
    detail = ""
    try:
        payload = json.loads(exc.read().decode("utf-8"))
        candidate = (
            payload.get("message")
            or payload.get("msg")
            or payload.get("error_description")
            or payload.get("error")
        )
        if isinstance(candidate, str):
            detail = candidate
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        pass
    for value in [email, *secrets]:
        if value:
            detail = re.sub(re.escape(value), "[redacted]", detail, flags=re.IGNORECASE)
    return detail[:300]


def resend_confirmation(environ: dict[str, str] | None = None) -> dict:
    env = dict(os.environ if environ is None else environ)
    supabase_url = _required("SUPABASE_URL", env).rstrip("/")
    anon_key = _required("SUPABASE_ANON_KEY", env)
    email = _required("KIS_OWNER_EMAIL_CANDIDATE", env).lower()
    if not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("KIS owner email must contain exactly one valid address")

    body = {
        "type": "signup",
        "email": email,
        "options": {
            "emailRedirectTo": env.get("AUTH_REDIRECT_URL", DEFAULT_REDIRECT_URL).strip()
            or DEFAULT_REDIRECT_URL
        },
    }
    request = Request(
        f"{supabase_url}/auth/v1/resend",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "apikey": anon_key,
            "Authorization": f"Bearer {anon_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        detail = _safe_error(exc, email, [anon_key])
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"Confirmation resend failed (HTTP {exc.code}){suffix}") from exc
    except URLError as exc:
        raise RuntimeError("Confirmation resend request failed") from exc


def main() -> None:
    resend_confirmation()
    print("Supabase accepted the owner's signup confirmation resend request.")


if __name__ == "__main__":
    main()

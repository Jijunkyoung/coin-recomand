"""Configure Supabase Auth email delivery without exposing SMTP credentials."""
from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


AUTH_CONFIG_URL = "https://api.supabase.com/v1/projects/{project_ref}/config/auth"
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _required(name: str, environ: dict[str, str]) -> str:
    value = environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} secret is missing")
    return value


def build_payload(environ: dict[str, str] | None = None) -> dict[str, Any]:
    env = dict(os.environ if environ is None else environ)
    smtp_user = _required("SMTP_USERNAME", env)
    if not EMAIL_PATTERN.fullmatch(smtp_user):
        raise ValueError("SMTP_USERNAME must be a valid sender email address")
    try:
        smtp_port = int(env.get("SMTP_PORT", "465").strip() or "465")
    except ValueError as exc:
        raise ValueError("SMTP_PORT must be a number") from exc
    if not 1 <= smtp_port <= 65535:
        raise ValueError("SMTP_PORT must be between 1 and 65535")

    return {
        "external_email_enabled": True,
        "mailer_secure_email_change_enabled": True,
        "mailer_autoconfirm": False,
        "smtp_admin_email": smtp_user,
        "smtp_host": _required("SMTP_HOST", env),
        "smtp_port": smtp_port,
        "smtp_user": smtp_user,
        "smtp_pass": _required("SMTP_PASSWORD", env),
        "smtp_sender_name": "Coin Signal Desk",
    }


def configure_auth(environ: dict[str, str] | None = None) -> dict[str, Any]:
    env = dict(os.environ if environ is None else environ)
    project_ref = _required("SUPABASE_PROJECT_REF", env)
    access_token = _required("SUPABASE_ACCESS_TOKEN", env)
    payload = build_payload(env)
    request = Request(
        AUTH_CONFIG_URL.format(project_ref=project_ref),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="PATCH",
    )
    try:
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
    except HTTPError as exc:
        detail = ""
        try:
            error_data = json.loads(exc.read().decode("utf-8"))
            candidate = error_data.get("message") or error_data.get("msg") or error_data.get("error")
            if isinstance(candidate, str):
                detail = candidate
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            pass
        for name in ("SUPABASE_ACCESS_TOKEN", "SMTP_PASSWORD", "SMTP_USERNAME"):
            secret = env.get(name, "")
            if secret:
                detail = detail.replace(secret, "[redacted]")
        suffix = f": {detail[:300]}" if detail else ""
        raise RuntimeError(f"Supabase Auth configuration failed (HTTP {exc.code}){suffix}") from exc
    except URLError as exc:
        raise RuntimeError("Supabase Auth configuration request failed") from exc

    if result.get("smtp_host") != payload["smtp_host"]:
        raise RuntimeError("Supabase did not confirm the custom SMTP host")
    if result.get("mailer_autoconfirm") is not False:
        raise RuntimeError("Supabase email confirmation is not enabled")
    return result


def main() -> None:
    configure_auth()
    print("Supabase Auth custom SMTP is configured; email confirmation remains enabled.")


if __name__ == "__main__":
    main()

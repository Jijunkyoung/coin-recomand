"""Write a validated public Supabase configuration into the Pages artifact."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


PROJECT_REF = "pgtxtnggjqaysjhtdepz"


def _jwt_role(value: str) -> str:
    try:
        payload = value.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return str(json.loads(base64.urlsafe_b64decode(payload))["role"])
    except (IndexError, KeyError, ValueError, json.JSONDecodeError):
        return ""


def _is_public_key(value: str) -> bool:
    return value.startswith("sb_publishable_") or _jwt_role(value) == "anon"


def _fetch_public_key(project_ref: str, access_token: str) -> str:
    request = Request(
        f"https://api.supabase.com/v1/projects/{project_ref}/api-keys?reveal=true",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    )
    with urlopen(request, timeout=30) as response:
        keys = json.load(response)
    if not isinstance(keys, list):
        raise RuntimeError("Supabase API key response was not a list")
    candidates: list[str] = []
    for item in keys:
        if not isinstance(item, dict):
            continue
        value = str(item.get("api_key") or item.get("key") or "").strip()
        key_type = str(item.get("type") or "").lower()
        name = str(item.get("name") or "").lower()
        if _is_public_key(value) and (key_type == "publishable" or name in {"anon", "publishable", "default"}):
            candidates.append(value)
    candidates.sort(key=lambda value: not value.startswith("sb_publishable_"))
    if not candidates:
        raise RuntimeError("No Supabase publishable/anon key was found")
    return candidates[0]


def _validate_public_key(url: str, key: str) -> None:
    request = Request(
        f"{url.rstrip('/')}/auth/v1/settings",
        headers={"apikey": key, "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            settings = json.load(response)
    except HTTPError as error:
        if error.code in {401, 403}:
            raise RuntimeError(
                f"Supabase rejected the configured public login key (HTTP {error.code}). "
                "Replace SUPABASE_ANON_KEY with this project's current publishable/anon key."
            ) from None
        raise RuntimeError(f"Supabase public login key verification failed (HTTP {error.code}).") from None
    except (URLError, TimeoutError, ValueError):
        raise RuntimeError("Supabase public login key verification is unavailable; no login configuration was written.") from None
    if not isinstance(settings, dict):
        raise RuntimeError("Supabase returned an invalid Auth settings response; no login configuration was written.")


def main() -> None:
    project_ref = os.getenv("SUPABASE_PROJECT_REF", PROJECT_REF).strip()
    url = os.getenv("SUPABASE_URL", "").strip() or f"https://{project_ref}.supabase.co"
    key = os.getenv("SUPABASE_ANON_KEY", "").strip()
    access_token = os.getenv("SUPABASE_ACCESS_TOKEN", "").strip()
    expected_host = f"{project_ref}.supabase.co"
    parsed_url = urlsplit(url)
    if (parsed_url.scheme != "https" or parsed_url.netloc != expected_host
            or parsed_url.path not in {"", "/"} or parsed_url.query or parsed_url.fragment):
        raise RuntimeError(f"SUPABASE_URL must target {expected_host}")
    # The public browser key is sufficient for a static deployment. Do not let
    # an unrelated expired management token override an explicitly configured key.
    if not key:
        if not access_token:
            raise RuntimeError("SUPABASE_ANON_KEY or SUPABASE_ACCESS_TOKEN is required")
        try:
            key = _fetch_public_key(project_ref, access_token)
        except HTTPError as error:
            raise RuntimeError(
                f"Public login key lookup failed (HTTP {error.code}). "
                "Set SUPABASE_ANON_KEY to the project's publishable/anon key, "
                "or renew SUPABASE_ACCESS_TOKEN."
            ) from None
        except (URLError, TimeoutError) as error:
            raise RuntimeError("Public login key lookup is unavailable; configure SUPABASE_ANON_KEY directly.") from None
    if not _is_public_key(key):
        raise RuntimeError("SUPABASE_ANON_KEY must be a publishable key or legacy anon JWT")
    _validate_public_key(url, key)
    config = {
        "url": url.rstrip("/"),
        "anonKey": key,
    }
    target = Path("docs/supabase-runtime-config.js")
    target.write_text(
        "window.COIN_RECOMAND_SUPABASE = Object.freeze("
        + json.dumps(config, ensure_ascii=False)
        + ");\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

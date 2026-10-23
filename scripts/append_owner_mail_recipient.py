"""Append one explicitly selected, already configured address to both owner lists.

The address is selected by fingerprint from repository secrets, never embedded in
public source. Only email preference columns are changed, with a concurrency
check; account identity and other recipients are preserved.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from scripts.bind_sole_owner import resolve_owner_id
from scripts.load_member_settings import valid_recipients


def addresses(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[,;\n]+", value) if item.strip()]


def select_recipient(env: dict[str, str]) -> str:
    fingerprint = env.get("RECIPIENT_SHA256", "").strip().lower()
    if not re.fullmatch(r"[a-f0-9]{64}", fingerprint):
        raise ValueError("A valid recipient fingerprint is required")
    candidates = addresses(env.get("EMAIL_TO", "")) + addresses(env.get("STOCK_EMAIL_TO", ""))
    matches = {value.lower() for value in candidates
               if hashlib.sha256(value.lower().encode()).hexdigest() == fingerprint}
    if len(matches) != 1 or not valid_recipients(next(iter(matches), "")):
        raise ValueError("The selected recipient was not found in existing mail secrets")
    return matches.pop()


def append_recipient(value: str, recipient: str) -> str:
    if not valid_recipients(value):
        raise ValueError("The existing recipient list is invalid")
    items = addresses(value)
    if recipient.lower() in {item.lower() for item in items}:
        return value
    merged = ", ".join([*items, recipient])
    if len(merged) > 320:
        raise ValueError("The recipient list exceeds the stored setting limit")
    return merged


def request_json(env: dict[str, str], path: str, method: str = "GET", payload=None):
    key = env["SUPABASE_SERVICE_ROLE_KEY"].strip()
    headers = {"apikey": key, "Authorization": f"Bearer {key}",
               "Content-Type": "application/json", "Prefer": "return=representation"}
    scheduler_key = env.get("KIS_SCHEDULER_KEY", "").strip()
    if scheduler_key:
        headers["x-kis-scheduler-key"] = scheduler_key
    request = Request(env["SUPABASE_URL"].strip().rstrip("/") + path,
                      data=None if payload is None else json.dumps(payload).encode(),
                      method=method, headers=headers)
    try:
        with urlopen(request, timeout=45) as response:
            return json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"Mail preference request failed (HTTP {error.code})") from None


def run(env: dict[str, str]) -> bool:
    recipient = select_recipient(env)
    # Refuse ambiguous membership rather than selecting an arbitrary user.
    owner_id = resolve_owner_id(env)
    query = urlencode({"user_id": f"eq.{owner_id}", "select": "coin_email,stock_email"})
    rows = request_json(env, f"/rest/v1/user_preferences?{query}")
    if not isinstance(rows, list) or len(rows) != 1:
        raise RuntimeError("The existing owner's preference row was not found")
    current = rows[0]
    profile = request_json(env, "/functions/v1/owner-settings", "POST", {}).get("profile") or {}
    updated = {name: append_recipient(str(current.get(name) or profile.get(name) or ""), recipient)
               for name in ("coin_email", "stock_email")}
    changed = any(current.get(name) != value for name, value in updated.items())
    if changed:
        filters = {"user_id": f"eq.{owner_id}", "select": "coin_email,stock_email"}
        for name in updated:
            # A one-item IN list explicitly supports quoted text (including
            # commas). EQ treats quotes as part of the scalar on some servers.
            filters[name] = "is.null" if current.get(name) is None else "in.(" + json.dumps(current[name]) + ")"
        saved = request_json(env, "/rest/v1/user_preferences?" + urlencode(filters), "PATCH", updated)
        if saved != [updated]:
            count = len(saved) if isinstance(saved, list) else "unexpected response"
            raise RuntimeError(f"Preference settings changed concurrently; reload before retrying (matched rows: {count})")
    verified = request_json(env, "/functions/v1/owner-settings", "POST", {}).get("profile") or {}
    if any(recipient not in {value.lower() for value in addresses(str(verified.get(name) or ""))}
           for name in updated):
        raise RuntimeError("The effective coin and stock recipient lists could not be verified")
    return changed


if __name__ == "__main__":
    try:
        changed = run(dict(os.environ))
        print("Verified: selected recipient is saved in both coin and stock browser preferences. "
              + ("Existing recipients preserved." if changed else "Already configured; no changes needed."))
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        raise SystemExit(str(error)) from None

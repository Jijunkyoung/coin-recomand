"""Skip the fallback mail run when today's successful delivery marker exists."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone


KST = timezone(timedelta(hours=9))


def marker_name(now: datetime | None = None, scope: str = "") -> str:
    current = now or datetime.now(timezone.utc)
    base = f"daily-email-kst-{current.astimezone(KST):%Y-%m-%d}"
    normalized_scope = scope.strip().lower()
    return f"{base}-{normalized_scope}" if normalized_scope else base


def has_active_marker(payload: dict, expected_name: str) -> bool:
    return any(
        item.get("name") == expected_name and not item.get("expired", False)
        for item in payload.get("artifacts", [])
    )


def is_not_before_kst(value: str, now: datetime | None = None) -> bool:
    """Return whether the Korean local time reached an optional HH:MM threshold."""
    if not value.strip():
        return True
    try:
        hour, minute = (int(part) for part in value.split(":", 1))
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("NOT_BEFORE_KST는 HH:MM 형식이어야 합니다.") from None
    current = (now or datetime.now(timezone.utc)).astimezone(KST)
    return (current.hour, current.minute) >= (hour, minute)


def main() -> None:
    scope = os.getenv("DELIVERY_MARKER_SCOPE", "").strip().lower()
    name = marker_name(scope=scope)
    force = os.getenv("FORCE_SEND", "").lower() in {"1", "true", "yes"}
    eligible = force or is_not_before_kst(os.getenv("NOT_BEFORE_KST", ""))
    exists = False
    token, repository = os.getenv("GH_API_TOKEN", "").strip(), os.getenv("GH_REPOSITORY", "").strip()
    if eligible and not force and token and repository:
        query = urllib.parse.urlencode({"name": name, "per_page": 10})
        request = urllib.request.Request(
            f"https://api.github.com/repos/{repository}/actions/artifacts?{query}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "User-Agent": "coin-recomand"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            exists = has_active_marker(json.load(response), name)
    output_path = os.getenv("GITHUB_OUTPUT")
    should_send = eligible and not exists
    lines = f"marker_name={name}\nshould_send={'true' if should_send else 'false'}\n"
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            output.write(lines)
    if not eligible:
        print("한국시간 예약 발송 시각 전이므로 보고서 발송을 기다립니다.")
    else:
        label = {"coin": "코인", "stock": "주식"}.get(scope, "보고서")
        print(f"오늘 {label} 메일 발송 완료 기록이 있어 건너뜁니다." if exists else f"오늘 {label} 메일 발송을 진행합니다.")


if __name__ == "__main__":
    main()

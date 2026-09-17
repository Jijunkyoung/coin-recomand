"""Load the single KIS owner's live portfolio and mail preferences for a scheduled report."""
from __future__ import annotations

import json
import os
import re
import urllib.request
import urllib.error
import uuid
from pathlib import Path


def function_url(supabase_url: str) -> str:
    return f"{supabase_url.rstrip('/')}/functions/v1/kis-portfolio"


def env_block(name: str, value: str) -> str:
    delimiter = f"EOF_{uuid.uuid4().hex}"
    return f"{name}<<{delimiter}\n{value}\n{delimiter}\n"


def validate_profile(payload: dict) -> dict:
    profile = payload.get("mail_profile") or {}
    email = str(profile.get("stock_email") or "").strip()
    addresses = [item.strip() for item in re.split(r"[,;\n]+", email) if item.strip()]
    if not addresses or any(not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", item) for item in addresses):
        raise ValueError("소유자 주식 메일 주소가 비어 있거나 형식이 올바르지 않습니다.")
    if not isinstance(payload.get("positions"), list):
        raise ValueError("KIS 계좌 보유현황 응답이 올바르지 않습니다.")
    return profile


def load_payload(url: str, service_key: str, scheduler_key: str) -> dict:
    request = urllib.request.Request(
        function_url(url), data=b"{}", method="POST",
        headers={
            "apikey": service_key,
            "x-kis-scheduler-key": scheduler_key, "content-type": "application/json",
            "user-agent": "coin-recomand-actions",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Supabase KIS 함수 호출 실패 (HTTP {error.code}): {detail[:300]}") from error
    if payload.get("error"):
        raise RuntimeError(str(payload["error"]))
    return payload


def main() -> None:
    url = os.getenv("SUPABASE_URL", "").strip()
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    scheduler_key = os.getenv("KIS_SCHEDULER_KEY", "").strip()
    required = os.getenv("REQUIRE_MEMBER_STOCK_PROFILE", "").lower() in {"1", "true", "yes"}
    missing = [
        name for name, value in (
            ("SUPABASE_URL", url),
            ("SUPABASE_SERVICE_ROLE_KEY", service_key),
            ("KIS_SCHEDULER_KEY", scheduler_key),
        ) if not value
    ]
    if missing:
        message = f"회원 KIS 예약메일 필수 Secret이 없습니다: {', '.join(missing)}"
        if required:
            raise SystemExit(message)
        print(f"{message}. 기존 주식 설정을 사용합니다.")
        return

    payload = load_payload(url, service_key, scheduler_key)
    profile = validate_profile(payload)
    runtime_dir = Path(".runtime")
    runtime_dir.mkdir(exist_ok=True)
    snapshot_path = runtime_dir / "member-kis-portfolio.json"
    snapshot_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    values = {
        "MEMBER_STOCK_HOLDINGS_US": str(profile.get("holdings_us") or ""),
        "MEMBER_STOCK_HOLDINGS_KR": str(profile.get("holdings_kr") or ""),
        "MEMBER_STOCK_SECTORS": ",".join(str(item) for item in profile.get("sector_ids") or []),
        "MEMBER_STOCK_EMAIL_TO": str(profile.get("stock_email") or ""),
        "MEMBER_KIS_PORTFOLIO_PATH": str(snapshot_path.resolve()),
    }
    github_env = os.getenv("GITHUB_ENV", "").strip()
    if github_env:
        with open(github_env, "a", encoding="utf-8") as output:
            for name, value in values.items():
                output.write(env_block(name, value))
    else:
        for name in values:
            print(f"{name}=<loaded>")
    print(f"소유자 KIS 계좌 {len(payload.get('positions') or [])}개 종목과 개인 주식 메일 설정을 불러왔습니다.")


if __name__ == "__main__":
    main()

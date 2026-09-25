"""Load the owner's browser-saved mail and personalization settings."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
import uuid


def env_block(name: str, value: str) -> str:
    delimiter = f"EOF_{uuid.uuid4().hex}"
    return f"{name}<<{delimiter}\n{value}\n{delimiter}\n"


def valid_recipients(value: str) -> bool:
    addresses = [item.strip() for item in re.split(r"[,;\n]+", value) if item.strip()]
    return bool(addresses) and all(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", item) for item in addresses)


def main() -> None:
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    scheduler_key = os.getenv("KIS_SCHEDULER_KEY", "").strip()
    if not url or not service_key or not scheduler_key:
        raise SystemExit("회원 맞춤 설정을 불러올 Supabase 서버값이 없습니다.")
    request = urllib.request.Request(
        f"{url}/functions/v1/owner-settings", data=b"{}", method="POST",
        headers={"apikey": service_key, "x-kis-scheduler-key": scheduler_key, "content-type": "application/json", "user-agent": "coin-recomand-actions"},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"회원 맞춤 설정 조회 실패 (HTTP {error.code}): {detail[:300]}") from error
    if payload.get("error"):
        raise SystemExit(str(payload["error"]))
    profile = payload.get("profile") or {}
    coin_email, stock_email = str(profile.get("coin_email") or "").strip(), str(profile.get("stock_email") or "").strip()
    if not valid_recipients(coin_email) or not valid_recipients(stock_email):
        raise SystemExit("브라우저에 저장된 코인 또는 주식 수신주소 형식이 올바르지 않습니다.")
    values = {
        "MEMBER_COIN_EMAIL_TO": coin_email, "MEMBER_STOCK_EMAIL_TO": stock_email,
        "MEMBER_STOCK_HOLDINGS_US": str(profile.get("holdings_us") or ""),
        "MEMBER_STOCK_HOLDINGS_KR": str(profile.get("holdings_kr") or ""),
        "MEMBER_STOCK_SECTORS": ",".join(str(item) for item in profile.get("sector_ids") or []),
    }
    github_env = os.getenv("GITHUB_ENV", "").strip()
    if github_env:
        with open(github_env, "a", encoding="utf-8") as output:
            for name, value in values.items():
                output.write(env_block(name, value))
    print("회원의 브라우저 저장 코인·주식 메일 설정을 불러왔습니다.")


if __name__ == "__main__":
    main()

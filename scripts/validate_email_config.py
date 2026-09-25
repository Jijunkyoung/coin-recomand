"""Fail a scheduled mail job before analysis when required secrets are missing."""
from __future__ import annotations

import os


def main() -> None:
    missing = [name for name in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD") if not os.getenv(name, "").strip()]
    coin_recipient = os.getenv("MEMBER_COIN_EMAIL_TO", "").strip() or os.getenv("EMAIL_TO", "").strip()
    stock_recipient = os.getenv("MEMBER_STOCK_EMAIL_TO", "").strip() or os.getenv("STOCK_EMAIL_TO", "").strip()
    if not coin_recipient and not stock_recipient:
        missing.append("회원 또는 기본 코인·주식 수신주소")
    if missing:
        raise SystemExit("메일 발송 필수 Secret 누락: " + ", ".join(missing))
    print("SMTP와 발송 대상 수신주소가 준비되어 있습니다.")


if __name__ == "__main__":
    main()

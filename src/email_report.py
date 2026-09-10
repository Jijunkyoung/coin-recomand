from __future__ import annotations

import html
import os
import smtplib
from email.message import EmailMessage
from typing import Any


def build_email_html(report: dict[str, Any]) -> str:
    market = report["market"]
    rows = []
    for coin in report["recommendations"]:
        reasons = coin["reasons"][:3] if coin["reasons"] else ["점수 기준 상위 종목"]
        risks = coin["risks"][:3] if coin["risks"] else ["뚜렷한 정량 위험 신호 없음"]
        rows.append(
            "<tr>"
            f"<td>{html.escape(coin['name'])} ({html.escape(coin['symbol'])})</td>"
            f"<td>{coin['score']}</td><td>{html.escape(coin['decision'])}</td>"
            f"<td>{'<br>'.join(html.escape(reason) for reason in reasons)}</td>"
            f"<td>{'<br>'.join(html.escape(risk) for risk in risks)}</td>"
            "</tr>"
        )
    warning = "<p style='color:#b45309'>하락장에서는 신규 매수 후보를 표시하지 않습니다.</p>" if market["regime"] == "하락" else ""
    mvrv = market["bitcoin"].get("mvrv_z")
    mvrv_text = f"{mvrv:.2f}" if mvrv is not None else "미수집"
    mvrv_source = market["bitcoin"].get("mvrv_source")
    if mvrv_source:
        mvrv_text += f" ({mvrv_source})"
    return f"""
    <div style="font-family:Arial,'Noto Sans KR',sans-serif;max-width:760px;margin:auto;color:#172033">
      <h1 style="font-size:24px">코인 시장 분석 보고서</h1>
      <p>{html.escape(report['generated_at_kst'])} 기준</p>
      <div style="padding:18px;background:#eef4ff;border-radius:12px">
        <strong>비트코인 시장 국면: {html.escape(market['regime'])} · {market['score']}점</strong><br>
        BTC ₩{market['bitcoin']['price']:,.0f} · MVRV Z {mvrv_text}
      </div>
      {warning}
      <h2 style="font-size:19px">알트코인 우선순위</h2>
      <table style="width:100%;border-collapse:collapse" border="1" cellpadding="8">
        <thead><tr><th>종목</th><th>점수</th><th>판정</th><th>호재·선정 근거</th><th>악재·위험</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
      <p style="font-size:12px;color:#64748b">본 보고서는 정량 지표 기반 참고자료이며 투자 자문이나 수익 보장이 아닙니다. 실제 주문을 실행하지 않습니다.</p>
    </div>
    """


def send_email(report: dict[str, Any]) -> bool:
    required = {
        "SMTP_HOST": os.getenv("SMTP_HOST", "").strip(),
        "SMTP_USERNAME": os.getenv("SMTP_USERNAME", "").strip(),
        "SMTP_PASSWORD": os.getenv("SMTP_PASSWORD", "").strip(),
        "EMAIL_TO": os.getenv("EMAIL_TO", "").strip(),
    }
    if not all(required.values()):
        print("메일 설정이 없어 발송을 건너뜁니다.")
        return False
    port = int(os.getenv("SMTP_PORT", "465"))
    sender = os.getenv("EMAIL_FROM", "").strip() or required["SMTP_USERNAME"]
    recipients = [address.strip() for address in required["EMAIL_TO"].split(",") if address.strip()]
    message = EmailMessage()
    message["Subject"] = f"[{report['market']['regime']}] 코인 분석 {report['generated_at_kst'][:10]}"
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content("HTML을 지원하는 메일 앱에서 보고서를 확인해 주세요.")
    message.add_alternative(build_email_html(report), subtype="html")
    if port == 465:
        with smtplib.SMTP_SSL(required["SMTP_HOST"], port, timeout=30) as smtp:
            smtp.login(required["SMTP_USERNAME"], required["SMTP_PASSWORD"])
            smtp.send_message(message)
    else:
        with smtplib.SMTP(required["SMTP_HOST"], port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(required["SMTP_USERNAME"], required["SMTP_PASSWORD"])
            smtp.send_message(message)
    print(f"분석 메일을 {len(recipients)}개 주소로 발송했습니다.")
    return True

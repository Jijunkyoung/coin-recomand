from __future__ import annotations

import html
import os
import re
import smtplib
from email.message import EmailMessage
from typing import Any


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def parse_recipients(value: str) -> list[str]:
    recipients: list[str] = []
    seen: set[str] = set()
    for raw in re.split(r"[,;\n]+", value):
        address = raw.strip()
        normalized = address.lower()
        if not address or normalized in seen:
            continue
        if not EMAIL_PATTERN.fullmatch(address):
            raise ValueError(f"잘못된 수신 이메일 주소: {address}")
        recipients.append(address)
        seen.add(normalized)
    return recipients


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
    cmc = market.get("coinmarketcap") or {}
    liquidity = market.get("liquidity") or {}

    def money(value: Any) -> str:
        if value is None:
            return "미수집"
        number = float(value)
        if abs(number) >= 1_000_000_000_000:
            return f"${number / 1_000_000_000_000:.2f}T"
        if abs(number) >= 1_000_000_000:
            return f"${number / 1_000_000_000:.1f}B"
        return f"${number:,.0f}"

    def pct(value: Any) -> str:
        return "미수집" if value is None else f"{float(value):+.2f}%"

    market_context = (
        "<div style='margin-top:12px;padding:14px;background:#f8fafc;border-radius:10px'>"
        "<strong>시장 보조지표</strong><br>"
        f"BTC 도미넌스 {cmc.get('btc_dominance', '미수집')}% · 전체 시총 {money(cmc.get('total_market_cap_usd'))}<br>"
        f"DeFi TVL {money(liquidity.get('defi_tvl_usd'))} ({pct(liquidity.get('defi_tvl_change_7d'))}, 7일) · "
        f"스테이블코인 공급 {money(liquidity.get('stablecoin_supply_usd'))} ({pct(liquidity.get('stablecoin_supply_change_7d'))}, 7일)"
        "</div>"
    )
    issue_rows = []
    for issue in report.get("news_issues", [])[:7]:
        symbols = ", ".join(issue.get("related_symbols") or []) or "시장 전체"
        issue_rows.append(
            "<li style='margin:0 0 12px'>"
            f"<a href='{html.escape(issue.get('url', ''), quote=True)}' style='color:#1d4ed8;text-decoration:none'>"
            f"<strong>{html.escape(issue.get('title', '제목 없음'))}</strong></a><br>"
            f"<span style='font-size:12px;color:#64748b'>{html.escape(issue.get('published_at_kst', ''))} KST · "
            f"{html.escape(issue.get('source', '출처 미상'))} · {html.escape(issue.get('category', '시장'))} · "
            f"{html.escape(issue.get('impact', '중립·혼재'))} · 관련: {html.escape(symbols)}</span>"
            "</li>"
        )
    issues_html = (
        f"<ul style='padding-left:20px'>{''.join(issue_rows)}</ul>"
        if issue_rows
        else "<p style='color:#64748b'>최근 24시간 주요 이슈를 수집하지 못했거나 선별된 기사가 없습니다.</p>"
    )
    return f"""
    <div style="font-family:Arial,'Noto Sans KR',sans-serif;max-width:760px;margin:auto;color:#172033">
      <h1 style="font-size:24px">코인 시장 분석 보고서</h1>
      <p>{html.escape(report['generated_at_kst'])} 기준</p>
      <div style="padding:18px;background:#eef4ff;border-radius:12px">
        <strong>비트코인 시장 국면: {html.escape(market['regime'])} · {market['score']}점</strong><br>
        BTC ₩{market['bitcoin']['price']:,.0f} · MVRV Z {mvrv_text}
      </div>
      {market_context}
      {warning}
      <h2 style="font-size:19px">알트코인 우선순위</h2>
      <table style="width:100%;border-collapse:collapse" border="1" cellpadding="8">
        <thead><tr><th>종목</th><th>점수</th><th>판정</th><th>호재·선정 근거</th><th>악재·위험</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
      <h2 style="font-size:19px">최근 24시간 주요 코인 이슈</h2>
      <p style="font-size:12px;color:#64748b">제목의 핵심어를 기준으로 분류한 참고용 영향 방향이며, 원문 확인이 필요합니다.</p>
      {issues_html}
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
    recipients = parse_recipients(required["EMAIL_TO"])
    if not recipients:
        print("유효한 수신 이메일 주소가 없어 발송을 건너뜁니다.")
        return False
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

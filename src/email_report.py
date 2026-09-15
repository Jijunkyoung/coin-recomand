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


def _pct(value: Any, digits: int = 1) -> str:
    return "—" if value is None else f"{float(value):+.{digits}f}%"


def _change_badge(value: Any) -> str:
    color = "#ff7b88" if value is not None and float(value) >= 0 else "#78aaff"
    return f"<span style='margin-left:6px;color:{color};font-weight:800'>{_pct(value)}</span>"


def email_subject(report: dict[str, Any], test_email: bool = False) -> str:
    prefix = "[테스트] " if test_email else ""
    return f"{prefix}[{report['market']['regime']}] 코인·주식 분석 {report['generated_at_kst'][:10]}"


def _asset_card(asset: dict[str, Any], currency: str, rank: int) -> str:
    price = float(asset.get("price") or 0)
    price_text = f"${price:,.2f}" if currency == "USD" else f"₩{price:,.0f}"
    reasons = asset.get("reasons") or ["점수 기준 상위 종목"]
    risks = asset.get("risks") or ["뚜렷한 정량 위험 신호 없음"]
    reason_text = " · ".join(html.escape(str(item)) for item in reasons[:3])
    risk_text = " · ".join(html.escape(str(item)) for item in risks[:2])
    decision = html.escape(str(asset.get("decision", "관찰")))
    decision_color = "#4fe09b" if asset.get("decision") == "분할매수 후보" else "#ffbf47" if asset.get("decision") == "관찰" else "#ff7b88"
    volume_text = "—" if asset.get("volume_ratio") is None else f"{float(asset['volume_ratio']):.2f}×"
    return (
        "<div style='margin:0 0 10px;padding:16px;border:1px solid #263a59;border-radius:12px;background:#0d1d33'>"
        "<table role='presentation' style='width:100%;border-collapse:collapse'><tr>"
        f"<td><span style='color:#78aaff;font-size:11px;font-weight:800'>#{rank}</span><br>"
        f"<strong style='font-size:17px;color:#f1f6ff'>{html.escape(str(asset.get('name', '')))}</strong> "
        f"<span style='font-size:11px;color:#8fa4bf'>{html.escape(str(asset.get('symbol', '')))}</span><br>"
        f"<span style='font-size:13px;color:#c6d4e7'>{price_text}{_change_badge(asset.get('return_1d'))}</span></td>"
        f"<td style='text-align:right'><span style='color:{decision_color};font-size:11px;font-weight:800'>{decision}</span><br>"
        f"<strong style='font-size:28px;color:#eaf2ff'>{asset.get('score', '—')}</strong><span style='color:#7f93af'> / 100</span></td>"
        "</tr></table>"
        "<table role='presentation' style='width:100%;margin-top:12px;border-collapse:separate;border-spacing:4px'><tr>"
        f"<td style='padding:8px;background:#132743;border-radius:7px;color:#9eb1ca;font-size:11px'>RSI<br><b style='color:#eef5ff'>{asset.get('rsi', '—')}</b></td>"
        f"<td style='padding:8px;background:#132743;border-radius:7px;color:#9eb1ca;font-size:11px'>7일<br><b style='color:#eef5ff'>{_pct(asset.get('return_7d'))}</b></td>"
        f"<td style='padding:8px;background:#132743;border-radius:7px;color:#9eb1ca;font-size:11px'>30일<br><b style='color:#eef5ff'>{_pct(asset.get('return_30d'))}</b></td>"
        f"<td style='padding:8px;background:#132743;border-radius:7px;color:#9eb1ca;font-size:11px'>거래량<br><b style='color:#eef5ff'>{volume_text}</b></td>"
        "</tr></table>"
        f"<p style='margin:10px 0 0;color:#b9c9dc;font-size:12px;line-height:1.55'><b style='color:#65deb1'>선정</b> {reason_text}</p>"
        f"<p style='margin:4px 0 0;color:#b9c9dc;font-size:12px;line-height:1.55'><b style='color:#ff8791'>위험</b> {risk_text}</p>"
        "</div>"
    )


def _major_event_section(events: list[dict[str, Any]]) -> str:
    if not events:
        return (
            "<div style='margin-top:16px;padding:17px;border:1px solid #263a59;border-radius:12px;background:#0d1d33'>"
            "<h2 style='margin:0 0 6px;font-size:18px'>주요 시장 이벤트</h2>"
            "<p style='margin:0;color:#8fa4bf;font-size:12px'>현재 선별된 고영향 일정이 없습니다.</p></div>"
        )
    rows = []
    for event in events[:5]:
        importance = str(event.get("importance", "보통"))
        border = "#ff805d" if importance == "매우 높음" else "#e9b949"
        days = event.get("days_until")
        dday = "일정 확인" if days is None else "D-DAY" if int(days) == 0 else f"D-{int(days)}" if int(days) > 0 else f"D+{abs(int(days))}"
        symbols = " · ".join(event.get("related_symbols") or []) or "시장 전체"
        source_url = str(event.get("source_url") or "")
        source_name = html.escape(str(event.get("source") or "출처 미상"))
        source = (
            f"<a href='{html.escape(source_url, quote=True)}' style='color:#9bc0ff;text-decoration:none'>{source_name} ↗</a>"
            if re.match(r"^https?://", source_url, re.IGNORECASE)
            else source_name
        )
        rows.append(
            f"<div style='margin-top:10px;padding:14px;border-left:3px solid {border};border-radius:8px;background:#10223b'>"
            f"<p style='margin:0 0 6px;color:#a9bad0;font-size:11px'><b style='color:{border}'>{html.escape(importance)}</b> · "
            f"{html.escape(str(event.get('status', '확인 필요')))} · {html.escape(dday)} · {html.escape(str(event.get('date') or '일정 확인 중'))} · {html.escape(str(event.get('time_kst') or '시각 미정'))} KST</p>"
            f"<h3 style='margin:0 0 6px;color:#f1f6ff;font-size:15px'>{html.escape(str(event.get('title', '시장 일정')))}</h3>"
            f"<p style='margin:0;color:#b9c9dc;font-size:12px;line-height:1.55'>{html.escape(str(event.get('summary') or '시장 영향을 확인 중입니다.'))}</p>"
            f"<p style='margin:7px 0 0;color:#8fa4bf;font-size:11px'>관련 {html.escape(symbols)} · {source}</p>"
            f"<p style='margin:7px 0 0;color:#75dcae;font-size:11px'><b>긍정</b> {html.escape(str(event.get('bull_case') or '긍정적 결과 시 시장심리 개선 가능'))}</p>"
            f"<p style='margin:3px 0 0;color:#ff9ba4;font-size:11px'><b>부정</b> {html.escape(str(event.get('bear_case') or '부정적 결과 시 변동성 확대 가능'))}</p>"
            "</div>"
        )
    return (
        "<div style='margin-top:16px;padding:17px;border:1px solid #375b87;border-radius:12px;background:#0d1d33'>"
        "<p style='margin:0;color:#6fa6ff;font-size:11px;font-weight:800;letter-spacing:1px'>MARKET MOVING EVENTS</p>"
        "<h2 style='margin:5px 0 3px;font-size:18px'>주요 시장 이벤트</h2>"
        "<p style='margin:0;color:#8398b4;font-size:11px'>공식 결과 확인 전에는 추천 점수에 가산하지 않고 변동성 위험으로만 관리합니다.</p>"
        + "".join(rows)
        + "</div>"
    )


def _stock_email_section(stock_reports: dict[str, dict[str, Any]] | None) -> str:
    if not stock_reports:
        return ""
    sections = []
    for market in ("us", "kr"):
        stock_report = stock_reports.get(market) or {}
        market_name = html.escape(str(stock_report.get("market_name", market)))
        assets = stock_report.get("recommendations") or []
        if assets:
            cards = "".join(_asset_card(stock, stock_report.get("currency", "KRW"), rank) for rank, stock in enumerate(assets, 1))
            sections.append(
                f"<div style='margin-top:28px'><p style='margin:0;color:#6fa6ff;font-size:11px;font-weight:800;letter-spacing:1px'>STOCK PRIORITY</p>"
                f"<h2 style='margin:5px 0 6px;color:#f1f6ff;font-size:20px'>{market_name} 추천</h2>"
                f"<p style='margin:0 0 12px;color:#93a8c2;font-size:12px'>{html.escape(str(stock_report.get('regime', '—')))} 국면 · 시장점수 {stock_report.get('market_score', '—')}</p>{cards}</div>"
            )
        else:
            warning = (stock_report.get("warnings") or ["데이터 미수집"])[0]
            sections.append(f"<div style='margin-top:24px;padding:14px;border:1px solid #6d5a29;border-radius:10px;background:#282211;color:#ffd77b'><b>{market_name}</b><br><span style='font-size:12px'>{html.escape(str(warning))}</span></div>")
    return "".join(sections)


def build_email_html(report: dict[str, Any], stock_reports: dict[str, dict[str, Any]] | None = None) -> str:
    market = report["market"]
    bitcoin = market["bitcoin"]
    mvrv = bitcoin.get("mvrv_z")
    mvrv_text = f"{mvrv:.2f}" if mvrv is not None else "미수집"
    coin_cards = "".join(_asset_card(coin, "KRW", rank) for rank, coin in enumerate(report.get("recommendations", []), 1))
    liquidity = market.get("liquidity") or {}

    def money(value: Any) -> str:
        if value is None: return "미수집"
        number = float(value)
        return f"${number / 1_000_000_000_000:.2f}T" if abs(number) >= 1_000_000_000_000 else f"${number / 1_000_000_000:.1f}B" if abs(number) >= 1_000_000_000 else f"${number:,.0f}"

    event_rows = []
    for event in report.get("upcoming_events", [])[:8]:
        symbols = ", ".join(event.get("related_symbols") or [])
        event_rows.append(f"<div style='padding:11px 0;border-bottom:1px solid #223650'><b style='color:#eaf2ff'>{html.escape(event.get('date_kst', ''))} · {html.escape(event.get('title', '일정'))}</b><br><span style='color:#8fa4bf;font-size:11px'>관련: {html.escape(symbols)}</span></div>")
    events_html = "".join(event_rows) or "<p style='color:#8fa4bf;font-size:12px'>향후 7일 안에 선별된 일정이 없습니다.</p>"
    issue_rows = []
    for issue in report.get("news_issues", [])[:7]:
        symbols = ", ".join(issue.get("related_symbols") or []) or "시장 전체"
        issue_rows.append(
            f"<div style='padding:11px 0;border-bottom:1px solid #223650'><a href='{html.escape(issue.get('url', ''), quote=True)}' style='color:#9bc0ff;text-decoration:none'><b>{html.escape(issue.get('title', '제목 없음'))}</b></a><br>"
            f"<span style='color:#8fa4bf;font-size:11px'>{html.escape(issue.get('published_at_kst', ''))} KST · {html.escape(issue.get('source', '출처 미상'))} · {html.escape(issue.get('impact', '중립·혼재'))} · {html.escape(symbols)}</span></div>"
        )
    issues_html = "".join(issue_rows) or "<p style='color:#8fa4bf;font-size:12px'>최근 24시간 선별된 주요 이슈가 없습니다.</p>"
    major_event_section = _major_event_section(report.get("major_events") or [])
    stock_section = _stock_email_section(stock_reports)
    return f"""
    <div style="margin:0;padding:24px 10px;background:#06101f;font-family:Arial,'Noto Sans KR',sans-serif;color:#eaf2ff">
      <div style="max-width:760px;margin:auto">
        <p style="margin:0;color:#6fa6ff;font-size:11px;font-weight:800;letter-spacing:1.3px">MARKET SIGNAL DESK</p>
        <h1 style="margin:6px 0 4px;font-size:27px;color:#f5f8ff">오늘의 코인·주식 분석</h1>
        <p style="margin:0 0 18px;color:#8398b4;font-size:12px">{html.escape(report['generated_at_kst'])} 기준 · 매일 오전 7시 30분</p>
        <div style="padding:20px;border:1px solid #31517f;border-radius:15px;background:linear-gradient(135deg,#122b4b,#0a192d)">
          <table role="presentation" style="width:100%;border-collapse:collapse"><tr><td>
            <span style="color:#8fa4bf;font-size:11px">BITCOIN MARKET REGIME</span><br><strong style="font-size:24px;color:#f1f6ff">{html.escape(market['regime'])} 국면</strong>
          </td><td style="text-align:right"><strong style="font-size:30px;color:#64e0b0">{market['score']}</strong><span style="color:#8fa4bf"> / 100</span></td></tr></table>
          <p style="margin:13px 0 0;color:#c5d4e6;font-size:13px">BTC <b>₩{bitcoin['price']:,.0f}</b>{_change_badge(bitcoin.get('return_1d'))} · MVRV Z {mvrv_text} · RSI {bitcoin.get('rsi', '—')}</p>
        </div>
        <table role="presentation" style="width:100%;margin-top:10px;border-collapse:separate;border-spacing:5px"><tr>
          <td style="padding:11px;background:#0d1d33;border-radius:9px;color:#8fa4bf;font-size:11px">DeFi TVL<br><b style="color:#eaf2ff">{money(liquidity.get('defi_tvl_usd'))}</b> {_pct(liquidity.get('defi_tvl_change_7d'))}</td>
          <td style="padding:11px;background:#0d1d33;border-radius:9px;color:#8fa4bf;font-size:11px">스테이블코인 공급<br><b style="color:#eaf2ff">{money(liquidity.get('stablecoin_supply_usd'))}</b> {_pct(liquidity.get('stablecoin_supply_change_7d'))}</td>
        </tr></table>
        {major_event_section}
        <div style="margin-top:28px"><p style="margin:0;color:#6fa6ff;font-size:11px;font-weight:800;letter-spacing:1px">ALTCOIN PRIORITY</p><h2 style="margin:5px 0 12px;font-size:20px">추천 알트코인</h2>{coin_cards or '<p style="color:#8fa4bf">표시할 추천 종목이 없습니다.</p>'}</div>
        {stock_section}
        <div style="margin-top:28px;padding:17px;border:1px solid #263a59;border-radius:12px;background:#0d1d33"><h2 style="margin:0 0 8px;font-size:18px">향후 7일 주요 일정</h2>{events_html}</div>
        <div style="margin-top:12px;padding:17px;border:1px solid #263a59;border-radius:12px;background:#0d1d33"><h2 style="margin:0 0 4px;font-size:18px">최근 24시간 주요 코인 이슈</h2><p style="margin:0 0 6px;color:#8398b4;font-size:11px">제목 기반 영향 분류이므로 원문 확인이 필요합니다.</p>{issues_html}</div>
        <p style="margin:20px 4px 0;color:#70849e;font-size:11px;line-height:1.5">정량 지표 기반 연구용 참고자료이며 투자 자문이나 수익 보장이 아닙니다. 실제 주문은 실행하지 않습니다.</p>
      </div>
    </div>
    """


def send_email(report: dict[str, Any], stock_reports: dict[str, dict[str, Any]] | None = None) -> bool:
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
    is_test_email = os.getenv("TEST_EMAIL", "").strip().lower() in {"1", "true", "yes"}
    message["Subject"] = email_subject(report, is_test_email)
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content("HTML을 지원하는 메일 앱에서 보고서를 확인해 주세요.")
    message.add_alternative(build_email_html(report, stock_reports), subtype="html")
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

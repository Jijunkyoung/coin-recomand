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
    color = "#c62828" if value is not None and float(value) >= 0 else "#1565c0"
    return f"<span style='margin-left:6px;color:{color};font-weight:800'>{_pct(value)}</span>"


def email_subject(report: dict[str, Any], test_email: bool = False) -> str:
    prefix = "[테스트] " if test_email else ""
    return f"{prefix}[{report['market']['regime']}] 코인 분석 {report['generated_at_kst'][:10]}"


def stock_email_subject(stock_reports: dict[str, dict[str, Any]], test_email: bool = False) -> str:
    prefix = "[테스트] " if test_email else ""
    date = next((str(stock_reports.get(market, {}).get("generated_at_kst", ""))[:10] for market in ("us", "kr") if stock_reports.get(market)), "")
    return f"{prefix}맞춤 주식 브리핑 {date}".strip()


def _asset_card(asset: dict[str, Any], currency: str, rank: int) -> str:
    price = float(asset.get("price") or 0)
    price_text = f"${price:,.2f}" if currency == "USD" else f"₩{price:,.0f}"
    reasons = asset.get("reasons") or ["점수 기준 상위 종목"]
    risks = asset.get("risks") or ["뚜렷한 정량 위험 신호 없음"]
    reason_text = " · ".join(html.escape(str(item)) for item in reasons[:3])
    risk_text = " · ".join(html.escape(str(item)) for item in risks[:2])
    decision = html.escape(str(asset.get("decision", "관찰")))
    decision_color = "#087a52" if asset.get("decision") == "분할매수 후보" else "#9a6200" if asset.get("decision") == "관찰" else "#b42336"
    volume_text = "—" if asset.get("volume_ratio") is None else f"{float(asset['volume_ratio']):.2f}×"
    return (
        "<div style='margin:0 0 10px;padding:16px;border:1px solid #d6e0ec;border-radius:12px;background:#ffffff;color:#10233f'>"
        "<table role='presentation' style='width:100%;border-collapse:collapse'><tr>"
        f"<td><span style='color:#1d5fbd;font-size:11px;font-weight:800'>#{rank}</span><br>"
        f"<strong style='font-size:17px;color:#10233f'>{html.escape(str(asset.get('name', '')))}</strong> "
        f"<span style='font-size:11px;color:#52657d'>{html.escape(str(asset.get('symbol', '')))}</span><br>"
        f"<span style='font-size:13px;color:#263b55'>{price_text}{_change_badge(asset.get('return_1d'))}</span></td>"
        f"<td style='text-align:right'><span style='color:{decision_color};font-size:11px;font-weight:800'>{decision}</span><br>"
        f"<strong style='font-size:28px;color:#10233f'>{asset.get('score', '—')}</strong><span style='color:#52657d'> / 100</span></td>"
        "</tr></table>"
        "<table role='presentation' style='width:100%;margin-top:12px;border-collapse:separate;border-spacing:4px'><tr>"
        f"<td style='padding:8px;background:#eef3f8;border-radius:7px;color:#52657d;font-size:11px'>RSI<br><b style='color:#10233f'>{asset.get('rsi', '—')}</b></td>"
        f"<td style='padding:8px;background:#eef3f8;border-radius:7px;color:#52657d;font-size:11px'>7일<br><b style='color:#10233f'>{_pct(asset.get('return_7d'))}</b></td>"
        f"<td style='padding:8px;background:#eef3f8;border-radius:7px;color:#52657d;font-size:11px'>30일<br><b style='color:#10233f'>{_pct(asset.get('return_30d'))}</b></td>"
        f"<td style='padding:8px;background:#eef3f8;border-radius:7px;color:#52657d;font-size:11px'>거래량<br><b style='color:#10233f'>{volume_text}</b></td>"
        "</tr></table>"
        f"<p style='margin:10px 0 0;color:#263b55;font-size:12px;line-height:1.55'><b style='color:#087a52'>선정</b> {reason_text}</p>"
        f"<p style='margin:4px 0 0;color:#263b55;font-size:12px;line-height:1.55'><b style='color:#b42336'>위험</b> {risk_text}</p>"
        "</div>"
    )


def _major_event_section(events: list[dict[str, Any]]) -> str:
    if not events:
        return (
            "<div style='margin-top:16px;padding:17px;border:1px solid #d6e0ec;border-radius:12px;background:#ffffff;color:#10233f'>"
            "<h2 style='margin:0 0 6px;color:#10233f;font-size:18px'>주요 시장 이벤트</h2>"
            "<p style='margin:0;color:#52657d;font-size:12px'>현재 선별된 고영향 일정이 없습니다.</p></div>"
        )
    rows = []
    for event in events[:5]:
        importance = str(event.get("importance", "보통"))
        border = "#c2412d" if importance == "매우 높음" else "#9a6200"
        days = event.get("days_until")
        dday = "일정 확인" if days is None else "D-DAY" if int(days) == 0 else f"D-{int(days)}" if int(days) > 0 else f"D+{abs(int(days))}"
        symbols = " · ".join(event.get("related_symbols") or []) or "시장 전체"
        source_url = str(event.get("source_url") or "")
        source_name = html.escape(str(event.get("source") or "출처 미상"))
        source = (
            f"<a href='{html.escape(source_url, quote=True)}' style='color:#1d5fbd;text-decoration:underline'>{source_name} ↗</a>"
            if re.match(r"^https?://", source_url, re.IGNORECASE)
            else source_name
        )
        rows.append(
            f"<div style='margin-top:10px;padding:14px;border-left:3px solid {border};border-radius:8px;background:#f6f8fb;color:#10233f'>"
            f"<p style='margin:0 0 6px;color:#52657d;font-size:11px'><b style='color:{border}'>{html.escape(importance)}</b> · "
            f"{html.escape(str(event.get('status', '확인 필요')))} · {html.escape(dday)} · {html.escape(str(event.get('date') or '일정 확인 중'))} · {html.escape(str(event.get('time_kst') or '시각 미정'))} KST</p>"
            f"<h3 style='margin:0 0 6px;color:#10233f;font-size:15px'>{html.escape(str(event.get('title', '시장 일정')))}</h3>"
            f"<p style='margin:0;color:#263b55;font-size:12px;line-height:1.55'>{html.escape(str(event.get('summary') or '시장 영향을 확인 중입니다.'))}</p>"
            f"<p style='margin:7px 0 0;color:#52657d;font-size:11px'>관련 {html.escape(symbols)} · {source}</p>"
            f"<p style='margin:7px 0 0;color:#087a52;font-size:11px'><b>긍정</b> {html.escape(str(event.get('bull_case') or '긍정적 결과 시 시장심리 개선 가능'))}</p>"
            f"<p style='margin:3px 0 0;color:#b42336;font-size:11px'><b>부정</b> {html.escape(str(event.get('bear_case') or '부정적 결과 시 변동성 확대 가능'))}</p>"
            "</div>"
        )
    return (
        "<div style='margin-top:16px;padding:17px;border:1px solid #b9cbe0;border-radius:12px;background:#ffffff;color:#10233f'>"
        "<p style='margin:0;color:#1d5fbd;font-size:11px;font-weight:800;letter-spacing:1px'>MARKET MOVING EVENTS</p>"
        "<h2 style='margin:5px 0 3px;color:#10233f;font-size:18px'>주요 시장 이벤트</h2>"
        "<p style='margin:0;color:#52657d;font-size:11px'>공식 결과 확인 전에는 추천 점수에 가산하지 않고 변동성 위험으로만 관리합니다.</p>"
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
                f"<div style='margin-top:28px'><p style='margin:0;color:#1d5fbd;font-size:11px;font-weight:800;letter-spacing:1px'>STOCK PRIORITY</p>"
                f"<h2 style='margin:5px 0 6px;color:#10233f;font-size:20px'>{market_name} 추천</h2>"
                f"<p style='margin:0 0 12px;color:#52657d;font-size:12px'>{html.escape(str(stock_report.get('regime', '—')))} 국면 · 시장점수 {stock_report.get('market_score', '—')}</p>{cards}</div>"
            )
        else:
            warning = (stock_report.get("warnings") or ["데이터 미수집"])[0]
            sections.append(f"<div style='margin-top:24px;padding:14px;border:1px solid #d8b45f;border-radius:10px;background:#fff8e7;color:#684500'><b>{market_name}</b><br><span style='font-size:12px'>{html.escape(str(warning))}</span></div>")
    return "".join(sections)


def build_stock_email_html(stock_reports: dict[str, dict[str, Any]]) -> str:
    mail_context = stock_reports.get("_mail") or {}
    sectors = " · ".join(mail_context.get("selected_sector_labels") or []) or "선택 없음"
    holding_counts = mail_context.get("holding_counts") or {}
    generated_at = next((stock_reports.get(market, {}).get("generated_at_kst") for market in ("us", "kr") if stock_reports.get(market)), "—")
    news_rows = []
    for issue in mail_context.get("news_issues") or []:
        related = [*(issue.get("related_holdings") or []), *(issue.get("related_sectors") or [])]
        news_rows.append(
            f"<div style='padding:12px 0;border-bottom:1px solid #d6e0ec'><a href='{html.escape(str(issue.get('url') or ''), quote=True)}' style='color:#1d5fbd;text-decoration:underline'><b>{html.escape(str(issue.get('title') or '제목 없음'))}</b></a><br>"
            f"<span style='color:#52657d;font-size:11px'>{html.escape(str(issue.get('published_at_kst') or ''))} KST · {html.escape(str(issue.get('source') or '출처 미상'))} · {html.escape(str(issue.get('impact') or '중립·혼재'))} · 관련 {html.escape(' · '.join(related) or '선택 주식')}</span></div>"
        )
    news_html = "".join(news_rows) or "<p style='color:#52657d;font-size:12px'>최근 24시간 선별된 맞춤 주식뉴스가 없습니다.</p>"
    portfolio = mail_context.get("portfolio") or {}
    changes = portfolio.get("changes") or {}
    position_rows = []
    for item in portfolio.get("positions") or []:
        symbol, name = html.escape(str(item.get("symbol") or "")), html.escape(str(item.get("name") or ""))
        prefix = "$" if str(item.get("currency") or "KRW") == "USD" else "₩"
        profit = float(item.get("profit_loss") or 0)
        daily_rate = item.get("daily_change_rate")
        daily_color = "#52657d" if daily_rate is None else "#c62828" if float(daily_rate) >= 0 else "#1565c0"
        position_rows.append(
            f"<tr><td style='padding:8px;border-bottom:1px solid #e3e9f0'><b>{name}</b><br><span style='color:#52657d;font-size:10px'>{symbol} · {float(item.get('quantity') or 0):,.4f}주</span></td>"
            f"<td style='padding:8px;text-align:right;border-bottom:1px solid #e3e9f0'><span style='color:#52657d;font-size:10px'>현재가</span><br>{prefix}{float(item.get('current_price') or 0):,.2f}<br><span style='font-size:10px;color:{daily_color}'>일간 {_pct(daily_rate)}</span></td>"
            f"<td style='padding:8px;text-align:right;border-bottom:1px solid #e3e9f0'><span style='color:#52657d;font-size:10px'>평가액</span><br>{prefix}{float(item.get('evaluation_amount') or 0):,.2f}</td>"
            f"<td style='padding:8px;text-align:right;border-bottom:1px solid #e3e9f0;color:{'#c62828' if profit >= 0 else '#1565c0'}'><span style='color:#52657d;font-size:10px'>평가손익</span><br>{prefix}{profit:+,.2f}<br><span style='font-size:10px'>{_pct(item.get('profit_rate'))}</span></td></tr>"
        )
    change_labels = []
    for item in changes.get("added") or []:
        change_labels.append(f"신규 {html.escape(str(item.get('name') or item.get('symbol')))}")
    for item in changes.get("removed") or []:
        change_labels.append(f"전량매도 {html.escape(str(item.get('name') or item.get('symbol')))}")
    for item in changes.get("quantity_changes") or []:
        change_labels.append(f"{html.escape(str(item.get('name') or item.get('symbol')))} {float(item.get('difference') or 0):+,.4f}주")
    portfolio_html = ""
    if portfolio:
        baseline_text = html.escape(str(changes.get("baseline_at") or "첫 기록"))
        rows = "".join(position_rows) or '<tr><td style="padding:8px">조회된 보유종목이 없습니다.</td></tr>'
        portfolio_html = (
            "<div style='margin-top:24px;padding:17px;border:1px solid #b9cbe0;border-radius:12px;background:#ffffff;color:#10233f'>"
            "<h2 style='margin:0 0 4px;color:#10233f;font-size:18px'>내 한국투자증권 계좌</h2>"
            f"<p style='margin:0 0 10px;color:#52657d;font-size:11px'>비교 기준 {baseline_text} · {html.escape(str(portfolio.get('synced_at') or ''))} 조회</p>"
            f"<p style='margin:0 0 10px;color:#263b55;font-size:12px'><b>보유 변동</b> {' · '.join(change_labels) if change_labels else '신규·매도·수량 변동 없음'}</p>"
            f"<table role='presentation' style='width:100%;border-collapse:collapse;font-size:12px'>{rows}</table></div>"
        )
    return f"""<!doctype html>
    <html><head><meta charset="utf-8"><meta name="color-scheme" content="light"><meta name="supported-color-schemes" content="light"><style>:root{{color-scheme:light only}} body{{margin:0!important;background:#f3f6fb!important;color:#10233f!important}}</style></head>
    <body bgcolor="#f3f6fb" style="margin:0;background:#f3f6fb;color:#10233f">
    <div style="margin:0;padding:24px 10px;background:#f3f6fb;font-family:Arial,'Noto Sans KR',sans-serif;color:#10233f">
      <div style="max-width:760px;margin:auto;background:#f3f6fb;color:#10233f">
        <p style="margin:0;color:#1d5fbd;font-size:11px;font-weight:800;letter-spacing:1.3px">PERSONAL STOCK DESK</p>
        <h1 style="margin:6px 0 4px;font-size:27px;color:#10233f">맞춤 주식 브리핑</h1>
        <p style="margin:0 0 18px;color:#52657d;font-size:12px">{html.escape(str(generated_at))} 기준 · 매일 오전 7시 30분</p>
        <div style="padding:18px;border:1px solid #b9cbe0;border-radius:14px;background:#eaf2ff;color:#10233f">
          <p style="margin:0 0 7px;color:#52657d;font-size:11px">선택 섹터</p><strong style="color:#10233f">{html.escape(sectors)}</strong>
          <p style="margin:10px 0 0;color:#263b55;font-size:12px">보유종목 뉴스 대상: 미국 {int(holding_counts.get('us', 0))}개 · 국내 {int(holding_counts.get('kr', 0))}개</p>
        </div>
        {portfolio_html}
        {_stock_email_section(stock_reports)}
        <div style="margin-top:24px;padding:17px;border:1px solid #d6e0ec;border-radius:12px;background:#ffffff;color:#10233f"><h2 style="margin:0 0 4px;color:#10233f;font-size:18px">보유종목·선택 섹터 주요뉴스</h2><p style="margin:0 0 6px;color:#52657d;font-size:11px">최근 24시간 제목 기반 선별이며 투자 판단 전 원문 확인이 필요합니다.</p>{news_html}</div>
        <p style="margin:20px 4px 0;color:#52657d;font-size:11px;line-height:1.5">보유종목 목록은 메일 생성에만 사용하며 공개 대시보드 JSON에는 저장하지 않습니다. 정량 지표 기반 참고자료이며 투자 자문이 아닙니다.</p>
      </div>
    </div></body></html>"""


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
        event_rows.append(f"<div style='padding:11px 0;border-bottom:1px solid #d6e0ec'><b style='color:#10233f'>{html.escape(event.get('date_kst', ''))} · {html.escape(event.get('title', '일정'))}</b><br><span style='color:#52657d;font-size:11px'>관련: {html.escape(symbols)}</span></div>")
    events_html = "".join(event_rows) or "<p style='color:#52657d;font-size:12px'>향후 7일 안에 선별된 일정이 없습니다.</p>"
    issue_rows = []
    for issue in report.get("news_issues", [])[:7]:
        symbols = ", ".join(issue.get("related_symbols") or []) or "시장 전체"
        issue_rows.append(
            f"<div style='padding:11px 0;border-bottom:1px solid #d6e0ec'><a href='{html.escape(issue.get('url', ''), quote=True)}' style='color:#1d5fbd;text-decoration:underline'><b>{html.escape(issue.get('title', '제목 없음'))}</b></a><br>"
            f"<span style='color:#52657d;font-size:11px'>{html.escape(issue.get('published_at_kst', ''))} KST · {html.escape(issue.get('source', '출처 미상'))} · {html.escape(issue.get('impact', '중립·혼재'))} · {html.escape(symbols)}</span></div>"
        )
    issues_html = "".join(issue_rows) or "<p style='color:#52657d;font-size:12px'>최근 24시간 선별된 주요 이슈가 없습니다.</p>"
    major_event_section = _major_event_section(report.get("major_events") or [])
    stock_section = _stock_email_section(stock_reports)
    return f"""<!doctype html>
    <html><head><meta charset="utf-8"><meta name="color-scheme" content="light"><meta name="supported-color-schemes" content="light"><style>:root{{color-scheme:light only}} body{{margin:0!important;background:#f3f6fb!important;color:#10233f!important}}</style></head>
    <body bgcolor="#f3f6fb" style="margin:0;background:#f3f6fb;color:#10233f">
    <div style="margin:0;padding:24px 10px;background:#f3f6fb;font-family:Arial,'Noto Sans KR',sans-serif;color:#10233f">
      <div style="max-width:760px;margin:auto;background:#f3f6fb;color:#10233f">
        <p style="margin:0;color:#1d5fbd;font-size:11px;font-weight:800;letter-spacing:1.3px">MARKET SIGNAL DESK</p>
        <h1 style="margin:6px 0 4px;font-size:27px;color:#10233f">오늘의 코인 분석</h1>
        <p style="margin:0 0 18px;color:#52657d;font-size:12px">{html.escape(report['generated_at_kst'])} 기준 · 매일 오전 7시 30분</p>
        <div style="padding:20px;border:1px solid #b9cbe0;border-radius:15px;background:#eaf2ff;color:#10233f">
          <table role="presentation" style="width:100%;border-collapse:collapse"><tr><td>
            <span style="color:#52657d;font-size:11px">BITCOIN MARKET REGIME</span><br><strong style="font-size:24px;color:#10233f">{html.escape(market['regime'])} 국면</strong>
          </td><td style="text-align:right"><strong style="font-size:30px;color:#087a52">{market['score']}</strong><span style="color:#52657d"> / 100</span></td></tr></table>
          <p style="margin:13px 0 0;color:#263b55;font-size:13px">BTC <b>₩{bitcoin['price']:,.0f}</b>{_change_badge(bitcoin.get('return_1d'))} · MVRV Z {mvrv_text} · RSI {bitcoin.get('rsi', '—')}</p>
        </div>
        <table role="presentation" style="width:100%;margin-top:10px;border-collapse:separate;border-spacing:5px"><tr>
          <td style="padding:11px;background:#ffffff;border:1px solid #d6e0ec;border-radius:9px;color:#52657d;font-size:11px">DeFi TVL<br><b style="color:#10233f">{money(liquidity.get('defi_tvl_usd'))}</b> {_pct(liquidity.get('defi_tvl_change_7d'))}</td>
          <td style="padding:11px;background:#ffffff;border:1px solid #d6e0ec;border-radius:9px;color:#52657d;font-size:11px">스테이블코인 공급<br><b style="color:#10233f">{money(liquidity.get('stablecoin_supply_usd'))}</b> {_pct(liquidity.get('stablecoin_supply_change_7d'))}</td>
        </tr></table>
        {major_event_section}
        <div style="margin-top:28px"><p style="margin:0;color:#1d5fbd;font-size:11px;font-weight:800;letter-spacing:1px">ALTCOIN PRIORITY</p><h2 style="margin:5px 0 12px;color:#10233f;font-size:20px">추천 알트코인</h2>{coin_cards or '<p style="color:#52657d">표시할 추천 종목이 없습니다.</p>'}</div>
        {stock_section}
        <div style="margin-top:28px;padding:17px;border:1px solid #d6e0ec;border-radius:12px;background:#ffffff;color:#10233f"><h2 style="margin:0 0 8px;color:#10233f;font-size:18px">향후 7일 주요 일정</h2>{events_html}</div>
        <div style="margin-top:12px;padding:17px;border:1px solid #d6e0ec;border-radius:12px;background:#ffffff;color:#10233f"><h2 style="margin:0 0 4px;color:#10233f;font-size:18px">최근 24시간 주요 코인 이슈</h2><p style="margin:0 0 6px;color:#52657d;font-size:11px">제목 기반 영향 분류이므로 원문 확인이 필요합니다.</p>{issues_html}</div>
        <p style="margin:20px 4px 0;color:#52657d;font-size:11px;line-height:1.5">정량 지표 기반 연구용 참고자료이며 투자 자문이나 수익 보장이 아닙니다. 실제 주문은 실행하지 않습니다.</p>
      </div>
    </div>
    </body></html>"""


def send_email(report: dict[str, Any], stock_reports: dict[str, dict[str, Any]] | None = None) -> bool:
    required = {
        "SMTP_HOST": os.getenv("SMTP_HOST", "").strip(),
        "SMTP_USERNAME": os.getenv("SMTP_USERNAME", "").strip(),
        "SMTP_PASSWORD": os.getenv("SMTP_PASSWORD", "").strip(),
    }
    if not all(required.values()):
        print("메일 설정이 없어 발송을 건너뜁니다.")
        return False
    port = int(os.getenv("SMTP_PORT", "465"))
    sender = os.getenv("EMAIL_FROM", "").strip() or required["SMTP_USERNAME"]
    is_test_email = os.getenv("TEST_EMAIL", "").strip().lower() in {"1", "true", "yes"}
    report_scope = os.getenv("EMAIL_REPORT_SCOPE", "all").strip().lower()
    deliveries = []
    if report_scope in {"all", "coin"}:
        deliveries.append(("코인", os.getenv("EMAIL_TO", "").strip(), email_subject(report, is_test_email), build_email_html(report)))
    if stock_reports and report_scope in {"all", "stock"}:
        deliveries.append(("주식", (os.getenv("MEMBER_STOCK_EMAIL_TO") or os.getenv("STOCK_EMAIL_TO", "")).strip(), stock_email_subject(stock_reports, is_test_email), build_stock_email_html(stock_reports)))
    sent = False
    for label, recipient_value, subject, body in deliveries:
        if not recipient_value:
            print(f"{label} 메일 수신주소가 없어 발송을 건너뜁니다.")
            continue
        recipients = parse_recipients(recipient_value)
        if not recipients:
            print(f"{label} 메일의 유효한 수신주소가 없어 발송을 건너뜁니다.")
            continue
        message = EmailMessage()
        message["Subject"], message["From"], message["To"] = subject, sender, ", ".join(recipients)
        message.set_content("HTML을 지원하는 메일 앱에서 보고서를 확인해 주세요.")
        message.add_alternative(body, subtype="html")
        if port == 465:
            with smtplib.SMTP_SSL(required["SMTP_HOST"], port, timeout=30) as smtp:
                smtp.login(required["SMTP_USERNAME"], required["SMTP_PASSWORD"])
                smtp.send_message(message)
        else:
            with smtplib.SMTP(required["SMTP_HOST"], port, timeout=30) as smtp:
                smtp.starttls()
                smtp.login(required["SMTP_USERNAME"], required["SMTP_PASSWORD"])
                smtp.send_message(message)
        print(f"{label} 분석 메일을 {len(recipients)}개 주소로 발송했습니다.")
        sent = True
    return sent

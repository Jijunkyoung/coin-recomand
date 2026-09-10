const $ = (selector, root = document) => root.querySelector(selector);
const fmt = (value, digits = 1) => value == null ? "미수집" : Number(value).toLocaleString("ko-KR", { maximumFractionDigits: digits });
const pct = value => value == null ? "—" : `${value > 0 ? "+" : ""}${fmt(value)}%`;
let detailCoin = null;
let detailDays = 30;
let detailPlot = null;
let detailFrame = null;
let detailHoverIndex = null;

function drawLine(canvas, values, color = "#4d8dff") {
  if (!values?.length) return;
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth || 300;
  const height = Number(canvas.getAttribute("height")) || 80;
  canvas.style.height = `${height}px`;
  const pixelWidth = Math.round(width * ratio), pixelHeight = Math.round(height * ratio);
  if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) { canvas.width = pixelWidth; canvas.height = pixelHeight; }
  const ctx = canvas.getContext("2d"); ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.clearRect(0, 0, width, height);
  const min = Math.min(...values), max = Math.max(...values), spread = max - min || 1;
  const points = values.map((v, i) => [8 + i * (width - 16) / Math.max(1, values.length - 1), height - 8 - (v - min) / spread * (height - 18)]);
  const gradient = ctx.createLinearGradient(0, 0, 0, height); gradient.addColorStop(0, `${color}55`); gradient.addColorStop(1, `${color}00`);
  ctx.beginPath(); ctx.moveTo(points[0][0], height); points.forEach(([x,y]) => ctx.lineTo(x,y)); ctx.lineTo(points.at(-1)[0], height); ctx.fillStyle = gradient; ctx.fill();
  ctx.beginPath(); points.forEach(([x,y],i) => i ? ctx.lineTo(x,y) : ctx.moveTo(x,y)); ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.stroke();
}

function compact(value) {
  if (value == null) return "—";
  return Intl.NumberFormat("ko-KR", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

function historyFor(coin) {
  if (coin.history?.length) return coin.history;
  const end = new Date();
  return (coin.sparkline || []).map((price, index, array) => {
    const date = new Date(end); date.setDate(end.getDate() - (array.length - index - 1));
    return { date: date.toISOString().slice(0, 10), open: price, high: price, low: price, price, volume: 0 };
  });
}

function emaValues(values, period) {
  if (!values.length) return [];
  const multiplier = 2 / (period + 1), result = [values[0]];
  for (let i = 1; i < values.length; i += 1) result.push((values[i] - result[i - 1]) * multiplier + result[i - 1]);
  return result;
}

function bollingerValues(values, period = 20, multiplier = 2) {
  const middle = Array(values.length).fill(null), upper = Array(values.length).fill(null), lower = Array(values.length).fill(null);
  for (let index = period - 1; index < values.length; index += 1) {
    const windowValues = values.slice(index - period + 1, index + 1);
    const average = windowValues.reduce((sum, value) => sum + value, 0) / period;
    const deviation = Math.sqrt(windowValues.reduce((sum, value) => sum + (value - average) ** 2, 0) / period);
    middle[index] = average; upper[index] = average + multiplier * deviation; lower[index] = average - multiplier * deviation;
  }
  return { middle, upper, lower };
}

function rsiValues(values, period = 14) {
  const result = Array(values.length).fill(null);
  if (values.length <= period) return result;
  let gain = 0, loss = 0;
  for (let index = 1; index <= period; index += 1) {
    const change = values[index] - values[index - 1];
    gain += Math.max(change, 0); loss += Math.max(-change, 0);
  }
  let averageGain = gain / period, averageLoss = loss / period;
  const value = () => averageLoss === 0 ? 100 : 100 - 100 / (1 + averageGain / averageLoss);
  result[period] = value();
  for (let index = period + 1; index < values.length; index += 1) {
    const change = values[index] - values[index - 1];
    averageGain = (averageGain * (period - 1) + Math.max(change, 0)) / period;
    averageLoss = (averageLoss * (period - 1) + Math.max(-change, 0)) / period;
    result[index] = value();
  }
  return result;
}

function drawDetailedChart(crossIndex = null) {
  if (!detailCoin) return;
  const all = historyFor(detailCoin);
  const length = detailDays === "all" ? all.length : Math.min(Number(detailDays), all.length);
  const start = all.length - length, rows = all.slice(start);
  if (!rows.length) return;
  const prices = rows.map(row => Number(row.price));
  const opens = rows.map(row => Number(row.open ?? row.price));
  const highs = rows.map(row => Number(row.high ?? row.price));
  const lows = rows.map(row => Number(row.low ?? row.price));
  const volumes = rows.map(row => Number(row.volume) || 0);
  const allPrices = all.map(row => Number(row.price));
  const ema20 = emaValues(allPrices, 20).slice(start);
  const ema50 = emaValues(allPrices, 50).slice(start);
  const bands = bollingerValues(allPrices);
  const bandUpper = bands.upper.slice(start), bandMiddle = bands.middle.slice(start), bandLower = bands.lower.slice(start);
  const rsi14 = rsiValues(allPrices).slice(start);
  const canvas = $("#detailChart"), ratio = window.devicePixelRatio || 1;
  const bounds = canvas.getBoundingClientRect();
  const width = Math.max(280, Math.floor(bounds.width)), height = Math.max(280, Math.floor(bounds.height));
  const pixelWidth = Math.round(width * ratio), pixelHeight = Math.round(height * ratio);
  if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) { canvas.width = pixelWidth; canvas.height = pixelHeight; }
  const ctx = canvas.getContext("2d"); ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.clearRect(0, 0, width, height);
  const pad = { left: width < 560 ? 49 : 68, right: 18, top: 21, bottom: 22 };
  const priceBottom = height * .56, volumeTop = priceBottom + 10, volumeBottom = height * .69;
  const dateY = volumeBottom + 6, rsiTop = height * .76, rsiBottom = height - pad.bottom;
  const plotWidth = width - pad.left - pad.right;
  const bandRange = [...bandUpper, ...bandLower].filter(value => value != null && Number.isFinite(value));
  const low = Math.min(...lows, ...bandRange), high = Math.max(...highs, ...bandRange), margin = (high - low || high * .02 || 1) * .09;
  const min = low - margin, max = high + margin, spread = max - min || 1;
  const candleSpace = plotWidth / Math.max(1, rows.length), candleWidth = Math.max(1.5, Math.min(10, candleSpace * .62));
  const x = index => pad.left + (index + .5) * candleSpace;
  const y = value => pad.top + (max - value) / spread * (priceBottom - pad.top);

  ctx.font = `${width < 560 ? 10 : 11}px system-ui`; ctx.textAlign = "right"; ctx.textBaseline = "middle";
  for (let i = 0; i <= 4; i += 1) {
    const gridY = pad.top + i * (priceBottom - pad.top) / 4, value = max - i * spread / 4;
    ctx.beginPath(); ctx.moveTo(pad.left, gridY); ctx.lineTo(width - pad.right, gridY); ctx.strokeStyle = "rgba(143,162,189,.13)"; ctx.lineWidth = 1; ctx.stroke();
    ctx.fillStyle = "#7f93af"; ctx.fillText(compact(value), pad.left - 8, gridY);
  }

  const bandIndexes = bandUpper.map((value, index) => value != null && bandLower[index] != null ? index : null).filter(index => index != null);
  if (bandIndexes.length > 1) {
    ctx.beginPath();
    bandIndexes.forEach((index, position) => position ? ctx.lineTo(x(index), y(bandUpper[index])) : ctx.moveTo(x(index), y(bandUpper[index])));
    [...bandIndexes].reverse().forEach(index => ctx.lineTo(x(index), y(bandLower[index])));
    ctx.closePath(); ctx.fillStyle = "rgba(169,139,255,.10)"; ctx.fill();
  }

  const plot = (values, color, lineWidth) => {
    ctx.beginPath(); let started = false;
    values.forEach((value, index) => {
      if (value == null || !Number.isFinite(value)) { started = false; return; }
      if (started) ctx.lineTo(x(index), y(value)); else { ctx.moveTo(x(index), y(value)); started = true; }
    });
    ctx.strokeStyle = color; ctx.lineWidth = lineWidth; ctx.lineJoin = "round"; ctx.lineCap = "round"; ctx.stroke();
  };
  plot(bandUpper, "rgba(169,139,255,.76)", 1.1); plot(bandLower, "rgba(169,139,255,.76)", 1.1); plot(bandMiddle, "rgba(169,139,255,.38)", 1);
  plot(ema50, "#ffbf47", 1.15); plot(ema20, "#31d8c5", 1.25);

  rows.forEach((row, index) => {
    const rising = prices[index] >= opens[index], color = rising ? "#ff6b78" : "#4d8dff";
    const center = x(index), openY = y(opens[index]), closeY = y(prices[index]);
    ctx.beginPath(); ctx.moveTo(center, y(highs[index])); ctx.lineTo(center, y(lows[index])); ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.stroke();
    const bodyTop = Math.min(openY, closeY), bodyHeight = Math.max(1.5, Math.abs(closeY - openY));
    ctx.fillStyle = color; ctx.fillRect(center - candleWidth / 2, bodyTop, candleWidth, bodyHeight);
  });

  const maxVolume = Math.max(...volumes, 1), barWidth = Math.max(1, candleWidth * .82);
  volumes.forEach((volume, index) => {
    const barHeight = volume / maxVolume * (volumeBottom - volumeTop);
    ctx.fillStyle = prices[index] >= opens[index] ? "rgba(255,107,120,.24)" : "rgba(77,141,255,.25)";
    ctx.fillRect(x(index) - barWidth / 2, volumeBottom - barHeight, barWidth, barHeight);
  });

  const labels = [0, Math.floor((rows.length - 1) / 2), rows.length - 1];
  ctx.fillStyle = "#7f93af"; ctx.textBaseline = "top";
  labels.forEach((index, position) => { ctx.textAlign = position === 0 ? "left" : position === 2 ? "right" : "center"; ctx.fillText(rows[index]?.date || "", x(index), dateY); });

  const rsiY = value => rsiTop + (100 - value) / 100 * (rsiBottom - rsiTop);
  ctx.fillStyle = "rgba(255,107,120,.035)"; ctx.fillRect(pad.left, rsiTop, plotWidth, rsiY(70) - rsiTop);
  ctx.fillStyle = "rgba(77,141,255,.035)"; ctx.fillRect(pad.left, rsiY(30), plotWidth, rsiBottom - rsiY(30));
  [70, 50, 30].forEach(level => {
    const lineY = rsiY(level); ctx.beginPath(); ctx.moveTo(pad.left, lineY); ctx.lineTo(width - pad.right, lineY);
    ctx.strokeStyle = level === 50 ? "rgba(143,162,189,.12)" : "rgba(212,129,255,.22)"; ctx.lineWidth = 1; ctx.stroke();
    ctx.fillStyle = "#7f93af"; ctx.textAlign = "right"; ctx.textBaseline = "middle"; ctx.fillText(String(level), pad.left - 8, lineY);
  });
  ctx.beginPath(); let rsiStarted = false;
  rsi14.forEach((value, index) => {
    if (value == null || !Number.isFinite(value)) { rsiStarted = false; return; }
    if (rsiStarted) ctx.lineTo(x(index), rsiY(value)); else { ctx.moveTo(x(index), rsiY(value)); rsiStarted = true; }
  });
  ctx.strokeStyle = "#d481ff"; ctx.lineWidth = 1.7; ctx.lineJoin = "round"; ctx.stroke();
  ctx.fillStyle = "#a8b8ce"; ctx.textAlign = "left"; ctx.textBaseline = "top"; ctx.fillText("RSI(14)", pad.left + 5, rsiTop + 4);

  if (crossIndex != null && rows[crossIndex]) {
    const pointX = x(crossIndex), pointY = y(prices[crossIndex]);
    ctx.beginPath(); ctx.moveTo(pointX, pad.top); ctx.lineTo(pointX, rsiBottom); ctx.strokeStyle = "rgba(237,244,255,.32)"; ctx.setLineDash([4,4]); ctx.stroke(); ctx.setLineDash([]);
    ctx.beginPath(); ctx.arc(pointX, pointY, 4, 0, Math.PI * 2); ctx.fillStyle = "#edf4ff"; ctx.fill();
  }
  detailPlot = { rows, rsi14, x, pad, width };
  const change = prices[0] ? (prices.at(-1) / prices[0] - 1) * 100 : null;
  const latestRsi = [...rsi14].reverse().find(value => value != null);
  $("#detailStats").innerHTML = metric("기간 수익률", pct(change)) + metric("기간 최고가", `₩${fmt(Math.max(...highs), 4)}`) + metric("기간 최저가", `₩${fmt(Math.min(...lows), 4)}`) + metric("EMA20", `₩${fmt(detailCoin.ema20, 4)}`) + metric("EMA50", `₩${fmt(detailCoin.ema50, 4)}`) + metric("RSI(14)", fmt(latestRsi, 1));
}

function scheduleDetailedChart(crossIndex = null) {
  detailHoverIndex = crossIndex;
  if (detailFrame != null) return;
  detailFrame = requestAnimationFrame(() => {
    detailFrame = null;
    drawDetailedChart(detailHoverIndex);
  });
}

function openDetailChart(coin) {
  detailCoin = coin; detailDays = 30;
  $("#chartSymbol").textContent = `${coin.symbol || "BTC"} / KRW · DAILY`;
  $("#chartTitle").textContent = `${coin.name || "비트코인"} 상세차트`;
  $("#chartPrice").textContent = `현재 ₩${fmt(coin.price, 4)} · 30일 ${pct(coin.return_30d)}`;
  $("#periodTabs").querySelectorAll("button").forEach(button => button.classList.toggle("active", button.dataset.days === "30"));
  const dialog = $("#chartDialog"); dialog.showModal();
  requestAnimationFrame(() => scheduleDetailedChart());
}

function metric(label, value) { return `<div><span>${label}</span><strong>${value}</strong></div>`; }

function renderMethodology(methodology) {
  if (!methodology?.groups) {
    const legacy = methodology ? Object.values(methodology) : [];
    $("#methodologyIntro").textContent = legacy.join(" · ");
    return;
  }
  $("#methodologyIntro").textContent = methodology.intro;
  $("#methodologyGroups").innerHTML = methodology.groups.map(group => `
    <article class="rule-group">
      <div class="rule-group-head"><h3>${group.title}</h3><strong>${group.range}</strong></div>
      <ul>${group.items.map(item => `<li>${item}</li>`).join("")}</ul>
    </article>`).join("");
  $("#methodologyDecisions").innerHTML = methodology.decisions.map(item => `<li>${item}</li>`).join("");
  $("#methodologyExecution").textContent = methodology.execution;
}

function renderCoin(coin, index) {
  const node = $("#coinTemplate").content.cloneNode(true);
  const card = $(".coin-card", node); card.setAttribute("aria-label", `${coin.name} 상세차트 열기`);
  card.addEventListener("click", () => openDetailChart(coin));
  card.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openDetailChart(coin); } });
  $(".rank", node).textContent = `#${index + 1}`; $("h3", node).textContent = coin.name; $(".ticker", node).textContent = `${coin.symbol} · ₩${fmt(coin.price, 4)}`;
  const decision = $(".decision", node); decision.textContent = coin.decision; decision.classList.add(coin.decision === "분할매수 후보" ? "buy" : coin.decision === "보류" ? "hold" : "watch");
  $(".coin-score strong", node).textContent = coin.score; $(".score-bar i", node).style.width = `${coin.score}%`;
  const communityText = coin.community_sources ? `${coin.community_total || 0}회 · ${coin.community_sources}곳` : coin.trending_rank ? `인기 ${coin.trending_rank}위` : "미수집";
  const developmentText = coin.development?.status || "미수집";
  const unlockText = coin.tokenomics?.next_unlock?.date || (coin.tokenomics?.unlock_data_available ? "예정 없음" : "미수집");
  $(".coin-metrics", node).innerHTML = metric("RSI", fmt(coin.rsi)) + metric("7일", pct(coin.return_7d)) + metric("30일", pct(coin.return_30d)) + metric("거래량 비율", coin.volume_ratio == null ? "—" : `${fmt(coin.volume_ratio,2)}×`) + metric("변동성", pct(coin.volatility)) + metric("커뮤니티", communityText) + metric("개발 진척", developmentText) + metric("다음 언락", unlockText);
  $(".reasons", node).innerHTML = (coin.reasons?.length ? coin.reasons : ["정량 점수 상위 종목입니다."]).map(x => `<li>${x}</li>`).join("");
  const risks = coin.risks?.length ? coin.risks : ["뚜렷한 정량 위험 신호 없음 — 시장 변동성은 별도 관리 필요"];
  $(".risks", node).innerHTML = risks.map(x => `<li>${x}</li>`).join("");
  const canvas = $("canvas", node); requestAnimationFrame(() => drawLine(canvas, coin.sparkline, coin.return_30d >= 0 ? "#31d8c5" : "#ff6b78"));
  return node;
}

function render(report) {
  const { market } = report, btc = market.bitcoin;
  $("#generatedAt").textContent = report.generated_at_kst; $("#qualityText").textContent = `데이터 ${report.data_quality.status}`;
  $("#qualityDot").style.background = report.data_quality.status === "정상" ? "var(--green)" : "var(--amber)";
  $("#marketTitle").textContent = `${market.regime} 국면`; $("#marketSummary").textContent = market.regime === "상승" ? "추세가 우호적입니다. 후보별 과열 여부를 확인하세요." : market.regime === "하락" ? "신규 매수보다 현금 비중과 손실 제한을 우선합니다." : "방향 확인 전 강한 종목만 선별적으로 관찰합니다.";
  $("#marketScore").textContent = market.score; $("#scoreRing").style.background = `conic-gradient(${market.regime === "하락" ? "var(--red)" : market.regime === "상승" ? "var(--green)" : "var(--blue)"} ${market.score * 3.6}deg, var(--line) 0)`;
  $("#marketReasons").innerHTML = market.reasons.map(x => `<p>${x}</p>`).join("");
  btc.symbol = "BTC"; btc.name = "비트코인";
  $("#btcPrice").textContent = `₩${fmt(btc.price,0)}`; $("#mvrv").textContent = fmt(btc.mvrv_z,2); $("#mvrvLabel").textContent = btc.mvrv_source ? `MVRV Z · ${btc.mvrv_source}` : "MVRV Z"; $("#btcRsi").textContent = fmt(btc.rsi); $("#btcReturn").textContent = pct(btc.return_30d); $("#btcVolume").textContent = btc.volume_ratio == null ? "—" : `${fmt(btc.volume_ratio,2)}×`; drawLine($("#btcChart"), btc.sparkline, "#4d8dff");
  const btcCard = $("#btcDetailCard"); btcCard.onclick = () => openDetailChart(btc); btcCard.onkeydown = event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openDetailChart(btc); } };
  $("#screenedCount").textContent = report.screened; const list = $("#recommendations"); list.innerHTML = ""; report.recommendations.forEach((coin, i) => list.appendChild(renderCoin(coin, i)));
  const fear = market.fear_greed; $("#fearValue").textContent = fear.value ?? "—"; $("#fearClass").textContent = fear.classification; $("#fearGauge").style.left = `${fear.value ?? 50}%`;
  renderMethodology(report.methodology);
  const warnings = report.data_quality.warnings || [], notices = report.data_quality.notices || [];
  $("#warnings").innerHTML = (warnings.length ? warnings.map(x => `<p>• ${x}</p>`).join("") : `<p class="ok">모든 핵심 데이터가 정상 수집됐습니다.</p>`) + notices.map(x => `<p class="notice">참고 · ${x}</p>`).join("");
  $("#sources").innerHTML = report.sources.map(s => `<a href="${s.url}" target="_blank" rel="noopener">${s.name}</a>`).join(""); $("#disclaimer").textContent = report.disclaimer;
}

$("#chartClose").addEventListener("click", () => $("#chartDialog").close());
$("#chartDialog").addEventListener("click", event => { if (event.target === event.currentTarget) event.currentTarget.close(); });
$("#periodTabs").addEventListener("click", event => {
  const button = event.target.closest("button"); if (!button) return;
  detailDays = button.dataset.days === "all" ? "all" : Number(button.dataset.days);
  $("#periodTabs").querySelectorAll("button").forEach(item => item.classList.toggle("active", item === button)); scheduleDetailedChart();
});
$("#detailChart").addEventListener("pointermove", event => {
  if (!detailPlot) return;
  const rect = event.currentTarget.getBoundingClientRect(), localX = event.clientX - rect.left;
  const ratioX = (localX - detailPlot.pad.left) / Math.max(1, detailPlot.width - detailPlot.pad.left - detailPlot.pad.right);
  const index = Math.max(0, Math.min(detailPlot.rows.length - 1, Math.round(ratioX * (detailPlot.rows.length - 1))));
  scheduleDetailedChart(index); const row = detailPlot.rows[index], tooltip = $("#chartTooltip");
  const open = row.open ?? row.price, high = row.high ?? row.price, low = row.low ?? row.price, pointRsi = detailPlot.rsi14[index];
  tooltip.innerHTML = `<strong>${row.date}</strong><span>시가 ₩${fmt(open,4)} · 고가 ₩${fmt(high,4)}</span><span>저가 ₩${fmt(low,4)} · 종가 ₩${fmt(row.price,4)}</span><span>거래대금 ${compact(row.volume)}원 · RSI ${fmt(pointRsi,1)}</span>`; tooltip.hidden = false;
  tooltip.style.left = `${Math.max(8, Math.min(rect.width - 234, localX + 13))}px`; tooltip.style.top = "18px";
});
$("#detailChart").addEventListener("pointerleave", () => { $("#chartTooltip").hidden = true; scheduleDetailedChart(); });
window.addEventListener("resize", () => { if ($("#chartDialog").open) scheduleDetailedChart(); });

fetch(`data/latest.json?v=${Date.now()}`).then(response => { if (!response.ok) throw new Error("분석 파일을 읽지 못했습니다."); return response.json(); }).then(render).catch(error => { $("#recommendations").innerHTML = `<div class="error-card">${error.message} 잠시 후 다시 시도하거나 GitHub Actions 실행 상태를 확인하세요.</div>`; $("#qualityText").textContent = "데이터 오류"; });

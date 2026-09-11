const $ = (selector, root = document) => root.querySelector(selector);
const fmt = (value, digits = 1) => value == null ? "미수집" : Number(value).toLocaleString("ko-KR", { maximumFractionDigits: digits });
const pct = value => value == null ? "—" : `${value > 0 ? "+" : ""}${fmt(value)}%`;
let detailCoin = null;
let detailDays = 30;
let detailPlot = null;
let detailFrame = null;
let detailHoverIndex = null;
let altRankings = [];
let sentimentHistory = [];
let sentimentPlot = null;
let currentReport = null;
let liveSocket = null;
let liveReconnectTimer = null;
let liveApplyTimer = null;
let liveCodeKey = "";
const liveTickerBuffer = new Map();

const escapeHTML = value => String(value ?? "").replace(/[&<>'"]/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);
const EMAIL_STORAGE_KEY = "coin-signal-email-recipients";
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function parseEmailRecipients(value) {
  const seen = new Set();
  const valid = [], invalid = [];
  value.split(/[,;\n]+/).map(item => item.trim()).filter(Boolean).forEach(address => {
    const key = address.toLocaleLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    if (EMAIL_PATTERN.test(address)) valid.push(address); else invalid.push(address);
  });
  return { valid, invalid };
}

function updateEmailPreview() {
  const parsed = parseEmailRecipients($("#emailRecipients").value);
  $("#emailRecipientPreview").innerHTML = parsed.valid.length
    ? parsed.valid.map(address => `<span>${escapeHTML(address)}</span>`).join("")
    : `<small>등록할 주소를 입력해 주세요.</small>`;
  $("#emailSettingsStatus").textContent = parsed.invalid.length ? `형식이 잘못된 주소: ${parsed.invalid.join(", ")}` : `${parsed.valid.length}개 주소 입력됨`;
  $("#emailSettingsStatus").classList.toggle("error", Boolean(parsed.invalid.length));
  return parsed;
}

function openEmailSettings() {
  $("#emailRecipients").value = localStorage.getItem(EMAIL_STORAGE_KEY) || "";
  updateEmailPreview();
  $("#emailDialog").showModal();
}

function toggleQualityNote(forceOpen) {
  const note = $("#dataQualityNote"), button = $("#dataQualityButton");
  const open = forceOpen ?? note.hidden;
  note.hidden = !open;
  button.setAttribute("aria-expanded", String(open));
}

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

function drawSentimentChart(history, hoverIndex = null) {
  const canvas = $("#sentimentChart");
  if (!canvas || !history?.length) return;
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(260, Math.floor(canvas.clientWidth || 320));
  const height = Math.max(150, Math.floor(canvas.clientHeight || 180));
  const pixelWidth = Math.round(width * ratio), pixelHeight = Math.round(height * ratio);
  if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) { canvas.width = pixelWidth; canvas.height = pixelHeight; }
  const ctx = canvas.getContext("2d"); ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.clearRect(0, 0, width, height);
  const pad = { left: 34, right: 12, top: 12, bottom: 27 }, plotWidth = width - 46, plotHeight = height - 39;
  const x = index => pad.left + index * plotWidth / Math.max(1, history.length - 1);
  const y = value => pad.top + (100 - value) / 100 * plotHeight;
  ctx.font = "10px system-ui"; ctx.textAlign = "right"; ctx.textBaseline = "middle";
  [75, 50, 25].forEach(level => {
    const lineY = y(level); ctx.beginPath(); ctx.moveTo(pad.left, lineY); ctx.lineTo(width - pad.right, lineY);
    ctx.strokeStyle = level === 50 ? "rgba(255,191,71,.24)" : "rgba(143,162,189,.14)"; ctx.lineWidth = 1; ctx.stroke();
    ctx.fillStyle = "#7f93af"; ctx.fillText(String(level), pad.left - 7, lineY);
  });
  const points = history.map((point, index) => [x(index), y(Number(point.value))]);
  const gradient = ctx.createLinearGradient(0, pad.top, 0, height - pad.bottom);
  gradient.addColorStop(0, "rgba(79,224,155,.28)"); gradient.addColorStop(.5, "rgba(255,191,71,.13)"); gradient.addColorStop(1, "rgba(255,107,120,.03)");
  ctx.beginPath(); ctx.moveTo(points[0][0], height - pad.bottom); points.forEach(point => ctx.lineTo(point[0], point[1])); ctx.lineTo(points.at(-1)[0], height - pad.bottom); ctx.closePath(); ctx.fillStyle = gradient; ctx.fill();
  ctx.beginPath(); points.forEach((point, index) => index ? ctx.lineTo(point[0], point[1]) : ctx.moveTo(point[0], point[1]));
  ctx.strokeStyle = "#ffbf47"; ctx.lineWidth = 2.2; ctx.lineJoin = "round"; ctx.lineCap = "round"; ctx.stroke();
  const latest = points.at(-1); ctx.beginPath(); ctx.arc(latest[0], latest[1], 3.5, 0, Math.PI * 2); ctx.fillStyle = "#fff1bd"; ctx.fill();
  const labels = [0, Math.floor((history.length - 1) / 2), history.length - 1];
  ctx.fillStyle = "#7f93af"; ctx.textBaseline = "bottom";
  labels.forEach((index, position) => { ctx.textAlign = position === 0 ? "left" : position === 2 ? "right" : "center"; ctx.fillText(history[index].date.slice(5), x(index), height - 3); });
  if (hoverIndex != null && history[hoverIndex]) {
    const point = points[hoverIndex]; ctx.beginPath(); ctx.moveTo(point[0], pad.top); ctx.lineTo(point[0], height - pad.bottom);
    ctx.strokeStyle = "rgba(237,244,255,.3)"; ctx.setLineDash([3, 3]); ctx.stroke(); ctx.setLineDash([]);
    ctx.beginPath(); ctx.arc(point[0], point[1], 4, 0, Math.PI * 2); ctx.fillStyle = "#edf4ff"; ctx.fill();
  }
  sentimentPlot = { history, pad, width };
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

function macdValues(values, fastPeriod = 12, slowPeriod = 26, signalPeriod = 9) {
  if (!values.length) return { line: [], signal: [], histogram: [] };
  const fast = emaValues(values, fastPeriod), slow = emaValues(values, slowPeriod);
  const line = values.map((_, index) => fast[index] - slow[index]);
  const signal = emaValues(line, signalPeriod);
  return { line, signal, histogram: line.map((value, index) => value - signal[index]) };
}

function liveTechnicalScore(metrics) {
  let points = 0;
  if (metrics.ema20 != null && metrics.ema50 != null) {
    if (metrics.price > metrics.ema20 && metrics.ema20 > metrics.ema50) points += 8;
    else if (metrics.price < metrics.ema20 && metrics.ema20 < metrics.ema50) points -= 10;
  }
  if (metrics.rsi != null) {
    if (metrics.rsi >= 45 && metrics.rsi <= 65) points += 4;
    else if (metrics.rsi >= 75) points -= 7;
    else if (metrics.rsi < 35) points -= 3;
  }
  points += metrics.macd_histogram == null ? 0 : metrics.macd_histogram > 0 ? 4 : -3;
  if (metrics.return_7d != null && metrics.return_30d != null) {
    if (metrics.return_7d > 0 && metrics.return_7d <= 15 && metrics.return_30d > 3 && metrics.return_30d <= 35) points += 6;
    if (metrics.return_7d > 25 || metrics.return_30d > 60) points -= 8;
  }
  const bounded = Math.max(-18, Math.min(22, points));
  return Math.round((bounded + 18) / 40 * 100);
}

function updateCoinWithLivePrice(coin, ticker) {
  if (!coin || !ticker?.trade_price) return coin;
  const price = Number(ticker.trade_price), today = new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10);
  const rows = historyFor(coin).map(row => ({ ...row }));
  if (!rows.length) return coin;
  const last = rows.at(-1);
  if (last.date === today) {
    last.price = price; last.high = Math.max(Number(last.high ?? price), price); last.low = Math.min(Number(last.low ?? price), price);
  } else {
    rows.push({ date: today, open: price, high: price, low: price, price, volume: Number(ticker.acc_trade_price_24h) || 0 });
    if (rows.length > 120) rows.shift();
  }
  const prices = rows.map(row => Number(row.price)), ema20 = emaValues(prices, 20), ema50 = emaValues(prices, 50);
  const rsi14 = rsiValues(prices), macd = macdValues(prices);
  const change = days => prices.length > days && prices.at(-days - 1) ? (price / prices.at(-days - 1) - 1) * 100 : null;
  Object.assign(coin, {
    price, history: rows, sparkline: prices.slice(-30), ema20: ema20.at(-1), ema50: ema50.at(-1),
    rsi: [...rsi14].reverse().find(value => value != null), macd: macd.line.at(-1), macd_signal: macd.signal.at(-1),
    macd_histogram: macd.histogram.at(-1), return_7d: change(7), return_30d: change(30),
    trade_value_24h: Number(ticker.acc_trade_price_24h) || coin.trade_value_24h,
  });
  coin.live_technical_score = liveTechnicalScore(coin);
  return coin;
}

function renderLiveRankings() {
  const ranked = [...altRankings].map(coin => {
    if (coin.live_technical_score == null) coin.live_technical_score = liveTechnicalScore(coin);
    return coin;
  }).sort((a, b) => (b.live_technical_score - a.live_technical_score) || ((b.trade_value_24h || 0) - (a.trade_value_24h || 0)));
  ranked.forEach((coin, index) => { coin.live_rank = index + 1; });
  $("#liveRankingGrid").innerHTML = ranked.slice(0, 10).map(coin => `
    <button type="button" class="live-rank-card" data-live-symbol="${escapeHTML(coin.symbol)}" aria-label="${escapeHTML(coin.name)} 상세차트 열기">
      <span class="live-rank-number">#${coin.live_rank}</span><span class="live-rank-name"><strong>${escapeHTML(coin.name)}</strong><small>${escapeHTML(coin.symbol)} · ₩${fmt(coin.price, 4)}</small></span>
      <span class="live-rank-metrics"><small>RSI ${fmt(coin.rsi, 1)}</small><small>MACD ${fmt(coin.macd_histogram, 4)}</small></span><strong class="live-rank-score">${coin.live_technical_score}<small>/100</small></strong>
    </button>`).join("");
  $("#liveRankingGrid").querySelectorAll("[data-live-symbol]").forEach(button => button.addEventListener("click", () => {
    const coin = altRankings.find(item => item.symbol === button.dataset.liveSymbol); if (coin) openDetailChart(coin);
  }));
}

function renderRecommendationCards() {
  if (!currentReport) return;
  const list = $("#recommendations"); list.innerHTML = "";
  currentReport.recommendations.forEach((coin, index) => {
    const liveCoin = altRankings.find(item => item.symbol === coin.symbol);
    if (liveCoin) Object.assign(coin, { price: liveCoin.price, history: liveCoin.history, sparkline: liveCoin.sparkline, ema20: liveCoin.ema20, ema50: liveCoin.ema50, rsi: liveCoin.rsi, macd_histogram: liveCoin.macd_histogram, return_7d: liveCoin.return_7d, return_30d: liveCoin.return_30d });
    list.appendChild(renderCoin(coin, index));
  });
}

function setLiveStatus(label, state = "connecting") {
  $("#liveStatus").textContent = label;
  $("#liveDot").className = `live-dot ${state}`;
}

function applyLiveMarket() {
  if (!currentReport || !liveTickerBuffer.size) return;
  altRankings.forEach(coin => updateCoinWithLivePrice(coin, liveTickerBuffer.get(coin.market || `KRW-${coin.symbol}`)));
  const bitcoin = currentReport.market.bitcoin;
  updateCoinWithLivePrice(bitcoin, liveTickerBuffer.get("KRW-BTC"));
  $("#btcPrice").textContent = `₩${fmt(bitcoin.price, 0)}`; $("#btcRsi").textContent = fmt(bitcoin.rsi); $("#btcReturn").textContent = pct(bitcoin.return_30d);
  drawLine($("#btcChart"), bitcoin.sparkline, "#4d8dff");
  renderLiveRankings(); renderRecommendationCards();
  const search = $("#altSearchInput").value.trim(); if (search && !$("#altSearchResult .search-empty")) searchAltcoin(search);
  if (detailCoin) { const liveCoin = detailCoin.symbol === "BTC" ? bitcoin : altRankings.find(item => item.symbol === detailCoin.symbol); if (liveCoin) detailCoin = liveCoin; if ($("#chartDialog").open) { $("#chartPrice").textContent = `현재 ₩${fmt(detailCoin.price, 4)} · 30일 ${pct(detailCoin.return_30d)}`; scheduleDetailedChart(); } }
  const updated = new Date().toLocaleTimeString("ko-KR", { timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit", second: "2-digit" });
  $("#liveUpdatedAt").textContent = `${updated} 반영`; setLiveStatus("1분 기술순위 정상", "connected");
}

function scheduleLiveApply() {
  if (liveApplyTimer) clearTimeout(liveApplyTimer);
  const delay = 60000 - Date.now() % 60000;
  liveApplyTimer = setTimeout(() => { applyLiveMarket(); scheduleLiveApply(); }, delay);
}

function startLiveMarket(codes) {
  if (!("WebSocket" in window) || !codes.length) { setLiveStatus("실시간 기능 미지원", "error"); return; }
  const codeKey = [...codes].sort().join(",");
  if (liveSocket && liveCodeKey === codeKey && liveSocket.readyState <= WebSocket.OPEN) return;
  if (liveSocket) { liveSocket.intentionalClose = true; liveSocket.close(); }
  liveCodeKey = codeKey;
  clearTimeout(liveReconnectTimer); setLiveStatus("업비트 연결 중", "connecting");
  const socket = new WebSocket("wss://api.upbit.com/websocket/v1"); liveSocket = socket;
  socket.binaryType = "arraybuffer";
  socket.addEventListener("open", () => {
    socket.send(JSON.stringify([{ ticket: `coin-recomand-${Date.now()}` }, { type: "ticker", codes, isOnlyRealtime: true }, { format: "DEFAULT" }]));
    setLiveStatus("시세 수신 중", "connected"); scheduleLiveApply();
  });
  socket.addEventListener("message", event => {
    try {
      const text = typeof event.data === "string" ? event.data : new TextDecoder().decode(event.data);
      const ticker = JSON.parse(text); if (ticker.code) liveTickerBuffer.set(ticker.code, ticker);
    } catch { setLiveStatus("시세 해석 오류", "error"); }
  });
  socket.addEventListener("error", () => setLiveStatus("실시간 연결 오류", "error"));
  socket.addEventListener("close", () => { if (socket.intentionalClose) return; setLiveStatus("재연결 대기 중", "connecting"); liveSocket = null; liveReconnectTimer = setTimeout(() => startLiveMarket(codes), 5000); });
  setTimeout(applyLiveMarket, 3000);
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
  const macd = macdValues(allPrices);
  const macdLine = macd.line.slice(start), macdSignal = macd.signal.slice(start), macdHistogram = macd.histogram.slice(start);
  const canvas = $("#detailChart"), ratio = window.devicePixelRatio || 1;
  const bounds = canvas.getBoundingClientRect();
  const width = Math.max(280, Math.floor(bounds.width)), height = Math.max(280, Math.floor(bounds.height));
  const pixelWidth = Math.round(width * ratio), pixelHeight = Math.round(height * ratio);
  if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) { canvas.width = pixelWidth; canvas.height = pixelHeight; }
  const ctx = canvas.getContext("2d"); ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.clearRect(0, 0, width, height);
  const pad = { left: width < 560 ? 49 : 68, right: 18, top: 21, bottom: 22 };
  const priceBottom = height * .47, volumeTop = priceBottom + 8, volumeBottom = height * .57;
  const dateY = volumeBottom + 4, macdTop = height * .635, macdBottom = height * .77;
  const rsiTop = height * .82, rsiBottom = height - pad.bottom;
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

  const plot = (values, color, lineWidth, mapY = y) => {
    ctx.beginPath(); let started = false;
    values.forEach((value, index) => {
      if (value == null || !Number.isFinite(value)) { started = false; return; }
      if (started) ctx.lineTo(x(index), mapY(value)); else { ctx.moveTo(x(index), mapY(value)); started = true; }
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

  const macdExtent = Math.max(...macdLine.map(Math.abs), ...macdSignal.map(Math.abs), ...macdHistogram.map(Math.abs), 1e-9);
  const macdY = value => macdTop + (macdExtent - value) / (macdExtent * 2) * (macdBottom - macdTop);
  const macdZeroY = macdY(0), macdBarWidth = Math.max(1, candleWidth * .78);
  ctx.beginPath(); ctx.moveTo(pad.left, macdZeroY); ctx.lineTo(width - pad.right, macdZeroY);
  ctx.strokeStyle = "rgba(143,162,189,.2)"; ctx.lineWidth = 1; ctx.stroke();
  macdHistogram.forEach((value, index) => {
    const valueY = macdY(value);
    ctx.fillStyle = value >= 0 ? "rgba(49,216,197,.48)" : "rgba(255,107,120,.45)";
    ctx.fillRect(x(index) - macdBarWidth / 2, Math.min(macdZeroY, valueY), macdBarWidth, Math.max(1, Math.abs(valueY - macdZeroY)));
  });
  plot(macdLine, "#4d8dff", 1.55, macdY); plot(macdSignal, "#ffbf47", 1.35, macdY);
  ctx.fillStyle = "#a8b8ce"; ctx.textAlign = "left"; ctx.textBaseline = "top"; ctx.fillText("MACD(12,26,9)", pad.left + 5, macdTop + 3);

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
  detailPlot = { rows, rsi14, macdLine, macdSignal, macdHistogram, x, pad, width };
  const change = prices[0] ? (prices.at(-1) / prices[0] - 1) * 100 : null;
  const latestRsi = [...rsi14].reverse().find(value => value != null);
  $("#detailStats").innerHTML = metric("기간 수익률", pct(change)) + metric("기간 최고가", `₩${fmt(Math.max(...highs), 4)}`) + metric("기간 최저가", `₩${fmt(Math.min(...lows), 4)}`) + metric("EMA20", `₩${fmt(detailCoin.ema20, 4)}`) + metric("EMA50", `₩${fmt(detailCoin.ema50, 4)}`) + metric("RSI(14)", fmt(latestRsi, 1)) + metric("MACD", fmt(macdLine.at(-1), 4)) + metric("시그널", fmt(macdSignal.at(-1), 4)) + metric("히스토그램", fmt(macdHistogram.at(-1), 4));
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

function renderAltSearchResult(coin) {
  const result = $("#altSearchResult");
  const decisionClass = coin.decision === "분할매수 후보" ? "buy" : coin.decision === "보류" ? "hold" : "watch";
  const mentions = coin.community_mentions || {};
  const community = coin.community_sources
    ? `오늘 ${coin.community_total || 0}회 · Reddit ${mentions.reddit ?? "미수집"} / 디시 ${mentions.dcinside ?? "미수집"} / 코인판 ${mentions.coinpan ?? "미수집"}`
    : "커뮤니티 데이터 미수집";
  const development = coin.development || {};
  const tokenomics = coin.tokenomics || {};
  const detailed = coin.analysis_scope === "정밀분석";
  const unlock = tokenomics.next_unlock;
  const unlockText = unlock
    ? `${unlock.date || "일정 확인 필요"}${unlock.days_until != null ? ` · ${unlock.days_until}일 후` : ""}${unlock.percent_circulating != null ? ` · 유통량의 ${fmt(unlock.percent_circulating, 2)}%` : " · 수량 미확인"}`
    : tokenomics.unlock_data_available ? "60일 이내 예정 없음" : "미수집";
  const reasons = coin.reasons?.length ? coin.reasons : ["현재 가산 근거가 확인되지 않았습니다."];
  const risks = coin.risks?.length ? coin.risks : ["뚜렷한 정량 위험 신호 없음 — 시장 변동성은 별도 관리 필요"];
  result.innerHTML = `
    <article class="search-result-card">
      <div class="search-result-top">
        <div><span class="search-rank">종합 #${escapeHTML(coin.rank)}${coin.live_rank ? ` · 실시간 기술 #${escapeHTML(coin.live_rank)}` : ""}</span><h3>${escapeHTML(coin.name)} <small>${escapeHTML(coin.symbol)}</small></h3><p>${escapeHTML(coin.english_name || "")} · 현재가 ₩${fmt(coin.price, 4)}</p></div>
        <div class="search-score"><span class="decision ${decisionClass}">${escapeHTML(coin.decision)}</span><strong>${escapeHTML(coin.score)}</strong><small>/ 100점</small></div>
      </div>
      <div class="search-score-track"><i style="width:${Math.max(0, Math.min(100, Number(coin.score) || 0))}%"></i></div>
      <div class="search-metrics">
        ${metric("RSI(14)", fmt(coin.rsi))}${metric("MACD 히스토그램", fmt(coin.macd_histogram, 4))}${metric("EMA 추세", coin.ema20 != null && coin.ema50 != null ? (coin.ema20 > coin.ema50 ? "정배열" : "역배열") : "—")}${metric("7일 수익률", pct(coin.return_7d))}${metric("30일 수익률", pct(coin.return_30d))}${metric("거래량 비율", coin.volume_ratio == null ? "—" : `${fmt(coin.volume_ratio, 2)}×`)}${metric("변동성", pct(coin.volatility))}${metric("커뮤니티 노출", escapeHTML(community))}
      </div>
      <button type="button" class="search-chart-button" data-search-chart>캔들 차트·전체 지표 보기 <span aria-hidden="true">↗</span></button>
      <div class="search-context">
        <section><h4>점수 상승 근거</h4><ul>${reasons.map(item => `<li>${escapeHTML(item)}</li>`).join("")}</ul></section>
        <section class="search-risks"><h4>감점·확인할 위험</h4><ul>${risks.map(item => `<li>${escapeHTML(item)}</li>`).join("")}</ul></section>
      </div>
      <div class="search-updates">
        <div><span>개발 진척</span><strong>${escapeHTML(development.status || (detailed ? "미수집" : "정밀분석 대상 외"))}</strong><small>${development.commits_30d != null ? `최근 30일 ${escapeHTML(development.commits_30d)}개 커밋` : detailed ? "공개 활동 기준" : "현재 상위 25개 종목만 조회"}</small></div>
        <div><span>최근 릴리스</span><strong>${escapeHTML(development.latest_release_name || "확인된 릴리스 없음")}</strong><small>${development.latest_release_days != null ? `${escapeHTML(development.latest_release_days)}일 전` : "GitHub 공개 저장소 기준"}</small></div>
        <div><span>토큰 언락</span><strong>${escapeHTML(unlockText)}</strong><small>${tokenomics.circulating_ratio != null ? `현재 유통 비율 ${fmt(tokenomics.circulating_ratio)}%` : "유통량 미수집"}</small></div>
        <div><span>프로젝트 공지</span><strong>${escapeHTML(tokenomics.project_notice || "확인된 주요 공지 없음")}</strong><small>CoinGecko 공개 공지 기준</small></div>
      </div>
      <p class="search-note">순위는 유동성·거래이력 기준을 통과한 ${escapeHTML(altRankings.length)}개 종목 안에서 산정됩니다. 개발·언락 정밀자료는 기술 점수 상위 25개를 우선 조회하며, 데이터 생성 시각 이후의 뉴스나 공지는 반영되지 않을 수 있습니다.</p>
    </article>`;
  result.querySelector("[data-search-chart]").addEventListener("click", () => openDetailChart(coin));
}

function searchAltcoin(query) {
  const normalized = query.trim().toLocaleLowerCase("ko-KR");
  if (!normalized) {
    $("#altSearchResult").innerHTML = `<p class="search-empty">검색할 코인 이름이나 심볼을 입력해 주세요.</p>`;
    return;
  }
  const exact = altRankings.find(coin => [coin.symbol, coin.name, coin.english_name].some(value => String(value || "").toLocaleLowerCase("ko-KR") === normalized));
  const partial = altRankings.find(coin => [coin.symbol, coin.name, coin.english_name].some(value => String(value || "").toLocaleLowerCase("ko-KR").includes(normalized)));
  const coin = exact || partial;
  if (coin) renderAltSearchResult(coin);
  else $("#altSearchResult").innerHTML = `<p class="search-empty"><strong>${escapeHTML(query)}</strong>은 현재 유동성·거래이력 기준을 통과한 ${escapeHTML(altRankings.length)}개 분석 종목에서 찾지 못했습니다.</p>`;
}

function render(report) {
  currentReport = report;
  const { market } = report, btc = market.bitcoin;
  $("#generatedAt").textContent = report.generated_at_kst;
  $("#qualityDot").style.background = report.data_quality.status === "정상" ? "var(--green)" : "var(--amber)";
  $("#marketTitle").textContent = `${market.regime} 국면`; $("#marketSummary").textContent = market.regime === "상승" ? "추세가 우호적입니다. 후보별 과열 여부를 확인하세요." : market.regime === "하락" ? "신규 매수보다 현금 비중과 손실 제한을 우선합니다." : "방향 확인 전 강한 종목만 선별적으로 관찰합니다.";
  $("#marketScore").textContent = market.score; $("#scoreRing").style.background = `conic-gradient(${market.regime === "하락" ? "var(--red)" : market.regime === "상승" ? "var(--green)" : "var(--blue)"} ${market.score * 3.6}deg, var(--line) 0)`;
  $("#marketReasons").innerHTML = market.reasons.map(x => `<p>${x}</p>`).join("");
  btc.symbol = "BTC"; btc.name = "비트코인"; btc.market = "KRW-BTC";
  $("#btcPrice").textContent = `₩${fmt(btc.price,0)}`; $("#mvrv").textContent = fmt(btc.mvrv_z,2); $("#mvrvLabel").textContent = btc.mvrv_source ? `MVRV Z · ${btc.mvrv_source}` : "MVRV Z"; $("#btcRsi").textContent = fmt(btc.rsi); $("#btcReturn").textContent = pct(btc.return_30d); $("#btcVolume").textContent = btc.volume_ratio == null ? "—" : `${fmt(btc.volume_ratio,2)}×`; drawLine($("#btcChart"), btc.sparkline, "#4d8dff");
  const btcCard = $("#btcDetailCard"); btcCard.onclick = () => openDetailChart(btc); btcCard.onkeydown = event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openDetailChart(btc); } };
  altRankings = report.alt_rankings?.length ? report.alt_rankings : report.recommendations.map((coin, index) => ({ ...coin, rank: index + 1 }));
  $("#screenedCount").textContent = report.screened; renderRecommendationCards(); renderLiveRankings();
  $("#altSearchOptions").innerHTML = altRankings.map(coin => `<option value="${escapeHTML(coin.symbol)}">${escapeHTML(coin.name)} · ${escapeHTML(coin.english_name || "")}</option>`).join("");
  const fear = market.fear_greed; $("#fearValue").textContent = fear.value ?? "—"; $("#fearClass").textContent = fear.classification; $("#fearGauge").style.left = `${fear.value ?? 50}%`;
  sentimentHistory = fear.history || [];
  if (sentimentHistory.length) {
    const change = Number(sentimentHistory.at(-1).value) - Number(sentimentHistory[0].value);
    $("#fearChange").textContent = `30일 ${change > 0 ? "+" : ""}${change}p`;
    requestAnimationFrame(() => drawSentimentChart(sentimentHistory));
  } else {
    $("#fearChange").textContent = "이력 미수집";
  }
  renderMethodology(report.methodology);
  const warnings = report.data_quality.warnings || [], notices = report.data_quality.notices || [];
  $("#qualityText").textContent = warnings.length ? "일부 보조자료 미수집" : "데이터 정상";
  $("#qualityNoteTitle").textContent = warnings.length ? "일부 보조자료를 가져오지 못했습니다" : "핵심 데이터가 정상 수집됐습니다";
  $("#qualityNoteSummary").textContent = warnings.length
    ? "가격·거래량·BTC 지표 전체의 오류를 뜻하지 않습니다. 아래 보조자료가 빠진 종목은 확인 가능한 데이터만으로 평가했습니다."
    : "가격·거래량·시장지표를 포함한 핵심 자료가 정상적으로 반영됐습니다.";
  $("#qualityNoteWarnings").innerHTML = warnings.length ? `<h3>미수집 항목</h3><ul>${warnings.map(item => `<li>${escapeHTML(item)}</li>`).join("")}</ul>` : "";
  $("#qualityNoteNotices").innerHTML = notices.length ? `<h3>분석 제외·참고</h3><ul>${notices.map(item => `<li>${escapeHTML(item)}</li>`).join("")}</ul>` : "";
  $("#warnings").innerHTML = (warnings.length ? warnings.map(x => `<p>• ${escapeHTML(x)}</p>`).join("") : `<p class="ok">모든 핵심 데이터가 정상 수집됐습니다.</p>`) + notices.map(x => `<p class="notice">참고 · ${escapeHTML(x)}</p>`).join("");
  $("#sources").innerHTML = report.sources.map(s => `<a href="${s.url}" target="_blank" rel="noopener">${s.name}</a>`).join(""); $("#disclaimer").textContent = report.disclaimer;
  startLiveMarket(["KRW-BTC", ...altRankings.map(coin => coin.market || `KRW-${coin.symbol}`)]);
}

$("#altSearchForm").addEventListener("submit", event => { event.preventDefault(); searchAltcoin($("#altSearchInput").value); });
$("#dataQualityButton").addEventListener("click", event => { event.stopPropagation(); toggleQualityNote(); });
$("#dataQualityNote").addEventListener("click", event => event.stopPropagation());
document.addEventListener("click", () => toggleQualityNote(false));
document.addEventListener("keydown", event => { if (event.key === "Escape") toggleQualityNote(false); });

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
  const pointMacd = detailPlot.macdLine[index], pointSignal = detailPlot.macdSignal[index], pointHistogram = detailPlot.macdHistogram[index];
  tooltip.innerHTML = `<strong>${row.date}</strong><span>시가 ₩${fmt(open,4)} · 고가 ₩${fmt(high,4)}</span><span>저가 ₩${fmt(low,4)} · 종가 ₩${fmt(row.price,4)}</span><span>거래대금 ${compact(row.volume)}원 · RSI ${fmt(pointRsi,1)}</span><span>MACD ${fmt(pointMacd,4)} · Signal ${fmt(pointSignal,4)} · Hist ${fmt(pointHistogram,4)}</span>`; tooltip.hidden = false;
  tooltip.style.left = `${Math.max(8, Math.min(rect.width - 234, localX + 13))}px`; tooltip.style.top = "18px";
});
$("#detailChart").addEventListener("pointerleave", () => { $("#chartTooltip").hidden = true; scheduleDetailedChart(); });
$("#sentimentChart").addEventListener("pointermove", event => {
  if (!sentimentPlot) return;
  const rect = event.currentTarget.getBoundingClientRect(), localX = event.clientX - rect.left;
  const plotWidth = sentimentPlot.width - sentimentPlot.pad.left - sentimentPlot.pad.right;
  const ratioX = (localX - sentimentPlot.pad.left) / Math.max(1, plotWidth);
  const index = Math.max(0, Math.min(sentimentPlot.history.length - 1, Math.round(ratioX * (sentimentPlot.history.length - 1))));
  drawSentimentChart(sentimentHistory, index);
  const point = sentimentPlot.history[index], tooltip = $("#sentimentTooltip");
  tooltip.innerHTML = `<strong>${escapeHTML(point.date)}</strong><span>지수 ${escapeHTML(point.value)} · ${escapeHTML(point.classification || "분류 없음")}</span>`;
  tooltip.hidden = false; tooltip.style.left = `${Math.max(7, Math.min(rect.width - 154, localX + 10))}px`; tooltip.style.top = "9px";
});
$("#sentimentChart").addEventListener("pointerleave", () => { $("#sentimentTooltip").hidden = true; drawSentimentChart(sentimentHistory); });
window.addEventListener("resize", () => { if ($("#chartDialog").open) scheduleDetailedChart(); if (sentimentHistory.length) drawSentimentChart(sentimentHistory); });

$("#emailSettingsButton").addEventListener("click", openEmailSettings);
$("#emailDialogClose").addEventListener("click", () => $("#emailDialog").close());
$("#emailDialog").addEventListener("click", event => { if (event.target === event.currentTarget) event.currentTarget.close(); });
$("#emailRecipients").addEventListener("input", updateEmailPreview);
$("#saveEmailRecipients").addEventListener("click", () => {
  const parsed = updateEmailPreview();
  if (parsed.invalid.length || !parsed.valid.length) return;
  localStorage.setItem(EMAIL_STORAGE_KEY, parsed.valid.join("\n"));
  $("#emailSettingsStatus").textContent = "이 브라우저에 주소 목록을 저장했습니다. 예약 발송에는 GitHub Secret 등록도 필요합니다.";
});
$("#copyEmailSecret").addEventListener("click", async () => {
  const parsed = updateEmailPreview();
  if (parsed.invalid.length || !parsed.valid.length) return;
  const value = parsed.valid.join(",");
  localStorage.setItem(EMAIL_STORAGE_KEY, parsed.valid.join("\n"));
  try {
    await navigator.clipboard.writeText(value);
    $("#emailSettingsStatus").textContent = "EMAIL_TO 값이 복사됐습니다. GitHub Secret 등록 버튼을 눌러 붙여넣으세요.";
  } catch {
    $("#emailRecipients").value = value;
    $("#emailRecipients").select();
    $("#emailSettingsStatus").textContent = "자동 복사가 차단됐습니다. 선택된 주소를 직접 복사해 주세요.";
  }
});

async function loadLatestReport() {
  try {
    const response = await fetch(`data/latest.json?v=${Date.now()}`); if (!response.ok) throw new Error("분석 파일을 읽지 못했습니다.");
    const report = await response.json(); if (!currentReport || report.generated_at !== currentReport.generated_at) render(report);
  } catch (error) {
    if (!currentReport) $("#recommendations").innerHTML = `<div class="error-card">${error.message} 잠시 후 다시 시도하거나 GitHub Actions 실행 상태를 확인하세요.</div>`;
    $("#qualityText").textContent = currentReport ? "새 종합자료 확인 지연" : "데이터 오류";
  }
}

loadLatestReport();
setInterval(loadLatestReport, 5 * 60 * 1000);

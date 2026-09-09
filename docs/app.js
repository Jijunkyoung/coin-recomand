const $ = (selector, root = document) => root.querySelector(selector);
const fmt = (value, digits = 1) => value == null ? "미수집" : Number(value).toLocaleString("ko-KR", { maximumFractionDigits: digits });
const pct = value => value == null ? "—" : `${value > 0 ? "+" : ""}${fmt(value)}%`;

function drawLine(canvas, values, color = "#4d8dff") {
  if (!values?.length) return;
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth || 300;
  const height = Number(canvas.getAttribute("height")) || 80;
  canvas.width = width * ratio; canvas.height = height * ratio;
  const ctx = canvas.getContext("2d"); ctx.scale(ratio, ratio);
  const min = Math.min(...values), max = Math.max(...values), spread = max - min || 1;
  const points = values.map((v, i) => [8 + i * (width - 16) / Math.max(1, values.length - 1), height - 8 - (v - min) / spread * (height - 18)]);
  const gradient = ctx.createLinearGradient(0, 0, 0, height); gradient.addColorStop(0, `${color}55`); gradient.addColorStop(1, `${color}00`);
  ctx.beginPath(); ctx.moveTo(points[0][0], height); points.forEach(([x,y]) => ctx.lineTo(x,y)); ctx.lineTo(points.at(-1)[0], height); ctx.fillStyle = gradient; ctx.fill();
  ctx.beginPath(); points.forEach(([x,y],i) => i ? ctx.lineTo(x,y) : ctx.moveTo(x,y)); ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.stroke();
}

function metric(label, value) { return `<div><span>${label}</span><strong>${value}</strong></div>`; }

function renderCoin(coin, index) {
  const node = $("#coinTemplate").content.cloneNode(true);
  $(".rank", node).textContent = `#${index + 1}`; $("h3", node).textContent = coin.name; $(".ticker", node).textContent = `${coin.symbol} · ₩${fmt(coin.price, 4)}`;
  const decision = $(".decision", node); decision.textContent = coin.decision; decision.classList.add(coin.decision === "분할매수 후보" ? "buy" : coin.decision === "보류" ? "hold" : "watch");
  $(".coin-score strong", node).textContent = coin.score; $(".score-bar i", node).style.width = `${coin.score}%`;
  $(".coin-metrics", node).innerHTML = metric("RSI", fmt(coin.rsi)) + metric("7일", pct(coin.return_7d)) + metric("30일", pct(coin.return_30d)) + metric("거래량 비율", coin.volume_ratio == null ? "—" : `${fmt(coin.volume_ratio,2)}×`) + metric("변동성", pct(coin.volatility)) + metric("커뮤니티", coin.trending_rank ? `인기 ${coin.trending_rank}위` : coin.reddit_mentions ? `${coin.reddit_mentions}회` : "미수집");
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
  $("#btcPrice").textContent = `₩${fmt(btc.price,0)}`; $("#mvrv").textContent = fmt(btc.mvrv_z,2); $("#btcRsi").textContent = fmt(btc.rsi); $("#btcReturn").textContent = pct(btc.return_30d); $("#btcVolume").textContent = btc.volume_ratio == null ? "—" : `${fmt(btc.volume_ratio,2)}×`; drawLine($("#btcChart"), btc.sparkline, "#4d8dff");
  $("#screenedCount").textContent = report.screened; const list = $("#recommendations"); list.innerHTML = ""; report.recommendations.forEach((coin, i) => list.appendChild(renderCoin(coin, i)));
  const fear = market.fear_greed; $("#fearValue").textContent = fear.value ?? "—"; $("#fearClass").textContent = fear.classification; $("#fearGauge").style.left = `${fear.value ?? 50}%`;
  $("#methodology").innerHTML = Object.values(report.methodology).map(x => `<li>${x}</li>`).join("");
  $("#warnings").innerHTML = report.data_quality.warnings.length ? report.data_quality.warnings.map(x => `<p>• ${x}</p>`).join("") : `<p class="ok">모든 핵심 데이터가 정상 수집됐습니다.</p>`;
  $("#sources").innerHTML = report.sources.map(s => `<a href="${s.url}" target="_blank" rel="noopener">${s.name}</a>`).join(""); $("#disclaimer").textContent = report.disclaimer;
}

fetch(`data/latest.json?v=${Date.now()}`).then(response => { if (!response.ok) throw new Error("분석 파일을 읽지 못했습니다."); return response.json(); }).then(render).catch(error => { $("#recommendations").innerHTML = `<div class="error-card">${error.message} 잠시 후 다시 시도하거나 GitHub Actions 실행 상태를 확인하세요.</div>`; $("#qualityText").textContent = "데이터 오류"; });

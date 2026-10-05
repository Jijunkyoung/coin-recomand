const $ = (selector, root = document) => root.querySelector(selector);
const market = document.body.dataset.stockMarket;
let report = null, detailStock = null, detailDays = 30, detailPlot = null, detailFrame = null;
let detailHistory = [], detailInterval = "1d", detailRequest = 0, manualRefreshRunning = false;
const sectorFallback = [{id:"defense",label:"방산"},{id:"semiconductor",label:"반도체"},{id:"energy",label:"에너지"},{id:"ai_platform",label:"AI·플랫폼"},{id:"mobility",label:"자동차·모빌리티"},{id:"bio",label:"바이오·헬스케어"},{id:"finance",label:"금융"},{id:"consumer",label:"소비·유통"},{id:"shipbuilding",label:"조선·기계"}];
const escapeHTML = value => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
const fmt = (value, digits = 2) => value == null || !Number.isFinite(Number(value)) ? "—" : Intl.NumberFormat("ko-KR", {maximumFractionDigits:digits}).format(Number(value));
const pct = value => value == null ? "—" : `${Number(value) > 0 ? "+" : ""}${fmt(value, 1)}%`;
const currency = value => (report?.currency || (market === "us" ? "USD" : "KRW")) === "USD" ? `$${fmt(value, 2)}` : `₩${fmt(value, 0)}`;
const metric = (label, value) => `<div><span>${label}</span><strong>${value}</strong></div>`;

function drawLine(canvas, values, color = "#31d8c5") {
  const ratio = window.devicePixelRatio || 1, rect = canvas.getBoundingClientRect(), width = Math.max(rect.width, 180), height = Math.max(rect.height, 58);
  canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
  const ctx = canvas.getContext("2d"); ctx.setTransform(ratio,0,0,ratio,0,0); ctx.clearRect(0,0,width,height);
  if (!values?.length) return;
  const min = Math.min(...values), max = Math.max(...values), spread = max - min || 1, x = i => i * width / Math.max(1, values.length - 1), y = v => 6 + (max - v) / spread * (height - 12);
  ctx.beginPath(); values.forEach((value,index) => index ? ctx.lineTo(x(index),y(value)) : ctx.moveTo(x(index),y(value))); ctx.strokeStyle=color; ctx.lineWidth=2; ctx.stroke();
}

function ema(values, period) { const k=2/(period+1), out=[values[0]]; for(let i=1;i<values.length;i++) out.push((values[i]-out[i-1])*k+out[i-1]); return out; }
function rsi(values, period=14) { const out=Array(values.length).fill(null); if(values.length<=period)return out; let gain=0,loss=0; for(let i=1;i<=period;i++){const d=values[i]-values[i-1];gain+=Math.max(d,0);loss+=Math.max(-d,0)} let ag=gain/period,al=loss/period; const calc=()=>al===0?100:100-100/(1+ag/al); out[period]=calc(); for(let i=period+1;i<values.length;i++){const d=values[i]-values[i-1];ag=(ag*(period-1)+Math.max(d,0))/period;al=(al*(period-1)+Math.max(-d,0))/period;out[i]=calc()} return out; }
function macd(values){const fast=ema(values,12),slow=ema(values,26),line=values.map((_,i)=>fast[i]-slow[i]),signal=ema(line,9);return{line,signal,hist:line.map((v,i)=>v-signal[i])}}
function bands(values, period=20){const middle=Array(values.length).fill(null),upper=[...middle],lower=[...middle];for(let i=period-1;i<values.length;i++){const part=values.slice(i-period+1,i+1),avg=part.reduce((a,b)=>a+b,0)/period,sd=Math.sqrt(part.reduce((s,v)=>s+(v-avg)**2,0)/period);middle[i]=avg;upper[i]=avg+2*sd;lower[i]=avg-2*sd}return{middle,upper,lower}}

function decisionClass(value){return value==="분할매수 후보"?"buy":value==="보류"?"hold":"watch"}
function renderCard(stock, index) {
  const card=document.createElement("article"); card.className="coin-card stock-card clickable-card"; card.tabIndex=0; card.setAttribute("role","button");
  card.innerHTML=`<div class="coin-top"><div><span class="rank">#${index+1}</span><h3>${escapeHTML(stock.name)}</h3><p class="ticker">${escapeHTML(stock.symbol)} · ${currency(stock.price)} <span class="price-change ${Number(stock.return_1d)>=0?"up":"down"}">${pct(stock.return_1d)}</span></p></div><span class="decision ${decisionClass(stock.decision)}">${escapeHTML(stock.decision)}</span></div><div class="coin-score"><strong>${stock.score}</strong><span>점</span><div class="score-bar"><i style="width:${stock.score}%"></i></div></div><canvas height="58"></canvas><div class="coin-metrics">${metric("일간",pct(stock.return_1d))}${metric("RSI",fmt(stock.rsi,1))}${metric("MACD",fmt(stock.macd_histogram,3))}${metric("7일",pct(stock.return_7d))}${metric("30일",pct(stock.return_30d))}${metric("거래량",stock.volume_ratio==null?"—":`${fmt(stock.volume_ratio,2)}×`)}${metric("변동성",pct(stock.volatility))}</div><div class="coin-copy"><h4>선정 근거</h4><ul>${(stock.reasons||[]).slice(0,4).map(x=>`<li>${escapeHTML(x)}</li>`).join("")}</ul><h4 class="risk-title">위험 확인</h4><ul>${(stock.risks?.length?stock.risks:["뚜렷한 정량 위험 신호 없음"]).slice(0,3).map(x=>`<li>${escapeHTML(x)}</li>`).join("")}</ul></div><span class="detail-hint">상세차트 보기 ↗</span>`;
  const open=()=>openChart(stock); card.addEventListener("click",open); card.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();open()}});
  requestAnimationFrame(()=>drawLine($("canvas",card),stock.sparkline,stock.return_30d>=0?"#31d8c5":"#ff6b78")); return card;
}

function renderRanking(stock){return `<button class="stock-rank-row" data-symbol="${escapeHTML(stock.symbol)}"><span class="stock-rank-number">#${stock.rank}</span><span class="stock-rank-name"><strong>${escapeHTML(stock.name)}</strong><small>${escapeHTML(stock.symbol)} · ${currency(stock.price)} <i class="price-change ${Number(stock.return_1d)>=0?"up":"down"}">${pct(stock.return_1d)}</i></small></span><span class="stock-rank-metric"><span>RSI</span><strong>${fmt(stock.rsi,1)}</strong></span><span class="stock-rank-metric"><span>MACD</span><strong>${fmt(stock.macd_histogram,3)}</strong></span><span class="stock-rank-metric"><span>30일</span><strong>${pct(stock.return_30d)}</strong></span><strong class="stock-rank-score">${stock.score}</strong></button>`}

function renderSearch(stock){
  $("#stockSearchResult").innerHTML=`<article class="search-result-card stock-search-card"><div class="search-result-top"><div><span class="search-rank">종합 #${stock.rank}</span><h3>${escapeHTML(stock.name)} <small>${escapeHTML(stock.symbol)}</small></h3><p>${currency(stock.price)} <span class="price-change ${Number(stock.return_1d)>=0?"up":"down"}">${pct(stock.return_1d)}</span></p></div><div class="search-score"><span class="decision ${decisionClass(stock.decision)}">${escapeHTML(stock.decision)}</span><strong>${stock.score}</strong><small>/ 100점</small></div></div><div class="search-score-track"><i style="width:${stock.score}%"></i></div><div class="search-metrics">${metric("일간 등락",pct(stock.return_1d))}${metric("RSI(14)",fmt(stock.rsi,1))}${metric("MACD 히스토그램",fmt(stock.macd_histogram,4))}${metric("EMA 추세",stock.ema20>stock.ema50?"정배열":"혼조·역배열")}${metric("7일",pct(stock.return_7d))}${metric("30일",pct(stock.return_30d))}${metric("거래량 비율",stock.volume_ratio==null?"—":`${fmt(stock.volume_ratio,2)}×`)}</div><button class="search-chart-button" type="button">캔들 차트·전체 지표 보기 ↗</button><div class="search-context"><section><h4>점수 상승 근거</h4><ul>${(stock.reasons||[]).map(x=>`<li>${escapeHTML(x)}</li>`).join("")}</ul></section><section class="search-risks"><h4>감점·확인할 위험</h4><ul>${(stock.risks?.length?stock.risks:["뚜렷한 정량 위험 신호 없음"]).map(x=>`<li>${escapeHTML(x)}</li>`).join("")}</ul></section></div></article>`;
  $("#stockSearchResult button").addEventListener("click",()=>openChart(stock));
}

function portfolioCurrency(value, code) { return code === "USD" ? `$${fmt(value,2)}` : `₩${fmt(value,0)}`; }
function brokerLabel(value) { return value === "toss" ? "토스증권" : "한국투자증권"; }
function renderPortfolio(data) {
  const panel=$("#accountPortfolio"); if(!panel)return;
  if(!data){panel.hidden=true;return}
  const positions=(data.positions||[]).filter(item=>item.market===market).sort((left,right)=>Number(right.evaluation_amount||0)-Number(left.evaluation_amount||0)), label=market==="us"?"미국":"국내", currencyCode=market==="us"?"USD":"KRW";
  const evaluation=positions.reduce((sum,item)=>sum+Number(item.evaluation_amount||0),0), profit=positions.reduce((sum,item)=>sum+Number(item.profit_loss||0),0), cost=evaluation-profit, rate=cost?profit/cost*100:0;
  const brokers=[...new Set(positions.map(item=>item.broker||"kis"))];
  const changes=data.changes||{}, changeItems=[];
  for(const item of changes.added||[])if(item.market===market)changeItems.push(`<span class="portfolio-change added">${brokerLabel(item.broker)} 신규 ${escapeHTML(item.name||item.symbol)}</span>`);
  for(const item of changes.removed||[])if(item.market===market)changeItems.push(`<span class="portfolio-change removed">${brokerLabel(item.broker)} 전량매도 ${escapeHTML(item.name||item.symbol)}</span>`);
  for(const item of changes.quantity_changes||[])if(item.market===market)changeItems.push(`<span class="portfolio-change quantity">${brokerLabel(item.broker)} ${escapeHTML(item.name||item.symbol)} ${Number(item.difference)>=0?"+":""}${fmt(item.difference,4)}주</span>`);
  const comparison=changes.baseline_at?`${escapeHTML(new Date(changes.baseline_at).toLocaleString("ko-KR"))} 대비`:`첫 계좌 기록`;
  const tossConnection=data.connections?.toss||{}, tossReady=Boolean(tossConnection.configured&&tossConnection.ok);
  const tossNote=tossConnection.source==="local_pc"
    ? `<p class="portfolio-connect-note"><b>토스증권 집 PC 동기화 ${tossReady?"완료":"대기"}</b>${tossConnection.synced_at?` · ${escapeHTML(new Date(tossConnection.synced_at).toLocaleString("ko-KR"))}`:" · PC 동기화 프로그램을 실행해 주세요."} · 매일 07:10 자동 동기화 · <a href="downloads/toss-browser-sync.zip" download>버튼 연결파일</a></p>`
    : !tossReady?`<p class="portfolio-connect-note"><b>토스증권 연결 대기</b> · <a href="https://corp.tossinvest.com/ko/open-api" target="_blank" rel="noopener">공식 Open API 키 발급</a> 후 저장소 Secret을 등록하면 이 목록에 자동 합산됩니다.</p>`:"";
  panel.hidden=false;
  panel.innerHTML=`<div class="section-head portfolio-section-head"><div><span class="eyebrow">MY STOCK ACCOUNTS</span><h2>내 ${label}주식 통합 보유현황</h2></div><div class="portfolio-head-actions"><p>${escapeHTML(new Date(data.synced_at).toLocaleString("ko-KR"))} 기준</p><button type="button" class="secondary-button" id="portfolioRefresh" ${manualRefreshRunning?"disabled":""}>${manualRefreshRunning?"갱신 중…":"수량·가격 갱신"}</button><button type="button" class="secondary-button" id="portfolioDownloadExcel">일별 기록 엑셀 다운로드</button></div></div><div class="portfolio-summary">${metric("표시 증권사",`${brokers.length}개`)}${metric("평가금액",portfolioCurrency(evaluation,currencyCode))}${metric("평가손익",`<span class="price-change ${profit>=0?"up":"down"}">${portfolioCurrency(profit,currencyCode)}</span>`)}${metric("수익률",`<span class="price-change ${rate>=0?"up":"down"}">${pct(rate)}</span>`)}</div><div class="portfolio-changes"><b>${comparison}</b>${changeItems.length?changeItems.join(""):`<span class="portfolio-change unchanged">보유수량 변동 없음</span>`}</div>${positions.length?`<div class="portfolio-list">${positions.map((item,index)=>`<div class="portfolio-row clickable-portfolio" role="button" tabindex="0" data-position="${index}" aria-label="${escapeHTML(item.name)} 상세차트 열기"><span><small class="broker-badge ${item.broker==="toss"?"toss":"kis"}">${brokerLabel(item.broker)}</small><strong>${escapeHTML(item.name)}</strong><small>${escapeHTML(item.symbol)} · ${fmt(item.quantity,4)}주</small></span><span><small>현재가</small><strong>${portfolioCurrency(item.current_price,item.currency)}</strong></span><span><small>일간 등락률</small><strong class="price-change ${item.daily_change_rate==null?"":Number(item.daily_change_rate)>=0?"up":"down"}">${pct(item.daily_change_rate)}</strong></span><span><small>평가금액</small><strong>${portfolioCurrency(item.evaluation_amount,item.currency)}</strong></span><span><small>평가손익</small><strong class="price-change ${Number(item.profit_loss)>=0?"up":"down"}">${portfolioCurrency(item.profit_loss,item.currency)} · ${pct(item.profit_rate)}</strong></span></div>`).join("")}</div>`:`<p class="portfolio-empty">조회된 ${label}주식 보유잔고가 없습니다.</p>`}${tossNote}${(data.warnings||[]).length?`<p class="portfolio-warning">계좌 조회 경고: ${escapeHTML(data.warnings.join(" · "))}</p>`:""}<p id="portfolioRefreshStatus" class="portfolio-export-status" aria-live="polite"></p><p id="portfolioExportStatus" class="portfolio-export-status" aria-live="polite"></p>`;
  $("#portfolioRefresh")?.addEventListener("click", () => refreshPortfolio(data));
  panel.querySelectorAll("[data-position]").forEach(row => {
    const open = () => { const item = positions[Number(row.dataset.position)]; openChart({ ...(report?.rankings||[]).find(stock=>stock.symbol===item.symbol), ...item, price:item.current_price, return_1d:item.daily_change_rate }); };
    row.addEventListener("click", open); row.addEventListener("keydown", event => { if(event.key==="Enter"||event.key===" "){event.preventDefault();open();} });
  });
  $("#portfolioDownloadExcel")?.addEventListener("click",async event=>{const button=event.currentTarget,status=$("#portfolioExportStatus"),original=button.textContent;button.disabled=true;button.textContent="엑셀 생성 중…";status.textContent="";status.classList.remove("error");try{const result=await window.PortfolioExcel.download(data);status.textContent=`최근 ${result.days}일 · ${result.records}개 종목 기록을 다운로드했습니다.${result.truncated?" 오래된 일부 종목 기록은 5,000행 제한으로 제외됐습니다.":""}`;}catch(error){status.textContent=error.message;status.classList.add("error");}finally{button.disabled=false;button.textContent=original;}});
}

async function refreshPortfolio(previous) {
  if (manualRefreshRunning) return; manualRefreshRunning = true;
  const local = previous.connections?.toss?.source === "local_pc";
  const before = previous.connections?.toss?.synced_at;
  const status = message => { const element = $("#portfolioRefreshStatus"); if(element)element.textContent = message; };
  $("#portfolioRefresh").disabled = true; $("#portfolioRefresh").textContent = "갱신 중…";
  try {
    if (local) window.location.href = "coin-toss-sync://run";
    if (local) {
      status("집 PC 동기화 프로그램의 실행을 허용해 주세요. 완료된 수량·가격을 기다리고 있습니다.");
      const until = Date.now() + 90000; let complete = false;
      while (Date.now() < until) {
        await new Promise(resolve=>setTimeout(resolve,3000));
        if (!window.CoinAuth?.user) throw new Error("로그인이 필요합니다.");
        const result = await window.CoinAuth.tossSyncStatus();
        if (result.synced_at && (!before || Date.parse(result.synced_at) > Date.parse(before))) { complete = true; break; }
      }
      if (!complete) throw new Error("PC 동기화 완료를 확인하지 못했습니다. 집 PC에서 아래 ‘버튼 연결파일’을 한 번 실행하고 다시 눌러 주세요. 기존 자료는 유지됩니다.");
    }
    await window.CoinAuth.syncBrokerageHoldings({force:true});
    status("보유수량·가격 갱신 완료");
  } catch (error) { status(error.message); }
  finally { manualRefreshRunning = false; const button=$("#portfolioRefresh");if(button){button.disabled=false;button.textContent="수량·가격 갱신";} }
}

function parseManualHoldings(value) {
  return String(value || "").split(/\r?\n/).map(line => line.trim()).filter(Boolean).map(line => {
    const [symbol, ...nameParts] = line.split("|");
    return { symbol: symbol.trim().toUpperCase(), name: nameParts.join("|").trim() || symbol.trim().toUpperCase() };
  }).filter(item => item.symbol);
}

function renderManualHoldings(profile, signedIn = Boolean(window.CoinAuth?.user)) {
  const panel = $("#manualPortfolio"); if (!panel) return;
  if (!signedIn) { panel.hidden = true; panel.innerHTML = ""; return; }
  const key = market === "us" ? "holdings_us" : "holdings_kr";
  const items = parseManualHoldings(profile?.[key]);
  const label = market === "us" ? "미국" : "국내";
  panel.hidden = false;
  panel.innerHTML = `<div class="section-head"><div><span class="eyebrow">MANUAL HOLDINGS</span><h2>내 ${label}주식 수동 등록</h2></div><button type="button" class="secondary-button" id="manualHoldingsEdit">${items.length ? "수정" : "종목 등록"}</button></div>${items.length ? `<div class="manual-holdings-list">${items.map((item,index) => `<span class="clickable-portfolio" role="button" tabindex="0" data-manual-position="${index}"><strong>${escapeHTML(item.name)}</strong><small>${escapeHTML(item.symbol)} · 상세차트 ↗</small></span>`).join("")}</div>` : `<p class="portfolio-empty">직접 등록한 종목이 없습니다. 종목 등록을 눌러 ${label} 보유주식을 추가할 수 있습니다.</p>`}`;
  panel.querySelectorAll("[data-manual-position]").forEach(row=>{
    const open=()=>{const item=items[Number(row.dataset.manualPosition)];openChart({...item,...(report?.rankings||[]).find(stock=>stock.symbol===item.symbol)});};
    row.addEventListener("click",open);row.addEventListener("keydown",event=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();open();}});
  });
  $("#manualHoldingsEdit")?.addEventListener("click", () => { renderStockSettings(); settingsDialog.showModal(); });
}

function showSetup(){
  const panel=$("#setupPanel"); panel.hidden=false; panel.innerHTML=`<h2>주식 데이터 연결을 위한 최초 설정이 필요합니다</h2><p>API 키는 대시보드에 저장하지 않으며 GitHub Actions에서만 사용합니다. 주문 기능은 연결하지 않습니다.</p><ol><li><a href="https://apiportal.koreainvestment.com/" target="_blank" rel="noopener">한국투자증권 Open API</a>에서 API 서비스를 신청합니다.</li><li>GitHub 저장소의 <b>Settings → Secrets and variables → Actions</b>로 이동합니다.</li><li><code>KIS_APP_KEY</code>와 <code>KIS_APP_SECRET</code>을 각각 Repository secret으로 등록합니다.</li><li>Actions에서 <b>Analyze, email and deploy → Run workflow</b>를 한 번 실행합니다.</li></ol>`;
  if(report?.configured&&report?.selected_sectors?.length){panel.innerHTML=`<h2>선택한 종목의 데이터를 수집하지 못했습니다</h2><p>한국투자증권 API는 연결됐지만 선택 섹터의 시세가 비어 있습니다. 아래 데이터 상태에서 종목별 오류를 확인해 주세요.</p>`;}
  else if(report?.configured){panel.innerHTML=`<h2>맞춤 수집 범위를 선택해 주세요</h2><p>한국투자증권 API는 연결됐습니다. 위의 <b>맞춤 수집 설정</b>에서 섹터를 선택하고 <code>STOCK_SECTORS</code> Secret에 저장하면 해당 그룹만 분석합니다. 보유종목은 추천 순위가 아니라 맞춤 뉴스 수집에만 사용합니다.</p>`;}
}

function render(data){
  report=data; $("#generatedAt").textContent=data.generated_at_kst||"—"; $("#stockStatus").textContent=data.status==="정상"?"데이터 정상":data.status; $("#stockStatus").className=`stock-status ${data.status==="정상"?"ok":"error"}`;
  if(!data.configured||!data.rankings?.length){showSetup(); const selected=Boolean(data.selected_sectors?.length); $("#marketTitle").textContent=!data.configured?`${data.market_name} API 설정 필요`:selected?`${data.market_name} 데이터 수집 실패`:`${data.market_name} 수집범위 선택 필요`; $("#marketSummary").textContent=(data.warnings||[])[0]||"주식 데이터를 아직 수집하지 못했습니다."; $("#recommendations").innerHTML=`<div class="error-card">${!data.configured?"API 설정 후 자동으로 추천 순위가 표시됩니다.":selected?"선택 종목의 수집 오류를 데이터 상태에서 확인해 주세요.":"맞춤 수집 설정 후 선택한 섹터의 추천 순위가 표시됩니다."}</div>`; $("#rankingList").innerHTML='<p class="search-empty">수집된 순위가 없습니다.</p>'; $("#warnings").innerHTML=(data.warnings||[]).map(x=>`<p>• ${escapeHTML(x)}</p>`).join(""); return;}
  const benchmark=data.benchmark; $("#marketTitle").textContent=`${data.regime} 국면`; $("#marketSummary").textContent=data.regime==="상승"?"대표지수 추세가 우호적입니다. 종목별 과열 여부를 함께 확인하세요.":data.regime==="하락"?"대표지수가 약세입니다. 신규 매수보다 위험 관리를 우선합니다.":"대표지수 방향이 혼조입니다. 강한 종목만 선별적으로 관찰합니다.";
  $("#marketScore").textContent=data.market_score; $("#scoreRing").style.background=`conic-gradient(${data.regime==="상승"?"var(--green)":data.regime==="하락"?"var(--red)":"var(--blue)"} ${data.market_score*3.6}deg,var(--line) 0)`; $("#marketReasons").innerHTML=`<p>${benchmark.price>benchmark.ema20&&benchmark.ema20>benchmark.ema50?"대표지수 EMA 정배열":"대표지수 EMA 혼조·역배열"}</p><p>30일 수익률 ${pct(benchmark.return_30d)}</p><p>MACD ${benchmark.macd_histogram>0?"상승":"약세"} 모멘텀</p>`;
  $("#benchmarkSymbol").textContent=`${benchmark.name} · ${benchmark.symbol}`; $("#benchmarkPrice").innerHTML=`${currency(benchmark.price)} <span class="price-change ${Number(benchmark.return_1d)>=0?"up":"down"}">${pct(benchmark.return_1d)}</span>`; $("#benchmarkMetrics").innerHTML=metric("일간",pct(benchmark.return_1d))+metric("RSI",fmt(benchmark.rsi,1))+metric("30일",pct(benchmark.return_30d))+metric("EMA20",currency(benchmark.ema20))+metric("EMA50",currency(benchmark.ema50)); drawLine($("#benchmarkChart"),benchmark.sparkline,"#4d8dff"); const openBenchmark=()=>openChart(benchmark); $("#benchmarkCard").onclick=openBenchmark; $("#benchmarkCard").onkeydown=e=>{if(e.key==="Enter"||e.key===" ")openBenchmark()};
  $("#screenedCount").textContent=data.screened; const cards=$("#recommendations"); cards.innerHTML=""; data.recommendations.forEach((stock,index)=>cards.appendChild(renderCard(stock,index)));
  $("#rankingList").innerHTML=data.rankings.map(renderRanking).join(""); $("#rankingList").querySelectorAll("[data-symbol]").forEach(button=>button.addEventListener("click",()=>openChart(data.rankings.find(x=>x.symbol===button.dataset.symbol))));
  $("#stockSearchOptions").innerHTML=data.rankings.map(x=>`<option value="${escapeHTML(x.symbol)}">${escapeHTML(x.name)}</option>`).join("");
  $("#methodologyIntro").textContent=data.methodology.intro; $("#methodologyItems").innerHTML=data.methodology.items.map(x=>`<li>${escapeHTML(x)}</li>`).join(""); $("#methodologyDecision").textContent=data.methodology.decisions;
  $("#warnings").innerHTML=data.warnings.length?data.warnings.map(x=>`<p>• ${escapeHTML(x)}</p>`).join(""):'<p class="ok">모든 대상 종목의 핵심 데이터가 정상 수집됐습니다.</p>'; $("#sources").innerHTML=(data.sources||[]).map(x=>`<a href="${x.url}" target="_blank" rel="noopener">${escapeHTML(x.name)}</a>`).join(""); $("#disclaimer").textContent=data.disclaimer;
}

function openChart(stock) {
  detailStock=stock;detailDays=30;detailHistory=[];detailPlot=null;
  $("#chartTitle").textContent=`${stock.name || stock.symbol} 상세차트`;
  $("#chartPrice").innerHTML=`조회가 ${currency(stock.price)} · <span class="price-change ${stock.return_1d==null?"":Number(stock.return_1d)>=0?"up":"down"}">일간 ${pct(stock.return_1d)}</span>`;
  $("#periodTabs").querySelectorAll("button").forEach(x=>x.classList.toggle("active",x.dataset.days==="30"));
  if(!$("#stockChartDialog").open)$("#stockChartDialog").showModal(); selectStockInterval("1d");
}
async function selectStockInterval(interval) {
  const request=++detailRequest, stock=detailStock;detailInterval=interval;detailHistory=[];detailPlot=null;
  $("#chartTooltip").hidden=true;$("#detailChart").hidden=true;$("#detailStats").innerHTML="";
  $("#candleTabs").querySelectorAll("button").forEach(button=>button.classList.toggle("active",button.dataset.interval===interval));
  $("#chartSymbol").textContent=`${stock.symbol} · ${window.ChartData.labels[interval]}`;
  $("#chartDataStatus").textContent=`${window.ChartData.labels[interval]} 불러오는 중…`;
  try {
    const data=await window.ChartData.loadStock(stock,market,interval);if(request!==detailRequest)return;
    detailHistory=data.rows;$("#detailChart").hidden=false;
    $("#chartDataStatus").textContent=`${data.source} · ${data.rows.length}개 ${window.ChartData.labels[interval]} · 시세 지연 가능 · 진행 중인 봉은 미확정`;
    scheduleChart();
  } catch(error) {
    if(request!==detailRequest)return;
    if((interval==="1d"||interval==="1w")&&stock.history?.length){detailHistory=window.ChartData.aggregate(stock.history.map(row=>({...row,timestamp:Date.parse(row.date),session:row.date})),interval);$("#detailChart").hidden=false;$("#chartDataStatus").textContent=`저장된 분석 시세 · ${window.ChartData.labels[interval]} · 최신 조회 실패: ${error.message}`;scheduleChart();}
    else $("#chartDataStatus").textContent=error.message;
  }
}
$("#candleTabs").addEventListener("click",event=>{const button=event.target.closest("button");if(button)selectStockInterval(button.dataset.interval)});
function scheduleChart(hover=null){if(detailFrame!=null)return;detailFrame=requestAnimationFrame(()=>{detailFrame=null;drawChart(hover)})}
function drawChart(hover=null){
  if(!detailHistory.length)return; const all=detailHistory,rows=window.ChartData.visible(all,detailDays),start=all.length-rows.length,prices=rows.map(x=>+x.price),opens=rows.map(x=>+x.open||+x.price),highs=rows.map(x=>+x.high||+x.price),lows=rows.map(x=>+x.low||+x.price),volumes=rows.map(x=>+x.volume||0),full=all.map(x=>+x.price),e20=ema(full,20).slice(start),e50=ema(full,50).slice(start),bb=bands(full),upper=bb.upper.slice(start),lower=bb.lower.slice(start),middle=bb.middle.slice(start),rs=rsi(full).slice(start),mc=macd(full),ml=mc.line.slice(start),ms=mc.signal.slice(start),mh=mc.hist.slice(start);
  const canvas=$("#detailChart"),ratio=devicePixelRatio||1,rect=canvas.getBoundingClientRect(),width=Math.max(280,rect.width),height=Math.max(520,rect.height);canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);const ctx=canvas.getContext("2d");ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,width,height);const pad={left:64,right:18,top:20,bottom:22},priceBottom=height*.47,volTop=priceBottom+8,volBottom=height*.57,macdTop=height*.64,macdBottom=height*.77,rsiTop=height*.82,rsiBottom=height-pad.bottom,plotWidth=width-pad.left-pad.right,rangeValues=[...highs,...lows,...upper.filter(Boolean),...lower.filter(Boolean)],lo=Math.min(...rangeValues),hi=Math.max(...rangeValues),margin=(hi-lo||1)*.08,min=lo-margin,max=hi+margin,spread=max-min||1,space=plotWidth/rows.length,x=i=>pad.left+(i+.5)*space,y=v=>pad.top+(max-v)/spread*(priceBottom-pad.top);
  ctx.font="10px system-ui";ctx.textAlign="right";ctx.textBaseline="middle";for(let i=0;i<=4;i++){const gy=pad.top+i*(priceBottom-pad.top)/4;ctx.beginPath();ctx.moveTo(pad.left,gy);ctx.lineTo(width-pad.right,gy);ctx.strokeStyle="rgba(143,162,189,.13)";ctx.stroke();ctx.fillStyle="#7f93af";ctx.fillText(fmt(max-i*spread/4,2),pad.left-7,gy)}
  const plot=(values,color,map=y)=>{ctx.beginPath();let begun=false;values.forEach((v,i)=>{if(v==null)return;if(begun)ctx.lineTo(x(i),map(v));else{ctx.moveTo(x(i),map(v));begun=true}});ctx.strokeStyle=color;ctx.lineWidth=1.2;ctx.stroke()};plot(upper,"#a98bff");plot(lower,"#a98bff");plot(middle,"rgba(169,139,255,.45)");plot(e20,"#31d8c5");plot(e50,"#ffbf47");
  rows.forEach((_,i)=>{const up=prices[i]>=opens[i],color=up?"#ff6b78":"#4d8dff",cx=x(i),oy=y(opens[i]),cy=y(prices[i]);ctx.beginPath();ctx.moveTo(cx,y(highs[i]));ctx.lineTo(cx,y(lows[i]));ctx.strokeStyle=color;ctx.stroke();ctx.fillStyle=color;ctx.fillRect(cx-Math.max(1,space*.28),Math.min(oy,cy),Math.max(2,space*.56),Math.max(1.5,Math.abs(cy-oy)))});
  const vmax=Math.max(...volumes,1);rows.forEach((_,i)=>{ctx.fillStyle=prices[i]>=opens[i]?"rgba(255,107,120,.35)":"rgba(77,141,255,.35)";const h=volumes[i]/vmax*(volBottom-volTop);ctx.fillRect(x(i)-Math.max(1,space*.28),volBottom-h,Math.max(2,space*.56),h)});
  const macdRange=Math.max(...ml.map(Math.abs),...ms.map(Math.abs),...mh.map(Math.abs),1e-8),ym=v=>(macdTop+macdBottom)/2-v/macdRange*(macdBottom-macdTop)/2;ctx.beginPath();ctx.moveTo(pad.left,ym(0));ctx.lineTo(width-pad.right,ym(0));ctx.strokeStyle="rgba(143,162,189,.2)";ctx.stroke();mh.forEach((v,i)=>{ctx.fillStyle=v>=0?"rgba(49,216,197,.55)":"rgba(255,107,120,.55)";ctx.fillRect(x(i)-Math.max(1,space*.25),Math.min(ym(v),ym(0)),Math.max(2,space*.5),Math.max(1,Math.abs(ym(v)-ym(0))))});ctx.textAlign="right";ctx.textBaseline="middle";ctx.fillStyle="#7f93af";[-macdRange,0,macdRange].forEach(value=>ctx.fillText(fmt(value,4),pad.left-7,ym(value)));plot(ml,"#4d8dff",ym);plot(ms,"#ffbf47",ym);
  const yr=v=>rsiTop+(100-v)/100*(rsiBottom-rsiTop);[0,30,50,70,100].forEach(v=>{ctx.beginPath();ctx.moveTo(pad.left,yr(v));ctx.lineTo(width-pad.right,yr(v));ctx.strokeStyle="rgba(143,162,189,.15)";ctx.stroke();ctx.fillStyle="#7f93af";ctx.textAlign="right";ctx.textBaseline="middle";ctx.fillText(String(v),pad.left-7,yr(v))});plot(rs,"#d481ff",yr);
  ctx.textAlign="left";ctx.textBaseline="top";ctx.fillStyle="#a8b8ce";ctx.fillText("MACD(12,26,9)",pad.left+5,macdTop+3);ctx.fillText("RSI(14)",pad.left+5,rsiTop+3);
  [0,Math.floor((rows.length-1)/2),rows.length-1].forEach((index,i)=>{ctx.textAlign=i===0?"left":i===2?"right":"center";ctx.fillText(rows[index].date,x(index),volBottom+5)});
  detailPlot={rows,pad,width,rsi:rs,macd:ml,signal:ms,hist:mh};$("#detailStats").innerHTML=metric("EMA20",currency(e20.at(-1)))+metric("EMA50",currency(e50.at(-1)))+metric("RSI",fmt(rs.at(-1),1))+metric("MACD",fmt(ml.at(-1),4))+metric("Signal",fmt(ms.at(-1),4))+metric("Histogram",fmt(mh.at(-1),4));
  if(hover!=null&&rows[hover]){const cx=x(hover);ctx.beginPath();ctx.moveTo(cx,pad.top);ctx.lineTo(cx,rsiBottom);ctx.strokeStyle="rgba(237,244,255,.3)";ctx.setLineDash([3,3]);ctx.stroke();ctx.setLineDash([])}
}

$("#stockSearchForm").addEventListener("submit",event=>{event.preventDefault();const raw=$("#stockSearchInput").value.trim(),normalize=value=>String(value||"").toLowerCase().replace(/\s+/g,"");const query=normalize(raw);if(!query)return;if(!report?.rankings?.length){$("#stockSearchResult").innerHTML='<p class="search-empty">검색 데이터를 준비하지 못했습니다. 잠시 후 새로고침해 주세요.</p>';return}const stock=report.rankings.find(x=>normalize(x.symbol)===query||normalize(x.name)===query)||report.rankings.find(x=>normalize(x.symbol).includes(query)||normalize(x.name).includes(query));if(stock)renderSearch(stock);else $("#stockSearchResult").innerHTML=`<p class="search-empty"><strong>${escapeHTML(raw)}</strong>을 분석 대상에서 찾지 못했습니다.</p>`});
$("#chartClose").addEventListener("click",()=>$("#stockChartDialog").close());$("#stockChartDialog").addEventListener("click",e=>{if(e.target===e.currentTarget)e.currentTarget.close()});$("#periodTabs").addEventListener("click",e=>{const b=e.target.closest("button");if(!b)return;detailDays=b.dataset.days==="all"?"all":+b.dataset.days;$("#periodTabs").querySelectorAll("button").forEach(x=>x.classList.toggle("active",x===b));scheduleChart()});
$("#detailChart").addEventListener("pointermove",event=>{if(!detailPlot)return;const rect=event.currentTarget.getBoundingClientRect(),local=event.clientX-rect.left,index=Math.max(0,Math.min(detailPlot.rows.length-1,Math.round((local-detailPlot.pad.left)/(detailPlot.width-detailPlot.pad.left-detailPlot.pad.right)*(detailPlot.rows.length-1)))),row=detailPlot.rows[index],tip=$("#chartTooltip");scheduleChart(index);tip.innerHTML=`<strong>${row.date}</strong><span>시가 ${currency(+row.open)} · 고가 ${currency(+row.high)}</span><span>저가 ${currency(+row.low)} · 종가 ${currency(+row.price)}</span><span>거래량 ${fmt(+row.volume,0)} · RSI ${fmt(detailPlot.rsi[index],1)}</span><span>MACD ${fmt(detailPlot.macd[index],4)} · Signal ${fmt(detailPlot.signal[index],4)}</span>`;tip.hidden=false;tip.style.left=`${Math.max(8,Math.min(rect.width-234,local+13))}px`;tip.style.top="18px"});$("#detailChart").addEventListener("pointerleave",()=>{$("#chartTooltip").hidden=true;scheduleChart()});window.addEventListener("resize",()=>{if($("#stockChartDialog").open)scheduleChart()});

const settingsDialog=$("#stockSettingsDialog"), holdingsKey=`stock-holdings-${market}-v1`, sectorsKey="stock-sectors-v1", emailKey="stock-email-recipients-v1";
function selectedSectorIds(){return [...$("#stockSectorOptions").querySelectorAll("input:checked")].map(input=>input.value)}
function setSettingsStatus(message,error=false){const node=$("#stockSettingsStatus");node.textContent=message;node.classList.toggle("error",error)}
function validEmailList(value){const addresses=value.split(/[,;\n]+/).map(item=>item.trim()).filter(Boolean);return addresses.length>0&&addresses.every(item=>/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(item))}
function renderStockSettings(){
  const options=report?.sector_options?.length?report.sector_options:sectorFallback;
  const member=window.CoinAuth?.profile, stored=localStorage.getItem(sectorsKey), selected=member?.sector_ids||(stored!==null?stored.split(",").filter(Boolean):(report?.selected_sectors||[]));
  $("#stockSectorOptions").innerHTML=options.map(item=>`<label><input type="checkbox" value="${escapeHTML(item.id)}" ${selected.includes(item.id)?"checked":""}><span>${escapeHTML(item.label)}</span></label>`).join("");
  $("#stockHoldings").value=(member?.[market==="us"?"holdings_us":"holdings_kr"]??localStorage.getItem(holdingsKey))||"";
  $("#stockEmailRecipients").value=(member?.stock_email??localStorage.getItem(emailKey))||"";
  $("#saveStockSettings").disabled=!window.CoinAuth?.user;
  setSettingsStatus(window.CoinAuth?.user?"저장하면 GitHub Actions 설정 없이 다음 자동 분석과 오전 7시 30분 메일부터 적용됩니다.":"자동 적용하려면 먼저 로그인해 주세요.",!window.CoinAuth?.user);
}
$("#stockSettingsOpen").addEventListener("click",()=>{renderStockSettings();settingsDialog.showModal()});
$("#stockSettingsClose").addEventListener("click",()=>settingsDialog.close());
settingsDialog.addEventListener("click",event=>{if(event.target===settingsDialog)settingsDialog.close()});
$("#saveStockSettings").addEventListener("click",async event=>{if(!window.CoinAuth?.user){setSettingsStatus("자동 적용하려면 먼저 로그인해 주세요.",true);return}const holdings=$("#stockHoldings").value.trim(),sector_ids=selectedSectorIds(),stock_email=$("#stockEmailRecipients").value.trim();if(!validEmailList(stock_email)){setSettingsStatus("수신 메일 주소를 올바르게 입력해 주세요. 여러 주소는 쉼표나 줄바꿈으로 구분할 수 있습니다.",true);return}const button=event.currentTarget,original=button.textContent;button.disabled=true;button.textContent="저장 중…";try{const saved=await window.CoinAuth.savePreferences({[market==="us"?"holdings_us":"holdings_kr"]:holdings,sector_ids,stock_email});renderManualHoldings(saved,true);setSettingsStatus("저장 완료. GitHub Actions 설정 없이 다음 자동 분석과 오전 7시 30분 메일부터 적용됩니다.")}catch(error){setSettingsStatus(`회원 설정 저장 실패: ${error.message}`,true)}finally{button.disabled=false;button.textContent=original}});
document.addEventListener("keydown",event=>{if(event.key==="Escape"&&settingsDialog.open)settingsDialog.close()});
window.addEventListener("coin-auth-change",event=>{renderManualHoldings(event.detail?.profile,Boolean(event.detail?.user));if(!event.detail?.user)renderPortfolio(null)});
window.addEventListener("kis-portfolio-sync",event=>renderPortfolio(event.detail));
if(window.CoinAuth?.portfolio)renderPortfolio(window.CoinAuth.portfolio);

fetch(`data/stocks-${market}.json?v=${Date.now()}`).then(response=>{if(!response.ok)throw new Error("주식 분석 파일을 읽지 못했습니다.");return response.json()}).then(render).catch(error=>{$("#stockStatus").textContent="데이터 오류";$("#stockStatus").className="stock-status error";$("#recommendations").innerHTML=`<div class="error-card">${escapeHTML(error.message)}</div>`;showSetup()});

/* Public stock research. Account data never enters these panels or exports. */
(() => {
  'use strict';
  const root = document.querySelector('#stockWorkbench');
  if (!root) return;
  const market = document.body.dataset.stockMarket;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num = value => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value)) ? Number(value) : null;
  const fmt = (value, digits = 1) => num(value) === null ? '—' : new Intl.NumberFormat('ko-KR', {maximumFractionDigits: digits}).format(Number(value));
  const pct = value => num(value) === null ? '—' : `${Number(value) > 0 ? '+' : ''}${fmt(value)}%`;
  const money = value => num(value) === null ? '—' : `${market === 'us' ? '$' : '₩'}${fmt(value, market === 'us' ? 2 : 0)}`;
  const short = value => num(value) === null ? '—' : new Intl.NumberFormat('ko-KR', {notation:'compact',maximumFractionDigits:1}).format(value);
  const tone = value => num(value) === null ? '' : Number(value) >= 0 ? 'wb-up' : 'wb-down';
  const link = (url, title) => /^https:\/\//i.test(url || '') ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(title)}</a>` : esc(title);
  const dateTime = value => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString('ko-KR', {timeZone:'Asia/Seoul',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}) : '시간 미제공';
  let data, openStock, active = 'themes', selectedTheme = '', external = null, externalError = '', externalPromise;
  let favorites = new Set();
  const favoriteKey = `stock-favorites-${market}-v1`;
  try { const saved = JSON.parse(localStorage.getItem(favoriteKey) || '[]'); if (Array.isArray(saved)) favorites = new Set(saved.filter(x => typeof x === 'string')); } catch (_) {}
  window.addEventListener('stock-lookup-update',()=>{
    try{favorites=new Set(JSON.parse(localStorage.getItem(favoriteKey)||'[]'));}catch{}
    if(active==='screener')drawResults();
  });
  const filters = {query:'',sector:'',returnPeriod:'1d',returnMin:'',returnMax:'',rsiMin:'',rsiMax:'',volumeMin:'',average:'',favorites:false,preset:'',sort:'score',direction:'desc'};
  const stocks = () => [...new Map([...(window.StockLookup?.recent() || []),...(data?.rankings || [])].map(row=>[row.symbol,row])).values()];
  const themes = () => data?.theme_board?.themes || [];
  const favorite = stock => `<button type="button" class="wb-star" data-favorite="${esc(stock.symbol)}" aria-label="${esc(stock.name)} 즐겨찾기" aria-pressed="${favorites.has(stock.symbol)}">${favorites.has(stock.symbol) ? '★' : '☆'}</button>`;
  const stockButton = stock => `<button type="button" class="wb-stock-link" data-stock="${esc(stock.symbol)}"><strong>${esc(stock.name || stock.symbol)}</strong><small>${esc(stock.symbol)}</small></button>`;
  const empty = text => `<p class="wb-empty">${esc(text)}</p>`;
  function render(report, onStock) {
    data = report; openStock = onStock;
    root.innerHTML = `<div class="section-head"><div><span class="eyebrow">STOCK RESEARCH DESK</span><h2>시장 탐색</h2></div><p>공개 분석자료 · 계좌정보 제외</p></div>
      <div class="wb-tabs" aria-label="시장 탐색 메뉴">${[['themes','테마·주도주'],['screener','조건검색·즐겨찾기'],['macro','경제일정·지표'],['companies','실적·공시·신규상장']].map(([id,label]) => `<button type="button" data-wb-tab="${id}" aria-pressed="${active === id}">${label}</button>`).join('')}</div>
      <div id="wbPane" class="wb-pane"></div>`;
    drawPane();
    if (!externalPromise) externalPromise = fetch(`data/stock-research.json?v=${Date.now()}`).then(response => {
      if (!response.ok) throw new Error('공개 일정 자료를 불러오지 못했습니다.'); return response.json();
    }).then(result => { external = result; if (['macro','companies'].includes(active)) drawPane(); }).catch(error => { externalError = error.message; if (['macro','companies'].includes(active)) drawPane(); });
  }
  function drawPane() {
    const pane = root.querySelector('#wbPane');
    if (!pane) return;
    if (active === 'themes') drawThemes(pane);
    if (active === 'screener') drawScreener(pane);
    if (active === 'macro') drawMacro(pane);
    if (active === 'companies') drawCompanies(pane);
  }
  function drawThemes(pane) {
    const rows = themes();
    if (!rows.length) { pane.innerHTML = empty('새 분석자료에 테마 데이터가 없습니다. 다음 분석 완료 후 새로고침해 주세요.'); return; }
    if (!rows.some(x => x.id === selectedTheme)) selectedTheme = rows.find(x => x.count)?.id || rows[0].id;
    const selected = rows.find(x => x.id === selectedTheme);
    const valid = rows.filter(x => num(x.return_1d) !== null);
    pane.innerHTML = `<div class="wb-summary"><div><small>관측일</small><strong>${esc(selected.date || '미수집')}</strong></div><div><small>분석 테마</small><strong>${valid.length} / ${rows.length}</strong></div><div><small>상승 / 하락</small><strong>${valid.filter(x => x.return_1d > 0).length} / ${valid.filter(x => x.return_1d < 0).length}</strong></div><div><small>비교 기준</small><strong>${esc(data.theme_board.benchmark || '미수집')}</strong></div></div>
      <p class="wb-note">${esc(data.theme_board.note)}</p>${(data.theme_news_warnings || []).length ? `<details class="wb-health"><summary>테마 뉴스 수집 상태</summary><p>${data.theme_news_warnings.map(esc).join(' · ')}</p></details>` : ''}
      <div class="wb-theme-layout"><div class="wb-scroll"><table class="wb-table"><caption>테마별 일간 강도 · 등락률순</caption><thead><tr><th>테마 / 수집범위</th><th>일간</th><th>기준 ETF 대비</th><th>상승 종목 비율</th><th>추정 거래대금</th></tr></thead><tbody>${rows.map(row => `<tr class="${row.id === selectedTheme ? 'wb-selected' : ''}"><td><button type="button" data-theme="${esc(row.id)}" aria-pressed="${row.id === selectedTheme}">${esc(row.label)}</button><small>${row.count} / ${row.expected_count}종목</small></td><td class="${tone(row.return_1d)}">${pct(row.return_1d)}</td><td class="${tone(row.relative)}">${num(row.relative) === null ? '—' : `${fmt(row.relative)}%p`}</td><td>${fmt(row.breadth)}%<span class="wb-bar"><i style="width:${Math.max(0,Math.min(100,num(row.breadth) || 0))}%"></i></span></td><td>${short(row.estimated_turnover)}<small>${esc(data.currency)} · ${row.turnover_coverage}종목</small></td></tr>`).join('')}</tbody></table></div>
      <aside class="wb-side"><h3>${esc(selected.label)} 주도주</h3><p class="wb-note">같은 관측일 일간 등락률순 · 거래대금 1위 비중 ${num(selected.concentration) === null ? '—' : `${fmt(selected.concentration)}%`}</p>${selected.leaders.length ? selected.leaders.map(stock => `<div class="wb-leader">${stockButton(stock)}<b class="${tone(stock.return_1d)}">${pct(stock.return_1d)}</b></div>`).join('') : empty('비교 가능한 종목 없음')}
      <h3>최근 24시간 관련 뉴스</h3><p class="wb-note">Yahoo Finance RSS · 원문 언어 · 미국·국내 종목 구분</p>${newsHTML((data.theme_board.news || []).filter(x => x.sector_id === selectedTheme))}</aside></div>`;
  }
  function newsHTML(items) {
    return items.length ? `<ul class="wb-news">${items.map(row => `<li>${link(row.url,row.title)}<small>${esc(row.source)} · ${esc(dateTime(row.published_at))} KST · ${esc(row.verification || '원문 확인')}</small></li>`).join('')}</ul>` : empty('수집된 관련 뉴스 없음. 뉴스가 없다는 뜻은 아닙니다.');
  }
  function filteredStocks() {
    const query = filters.query.trim().toLowerCase().replace(/\s/g,'');
    const rows = stocks().filter(row => {
      const s = row.screening || {}, price = num(row.price), rsi = num(row.rsi), vol = num(row.volume_ratio);
      if (query && !`${row.symbol}${row.name}`.toLowerCase().replace(/\s/g,'').includes(query)) return false;
      if (filters.sector && !(row.sector_ids || []).includes(filters.sector)) return false;
      if (filters.favorites && !favorites.has(row.symbol)) return false;
      const selectedReturn = filters.returnPeriod==='1d' ? num(row.return_1d) : num(s[`return_${filters.returnPeriod}`]);
      for (const [input,value,minimum] of [[filters.returnMin,selectedReturn,true],[filters.returnMax,selectedReturn,false],[filters.rsiMin,rsi,true],[filters.rsiMax,rsi,false],[filters.volumeMin,vol,true]]) {
        if (input !== '' && (value === null || (minimum ? value < Number(input) : value > Number(input)))) return false;
      }
      if (filters.average) {
        const [period,position] = filters.average.split(':'); const average = num(s[`sma${period}`]);
        if (price === null || average === null || (position === 'above' ? price <= average : price >= average)) return false;
      }
      if (filters.preset === 'high' && (num(s.drawdown_52w) === null || s.drawdown_52w < -5)) return false;
      if (filters.preset === 'low' && (!(num(s.low_52w)>0) || price===null || price/s.low_52w>1.05)) return false;
      return true;
    });
    const value = row => filters.sort === 'return_21' ? num(row.screening?.return_21) : filters.sort === 'turnover' ? num(row.screening?.estimated_turnover) : num(row[filters.sort]);
    return rows.sort((a,b) => { const x=value(a),y=value(b); if(x===null||y===null)return x===y?String(a.symbol).localeCompare(b.symbol):x===null?1:-1;return (filters.direction==='asc'?x-y:y-x)||String(a.symbol).localeCompare(b.symbol); });
  }
  function drawScreener(pane) {
    pane.innerHTML = `<p class="wb-note">전체 상장종목은 종목 검색에서 찾은 뒤 선택해 분석할 수 있습니다. 아래 조건검색은 정기 분석 및 이 브라우저에서 조회한 종목에 적용합니다.</p><button type="button" data-full-lookup>전체 상장종목에서 찾기</button><div class="wb-presets" aria-label="빠른 조건"><button type="button" data-preset="all">조회된 종목 전체</button><button type="button" data-preset="trend">50일선 위</button><button type="button" data-preset="oversold">RSI 30 이하</button><button type="button" data-preset="high">52주 고점 5% 이내</button><button type="button" data-preset="low">52주 저점 5% 이내</button></div>
      <form id="wbFilterForm" class="wb-filters"><label>종목 검색<input name="query" type="search" value="${esc(filters.query)}" placeholder="종목명 또는 코드"></label><label>테마<select name="sector"><option value="">전체 테마</option>${themes().map(row => `<option value="${esc(row.id)}" ${filters.sector===row.id?'selected':''}>${esc(row.label)}</option>`).join('')}</select></label>
      <label>수익률 기간<select name="returnPeriod">${[['1d','일간'],['5','1주 · 5거래일'],['21','1개월 · 21거래일'],['63','3개월 · 63거래일'],['126','6개월 · 126거래일'],['252','1년 · 252거래일']].map(([v,t])=>`<option value="${v}" ${filters.returnPeriod===v?'selected':''}>${t}</option>`).join('')}</select></label><label>선택기간 수익률 최소 %<input name="returnMin" type="number" step="0.1" value="${esc(filters.returnMin)}"></label><label>선택기간 수익률 최대 %<input name="returnMax" type="number" step="0.1" value="${esc(filters.returnMax)}"></label><label>RSI 최소<input name="rsiMin" type="number" min="0" max="100" step="0.1" value="${esc(filters.rsiMin)}"></label><label>RSI 최대<input name="rsiMax" type="number" min="0" max="100" step="0.1" value="${esc(filters.rsiMax)}"></label><label>거래량 배수 최소<input name="volumeMin" type="number" min="0" step="0.1" value="${esc(filters.volumeMin)}"></label>
      <label>이동평균<select name="average">${[['','제한 없음'],['50:above','50일선 위'],['50:below','50일선 아래'],['200:above','200일선 위'],['200:below','200일선 아래']].map(([v,t])=>`<option value="${v}" ${filters.average===v?'selected':''}>${t}</option>`).join('')}</select></label>
      <label>정렬<select name="sort">${[['score','기술점수'],['return_1d','일간 등락률'],['return_21','21거래일 수익률'],['rsi','RSI'],['turnover','추정 거래대금']].map(([v,t])=>`<option value="${v}" ${filters.sort===v?'selected':''}>${t}</option>`).join('')}</select></label><label>순서<select name="direction"><option value="desc" ${filters.direction==='desc'?'selected':''}>높은 순</option><option value="asc" ${filters.direction==='asc'?'selected':''}>낮은 순</option></select></label><label class="wb-check"><input name="favorites" type="checkbox" ${filters.favorites?'checked':''}>즐겨찾기만</label><button type="submit">조건 적용</button><button type="button" data-export="stocks">검색결과 CSV</button></form>
      <p class="wb-note">현재 조회된 ${stocks().length}종목에 조건을 적용합니다. 즐겨찾기는 이 브라우저에 저장합니다. 52주=최근 252개 일봉 · 1개월=21거래일 · 이력이 부족한 지표는 —로 표시하고 해당 조건에서 제외합니다. 개별 조회 종목의 기술점수는 —이며 자동 추천에 추가하지 않습니다.</p><div id="wbSearchResults" aria-live="polite"></div>`;
    drawResults();
  }
  function drawResults() {
    const target = root.querySelector('#wbSearchResults'); if (!target) return;
    const rows = filteredStocks();
    target.innerHTML = `<p class="wb-result-count">조건에 맞는 종목 ${rows.length}개${filters.preset==='high'?' · 52주 고점 5% 이내':filters.preset==='low'?' · 52주 저점 5% 이내':''}</p>${rows.length ? `<div class="wb-scroll"><table class="wb-table"><thead><tr><th>관심</th><th>종목</th><th>관측일 / 가격</th><th>일간</th><th>21거래일</th><th>RSI</th><th>거래량</th><th>50일선 대비</th><th>52주 고점 대비</th><th>점수</th></tr></thead><tbody>${rows.map(row => `<tr><td>${favorite(row)}</td><td>${stockButton(row)}</td><td>${money(row.price)}<small>${esc(row.screening?.date || row.history?.at(-1)?.date || '미수집')}</small></td><td class="${tone(row.return_1d)}">${pct(row.return_1d)}</td><td class="${tone(row.screening?.return_21)}">${pct(row.screening?.return_21)}</td><td>${fmt(row.rsi)}</td><td>${fmt(row.volume_ratio,2)}×</td><td>${num(row.screening?.sma50) > 0 ? pct((row.price/row.screening.sma50-1)*100) : '—'}</td><td>${pct(row.screening?.drawdown_52w)}</td><td>${fmt(row.score,0)}</td></tr>`).join('')}</tbody></table></div>` : empty('조건에 맞는 수집 종목이 없습니다.')}`;
  }
  function loading(pane) { if (!external) { pane.innerHTML=empty(externalError || '공개 일정 자료를 불러오는 중…'); return true; } return false; }
  function healthHTML(keys) {
    return `<details class="wb-health"><summary>수집 상태·출처 확인</summary>${keys.map(key => {const s=external.sources?.[key]; return s ? `<p>${esc(s.label)} · ${esc(s.status)}${s.cached?' · 이전 성공 수집본':''} · 자료 수집 ${esc(dateTime(s.observed_at))} KST ${link(s.url,'출처')}</p>` : '';}).join('')}<p>분석 생성 ${esc(dateTime(external.generated_at))} KST · 이전 성공 수집본의 수집시각은 갱신하지 않습니다. 외부 자료는 수정·지연될 수 있습니다.</p></details>`;
  }
  function sourceWarning(keys) {
    const sources=keys.map(key=>external.sources?.[key]).filter(s=>s && (s.cached || s.status?.includes('미수집')));
    if(!sources.length)return '';
    return `<aside class="wb-source-warning" role="status"><strong>일부 제공처 자동 조회 실패·제한</strong><ul>${sources.map(s=>`<li>${esc(s.label)}: ${s.cached?`이전 성공 수집본 · ${esc(dateTime(s.observed_at))} KST · 최대 ${esc(s.cache_limit_hours)}시간 재사용`:'수집 누락'}${s.status?.match(/HTTP \d+/)?` · ${esc(s.status.match(/HTTP \d+/)[0])}`:''}</li>`).join('')}</ul><p>아래 자료를 모두 방금 수집한 것으로 해석하지 마세요. 이전 자료는 예정일 변경·새 공시를 반영하지 못할 수 있습니다. 재사용 기한이 지나면 표시하지 않습니다.</p></aside>`;
  }
  function drawMacro(pane) {
    if (loading(pane)) return;
    const events=external.economic_events || [], now=Date.now();
    const next=events.find(row=>row.at && Date.parse(row.at)>now);
    pane.innerHTML=`${sourceWarning(['bls','bea','fomc','macro'])}<div class="wb-summary"><div><small>다음 시각 확정 발표</small><strong>${esc(next?.title || '수집 일정 없음')}</strong></div><div><small>한국시간</small><strong>${next ? esc(dateTime(next.at)) : '—'}</strong></div><div><small>남은 시간</small><strong id="wbCountdown" data-at="${esc(next?.at || '')}">—</strong></div><div><small>일정 범위</small><strong>최근 7일 · 향후 45일</strong></div></div>
    <div class="wb-macro-cards">${(external.macro_indicators || []).map(row=>`<article><h3>${esc(row.label)}</h3><strong>${fmt(row.value,2)} <small>${esc(row.unit)}</small></strong><p>${esc(row.date || '미수집')}${row.stale ? ' · 오래된 관측' : ''}</p><p>${esc(row.note || '')}</p>${link(row.source_url,row.source || '출처')}</article>`).join('')}</div>
    <p class="wb-note">미국 공식 발표 일정 · 시각은 KST로 변환하며 미국 서머타임을 반영합니다. FOMC 회의 마지막 날은 회의일로 표시하며 발표시각을 임의로 지정하지 않습니다. 시장 예상치·발표 결과는 이 일정표에 포함하지 않습니다.</p>
    <div class="wb-scroll"><table class="wb-table"><caption>경제 발표 일정 · 시간순</caption><thead><tr><th>한국시간 / 날짜</th><th>발표</th><th>중요도</th><th>상태</th><th>출처</th></tr></thead><tbody>${events.map(row=>`<tr><td>${row.at ? esc(dateTime(row.at))+' KST' : esc(row.date)+' ET · 시각 미공개'}</td><td>${esc(row.title)}<small>${esc(row.original_title || '')}</small></td><td>${esc(row.importance)}</td><td>${row.at && Date.parse(row.at)<now?'예정 시각 경과 · 결과 미연동':'기관 일정'}</td><td>${link(row.source_url,row.source)}</td></tr>`).join('') || '<tr><td colspan="5">수집된 일정 없음. 수집 상태를 확인하세요.</td></tr>'}</tbody></table></div>${healthHTML(['bls','bea','fomc','macro'])}`;
    updateCountdown();
  }
  function drawCompanies(pane) {
    if (loading(pane)) return;
    const us=market==='us', reports=(external.filings || []).filter(row=>row.market===market);
    pane.innerHTML=`${sourceWarning(['reported','earnings','sec','dart','ipo'])}<p class="wb-note">${us ? '미국 실적일정은 Nasdaq 제공 예상 일정입니다. 기업 확정 발표와 차이가 있을 수 있습니다. 예상 EPS는 컨센서스이며 전년 EPS와 실제 당기 EPS를 구분합니다.' : '아래 실적·공모 일정은 미국시장 자료입니다. 국내 공시는 DART 최근 RSS에 포함된 당일·분석종목 자료만 표시하며 당일 전체 공시가 아닙니다.'}</p>
      <details class="wb-detail" open><summary>미국 공시 실적 · 분석종목의 최근 분기·연간</summary><p class="wb-note">SEC에 실제 공시된 희석 EPS·매출입니다. 분기와 연간, US-GAAP과 IFRS를 구분합니다. 연간 EPS에서 9개월 EPS를 빼서 4분기 EPS를 만들지 않습니다. 예상 EPS와 회계기준이 확인되지 않아 실적 서프라이즈로 계산하지 않습니다.</p><div id="wbReportedFilters" class="wb-filters"><label>종목 검색<input name="reportedQuery" type="search" placeholder="종목명·티커"></label><label>대상기간<select name="reportedPeriod"><option value="all">분기·연간 모두</option><option value="quarter">분기만</option><option value="annual">연간만</option></select></label></div><div id="wbReportedResults" aria-live="polite"></div></details>
      <details class="wb-detail" open><summary>미국 실적 발표 일정 · ET 날짜 기준</summary><div class="wb-scroll"><table class="wb-table"><thead><tr><th>미국 날짜</th><th>종목</th><th>시간대</th><th>예상 EPS</th><th>전년 EPS</th><th>예상치 수</th><th>출처</th></tr></thead><tbody>${(external.earnings || []).map(row=>`<tr><td>${esc(row.date)}</td><td>${esc(row.symbol)}<small>${esc(row.name)}</small></td><td>${esc(row.session)}</td><td>${fmt(row.eps_estimate,2)}</td><td>${fmt(row.last_year_eps,2)}</td><td>${fmt(row.estimates_count,0)}</td><td>${link(row.source_url,'Nasdaq')}</td></tr>`).join('') || '<tr><td colspan="7">수집된 일정 없음. 수집 상태를 확인하세요.</td></tr>'}</tbody></table></div><p class="wb-note">EPS는 제공처 표기 기준. 실제 당기 EPS·매출·실적 서프라이즈는 이 자료에 미제공되어 계산하지 않습니다. 한국 날짜가 아닌 미국 날짜 기준이며 정확한 발표시각은 미제공입니다.</p></details>
      <details class="wb-detail" open><summary>${us?'SEC 최근 공시 · 분석종목 · 최근 90일 · 종목당 최대 8건':'DART 최근 RSS 중 당일 공시 · 분석종목'}</summary><div class="wb-scroll"><table class="wb-table"><thead><tr><th>접수일</th><th>종목</th><th>보고서</th><th>대상기간</th><th>원문</th></tr></thead><tbody>${reports.map(row=>`<tr><td>${esc(row.date)}</td><td>${esc(row.name)}<small>${esc(row.symbol)}</small></td><td>${esc(row.form)}</td><td>${esc(row.report_date || '—')}</td><td>${link(row.url,'공시 원문')}</td></tr>`).join('') || '<tr><td colspan="5">수집된 해당 공시 없음. 수집 상태를 확인하세요.</td></tr>'}</tbody></table></div></details>
      <details class="wb-detail" open><summary>미국 신규공모 추적 · 지난달~다음달</summary><p class="wb-note">공모가 확정일·신고일·철회일을 실제 상장일과 구분합니다. 예정일은 추정이며 상장이 보장되지 않습니다. 첫날·현재 수익률은 검증된 상장 시세 미연동으로 표시하지 않습니다.</p><div class="wb-scroll"><table class="wb-table"><thead><tr><th>날짜 / 구분</th><th>기업 / 예정 티커</th><th>상태</th><th>공모가격·범위</th><th>공모규모</th><th>거래소</th><th>출처</th></tr></thead><tbody>${(external.ipos || []).map(row=>`<tr><td>${esc(row.date || '미정')}<small>${esc(row.date_kind)}</small></td><td>${esc(row.name)}<small>${esc(row.symbol || '미정')}</small></td><td>${esc(row.status)}</td><td>${esc(row.price || '미제공')}</td><td>${esc(row.amount || '미제공')}</td><td>${esc(row.exchange || '미제공')}</td><td>${link(row.source_url,'Nasdaq')}</td></tr>`).join('') || '<tr><td colspan="7">수집된 공모정보 없음. 수집 상태를 확인하세요.</td></tr>'}</tbody></table></div></details>${healthHTML(['reported','earnings','sec','dart','ipo'])}`;
    renderReportedRows();
  }
  function renderReportedRows() {
    const target=root.querySelector('#wbReportedResults');if(!target)return;
    const query=(root.querySelector('[name="reportedQuery"]')?.value || '').trim().toLowerCase();
    const period=root.querySelector('[name="reportedPeriod"]')?.value || 'all';
    const rows=(external.reported_earnings || []).filter(row=>(period==='all'||row.period_type===period)&&`${row.symbol} ${row.name}`.toLowerCase().includes(query));
    target.innerHTML=`<p class="wb-note">${rows.length}개 실적 · 회사별 수집 가능한 최근 분기·연간 각각 최대 1개. EPS는 USD/주, 매출은 USD. 전년 적자·0 또는 동일 공시 비교값이 없으면 EPS 증감률을 표시하지 않습니다.</p>${rows.length?`<div class="wb-scroll"><table class="wb-table"><thead><tr><th>종목</th><th>기간·회계기준</th><th>실제 희석 EPS</th><th>전년 EPS</th><th>EPS 변화</th><th>실제 매출</th><th>매출 전년 대비</th><th>접수일·원문</th></tr></thead><tbody>${rows.map(row=>`<tr><td>${esc(row.name)}<small>${esc(row.symbol)}</small></td><td>${row.period_type==='quarter'?'분기':'연간'} · ${esc(row.basis)}<small>${esc(row.period_start)} ~ ${esc(row.period_end)}</small></td><td>${fmt(row.eps,2)}</td><td>${fmt(row.previous_eps,2)}</td><td>${num(row.eps_yoy)!==null?`<b class="${tone(row.eps_yoy)}">${pct(row.eps_yoy)}</b>`:'—'}<small>${esc(row.eps_state)}</small></td><td title="${esc(fmt(row.revenue,0))} USD">${num(row.revenue)!==null?'$'+short(row.revenue):'—'}</td><td class="${tone(row.revenue_yoy)}">${pct(row.revenue_yoy)}</td><td>${esc(row.filed)}<small>${link(row.eps_source_url || row.source_url,'EPS 공시')}${row.revenue_source_url&&row.revenue_source_url!==row.eps_source_url?' · '+link(row.revenue_source_url,'매출 공시'):''}</small>${row.revenue_filed&&row.revenue_filed!==row.eps_filed?`<small>매출 접수 ${esc(row.revenue_filed)}</small>`:''}</td></tr>`).join('')}</tbody></table></div>`:empty('수집된 해당 실적 없음. 수집 상태·대상기간을 확인하세요.')}`;
  }
  function updateCountdown() {
    const node=root.querySelector('#wbCountdown'); if (!node) return;
    const at=Date.parse(node.dataset.at);if(!Number.isFinite(at)){node.textContent='—';return;}
    const seconds=Math.max(0,Math.floor((at-Date.now())/1000));
    node.textContent=`${Math.floor(seconds/86400)}일 ${Math.floor(seconds%86400/3600)}시간 ${Math.floor(seconds%3600/60)}분`;
  }
  function csvCell(value) { if(value===null||value===undefined)return '""';const text=String(value);return '"'+(typeof value==='string'&&/^[\s]*[=+\-@\t\r]/.test(text)?"'":'')+text.replace(/"/g,'""')+'"'; }
  function exportCSV() {
    const headers=['종목코드','종목명','관측일','현재가','일간등락률%','21거래일수익률%','RSI','거래량배수','52주고점대비%','기술점수'];
    const rows=filteredStocks().map(row=>[row.symbol,row.name,row.screening?.date,row.price,row.return_1d,row.screening?.return_21,row.rsi,row.volume_ratio,row.screening?.drawdown_52w,row.score]);
    const blob=new Blob(['\ufeff'+[headers,...rows].map(row=>row.map(csvCell).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'});
    const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`stocks-${market}-screening.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  root.addEventListener('click', event => {
    if(event.target.closest('[data-full-lookup]')){window.StockLookup?.search(filters.query);return;}
    const tab=event.target.closest('[data-wb-tab]');if(tab){active=tab.dataset.wbTab;root.querySelectorAll('[data-wb-tab]').forEach(b=>b.setAttribute('aria-pressed',String(b===tab)));drawPane();return;}
    const star=event.target.closest('[data-favorite]');if(star){const id=star.dataset.favorite;favorites.has(id)?favorites.delete(id):favorites.add(id);try{localStorage.setItem(favoriteKey,JSON.stringify([...favorites]));}catch(_){}drawResults();window.dispatchEvent(new window.CustomEvent('stock-favorites-change'));return;}
    const stock=event.target.closest('[data-stock]');if(stock){const row=stocks().find(x=>x.symbol===stock.dataset.stock);if(row)openStock?.(row);return;}
    const theme=event.target.closest('[data-theme]');if(theme){selectedTheme=theme.dataset.theme;drawPane();return;}
    const preset=event.target.closest('[data-preset]');if(preset){Object.assign(filters,{query:'',sector:'',returnPeriod:'1d',returnMin:'',returnMax:'',rsiMin:'',rsiMax:'',volumeMin:'',average:'',favorites:false,preset:''});if(preset.dataset.preset==='trend')filters.average='50:above';if(preset.dataset.preset==='oversold')filters.rsiMax='30';if(['high','low'].includes(preset.dataset.preset))filters.preset=preset.dataset.preset;drawPane();return;}
    if(event.target.closest('[data-export]'))exportCSV();
  });
  function readFilters(form) { for(const control of form.querySelectorAll('input,select')) {if(control.name in filters)filters[control.name]=control.type==='checkbox'?control.checked:control.value;}drawResults(); }
  root.addEventListener('submit',event=>{if(event.target.id==='wbFilterForm'){event.preventDefault();readFilters(event.target);}});
  root.addEventListener('change',event=>{const form=event.target.closest('#wbFilterForm');if(form)readFilters(form);if(event.target.closest('#wbReportedFilters'))renderReportedRows();});
  root.addEventListener('input',event=>{const form=event.target.closest('#wbFilterForm');if(form)readFilters(form);if(event.target.closest('#wbReportedFilters'))renderReportedRows();});
  setInterval(updateCountdown,30000);
  window.StockWorkbench={render};
})();

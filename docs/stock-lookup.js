// Full listing directory and bounded, on-demand quotes. No account data is sent
// to the directory or written into public analysis results.
(() => {
  'use strict';
  const market = document.body.dataset.stockMarket;
  const form = document.querySelector('#stockSearchForm');
  if (!form) return;
  const input = document.querySelector('#stockSearchInput'), result = document.querySelector('#stockSearchResult');
  const status = document.querySelector('#stockSearchStatus'), watch = document.querySelector('#stockWatchlist');
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const norm = value => String(value || '').toLowerCase().replace(/\s+/g, '');
  const number = value => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value)) ? Number(value) : null;
  const fmt = (value, digits=2) => number(value) === null ? '—' : new Intl.NumberFormat('ko-KR',{maximumFractionDigits:digits}).format(Number(value));
  const pct = value => number(value) === null ? '—' : `${value>0?'+':''}${fmt(value)}%`;
  const time = value => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}) : '미확인';
  const metric = (name,value) => `<div><span>${esc(name)}</span><strong>${esc(value)}</strong></div>`;
  const favoriteKey = `stock-favorites-${market}-v1`, recent = new Map(), quotes = new Map(), inflight = new Map(), failures = new Map();
  let getReport = () => null, openChart = () => {}, directory, directoryPromise, requestId=0, current=null, watchBusy=false, watchCursor=0;
  function favorites() { try { const rows=JSON.parse(localStorage.getItem(favoriteKey)||'[]');return new Set(Array.isArray(rows)?rows.filter(x=>typeof x==='string'):[]); } catch { return new Set(); } }
  function price(value, currency) { return `${currency==='USD'?'$':currency==='KRW'?'₩':`${currency||''} `}${fmt(value,currency==='KRW'?0:2)}`; }
  function updateEvent() { window.dispatchEvent(new CustomEvent('stock-lookup-update')); }
  function toggleFavorite(symbol) {
    const rows=favorites(); if(rows.has(symbol))rows.delete(symbol);else rows.add(symbol);
    try {localStorage.setItem(favoriteKey,JSON.stringify([...rows]));} catch {status.textContent='브라우저 저장공간에 즐겨찾기를 저장하지 못했습니다.';}
    drawWatch();updateEvent();
  }
  async function loadDirectory() {
    if(directory)return directory;
    if(!directoryPromise)directoryPromise=fetch(`data/stock-symbols-${market}.json?v=${new Date().toISOString().slice(0,10)}`)
      .then(async response=>{if(!response.ok)throw new Error('종목 목록을 불러오지 못했습니다.');const value=await response.json();if(value.market!==market||!Array.isArray(value.symbols)||!value.symbols.length)throw new Error('종목 목록이 비어 있습니다.');directory=value;drawDirectoryStatus();drawWatch();return value;})
      .catch(error=>{directoryPromise=null;status.textContent=`${error.message} 티커·종목코드 직접 조회는 가능합니다.`;throw error;});
    return directoryPromise;
  }
  function drawDirectoryStatus() {
    const sources=Object.values(directory.sources||{}), failed=sources.filter(x=>x.cached||x.status!=='정상');
    const old=sources.some(x=>!x.observed_at||Date.now()-Date.parse(x.observed_at)>48*3600000);
    status.textContent=`${directory.source} 기준 ${fmt(directory.symbols.length,0)}개 · ${sources.map(x=>`${x.label} ${time(x.observed_at)}`).join(' / ')}${failed.length?' · 일부 목록 갱신 실패: 이전 목록 사용':''}${old?' · 오래된 목록: 신규 상장·상장폐지 반영이 지연될 수 있습니다.':''}`;
  }
  function catalog() {
    const rows=new Map((directory?.symbols||[]).map(row=>[row.symbol,row]));
    for(const row of getReport()?.rankings||[]) {const known=rows.get(row.symbol);rows.set(row.symbol,known?{...known,alias:row.name}:row);}
    return [...rows.values()];
  }
  function matches(query) {
    const q=norm(query), rows=catalog();
    const rank=row=>norm(row.symbol)===q?0:[row.name,row.alias,row.english_name].some(x=>norm(x)===q)?1:norm(row.symbol).startsWith(q)?2:3;
    return rows.filter(row=>[row.symbol,row.name,row.alias,row.english_name].some(x=>norm(x).includes(q))).sort((a,b)=>rank(a)-rank(b)||a.symbol.localeCompare(b.symbol));
  }
  function directSymbol(query) {
    const symbol=query.trim().toUpperCase();
    return market==='kr' ? /^[A-Z0-9]{6}$/.test(symbol) : /^[A-Z0-9][A-Z0-9.\-]{0,15}$/.test(symbol);
  }
  function ema(values,period) {if(values.length<period)return null;const k=2/(period+1);return values.slice(1).reduce((out,v)=>(v-out)*k+out,values[0]);}
  function emaSeries(values,period) {const out=[values[0]],k=2/(period+1);for(let i=1;i<values.length;i++)out.push((values[i]-out.at(-1))*k+out.at(-1));return out;}
  function analyze(item, data) {
    // Deduplicate by session, reject malformed/zero prices, preserve missing volume.
    const unique=new Map();
    for(const row of data.rows||[]) {
      const at=number(row.timestamp), close=number(row.price), date=String(row.session||row.date||'').slice(0,10);
      if(at===null||at>Date.now()+60000||close===null||close<=0||!/^\d{4}-\d{2}-\d{2}$/.test(date))continue;
      unique.set(date,{...row,price:close,volume:number(row.volume),timestamp:at,date,session:date});
    }
    const rows=[...unique.values()].sort((a,b)=>a.timestamp-b.timestamp), values=rows.map(x=>x.price), n=values.length;
    if(!n)throw new Error('조회 실패: 유효한 일봉 시세가 없습니다. 상장 여부를 의미하지는 않습니다.');
    const change=days=>n>days?(values.at(-1)/values[n-days-1]-1)*100:null;
    let rsi=null,macd=null,signal=null;
    if(n>14) {
      const changes=values.slice(1).map((v,i)=>v-values[i]);let gain=changes.slice(0,14).reduce((s,d)=>s+Math.max(d,0),0)/14,loss=changes.slice(0,14).reduce((s,d)=>s+Math.max(-d,0),0)/14;
      for(const d of changes.slice(14)){gain=(gain*13+Math.max(d,0))/14;loss=(loss*13+Math.max(-d,0))/14;}
      rsi=loss===0?100:100-100/(1+gain/loss);
    }
    if(n>=35){const fast=emaSeries(values,12),slow=emaSeries(values,26),line=fast.map((v,i)=>v-slow[i]);macd=line.at(-1);signal=emaSeries(line,9).at(-1);}
    const vols=rows.slice(-30).map(x=>x.volume), validVolume=vols.length===30&&vols.every(x=>x!==null&&x>=0), baseline=validVolume?vols.reduce((s,v)=>s+v,0)/30:null;
    const sma=days=>n>=days?values.slice(-days).reduce((s,v)=>s+v,0)/days:null;
    const highs=rows.slice(-252).map(x=>number(x.high)),lows=rows.slice(-252).map(x=>number(x.low));
    const high=n>=252&&highs.every(v=>v!==null)?Math.max(...highs):null,low=n>=252&&lows.every(v=>v!==null)?Math.min(...lows):null;
    return {...item,price:values.at(-1),currency:data.currency||(market==='us'?'USD':'KRW'),return_1d:change(1),return_7d:change(7),return_30d:change(30),rsi,macd,macd_signal:signal,macd_histogram:macd===null?null:macd-signal,
      ema20:ema(values,20),ema50:ema(values,50),volume_ratio:baseline>0?(vols.slice(-7).reduce((s,v)=>s+v,0)/7)/baseline:null,
      score:null,rank:null,decision:n<50?'이력 부족':'개별 조회',source:data.source||'시세 제공처',fetched_at:data.fetched_at||new Date().toISOString(),history:rows,
      screening:{date:rows.at(-1).date,sma50:sma(50),sma200:sma(200),high_52w:high,low_52w:low,drawdown_52w:high>0?(values.at(-1)/high-1)*100:null,estimated_turnover:rows.at(-1).volume===null?null:values.at(-1)*rows.at(-1).volume,...Object.fromEntries([5,21,63,126,252].map(d=>[`return_${d}`,change(d)]))}};
  }
  async function quote(item, force=false) {
    const cached=quotes.get(item.symbol);if(!force&&cached&&Date.now()-cached.at<300000)return cached.stock;
    if(inflight.has(item.symbol))return inflight.get(item.symbol);
    const task=(async()=>{
      // Common class-share notation in the KIS directory differs from Yahoo.
      const aliases={'BRK/A':'BRK.A','BRK/B':'BRK.B','BF/A':'BF.A','BF/B':'BF.B'};
      const symbol=aliases[item.symbol]||item.symbol;
      if(!directSymbol(symbol))throw new Error('종목은 목록에 있으나 이 종목코드 표기는 현재 시세 제공처에서 지원하지 않습니다.');
      let timer;
      const data=await Promise.race([window.ChartData.loadStock({...item,symbol},market,'1d',force),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('시세 응답 시간 초과: 잠시 후 다시 조회해 주세요.')),40000);})]).finally(()=>clearTimeout(timer));
      const stock=analyze({...item,chart_symbol:symbol},data);
      if(quotes.size>=100&&!quotes.has(item.symbol)){const key=quotes.keys().next().value;quotes.delete(key);recent.delete(key);}
      quotes.set(item.symbol,{at:Date.now(),stock});recent.set(item.symbol,stock);failures.delete(item.symbol);updateEvent();return stock;
    })();inflight.set(item.symbol,task);
    try{return await task;}catch(error){failures.set(item.symbol,error.message);throw error;}finally{inflight.delete(item.symbol);}
  }
  function drawStock(stock, note='') {
    const saved=favorites().has(stock.symbol), enough=stock.history.length>=50;
    result.innerHTML=`<article class="search-result-card stock-search-card"><div class="search-result-top"><div><span class="search-rank">전체 종목 개별 조회 · ${esc(stock.exchange_name||'거래소 미확인')} · ${esc(stock.kind||'유형 미확인')}</span><h3>${esc(stock.name)} <small>${esc(stock.symbol)}</small></h3><p>${esc(price(stock.price,stock.currency))} · 일간 ${esc(pct(stock.return_1d))}</p></div><button type="button" data-lookup-favorite="${esc(stock.symbol)}" aria-pressed="${saved}">${saved?'★ 관심종목 해제':'☆ 관심종목 등록'}</button></div>
      <p class="lookup-note">${esc(stock.source)} · 관측일 ${esc(stock.screening.date)} · 조회 ${esc(time(stock.fetched_at))} · 시세 지연 가능, 진행 중인 일봉은 미확정</p>
      <div class="search-metrics">${metric('RSI(14)',fmt(stock.rsi,1))}${metric('MACD',fmt(stock.macd,4))}${metric('MACD 히스토그램',fmt(stock.macd_histogram,4))}${metric('EMA20',fmt(stock.ema20))}${metric('EMA50',fmt(stock.ema50))}${metric('거래량 비율',stock.volume_ratio===null?'—':`${fmt(stock.volume_ratio)}×`)}${metric('7거래일',pct(stock.return_7d))}${metric('30거래일',pct(stock.return_30d))}</div>
      <p class="lookup-note">${enough?'개별 조회 종목에는 추천 순위·점수를 부여하지 않습니다. 자동 추천은 별도 분석 대상과 기존 기준으로 산출합니다.':`이력 부족: ${stock.history.length}개 일봉입니다. 최소 50개 일봉이 필요한 종합 분석은 보류하며, 계산 가능한 지표만 표시합니다.`} ${esc(note)}</p>
      <div class="lookup-actions"><button type="button" data-lookup-chart>차트·거래량·RSI·MACD 보기</button><button type="button" data-lookup-refresh>시세 새로고침</button></div></article>`;
    result.querySelector('[data-lookup-chart]').addEventListener('click',()=>openChart({...stock,symbol:stock.chart_symbol||stock.symbol}));
    result.querySelector('[data-lookup-refresh]').addEventListener('click',()=>select(stock,true));
    result.querySelector('[data-lookup-favorite]').addEventListener('click',()=>{toggleFavorite(stock.symbol);drawStock(stock);});
  }
  async function select(item, force=false) {
    const id=++requestId; current=item;input.value=item.symbol;
    result.innerHTML=`<p class="search-empty">${esc(item.name||item.symbol)} 시세·지표 조회 중…</p>`;
    try { const stock=await quote(item,force);if(id!==requestId)return;current=stock;drawStock(stock);drawWatch(); }
    catch(error) {if(id!==requestId)return;const prior=quotes.get(item.symbol)?.stock;
      result.innerHTML=`<div class="search-empty lookup-error"><strong>${esc(item.name||item.symbol)} (${esc(item.symbol)})</strong><p>시세 조회 실패 · ${esc(error.message)}</p><p>검색 목록에 없는 경우와 다릅니다. 데이터 미제공·거래정지·일시적 통신 오류 가능성이 있으며 원인은 응답만으로 확정할 수 없습니다.</p><button type="button" data-lookup-retry>다시 조회</button>${prior?'<button type="button" data-lookup-prior>이전 조회값 보기</button>':''}</div>`;
      result.querySelector('[data-lookup-retry]').addEventListener('click',()=>select(item,true));
      result.querySelector('[data-lookup-prior]')?.addEventListener('click',()=>drawStock(prior,'최신 갱신 실패로 이전 조회값을 표시합니다.'));
    }
  }
  async function search(query, submit=true) {
    const id=++requestId;current=null;if(!query.trim()){result.innerHTML='<p class="search-empty">티커·종목코드·한글 또는 영문 종목명을 입력해 주세요.</p>';return;}
    result.innerHTML='<p class="search-empty">종목 목록 검색 중…</p>';
    try{await loadDirectory();}catch{/* Direct ticker lookup remains usable without a directory. */}
    if(id!==requestId)return;
    const rows=matches(query),exact=rows.filter(x=>[x.symbol,x.name,x.alias,x.english_name].some(v=>norm(v)===norm(query)));
    if(submit&&exact.length===1){await select(exact[0]);return;}
    const direct=!rows.length&&directSymbol(query);
    result.innerHTML=`<p class="lookup-note">${rows.length?`${fmt(rows.length,0)}개 일치 · 최대 30개 표시. 종목을 선택하면 시세를 조회합니다.`:'현재 종목 목록에서 일치하는 항목을 찾지 못했습니다. 신규 상장·이름 변경·목록 갱신 상태를 확인해 주세요.'}</p><div class="lookup-results">${rows.slice(0,30).map((row,index)=>`<button type="button" data-lookup-index="${index}"><span><strong>${esc(row.symbol)} · ${esc(row.name)}</strong><small>${esc(row.english_name||'')}</small></span><small>${esc(row.exchange_name||'')} · ${esc(row.kind||'')}</small></button>`).join('')}</div>${direct?'<button type="button" data-lookup-direct>입력한 코드로 직접 시세 조회</button>':''}`;
    result.querySelectorAll('[data-lookup-index]').forEach(button=>button.addEventListener('click',()=>select(rows[Number(button.dataset.lookupIndex)])));
    result.querySelector('[data-lookup-direct]')?.addEventListener('click',()=>select({symbol:query.trim().toUpperCase(),name:query.trim().toUpperCase()}));
  }
  function watchItems() {
    const rows=new Map(), known=new Map(catalog().map(x=>[x.symbol,x]));
    for(const symbol of favorites())rows.set(symbol,known.get(symbol)||{symbol,name:symbol});
    // Owner-only account access remains controlled by the existing auth module.
    for(const row of window.CoinAuth?.portfolio?.positions||[])if(row.market===market&&window.CoinAuth?.user)rows.set(row.symbol,known.get(row.symbol)||{symbol:row.symbol,name:row.name});
    return [...rows.values()];
  }
  function drawWatch() {
    if(!watch)return;const rows=watchItems();
    watch.innerHTML=`<div class="lookup-actions"><strong>관심·보유종목 ${rows.length}개</strong><button type="button" data-watch-refresh ${watchBusy?'disabled':''}>${watchBusy?'갱신 중…':'관심·보유종목 시세 갱신'}</button></div><p class="lookup-note">관심종목은 이 브라우저에 저장합니다. 계좌 보유종목은 본인 로그인 후에만 표시합니다. 페이지가 보이는 동안 5분마다 최대 5종목씩 순차 갱신하며, 계좌 수량은 기존 ‘수량·가격 갱신’ 버튼으로 동기화합니다.</p><div class="lookup-chips">${rows.map((row,index)=>`<button type="button" data-watch-index="${index}">${esc(row.name)} · ${esc(row.symbol)}${quotes.has(row.symbol)?` · ${esc(price(quotes.get(row.symbol).stock.price,quotes.get(row.symbol).stock.currency))} · ${esc(time(quotes.get(row.symbol).stock.fetched_at))}`:''}${failures.has(row.symbol)?' · 갱신 실패'+(quotes.has(row.symbol)?'·이전값':''):''}</button>`).join('')||'<span>관심종목을 등록하면 여기에 표시됩니다.</span>'}</div><p data-watch-status class="lookup-note" aria-live="polite"></p>`;
    watch.querySelectorAll('[data-watch-index]').forEach(button=>button.addEventListener('click',()=>select(rows[Number(button.dataset.watchIndex)])));
    watch.querySelector('[data-watch-refresh]').addEventListener('click',()=>refreshWatch(true));
  }
  async function refreshWatch(force=false) {
    if(watchBusy||document.visibilityState==='hidden')return;
    const items=watchItems();if(!items.length)return;watchBusy=true;drawWatch();let success=0,failed=0;
    const batch=force?items.slice(0,100):[...items.slice(watchCursor),...items.slice(0,watchCursor)].slice(0,5);
    if(!force)watchCursor=(watchCursor+batch.length)%items.length;
    for(const item of batch) {
      if(document.visibilityState==='hidden')break;
      try{await quote(item,force);success++;}catch{failed++;}
      await new Promise(resolve=>setTimeout(resolve,300));
    }
    watchBusy=false;drawWatch();const message=watch?.querySelector('[data-watch-status]');
    if(message)message.textContent=`갱신 성공 ${success}개 · 실패 ${failed}개${items.length>100?' · 한 번에 최대 100개 처리':''} · ${time(new Date().toISOString())}`;
    if(current&&quotes.has(current.symbol))drawStock(quotes.get(current.symbol).stock,failed?'일부 관심종목의 갱신에 실패했습니다.':'');
  }
  let debounce;
  form.addEventListener('submit',event=>{event.preventDefault();clearTimeout(debounce);search(input.value);});
  input.addEventListener('input',()=>{++requestId;current=null;clearTimeout(debounce);debounce=setTimeout(()=>search(input.value,false),200);});
  window.addEventListener('stock-favorites-change',()=>{drawWatch();refreshWatch();});
  window.addEventListener('coin-auth-change',()=>{drawWatch();});
  window.addEventListener('kis-portfolio-sync',()=>{drawWatch();refreshWatch();});
  setInterval(()=>{refreshWatch();if(current&&document.visibilityState!=='hidden')select(current);},300000);
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState!=='hidden')refreshWatch();});
  window.StockLookup={bind(options){getReport=options.getReport;openChart=options.openChart;loadDirectory().then(()=>refreshWatch()).catch(()=>{});},
    search(query){window.StockWorkbench?.openLookup();input.value=query;form.scrollIntoView?.({behavior:'smooth',block:'center'});input.focus();return search(query);},
    recent:()=>[...recent.values()],analyze,refreshWatch};
  drawWatch();
})();

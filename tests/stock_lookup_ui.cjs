const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {parseHTML}=require('linkedom');
const tick=()=>new Promise(resolve=>setTimeout(resolve,10));
const candles=(count=80)=>Array.from({length:count},(_,i)=>({timestamp:Date.UTC(2026,0,1+i),session:new Date(Date.UTC(2026,0,1+i)).toISOString().slice(0,10),price:100+i,open:100+i,high:101+i,low:99+i,volume:1000+i}));
async function setup(market='us',directoryError=false){
 const {window}=parseHTML(fs.readFileSync(`docs/${market}-stocks.html`,'utf8')),document=window.document;
 const stored=new Map(),requests=[],opened=[],timers=[];let behavior=()=>({rows:candles(),source:'Fixture',currency:market==='us'?'USD':'KRW',fetched_at:'2026-11-27T01:00:00Z'});
 const directory={market,source:'공개 종목마스터',sources:{NAS:{label:'NASDAQ',observed_at:'2026-11-20T01:00:00Z',status:'목록 갱신 실패',cached:true}},symbols:market==='us'?[
  {symbol:'ASPI',name:'ASP 아이소토프',english_name:'ASP ISOTOPES INC',exchange:'NAS',exchange_name:'NASDAQ',kind:'주식'},
  {symbol:'BRK/B',name:'버크셔 B',english_name:'BERKSHIRE B',exchange:'NYS'},
  {symbol:'TEST',name:'<img src=x>',english_name:'Test ETF',exchange:'AMS',kind:'ETF'}]:[
  {symbol:'005930',name:'삼성전자',exchange:'KOSPI',exchange_name:'코스피',kind:'주식'},
  {symbol:'0001A0',name:'알파신규',exchange:'KOSDAQ',exchange_name:'코스닥',kind:'주식'}]};
 window.ChartData={loadStock:async(stock,m,i,force)=>{requests.push({symbol:stock.symbol,market:m,interval:i,force});return behavior(stock);}};
 window.CoinAuth={user:null,portfolio:{positions:[{market,symbol:'SECRET',name:'Private holding'}]}};
 document.querySelector('#stockSearchInput').focus=()=>{};
 const context=vm.createContext({window,document,CustomEvent:window.CustomEvent,Date,Intl,Map,Set,Promise,JSON,console,
   localStorage:{getItem:key=>stored.get(key)||null,setItem:(key,value)=>stored.set(key,value)},
   setInterval:fn=>{timers.push(fn);return 0;},setTimeout,clearTimeout,
   fetch:async()=>{if(directoryError)throw new Error('offline');return {ok:true,json:async()=>directory};}});
 vm.runInContext(fs.readFileSync('docs/stock-lookup.js','utf8'),context);
 vm.runInContext(fs.readFileSync('docs/stock-workbench.js','utf8'),context);
 window.StockWorkbench.render({rankings:[]},row=>opened.push(row));
 window.StockLookup.bind({getReport:()=>({rankings:[]}),openChart:row=>opened.push(row)});await tick();
 return {window,document,stored,requests,opened,timers,change:fn=>behavior=fn};
}
(async()=>{
 const ui=await setup(),{window,document,requests,opened}=ui;
 assert.match(document.querySelector('#stockSearchStatus').textContent,/오래된 목록/);
 assert.doesNotMatch(document.querySelector('#stockWatchlist').textContent,/Private holding/,'anonymous cannot see account holdings');
 assert.equal(document.querySelector('.wb-tabs button:last-child').textContent,'개별검색');
 assert.equal(document.querySelector('#stockIndividualSearch').hidden,true);
 assert.equal(document.querySelectorAll('main > .alt-search-panel').length,0,'no separate search card');
 await window.StockLookup.search('ASP ISOTOPES INC');
 assert.equal(document.querySelector('#stockIndividualSearch').hidden,false,'search opens its market research tab');
 assert.equal(document.querySelector('#wbPane').hidden,true);
 assert.equal(requests.length,1);assert.equal(requests[0].symbol,'ASPI');assert.equal(document.querySelector('#stockSearchResult h3').textContent,'ASP 아이소토프 ASPI');
 assert.match(document.querySelector('#stockSearchResult').textContent,/추천 순위·점수를 부여하지/);
 assert.match(document.querySelector('#stockSearchResult').textContent,/Fixture/);
 document.querySelector('[data-lookup-chart]').click();assert.equal(opened[0].symbol,'ASPI');
 const originalForm=document.querySelector('#stockSearchForm');
 document.querySelector('[data-wb-tab="themes"]').click();assert.equal(document.querySelector('#stockIndividualSearch').hidden,true);
 document.querySelector('[data-wb-tab="lookup"]').click();
 assert.equal(document.querySelector('#stockSearchForm'),originalForm);
 assert.match(document.querySelector('#stockSearchResult').textContent,/ASP 아이소토프/,'switching tabs preserves search results');
 window.StockWorkbench.render({rankings:[]},row=>opened.push(row));
 assert.equal(document.querySelector('#stockSearchForm'),originalForm,'report refresh preserves form listeners');
 originalForm.dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));await tick();
 assert.equal(requests.length,1,'preserved search handler continues to use its quote cache');
 document.querySelector('[data-lookup-favorite]').click();assert.match(ui.stored.get('stock-favorites-us-v1'),/ASPI/);
 await window.StockLookup.search('ASPI');assert.equal(requests.length,1,'five-minute quote cache');
 document.querySelector('[data-lookup-refresh]').click();await tick();assert.equal(requests.length,2);assert.equal(requests[1].force,true);
 await window.StockLookup.search('Test');assert.equal(document.querySelector('#stockSearchResult img'),null,'company names escaped');
 const beforeMiss=requests.length;
 await window.StockLookup.search('Unlisted ticker phrase');assert.match(document.querySelector('#stockSearchResult').textContent,/일치하는 항목을 찾지 못/);assert.equal(requests.length,beforeMiss,'unmatched names do not trigger random quotes');
 await window.StockLookup.search('NEWT');assert.ok(document.querySelector('[data-lookup-direct]'));assert.equal(requests.length,beforeMiss);
 ui.change(()=>{throw new Error('provider timeout');});document.querySelector('[data-lookup-direct]').click();await tick();
 assert.match(document.querySelector('#stockSearchResult').textContent,/시세 조회 실패/);assert.match(document.querySelector('#stockSearchResult').textContent,/provider timeout/);assert.match(document.querySelector('#stockSearchResult').textContent,/검색 목록에 없는 경우와 다릅니다/);
 ui.change(()=>({rows:candles(5),currency:'USD',source:'Short history'}));await window.StockLookup.search('BRK/B');
 assert.equal(requests.at(-1).symbol,'BRK.B');assert.match(document.querySelector('#stockSearchResult').textContent,/이력 부족: 5개/);assert.match(document.querySelector('#stockSearchResult').textContent,/—/);
 const partial=window.StockLookup.analyze({symbol:'P'},{rows:candles(20).map(row=>({...row,volume:null})),currency:'USD'});
 assert.equal(partial.volume_ratio,null);assert.equal(partial.ema50,null);assert.equal(partial.macd,null);assert.equal(partial.score,null);assert.equal(partial.screening.sma200,null);assert.equal(partial.screening.high_52w,null);
 assert.equal(partial.return_30d,null);assert.notEqual(partial.rsi,null);
 const full=window.StockLookup.analyze({symbol:'FULL'},{rows:[...candles(260),...candles(2)]});
 assert.equal(full.history.length,260,'duplicate sessions cannot inflate indicator history');assert.notEqual(full.screening.high_52w,null);
 let resolve;ui.change(()=>new Promise(r=>resolve=r));await window.StockLookup.search('RACET');document.querySelector('[data-lookup-direct]').click();await tick();
 await window.StockLookup.search('no match phrase');resolve({rows:candles(),source:'Late'});await tick();
 assert.match(document.querySelector('#stockSearchResult').textContent,/일치하는 항목/,'late quote cannot overwrite a newer search');
 const kr=await setup('kr');await kr.window.StockLookup.search('알파신규');assert.equal(kr.requests[0].symbol,'0001A0');assert.match(kr.document.querySelector('#stockSearchResult').textContent,/코스닥/);
 const offline=await setup('us',true);await offline.window.StockLookup.search('ASPI');assert.ok(offline.document.querySelector('[data-lookup-direct]'));assert.match(offline.document.querySelector('#stockSearchStatus').textContent,/직접 조회/);
 console.log('Full listing lookup: names, ticker lookup, cache/refresh, favorites, privacy, failure states, short history, races and KR alphanumeric codes passed');
})().catch(error=>{console.error(error);process.exitCode=1});

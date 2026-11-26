// Offline UI integration: NODE_PATH=/tmp/stock-workbench-dom/node_modules node tests/stock_workbench_ui.cjs
const {parseHTML}=require('linkedom'),vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const tick=()=>new Promise(resolve=>setTimeout(resolve,5));
(async()=>{
 for(const market of ['us','kr']){
  const {window}=parseHTML(fs.readFileSync(`docs/${market}-stocks.html`,'utf8')),document=window.document;
  const opened=[],stored=new Map();let exported;
  const publicData={generated_at:'2026-11-25T02:00:00Z',economic_events:[{title:'공식 일정',original_title:'Release',at:'2099-11-25T13:30:00Z',source:'BLS',source_url:'https://www.bls.gov/',importance:'높음'}],macro_indicators:[{label:'WTI 현물',value:null,unit:'USD',note:'미수집',source:'FRED',source_url:'https://fred.stlouisfed.org'}],earnings:[{date:'2026-11-25',symbol:'TEST',name:'Test',session:'장전',eps_estimate:-.09,last_year_eps:1.2,estimates_count:2,source_url:'https://www.nasdaq.com/'}],filings:[],ipos:[{date:'2026-11-20',date_kind:'공모가 확정일',name:'<img src=x>',status:'공모가 확정',source_url:'javascript:alert(1)'}],sources:{bls:{label:'BLS',status:'정상 수집',url:'https://www.bls.gov/'}}};
  const context=vm.createContext({window,document,Date,Intl,Set,JSON,console,Blob:class extends Blob{constructor(...args){super(...args);exported=this;}},URL:{createObjectURL:()=> 'blob:test',revokeObjectURL:()=>{}},setTimeout:fn=>setTimeout(fn,0),setInterval:()=>0,localStorage:{getItem:key=>stored.get(key)||null,setItem:(key,value)=>stored.set(key,value)},fetch:async()=>({ok:true,json:async()=>publicData})});
  vm.runInContext(fs.readFileSync('docs/stock-workbench.js','utf8'),context);
  const report={currency:market==='us'?'USD':'KRW',rankings:[
   {symbol:'A',name:'Alpha',price:100,return_1d:2,rsi:0,volume_ratio:2,score:80,sector_ids:['t'],screening:{date:'2026-11-24',sma50:90,sma200:80,low_52w:99,drawdown_52w:-2,return_21:5,estimated_turnover:1000}},
   {symbol:'B',name:'Beta',price:90,return_1d:-2,rsi:60,volume_ratio:.5,score:40,sector_ids:['t'],screening:{date:'2026-11-24',sma50:100,drawdown_52w:null,return_21:null,estimated_turnover:900}},
   {symbol:'C',name:'=HYPERLINK("evil")',price:120,return_1d:0,rsi:null,volume_ratio:null,score:50,sector_ids:[],screening:{date:'2026-11-24',sma50:null,drawdown_52w:null}}],theme_board:{benchmark:'SPY',note:'설정된 분석종목 · 종가×거래량 추정',themes:[{id:'t',label:'Test',date:'2026-11-24',count:2,expected_count:3,return_1d:0,relative:-1,breadth:50,estimated_turnover:1900,turnover_coverage:2,concentration:52.6,leaders:[{symbol:'A',name:'Alpha',return_1d:2}]}],news:[{sector_id:'t',title:'<img src=x>',url:'javascript:alert(1)',source:'Source',published_at:'2026-11-25T01:00:00Z'}]}};
  window.StockWorkbench.render(report,row=>opened.push(row.symbol));await tick();
  const root=document.querySelector('#stockWorkbench');
  assert.match(root.textContent,/종가×거래량 추정/);assert.equal(root.querySelector('img'),null);assert.equal(root.querySelector('a[href^="javascript:"]'),null);
  root.querySelector('[data-stock="A"]').click();assert.deepEqual(opened,['A']);
  root.querySelector('[data-wb-tab="screener"]').click();
  assert.equal(root.querySelectorAll('#wbSearchResults tbody tr').length,3);
  root.querySelector('[data-favorite="A"]').click();assert.match(stored.get(`stock-favorites-${market}-v1`),/A/);
  const checkbox=root.querySelector('[name="favorites"]');checkbox.checked=true;checkbox.dispatchEvent(new window.Event('change',{bubbles:true}));
  assert.equal(root.querySelectorAll('#wbSearchResults tbody tr').length,1);
  root.querySelector('[data-preset="all"]').click();
  root.querySelector('[data-preset="oversold"]').click();assert.equal(root.querySelectorAll('#wbSearchResults tbody tr').length,1,'zero RSI valid, missing RSI excluded');
  root.querySelector('[data-preset="high"]').click();assert.equal(root.querySelectorAll('#wbSearchResults tbody tr').length,1,'missing 52-week metrics excluded');
  root.querySelector('[data-preset="low"]').click();assert.equal(root.querySelectorAll('#wbSearchResults tbody tr').length,1,'52-week low preset requires a valid low');
  root.querySelector('[data-preset="all"]').click();
  const period=root.querySelector('[name="returnPeriod"]');period.querySelectorAll('option').forEach(option=>option.removeAttribute('selected'));period.querySelector('[value="21"]').setAttribute('selected','');
  const minimum=root.querySelector('[name="returnMin"]');minimum.value='3';minimum.dispatchEvent(new window.Event('input',{bubbles:true}));assert.equal(root.querySelectorAll('#wbSearchResults tbody tr').length,1,'selected-period filter excludes missing returns');
  const maximum=root.querySelector('[name="returnMax"]');maximum.value='4';maximum.dispatchEvent(new window.Event('input',{bubbles:true}));assert.equal(root.querySelectorAll('#wbSearchResults tbody tr').length,0,'upper and lower return bounds combine');
  root.querySelector('[data-preset="all"]').click();
  const input=root.querySelector('[name="query"]');input.value='Beta';input.dispatchEvent(new window.Event('input',{bubbles:true}));assert.equal(root.querySelectorAll('#wbSearchResults tbody tr').length,1);
  root.querySelector('[data-preset="all"]').click();root.querySelector('[data-export]').click();
  const csv=await exported.text();assert.ok(csv.includes("'=HYPERLINK"),'spreadsheet formula injection is neutralized');assert.ok(csv.includes('관측일'));
  root.querySelector('[data-wb-tab="macro"]').click();assert.match(root.textContent,/공식 일정/);assert.match(root.querySelector('.wb-macro-cards strong').textContent,/—/);
  root.querySelector('[data-wb-tab="companies"]').click();assert.match(root.textContent,/전년 EPS/);assert.match(root.textContent,/実際|실제 당기 EPS/);assert.match(root.textContent,/공모가 확정일/);assert.equal(root.querySelector('img'),null);assert.equal(root.querySelector('a[href^="javascript:"]'),null);
  publicData.reported_earnings=[{symbol:'TEST',name:'Reported Test',period_type:'quarter',basis:'US-GAAP',period_start:'2026-07-01',period_end:'2026-09-30',eps:0,previous_eps:-1,eps_yoy:null,eps_state:'손익분기',revenue:1000000000,revenue_yoy:20,filed:'2026-11-01',source_url:'https://www.sec.gov/'},{symbol:'TEST',name:'Reported Test',period_type:'annual',basis:'US-GAAP',period_start:'2025-01-01',period_end:'2025-12-31',eps:3,previous_eps:2,eps_yoy:50,eps_state:'증가',revenue:2000000000,revenue_yoy:10,filed:'2026-02-01',source_url:'https://www.sec.gov/'}];
  root.querySelector('[data-wb-tab="companies"]').click();
  assert.equal(root.querySelectorAll('#wbReportedResults tbody tr').length,2);
  const periods=root.querySelector('[name="reportedPeriod"]');periods.querySelectorAll('option').forEach(o=>o.removeAttribute('selected'));periods.querySelector('[value="quarter"]').setAttribute('selected','');periods.dispatchEvent(new window.Event('change',{bubbles:true}));
  assert.equal(root.querySelectorAll('#wbReportedResults tbody tr').length,1);
  assert.equal(root.querySelector('#wbReportedResults tbody tr td:nth-child(3)').textContent,'0','zero reported EPS is not missing');
  const reportedQuery=root.querySelector('[name="reportedQuery"]');reportedQuery.value='NoMatch';reportedQuery.dispatchEvent(new window.Event('input',{bubbles:true}));assert.equal(root.querySelectorAll('#wbReportedResults tbody tr').length,0);
  publicData.sources.sec={label:'SEC',status:'미수집 · HTTP 403',cached:true,observed_at:'2026-11-25T01:00:00Z',cache_limit_hours:168};
  root.querySelector('[data-wb-tab="companies"]').click();
  assert.match(root.querySelector('.wb-source-warning').textContent,/이전 성공 수집본/);
  assert.match(root.querySelector('.wb-source-warning').textContent,/HTTP 403/);
  assert.match(root.querySelector('.wb-source-warning').textContent,/예정일 변경·새 공시/);
  console.log(market+': themes, chart links, strict filters, favorites, safe CSV, macro and company panels passed');
 }
})().catch(error=>{console.error(error);process.exitCode=1});

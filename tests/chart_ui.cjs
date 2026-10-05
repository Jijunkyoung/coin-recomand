// Offline DOM integration: npm install --prefix /tmp/chart-dom linkedom
// NODE_PATH=/tmp/chart-dom/node_modules node tests/chart_ui.cjs
const {parseHTML}=require('linkedom'),vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const tick=()=>new Promise(resolve=>setTimeout(resolve,15));
(async()=>{
 for(const name of ['kr-stocks.html','us-stocks.html','index.html']){
  const {window}=parseHTML(fs.readFileSync('docs/'+name,'utf8')),document=window.document,labels=[];
  window.location={href:''};window.HTMLElement.prototype.showModal=function(){this.open=true};window.HTMLElement.prototype.close=function(){this.open=false};
  window.HTMLElement.prototype.getBoundingClientRect=function(){return {width:900,height:620,left:0,top:0}};
  const ctx=new Proxy({fillText:text=>labels.push(String(text))},{get:(target,key)=>key in target?target[key]:()=>{},set:(target,key,value)=>(target[key]=value,true)});
  window.HTMLCanvasElement.prototype.getContext=()=>ctx;
  const makeRows=interval=>Array.from({length:200},(_,i)=>{const timestamp=Date.parse('2026-01-01T00:00:00Z')+i*(interval.endsWith('h')?3600000:86400000),session=new Date(timestamp).toISOString().slice(0,10),price=100+Math.sin(i/5)*10;return {timestamp,session,date:session,open:price-1,high:price+2,low:price-2,price,volume:1000+i}});
  let refreshes=0,checks=0;
  window.CoinAuth={user:{id:'owner'},stockChart:async body=>({rows:makeRows(body.interval),source:'fixture'}),coinChart:async body=>({rows:makeRows(body.interval),source:'fixture'}),syncBrokerageHoldings:async()=>{refreshes++;return{}},tossSyncStatus:async()=>{checks++;return{synced_at:'2026-10-06T00:00:05Z'}}};
  const context=vm.createContext({window,document,CustomEvent:window.CustomEvent,Date,Intl,Map,console,devicePixelRatio:1,requestAnimationFrame:fn=>setTimeout(fn,0),setTimeout:(fn,ms)=>setTimeout(fn,Math.min(ms,20)),clearTimeout,setInterval:()=>0,fetch:()=>new Promise(()=>{}),localStorage:{getItem:()=>null,setItem:()=>{}},location:window.location});
  vm.runInContext(fs.readFileSync('docs/chart-data.js','utf8'),context);vm.runInContext(fs.readFileSync('docs/'+(name==='index.html'?'app.js':'stock.js'),'utf8'),context);
  if(name==='index.html')vm.runInContext("openDetailChart({symbol:'BTC',market:'KRW-BTC',name:'BTC',price:100})",context);
  else{
   const market=name.startsWith('kr')?'kr':'us';context.sample={positions:[{broker:'toss',market,symbol:market==='kr'?'005930':'AAPL',name:'테스트종목',quantity:3,current_price:100,evaluation_amount:300,profit_loss:5,currency:market==='kr'?'KRW':'USD'}],synced_at:'2026-10-06T00:00:00Z',connections:{toss:{source:'direct',configured:true,ok:true}}};
   vm.runInContext('renderPortfolio(sample)',context);document.querySelector('#portfolioRefresh').click();await tick();assert.equal(refreshes,1);
   document.querySelector('[data-position]').click();
  }
  await tick();assert.equal(document.querySelector('#detailChart').hidden,false);assert.equal(document.querySelector('#'+(name==='index.html'?'chartDialog':'stockChartDialog')).open,true);
  for(const interval of ['1h','4h','1w','1d']){
   document.querySelector(`[data-interval="${interval}"]`).click();await tick();assert.match(document.querySelector('#chartDataStatus').textContent,name==='index.html'?/업비트/:/fixture/);assert.match(document.querySelector('#detailStats').textContent,/MACD/);
  }
  for(const value of ['0','30','50','70','100'])assert.ok(labels.includes(value),name+' RSI scale '+value);assert.ok(labels.includes('MACD(12,26,9)'));
  if(name!=='index.html'){
   vm.runInContext("sample.connections.toss={source:'local_pc',configured:true,ok:true,synced_at:'2026-10-06T00:00:00Z'};renderPortfolio(sample)",context);document.querySelector('#portfolioRefresh').click();await new Promise(resolve=>setTimeout(resolve,80));assert.equal(window.location.href,'coin-toss-sync://run');assert.equal(checks,1);assert.equal(refreshes,2);assert.match(document.querySelector('#portfolioRefreshStatus').textContent,/갱신 완료/);
   // A newer selected timeframe must win when earlier responses arrive late.
   let resolveOld;window.CoinAuth.stockChart=body=>body.interval==='1h'?new Promise(resolve=>resolveOld=resolve):Promise.resolve({rows:makeRows(body.interval),source:'new-selection'});
   vm.runInContext("detailStock={...detailStock,symbol:'NEW'};selectStockInterval('1h');selectStockInterval('4h')",context);await tick();resolveOld({rows:makeRows('1h'),source:'stale-response'});await tick();assert.match(document.querySelector('#chartDataStatus').textContent,/new-selection/);
  }
  console.log(name+': holding click, manual refresh, interval changes, left indicator scales and stale response protection passed');
 }
})().catch(error=>{console.error(error);process.exitCode=1});

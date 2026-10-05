const assert=require('node:assert/strict'), vm=require('node:vm'),fs=require('node:fs');
const context=vm.createContext({window:{},Date,Map,console});vm.runInContext(fs.readFileSync('docs/chart-data.js','utf8'),context);
const {aggregate,visible}=context.window.ChartData;
const rows=[];for(const day of ['2026-03-06','2026-03-09'])for(let i=0;i<7;i++)rows.push({timestamp:Date.parse(`${day}T14:30:00Z`)+i*3600000,date:`${day} ${i}`,session:day,open:10+i,high:12+i,low:9+i,price:11+i,volume:2});
const four=aggregate(rows,'4h');assert.equal(four.length,4);assert.equal(four[0].open,10);assert.equal(four[0].price,14);assert.equal(four[0].volume,8);assert.equal(four[1].volume,6);assert.equal(four[2].session,'2026-03-09');
const weekly=aggregate(rows,'1w');assert.equal(weekly.length,2);assert.equal(weekly[0].date,'2026-03-02');assert.equal(weekly[1].date,'2026-03-09');assert.equal(weekly[0].volume,14);
assert.equal(visible(rows,1).length,7);assert.equal(visible(rows,'all').length,14);
const {stripTypeScriptTypes}=require('node:module');let calls=0;
const stockContext=vm.createContext({Map,Date,Intl,URLSearchParams,AbortSignal,console,fetch:async url=>{calls++;if(url.includes('.KS'))return{ok:false};return{ok:true,json:async()=>({chart:{result:[{meta:{exchangeTimezoneName:'Asia/Seoul',currency:'KRW'},timestamp:[1773018000,1773021600],indicators:{quote:[{open:[10,null],high:[12,13],low:[9,10],close:[11,12],volume:[4,5]}]}}]}})}}});
vm.runInContext(stripTypeScriptTypes(fs.readFileSync('supabase/functions/kis-portfolio/stock-chart.ts','utf8')).replaceAll('export ','')+';globalThis.load=stockChart',stockContext);
(async()=>{await assert.rejects(stockContext.load({symbol:'../bad',market:'kr'}));assert.equal(calls,0);const data=await stockContext.load({symbol:'123456',market:'kr',interval:'1h'});assert.equal(data.rows.length,1);assert.equal(data.rows[0].price,11);const before=calls;await stockContext.load({symbol:'123456',market:'kr',interval:'4h'});assert.equal(calls,before);console.log('Chart OHLC aggregation, trading-session boundaries, null-candle filtering, symbol validation and quote caching passed.');})().catch(e=>{console.error(e);process.exitCode=1;});
(async()=>{
 const {webcrypto}=require('node:crypto');let handle,reads=0;
 const env={KIS_OWNER_USER_ID:'owner',SUPABASE_SERVICE_ROLE_KEY:'synthetic-service-key',SUPABASE_URL:'https://example.invalid'};
 const context=vm.createContext({Request,Response,URLSearchParams,TextEncoder,crypto:webcrypto,Date,Intl,Map,console,
  Deno:{env:{get:key=>env[key]},serve:fn=>handle=fn},
  createClient:()=>({auth:{getUser:async token=>({data:{user:{id:token,email:'test@example.invalid'}},error:null})},from:()=>{reads++;const query={select:()=>query,eq:(column,value)=>{if(column==='user_id')assert.equal(value,'owner');return query},maybeSingle:async()=>({data:{synced_at:'2026-03-09T00:00:00Z'},error:null})};return query}}),stockChart:async()=>({rows:[]}),coinChart:async()=>({rows:[]})});
 const code=stripTypeScriptTypes(fs.readFileSync('supabase/functions/kis-portfolio/index.ts','utf8')).replace(/^import .*;\n/gm,'');vm.runInContext(code,context);
 const request=token=>new Request('https://example.invalid',{method:'POST',headers:{'content-type':'application/json',...(token?{authorization:'Bearer '+token}:{})},body:JSON.stringify({action:'toss_sync_status'})});
 assert.equal((await handle(request())).status,400);assert.equal(reads,0);
 assert.equal((await handle(request('another-user'))).status,403);assert.equal(reads,0);
 const allowed=await handle(request('owner'));assert.equal(allowed.status,200);assert.equal((await allowed.json()).synced_at,'2026-03-09T00:00:00Z');assert.equal(reads,1);
 console.log('Manual sync status: anonymous and non-owner blocked; owner lookup is scoped to owner ID.');
})().catch(e=>{console.error(e);process.exitCode=1;});

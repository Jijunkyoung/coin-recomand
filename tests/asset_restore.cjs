const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {stripTypeScriptTypes}=require('node:module'),{webcrypto}=require('node:crypto');
const RealDate=Date;class Clock extends Date{constructor(...args){super(...(args.length?args:['2026-10-06T05:00:00Z']))}static now(){return RealDate.parse('2026-10-06T05:00:00Z')}}
let quotes=[],fx={base:'USD',quote:'KRW',date:'2026-10-02',rate:1400},coin=[];
const context=vm.createContext({Date:Clock,Map,Set,Promise,URLSearchParams,AbortSignal,AbortController,console,setTimeout,clearTimeout,stockChart:async()=>({rows:quotes}),fetch:async url=>({ok:true,json:async()=>url.includes('frankfurter')?fx:coin})});
vm.runInContext(stripTypeScriptTypes(fs.readFileSync('supabase/functions/kis-portfolio/asset-restore.ts','utf8')).replace(/^import .*;\n/gm,'').replaceAll('export ','')+';globalThis.restore={restoreDate,historicalPrice,prepareRestore,restoredSnapshot,saveRestore};',context);
const {restoreDate,historicalPrice,prepareRestore,restoredSnapshot,saveRestore}=context.restore;
const usd={broker:'toss',market:'us',symbol:'AAPL',name:'Apple',quantity:2,current_price:100,average_price:80};
const body={snapshot_date:'2026-10-05',confirmed:true,positions:[usd],fx_rate:1400,fx_date:'2026-10-02'};
function database({assets=[],stocks=[],error=null}={}){let writes=[];return {writes,from:table=>{let scoped=false;const q={select:()=>q,eq:(key,value)=>{assert.equal(key,'user_id');assert.equal(value,'owner');scoped=true;return q},order:()=>q,limit:()=>q,then:resolve=>{assert(scoped);resolve({data:table.startsWith('asset')?assets:stocks})},insert:async row=>{assert.equal(table,'asset_portfolio_daily_snapshots');assert.equal(row.user_id,'owner');writes.push(row);return {error}}};return q}}}
(async()=>{
 assert.equal(restoreDate('2026-10-05'),'2026-10-05');for(const date of ['2026-10-06','2026-10-07','2026-02-30','not-a-date','2025-10-05'])assert.throws(()=>restoreDate(date));
 const row=restoredSnapshot('owner',body);assert.equal(row.totals.us,200);assert.equal(row.positions[0].currency,'USD');assert.equal(row.positions[0].profit_loss,40);assert.equal(row.positions[0].record_source,'manual_restore');assert(row.warnings[0].includes('수동복원'));
 assert.throws(()=>restoredSnapshot('owner',{...body,confirmed:false}));assert.throws(()=>restoredSnapshot('owner',{...body,fx_rate:null}));assert.throws(()=>restoredSnapshot('owner',{...body,fx_date:'2026-10-06'}));assert.throws(()=>restoredSnapshot('owner',{...body,fx_date:'2026-09-25'}));assert.throws(()=>restoredSnapshot('owner',{...body,fx_date:'2026-02-30'}));
 for(const bad of [null,true,{},-1,Infinity,'NaN'])assert.throws(()=>restoredSnapshot('owner',{...body,positions:[{...usd,quantity:bad}]}));
 assert.throws(()=>restoredSnapshot('owner',{...body,positions:[usd,usd]}));assert.throws(()=>restoredSnapshot('owner',{...body,positions:[{...usd,current_price:0}]}));assert.throws(()=>restoredSnapshot('owner',{...body,positions:[{...usd,broker:'upbit'}]}));
 const zero=restoredSnapshot('owner',{...body,positions:[{...usd,quantity:0,current_price:null}],fx_rate:null});assert.equal(zero.positions.length,0);
 const cash=restoredSnapshot('owner',{...body,positions:[{broker:'upbit',market:'coin',symbol:'KRW',quantity:1000,current_price:700}],fx_rate:null});assert.equal(cash.totals.coin,1000);
 quotes=[{timestamp:Date.parse('2026-10-02T13:30:00Z'),price:90,session:'2026-10-02'},{timestamp:Date.parse('2026-10-05T13:30:00Z'),price:100,session:'2026-10-05'}];
 assert.equal((await historicalPrice(usd,'2026-10-05')).current_price,90,'US close after KST midnight must not leak future price');
 quotes=[{timestamp:Date.parse('2026-10-05T00:00:00Z'),price:70000,session:'2026-10-05'}];assert.equal((await historicalPrice({market:'kr',symbol:'005930'},'2026-10-05')).current_price,70000);
 coin=[{candle_date_time_utc:'2026-10-05T15:00:00',trade_price:900},{candle_date_time_utc:'2026-10-05T14:00:00',trade_price:800}];assert.equal((await historicalPrice({market:'coin',symbol:'BTC'},'2026-10-05')).current_price,800);
 const db=database({assets:[{snapshot_date:'2026-10-06',positions:[usd]},{snapshot_date:'2026-10-01',positions:[usd]}]});
 const prepared=await prepareRestore(db,'owner','2026-10-05');assert.equal(prepared.reference_date,'2026-10-01');assert.equal(prepared.positions.length,1);assert.equal(prepared.fx.rate,1400);
 await assert.rejects(()=>prepareRestore(database({assets:[{snapshot_date:'2026-10-05'}]}),'owner','2026-10-05'),/이미 정상 기록/);
 const saved=await saveRestore(db,'owner',body);assert.equal(saved.ok,true);assert.equal(db.writes.length,1);
 await assert.rejects(()=>saveRestore(database({error:{code:'23505'}}),'owner',body),/덮어쓰지/);
 // Stale/incomplete rows are repairable, but normal rows and concurrent changes are protected.
 const staleDate={snapshot_date:'2026-10-05',captured_at:'2026-10-05T00:10:00Z',complete:true,warnings:['toss: 이전 날짜 조회자료 사용'],positions:[usd]};
 const stalePlan=await prepareRestore(database({assets:[staleDate]}),'owner','2026-10-05');assert.equal(stalePlan.replace_captured_at,staleDate.captured_at);
 function repairDb(previous,updated=true){let writes=0;return {get writes(){return writes},from:table=>{assert.equal(table,'asset_portfolio_daily_snapshots');let updating=false;const scope={};const q={select:()=>q,eq:(key,value)=>{scope[key]=value;return q},update:snapshot=>{assert.equal(snapshot.user_id,'owner');updating=true;return q},maybeSingle:async()=>{assert.equal(scope.user_id,'owner');assert.equal(scope.snapshot_date,'2026-10-05');if(updating){assert.equal(scope.captured_at,staleDate.captured_at);writes++;return {data:updated?{snapshot_date:'2026-10-05'}:null}}return {data:previous}}};return q}}}
 const repair=repairDb(staleDate);await saveRestore(repair,'owner',{...body,replace_captured_at:staleDate.captured_at});assert.equal(repair.writes,1);
 const normal=repairDb({...staleDate,warnings:[],complete:true});await assert.rejects(()=>saveRestore(normal,'owner',{...body,replace_captured_at:staleDate.captured_at}),/정상 기록/);assert.equal(normal.writes,0);
 const moved=repairDb({...staleDate,captured_at:'2026-10-05T01:00:00Z'});await assert.rejects(()=>saveRestore(moved,'owner',{...body,replace_captured_at:staleDate.captured_at}),/변경/);assert.equal(moved.writes,0);
 await assert.rejects(()=>saveRestore(repairDb(staleDate,false),'owner',{...body,replace_captured_at:staleDate.captured_at}),/변경/);
 const empty=await prepareRestore(database(),'owner','2026-10-05');assert.equal(empty.positions.length,0);assert.equal(empty.reference_date,null);
 // Real handler authorization: no restore operation may run before owner JWT validation.
 let handle,operations=0;const env={KIS_OWNER_USER_ID:'owner',SUPABASE_SERVICE_ROLE_KEY:'synthetic-admin',KIS_SCHEDULER_KEY:'synthetic-scheduler'};
 const authContext=vm.createContext({Request,Response,URLSearchParams,TextEncoder,Date:Clock,Intl,Map,crypto:webcrypto,console,Deno:{env:{get:key=>env[key]},serve:fn=>handle=fn},createClient:()=>({auth:{getUser:async token=>({data:{user:{id:token}}})}}),prepareRestore:async(db,id)=>{assert.equal(id,'owner');operations++;return{}},saveRestore:async(db,id)=>{assert.equal(id,'owner');operations++;return{}}});
 vm.runInContext(stripTypeScriptTypes(fs.readFileSync('supabase/functions/kis-portfolio/index.ts','utf8')).replace(/^import .*;\n/gm,''),authContext);
 const request=(action,token,headers={})=>new Request('https://example.invalid',{method:'POST',headers:{'content-type':'application/json',...(token?{authorization:'Bearer '+token}:{}),...headers},body:JSON.stringify({action,snapshot_date:'2026-10-05'})});
 for(const action of ['asset_restore_prepare','asset_restore_save']){assert.equal((await handle(request(action))).status,400);assert.equal((await handle(request(action,'another-user'))).status,403);assert.equal((await handle(request(action,null,{'x-kis-scheduler-key':'synthetic-scheduler'}))).status,400);assert.equal(operations,action.endsWith('prepare')?0:1);assert.equal((await handle(request(action,'owner'))).status,200);}
 assert.equal(operations,2);
 const report=await import('../docs/portfolio-report.js');const plan=report.createReport({asset_history:[row]});assert.equal(plan.sheets[0].rows[0][7],'수동복원');assert.equal(plan.charts[0].points[0],280000);assert(plan.sheets[1].rows[0][15].startsWith('수동복원'));
 console.log('Missed-day restore: owner-only, past-date validation, no future closes, manual values, duplicate protection, reference selection and Excel provenance passed.');
})().catch(error=>{console.error(error);process.exitCode=1});

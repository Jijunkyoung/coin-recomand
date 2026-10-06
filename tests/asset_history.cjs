const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const {stripTypeScriptTypes}=require('node:module');
async function scenario({previous=null,stocks=[],connections={},coins={configured:false,positions:[]},fx={base:'USD',quote:'KRW',rate:1400,date:'2026-10-05'},warnings=[]}){
 let saved;const db={from:table=>{assert.equal(table,'asset_portfolio_daily_snapshots');const q={select:()=>q,eq:(column,value)=>{assert.equal(column,'user_id');assert.equal(value,'owner');return q},order:()=>q,limit:()=>q,maybeSingle:async()=>({data:previous}),upsert:async(s,opts)=>{assert.equal(s.user_id,'owner');assert.equal(opts.onConflict,'user_id,snapshot_date');saved=s;return{}},then:resolve=>resolve({data:[saved]})};return q}};
 const context=vm.createContext({Date,Map,console,AbortSignal,loadUpbitAssets:async()=>{if(coins instanceof Error)throw coins;return coins},fetch:async()=>{if(fx instanceof Error)throw fx;return {ok:true,json:async()=>fx}}});
 vm.runInContext(stripTypeScriptTypes(fs.readFileSync('supabase/functions/_shared/asset-history.ts','utf8')).replace(/^import .*;\n/gm,'').replaceAll('export ','')+';globalThis.capture=captureAssetHistory;',context);
 const result=await context.capture(db,'owner',stocks,connections,warnings);assert.equal(result.length,1);return saved;
}
(async()=>{
 const stock={broker:'toss',market:'us',symbol:'AAPL',currency:'USD',evaluation_amount:500};
 const good=await scenario({stocks:[stock],connections:{toss:{configured:true,ok:true}},coins:{configured:true,positions:[{broker:'upbit',market:'coin',symbol:'BTC',evaluation_amount:1400000}]}});assert.equal(good.positions.length,2);assert.equal(good.totals.us,500);assert.equal(good.totals.coin,1400000);assert.equal(good.fx_rate,1400);assert.equal(good.complete,true);
 const missing=await scenario({connections:{kis:{configured:true,ok:false}},coins:new Error('조회 실패'),fx:new Error('offline')});assert.equal(missing.complete,false);assert.equal(missing.fx_rate,null);assert(missing.warnings.some(w=>w.includes('누락')));
 const stale=await scenario({previous:{positions:[{broker:'kis',market:'kr',symbol:'005930',evaluation_amount:700000,source_captured_at:'2026-10-05T00:10:00Z'}],fx_rate:1390,fx_date:'2026-10-05',fx_source:'source'},connections:{kis:{configured:true,ok:false}},fx:new Error('offline')});assert.equal(stale.positions.length,1);assert.equal(stale.positions[0].source_captured_at,'2026-10-05T00:10:00Z');assert(stale.warnings.some(w=>w.includes('이전 조회자료')));assert.equal(stale.fx_rate,1390);
 const partial=await scenario({stocks:[stock],connections:{toss:{configured:true,ok:true}},warnings:['일부 거래소 조회 실패']});assert.equal(partial.complete,false);
 console.log('Daily assets: owner-scoped writes/reads, configured sources, currency totals, partial failures and stale provenance passed.');
})().catch(e=>{console.error(e);process.exitCode=1});

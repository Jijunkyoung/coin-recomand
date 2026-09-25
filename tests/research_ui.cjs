// Small offline DOM harness: verify empty, loaded, filter, and hostile text handling.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
class Element {
  constructor() { this.children=[]; this.textContent=''; this.value='3'; this.events={}; }
  append(child) { this.children.push(child); }
  replaceChildren() { this.children=[]; }
  addEventListener(type, fn) { this.events[type]=fn; }
}
async function run(ok) {
  const elements={};
  const document={querySelector:s=>elements[s] ||= new Element(), createElement:()=>new Element()};
  const data={updated_at:new Date().toISOString(),observed_days:1,costs:{fee_bps_per_side:5,slippage_bps_per_side:10},model:{status:'자료 부족'},
    comparisons:[{strategy:'existing',days:3,signals:1,completed:0,missing:0,mean_net_pct:null},{strategy:'trend',days:1,signals:2,completed:1,mean_net_pct:1.234}],
    recent:[{observed_at:new Date().toISOString(),market:'<img src=x onerror=alert(1)>',strategies:['existing'],prediction:null,status:'pending_entry',outcomes:{}}],limitations:['미검증'],
    surge_tracking:{signals:3,completed_24h:1,hit_rate_pct:25,mean_peak_pct:11.2,cause_note:'인과 확정 아님',feedback:{status:'자료 축적 중'},
      recent:[{observed_at:new Date().toISOString(),name:'<b>코인</b>',symbol:'SAFE',model_probability_pct:22,status:'closed',peak_gross_pct:11.2,
        outcomes:{'1':{status:'complete',gross_pct:1.2},'4':{status:'complete',gross_pct:3.4},'12':{status:'complete',gross_pct:8},'24':{status:'complete',gross_pct:10.1}},
        observed_drivers:{labels:['거래대금 확대']}}]}};
  const latest={surge_research:{status:'실험 학습 완료·수익성 미검증',confidence:'보통',observed_days:90,samples:500,positive_samples:20,
    target:'다음 24시간 급등',validation:{auc:.612,precision_top_10pct:18.5},
    candidates:[{name:'<img src=x>',symbol:'SAFE',model_probability_pct:12.34,reasons:['거래대금 증가'],volume_ratio_20d:2.1,relative_7d_pct:4.2,development_signal:'커밋 30건',related_events:[],watch_status:'관찰 후보',risks:[]}],limitations:['실험값']}};
  const context=vm.createContext({document,fetch:async url=>({ok,json:async()=>url.includes('latest')?latest:data}),Date,console});
  vm.runInContext(fs.readFileSync('docs/research.js','utf8'),context);
  await new Promise(resolve=>setImmediate(resolve));
  if (!ok) { assert.match(elements['#status'].textContent,/아직 없거나/); return; }
  assert.equal(elements['#comparisons'].children.length,1);
  assert.equal(elements['#comparisons'].children[0].children[4].textContent,'—');
  assert.equal(elements['#recent'].children[0].children[1].textContent,data.recent[0].market);
  assert.equal(elements['#surgeCandidates'].children.length,1);
  assert.equal(elements['#surgeCandidates'].children[0].children[1].textContent,'<img src=x> (SAFE)');
  assert.equal(elements['#surgeAuc'].textContent,'0.612');
  assert.equal(elements['#trackingRows'].children.length,1);
  assert.equal(elements['#trackingRows'].children[0].children[1].textContent,'<b>코인</b> (SAFE)');
  assert.equal(elements['#trackingHitRate'].textContent,'25.00%');
  elements['#horizon'].value='1'; elements['#horizon'].events.change();
  assert.equal(elements['#comparisons'].children[0].children[4].textContent,'1.23%');
}
Promise.all([run(true),run(false)]).then(()=>console.log('Research UI harness passed')).catch(e=>{console.error(e);process.exitCode=1;});

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
    recent:[{observed_at:new Date().toISOString(),market:'<img src=x onerror=alert(1)>',strategies:['existing'],prediction:null,status:'pending_entry',outcomes:{}}],limitations:['미검증']};
  const context=vm.createContext({document,fetch:async()=>({ok,json:async()=>data}),Date,console});
  vm.runInContext(fs.readFileSync('docs/research.js','utf8'),context);
  await new Promise(resolve=>setImmediate(resolve));
  if (!ok) { assert.match(elements['#status'].textContent,/아직 없거나/); return; }
  assert.equal(elements['#comparisons'].children.length,1);
  assert.equal(elements['#comparisons'].children[0].children[4].textContent,'—');
  assert.equal(elements['#recent'].children[0].children[1].textContent,data.recent[0].market);
  elements['#horizon'].value='1'; elements['#horizon'].events.change();
  assert.equal(elements['#comparisons'].children[0].children[4].textContent,'1.23%');
}
Promise.all([run(true),run(false)]).then(()=>console.log('Research UI harness passed')).catch(e=>{console.error(e);process.exitCode=1;});

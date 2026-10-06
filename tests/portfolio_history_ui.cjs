const {parseHTML}=require('linkedom'),fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const tick=()=>new Promise(resolve=>setTimeout(resolve,10));
(async()=>{
 const {window}=parseHTML('<html><body></body></html>'),document=window.document;
 window.HTMLElement.prototype.showModal=function(){this.open=true};window.HTMLElement.prototype.close=function(){this.open=false;this.dispatchEvent(new window.Event('close'))};
 let saved=null,downloaded=0,resolveLate;
 window.CoinAuth={user:{id:'owner'},assetExport:async()=>({asset_history:[{snapshot_date:'2026-10-01'}]}),restoreAssets:async(body,save)=>{if(save){saved=body;return {snapshot_date:body.snapshot_date,positions_count:body.positions.length}}return {snapshot_date:body.snapshot_date,reference_date:'2026-10-01',positions:[{broker:'toss',market:'us',symbol:'AAPL',name:'Apple',quantity:2,current_price:100}],fx:{rate:1400,date:'2026-10-02'}}}};
 window.PortfolioExcel={download:async()=>{downloaded++}};
 const context=vm.createContext({window,document,Date,Map,Set,console,CustomEvent:window.CustomEvent});vm.runInContext(fs.readFileSync('docs/portfolio-history.js','utf8'),context);
 await window.PortfolioHistory.open();const find=s=>document.querySelector(s),dialog=find('dialog');assert(dialog.open);assert(find('#restoreMissing').textContent.includes('2026-10-05'));
 find('#restoreDate').value='2026-10-05';find('#restoreDate').reportValidity=()=>true;find('#restoreLoad').click();await tick();assert.equal(find('#restoreRows').children.length,1);assert.equal(find('#restoreEditor').hidden,false);assert(find('#restoreSave').disabled);assert.match(find('#restoreTotal').textContent,/280,000/);
 find('#restoreConfirmed').checked=true;find('#restoreConfirmed').dispatchEvent(new window.Event('change'));assert.equal(find('#restoreSave').disabled,false);
 find('[data-field="quantity"]').value='3';find('[data-field="quantity"]').dispatchEvent(new window.Event('input',{bubbles:true}));assert.equal(find('#restoreConfirmed').checked,false);assert(find('#restoreSave').disabled);assert.match(find('#restoreTotal').textContent,/420,000/);
 find('#restoreConfirmed').checked=true;find('#restoreConfirmed').dispatchEvent(new window.Event('change'));find('#restoreForm').dispatchEvent(new window.Event('submit',{cancelable:true}));await tick();assert.equal(saved.positions[0].quantity,'3');assert.equal(saved.confirmed,true);assert.equal(saved.snapshot_date,'2026-10-05');assert.equal(find('#restoreEditor').hidden,true);assert.equal(find('#restoreDownload').hidden,false);find('#restoreDownload').click();await tick();assert.equal(downloaded,1);
 find('#restoreDate').dispatchEvent(new window.Event('change'));assert.equal(find('#restoreDownload').hidden,true);
 window.CoinAuth.restoreAssets=()=>new Promise(resolve=>resolveLate=resolve);find('#restoreLoad').click();await tick();window.CoinAuth.user=null;window.dispatchEvent(new window.CustomEvent('coin-auth-change'));assert.equal(dialog.open,false);resolveLate({snapshot_date:'2026-10-05',positions:[{symbol:'PRIVATE'}]});await tick();assert.equal(find('#restoreRows').children.length,0);
 // All three portfolio pages load the shared feature and offer its action.
 for(const file of ['index.html','us-stocks.html','kr-stocks.html'])assert(fs.readFileSync('docs/'+file,'utf8').includes('portfolio-history.js?v=20261006-4'));
 assert(fs.readFileSync('docs/stock.js','utf8').includes('id="portfolioRestore"'));assert(fs.readFileSync('docs/app.js','utf8').includes('id="cryptoRestore"'));
 console.log('Restore UI: missing dates, editable quantities, confirmation reset, save/download, date invalidation and logout race passed.');
})().catch(error=>{console.error(error);process.exitCode=1});

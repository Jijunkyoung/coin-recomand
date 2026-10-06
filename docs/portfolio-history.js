(() => {
  const escape = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
  const dateAt = offset => new Date(Date.now() + 9 * 3600000 + offset * 86400000).toISOString().slice(0, 10);
  let dialog, generation = 0, owner = null, prepared = null;
  const find = selector => dialog.querySelector(selector);
  const status = (text, error = false) => { find("#restoreStatus").textContent = text; find("#restoreStatus").classList.toggle("error", error); };
  function reset() { prepared = null; find("#restoreEditor").hidden = true; find("#restoreRows").innerHTML = ""; find("#restoreReference").textContent = ""; find("#restoreFx").value = ""; find("#restoreFxDate").value = ""; find("#restoreTotal").textContent = ""; find("#restoreConfirmed").checked = false; find("#restoreSave").disabled = true; }
  function validSession(id) { return id === generation && owner && window.CoinAuth?.user?.id === owner && dialog.open; }
  function row(item = {}) {
    const element = document.createElement("div"); element.className = "restore-row";
    const options = (values, selected) => values.map(([value,label]) => `<option value="${value}" ${value===selected?"selected":""}>${label}</option>`).join("");
    const input = (name, label, value, type="text", optional=false) => `<label>${label}<input data-field="${name}" type="${type}" value="${escape(value)}" ${type==="number"?'min="0" max="1000000000000000" step="any"':''} ${optional?"":"required"}></label>`;
    element.innerHTML = `<label>계좌<select data-field="broker">${options([["toss","토스증권"],["kis","한국투자증권"],["upbit","업비트"]],item.broker||"toss")}</select></label><label>시장<select data-field="market">${options([["us","미국주식 · USD"],["kr","국내주식 · KRW"],["coin","코인 · KRW"]],item.market||"us")}</select></label>${input("symbol","종목코드",item.symbol||"")}${input("name","종목명",item.name||"","text",true)}${input("quantity","당시 수량",item.quantity??0,"number")}${input("current_price","당시 가격",item.current_price??"","number")}${input("average_price","당시 평단 (선택)",item.average_price??"","number",true)}<button type="button" class="secondary-button restore-remove">제외</button><small class="restore-price-note">${escape(item.price_note||"누락일 가격을 직접 입력해 주세요.")}</small>`;
    element.querySelector(".restore-remove").addEventListener("click",()=>{element.remove();changed();});
    element.addEventListener("input",event=>{
      const field = event.target.dataset.field;
      if (["symbol","market"].includes(field)) { element.querySelector('[data-field="current_price"]').value=""; element.querySelector(".restore-price-note").textContent="종목을 변경했습니다. 누락일 가격을 직접 입력해 주세요."; }
      else if(field==="current_price") element.querySelector(".restore-price-note").textContent="직접 입력한 가격 · 해당 날짜 기준인지 확인해 주세요.";
      if(field==="market") element.querySelector('[data-field="broker"]').value=event.target.value==="coin"?"upbit":element.querySelector('[data-field="broker"]').value==="upbit"?"toss":element.querySelector('[data-field="broker"]').value;
      if(field==="broker" && event.target.value==="upbit") element.querySelector('[data-field="market"]').value="coin";
      changed();
    });
    find("#restoreRows").appendChild(element);
  }
  function positions() { return [...find("#restoreRows").children].map(element=>Object.fromEntries([...element.querySelectorAll("[data-field]")].map(input=>[input.dataset.field,input.value]))); }
  function changed() {
    find("#restoreConfirmed").checked=false; find("#restoreSave").disabled=true;
    const fx=Number(find("#restoreFx").value), items=positions();
    [...find("#restoreRows").children].forEach(element=>{element.querySelector('[data-field="current_price"]').required=Number(element.querySelector('[data-field="quantity"]').value)>0;});
    const invalid = items.some(item=>Number(item.quantity)>0 && !(Number(item.current_price)>0));
    const needsFx = items.some(item=>item.market==="us" && Number(item.quantity)>0);
    const total = items.reduce((sum,item)=>sum+Number(item.quantity)*Number(item.current_price)*(item.market==="us"?fx:1),0);
    find("#restoreTotal").textContent = invalid || needsFx && !(fx>0) || !Number.isFinite(total) ? "가격·환율 입력 후 총액 계산" : `복원 총액: ₩${total.toLocaleString("ko-KR",{maximumFractionDigits:0})} · 주식 예수금 제외`;
  }
  async function prepare() {
    const id=++generation, selected=find("#restoreDate").value; reset(); status("과거 시세와 참고 보유종목을 불러오는 중…"); find("#restoreLoad").disabled=true;
    try {
      const data=await window.CoinAuth.restoreAssets({snapshot_date:selected});
      if(!validSession(id))return;
      prepared=data; find("#restoreEditor").hidden=false; find("#restoreSave").textContent=data.replace_captured_at?"확인한 수량·가격으로 이전 자료 교체":"확인한 누락일 기록 저장";
      find("#restoreReference").textContent=data.reference_date?`${data.reference_date} 기록의 종목·수량을 참고용으로 불러왔습니다. ${selected} 당시 매수·매도·입출금에 맞게 수정해 주세요.`:"참고 기록이 없습니다. 당시 보유종목과 원화 잔액을 직접 추가해 주세요.";
      for(const item of data.positions||[])row(item);
      find("#restoreFx").value=data.fx?.rate??""; find("#restoreFxDate").value=data.fx?.date||selected; find("#restoreFxDate").max=selected;
      find("#restoreFxDate").min=new Date(Date.parse(`${selected}T00:00:00Z`)-7*86400000).toISOString().slice(0,10);
      changed(); status("수량·가격을 확인해 주세요. 보유하지 않았던 종목은 제외하고 빠진 종목은 추가할 수 있습니다.");
    } catch(error) { if(validSession(id))status(error.message,true); }
    finally { if(id===generation)find("#restoreLoad").disabled=false; }
  }
  async function save(event) {
    event.preventDefault(); if(!prepared || !find("#restoreConfirmed").checked)return;
    const id=generation, button=find("#restoreSave"); button.disabled=true;
    status("누락일 기록을 저장하는 중…");
    const payload={snapshot_date:prepared.snapshot_date,replace_captured_at:prepared.replace_captured_at,positions:positions(),fx_rate:find("#restoreFx").value||null,fx_date:find("#restoreFxDate").value,confirmed:true};
    find("#restoreEditor").querySelectorAll("input,select,button").forEach(element=>element.disabled=true);
    try {
      const result=await window.CoinAuth.restoreAssets(payload,true); if(!validSession(id))return;
      reset(); status(`${result.snapshot_date} · ${result.positions_count}개 자산을 복원했습니다. 엑셀 다운로드에 표·그래프로 반영됩니다.`);
      find("#restoreDownload").hidden=false;
      window.dispatchEvent(new CustomEvent("asset-history-restored",{detail:result}));
    } catch(error) { if(validSession(id)){status(error.message,true);button.disabled=false;} }
    finally { if(validSession(id))find("#restoreEditor").querySelectorAll("input,select,button").forEach(element=>element.disabled=false); }
  }
  function create() {
    dialog=document.createElement("dialog");dialog.className="auth-dialog restore-dialog";dialog.setAttribute("aria-labelledby","restoreTitle");
    dialog.innerHTML=`<div class="auth-shell"><div class="section-head"><h2 id="restoreTitle">누락일 기록 복원</h2><button class="secondary-button" type="button" id="restoreClose">닫기</button></div><p class="auth-help">자동 동기화는 오늘 자료를 갱신합니다. 빠진 과거 날짜는 당시 수량·가격을 확인해 별도 복원합니다. 정상 기록은 유지하고 누락·이전 자료로 표시된 기록만 복원할 수 있습니다.</p><p class="auth-help">가격 기준은 한국시간 날짜 종료 시점까지 완료된 주식 일봉·코인 1시간봉입니다. 미국주식·휴장일은 그 시점의 마지막 거래일 종가를 사용합니다. 가격 조회가 실패한 종목은 직접 입력하고, 주식 분할 등이 있었다면 당시 실제 가격을 확인해 주세요. 복원 기록은 자동 조회 기록과 구분해 표시합니다.</p><div class="restore-date-row"><label class="auth-field">누락 날짜<input type="date" id="restoreDate" min="${dateAt(-365)}" max="${dateAt(-1)}" value="${dateAt(-1)}" required></label><button type="button" class="secondary-button" id="restoreLoad">과거 시세 불러오기</button></div><p class="auth-help" id="restoreMissing"></p><form id="restoreForm"><div id="restoreEditor" hidden><p id="restoreReference" class="restore-reference"></p><div id="restoreRows"></div><button type="button" class="secondary-button" id="restoreAdd">종목·원화 잔액 추가</button><div class="restore-fx"><label class="auth-field">1달러당 원화 환율<input type="number" id="restoreFx" min="0.000001" step="any" placeholder="미국주식이 있으면 필수"></label><label class="auth-field">환율 기준일<input type="date" id="restoreFxDate"></label></div><p id="restoreTotal"></p><label class="restore-confirm"><input type="checkbox" id="restoreConfirmed" required> 당시 모든 연결 계좌의 종목·수량·가격·평단·원화 잔액과 환율을 확인했습니다. 주식 예수금은 제외합니다.</label><button class="auth-submit" type="submit" id="restoreSave" disabled>확인한 누락일 기록 저장</button></div></form><p id="restoreStatus" class="auth-status" aria-live="polite"></p><button type="button" class="secondary-button" id="restoreDownload" hidden>복원 기록 포함 엑셀 다운로드</button></div>`;
    document.body.appendChild(dialog);
    find("#restoreClose").addEventListener("click",()=>dialog.close());
    dialog.addEventListener("close",()=>{generation++;reset();find("#restoreLoad").disabled=false;});
    find("#restoreDate").addEventListener("change",()=>{generation++;reset();status("");find("#restoreLoad").disabled=false;find("#restoreDownload").hidden=true;});
    find("#restoreLoad").addEventListener("click",()=>{if(find("#restoreDate").reportValidity())prepare();});
    find("#restoreAdd").addEventListener("click",()=>{if(find("#restoreRows").children.length>=500)return status("최대 500개까지 입력할 수 있습니다.",true);row();changed();});
    find("#restoreFx").addEventListener("input",changed);find("#restoreFxDate").addEventListener("input",changed);
    find("#restoreConfirmed").addEventListener("change",()=>{find("#restoreSave").disabled=!prepared||!find("#restoreConfirmed").checked;});
    find("#restoreForm").addEventListener("submit",save);
    find("#restoreDownload").addEventListener("click",async event=>{const button=event.currentTarget;button.disabled=true;try{await window.PortfolioExcel.download();status("복원 기록을 포함한 엑셀을 다운로드했습니다.");}catch(error){status(error.message,true);}finally{button.disabled=false;}});
  }
  async function open() {
    if(!window.CoinAuth?.user)throw new Error("계좌 소유자로 로그인해 주세요.");
    if(!dialog)create(); owner=window.CoinAuth.user.id; const id=++generation;reset();find("#restoreLoad").disabled=false;find("#restoreDownload").hidden=true;status("");dialog.showModal();
    find("#restoreMissing").textContent="기존 기록을 확인하는 중…";
    try {
      const data=await window.CoinAuth.assetExport();if(!validSession(id))return;
      const dates=new Set((data.asset_history||[]).filter(item=>item.complete!==false && !(item.warnings||[]).some(w=>/이전 날짜 조회자료|이전 조회자료|이전 환율|계좌자료 누락|조회 실패|마지막 동기화가/.test(w))).map(item=>item.snapshot_date));
      const all=[...(data.asset_history||[]),...(data.history||[])].map(item=>item.snapshot_date).sort();
      const start=all[0]||dateAt(-1), missing=[];
      for(let offset=-1;offset>=-365;offset--){const date=dateAt(offset);if(date<start)break;if(!dates.has(date))missing.push(date);}
      find("#restoreMissing").textContent=missing.length?`기록 시작일 이후 누락·이전 자료: ${missing.slice(0,10).join(", ")}${missing.length>10?` 외 ${missing.length-10}일`:""}. 다른 과거 날짜도 직접 선택할 수 있습니다.`:"기록 시작일 이후 확인된 누락일이 없습니다. 기록을 시작하기 전 날짜도 직접 선택해 복원할 수 있습니다.";
      if(missing.length)find("#restoreDate").value=missing[0];
    }catch(error){if(validSession(id)){find("#restoreMissing").textContent="";status(error.message,true);find("#restoreLoad").disabled=true;}}
  }
  window.addEventListener("coin-auth-change",()=>{if(dialog && window.CoinAuth?.user?.id!==owner){generation++;owner=null;dialog.close();reset();status("");find("#restoreMissing").textContent="";}});
  window.PortfolioHistory={open};
})();

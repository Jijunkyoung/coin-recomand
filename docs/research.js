const labels = {existing:"기존 추천",trend:"단순 추세",attention_news:"관심 확산·공식 뉴스",learned:"실험 학습 모델",universe:"관측 전체"};
const states = {pending_entry:"다음 관측 진입 대기",entry_missing:"진입 가격 누락",tracking:"추적 중",closed:"평가 종료"};
const percent = n => Number.isFinite(n) ? `${n.toFixed(2)}%` : "—";
const integer = n => Number.isFinite(n) ? n.toLocaleString("ko-KR") : "—";
function row(target, values) {
  const tr = document.createElement("tr");
  values.forEach(value => { const td=document.createElement("td"); td.textContent=String(value); tr.append(td); });
  target.append(tr);
}
async function loadSurge() {
  try {
    const response = await fetch("data/latest.json", {cache:"no-store"});
    if (!response.ok) throw new Error("unavailable");
    const report = await response.json();
    const data = report.surge_research;
    if (!data) throw new Error("missing");
    document.querySelector("#surgeStatus").textContent = `${data.status} · ${data.observed_days || 0}개 과거 날짜를 시간순으로 학습했습니다.`;
    document.querySelector("#surgeConfidence").textContent = `신뢰도 ${data.confidence || "낮음"}`;
    document.querySelector("#surgeSamples").textContent = integer(data.samples);
    document.querySelector("#surgePositives").textContent = integer(data.positive_samples);
    document.querySelector("#surgeAuc").textContent = Number.isFinite(data.validation?.auc) ? data.validation.auc.toFixed(3) : "—";
    document.querySelector("#surgePrecision").textContent = percent(data.validation?.precision_top_10pct);
    document.querySelector("#surgeTarget").textContent = `급등 판정: ${data.target}`;
    const body = document.querySelector("#surgeCandidates"); body.replaceChildren();
    data.candidates.forEach((candidate,index) => {
      const context = [candidate.development_signal, ...(candidate.related_events || []).map(event => `${event.title} [${event.importance}]`)].filter(Boolean).join(" · ") || "확인된 보조 신호 없음";
      const risk = [candidate.watch_status, ...(candidate.risks || [])].filter(Boolean).join(" · ");
      row(body,[index+1,`${candidate.name} (${candidate.symbol})`,percent(candidate.model_probability_pct),(candidate.reasons || []).join(" · "),`${candidate.volume_ratio_20d}×`,percent(candidate.relative_7d_pct),context,risk]);
    });
    if (!data.candidates.length) row(body,["—","학습 자료 축적 중","—","—","—","—","—","—"]);
    const limitations = document.querySelector("#surgeLimitations"); limitations.replaceChildren();
    (data.limitations || []).forEach(text=>{const li=document.createElement("li");li.textContent=text;limitations.append(li);});
  } catch {
    document.querySelector("#surgeStatus").textContent="급등 연구 결과가 아직 없거나 불러오지 못했습니다. 기존 추천에는 영향이 없습니다.";
    document.querySelector("#surgeConfidence").textContent="자료 확인 필요";
  }
}
async function loadResearch() {
  try {
    const response = await fetch("data/research.json", {cache:"no-store"});
    if (!response.ok) throw new Error("unavailable");
    const data = await response.json();
    const date = new Date(data.updated_at);
    const age = Date.now() - date.getTime();
    document.querySelector("#status").textContent = `관측 ${data.observed_days}일 · 마지막 기록 ${date.toLocaleString("ko-KR",{timeZone:"Asia/Seoul"})} KST${age > 6*3600000 ? " · 6시간 이상 지연: 수집 상태 확인 필요" : ""}`;
    const m = data.model || {};
    document.querySelector("#model").textContent = `학습: ${m.status || "자료 부족"} · 사용 가능 ${m.samples || 0}건 / ${m.days || 0}일 (최소 200건 / 60일)`;
    document.querySelector("#costs").textContent = `가정 비용(편도): 수수료 ${data.costs.fee_bps_per_side/100}% + 슬리피지 ${data.costs.slippage_bps_per_side/100}%. 실제 거래소·주문 크기에 따라 다릅니다.`;
    function render() {
      const body=document.querySelector("#comparisons"); body.replaceChildren();
      data.comparisons.filter(r=>r.days===Number(document.querySelector("#horizon").value)).forEach(r=>row(body,[labels[r.strategy],r.signals,r.completed,r.missing,percent(r.mean_net_pct),percent(r.win_rate),percent(r.excess_btc_pct),percent(r.double_cost_pct),percent(r.worst_sampled_drawdown_pct)]));
    }
    render(); document.querySelector("#horizon").addEventListener("change",render);
    const recent=document.querySelector("#recent");
    data.recent.forEach(r=>row(recent,[new Date(r.observed_at).toLocaleString("ko-KR",{timeZone:"Asia/Seoul"}),r.market,r.strategies.filter(s=>s!=="universe").map(s=>labels[s]).join(" · ") || "관측만",Number.isFinite(r.prediction)?percent(r.prediction*100):"자료 부족",states[r.status],percent(r.outcomes["3"]?.net_pct)]));
    data.limitations.forEach(text=>{const li=document.createElement("li");li.textContent=text;document.querySelector("#limitations").append(li);});
  } catch {
    document.querySelector("#status").textContent="연구 기록이 아직 없거나 불러오지 못했습니다. 첫 수집 완료 후 표시됩니다. 성과를 0%로 간주하지 마세요.";
  }
}
Promise.all([loadSurge(),loadResearch()]);

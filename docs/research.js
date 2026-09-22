const labels = {existing:"기존 추천",trend:"단순 추세",attention_news:"관심 확산·공식 뉴스",learned:"실험 학습 모델",universe:"관측 전체"};
const states = {pending_entry:"다음 관측 진입 대기",entry_missing:"진입 가격 누락",tracking:"추적 중",closed:"평가 종료"};
const percent = n => Number.isFinite(n) ? `${n.toFixed(2)}%` : "—";
function row(target, values) {
  const tr = document.createElement("tr");
  values.forEach(value => { const td=document.createElement("td"); td.textContent=String(value); tr.append(td); });
  target.append(tr);
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
loadResearch();

// Shared pure report model; deployed verbatim to the Edge Function for PC exports.
const numeric = value => value == null || value === "" || !Number.isFinite(Number(value)) ? null : Number(value);
const serial = iso => iso && Number.isFinite(Date.parse(`${String(iso).slice(0,10)}T00:00:00Z`)) ? Date.parse(`${String(iso).slice(0,10)}T00:00:00Z`) / 86400000 + 25569 : null;
const broker = id => ({kis:"한국투자증권",toss:"토스증권",upbit:"업비트"}[id] || String(id || ""));
const market = id => ({kr:"국내",us:"미국",coin:"코인"}[id] || String(id || ""));
const formula = (text,value) => ({formula:text,value:value == null ? "n.a." : value});
export function createReport(portfolio) {
  const byDate = new Map();
  for (const snapshot of portfolio?.history || []) byDate.set(snapshot.snapshot_date,{...snapshot,fx_rate:null,complete:false,warnings:["기존 주식기록: 코인·환율 미기록, 통합 총액 미산출"]});
  for (const snapshot of portfolio?.asset_history || []) byDate.set(snapshot.snapshot_date,snapshot);
  const history = [...byDate.values()].filter(s=>/^\d{4}-\d{2}-\d{2}$/.test(s.snapshot_date)).sort((a,b)=>a.snapshot_date.localeCompare(b.snapshot_date)).slice(-366);
  if (!history.length) throw new Error("다운로드할 일별 자산 기록이 아직 없습니다.");
  const amounts = s => Object.fromEntries(["kr","us","coin"].map(id=>[id,(s.positions||[]).filter(p=>p.market===id).reduce((a,p)=>a+(numeric(p.evaluation_amount)||0),0)]));
  const daily = history.map((s,i)=>{
    const r=i+2,a=amounts(s),fx=numeric(s.fx_rate),status=s.complete===false?"자료누락":s.warnings?.length?"안내 확인":"정상";
    const total=s.complete===false || a.us!==0&&!(fx>0) ? null : a.kr+a.coin+a.us*(fx||0);
    return [serial(s.snapshot_date),a.kr,a.us,a.coin,fx,formula(`IF(H${r}="자료누락","n.a.",IF(C${r}=0,SUM(B${r},D${r}),IF(ISNUMBER(E${r}),SUM(B${r},D${r},C${r}*E${r}),"n.a.")))`,total),(s.positions||[]).length,status,serial(s.fx_date),(s.warnings||[]).join(" / ")+(s.fx_source?` / 환율: ${s.fx_source}`:""),s.snapshot_date];
  });
  function details(s,positions,start) {
    return positions.map((p,i)=>{
      const r=start+i,fx=numeric(s.fx_rate),amount=numeric(p.evaluation_amount),converted=p.currency==="KRW"?amount:fx>0&&amount!=null?amount*fx:null;
      return [serial(s.snapshot_date),broker(p.broker),market(p.market),String(p.symbol||""),String(p.name||p.symbol||""),numeric(p.quantity),numeric(p.average_price),numeric(p.current_price),amount,numeric(p.profit_loss),numeric(p.profit_rate)==null?null:Number(p.profit_rate)/100,numeric(p.daily_change_rate)==null?null:Number(p.daily_change_rate)/100,p.currency,fx,formula(`IF(M${r}="KRW",I${r},IF(ISNUMBER(N${r}),I${r}*N${r},"n.a."))`,converted),p.source_captured_at||s.captured_at||""];
    });
  }
  const rows=[];for(const s of history)rows.push(...details(s,s.positions||[],rows.length+2));
  if(rows.length>1048575)throw new Error("기록이 엑셀 시트의 최대 행 수를 초과했습니다.");
  const latest=history.at(-1),latestTotals=amounts(latest),end=history.length+1;
  const current=details(latest,[...(latest.positions||[])].sort((a,b)=>{
    const value=p=>(numeric(p.evaluation_amount)||0)*(p.currency==="USD"?(numeric(latest.fx_rate)||0):1);return value(b)-value(a);
  }),2);
  const summary=[{ref:"B5",...formula(`'일별총액'!A${end}`,serial(latest.snapshot_date))},{ref:"A8",...formula(`'일별총액'!F${end}`,daily.at(-1)[5].value)},{ref:"D8",...formula(`'일별총액'!B${end}`,latestTotals.kr)},{ref:"G8",...formula(`'일별총액'!C${end}`,latestTotals.us)},{ref:"J8",...formula(`'일별총액'!D${end}`,latestTotals.coin)}];
  return {date:latest.snapshot_date,days:history.length,records:rows.length,summary,sheets:[{path:"xl/worksheets/sheet2.xml",table:"DailyAssets",columns:11,rows:daily},{path:"xl/worksheets/sheet3.xml",table:"AssetRecords",columns:16,rows},{path:"xl/worksheets/sheet4.xml",table:"CurrentAssets",columns:16,rows:current}],charts:[{path:"xl/drawings/charts/chart1.xml",category:"'일별총액'!$K$2:$K$"+end,values:"'일별총액'!$F$2:$F$"+end,labels:history.map(s=>s.snapshot_date),points:daily.map(r=>typeof r[5].value==="number"?r[5].value:null)},{path:"xl/drawings/charts/chart2.xml",category:"'최근보유종목'!$E$2:$E$"+Math.max(2,Math.min(current.length,10)+1),values:"'최근보유종목'!$O$2:$O$"+Math.max(2,Math.min(current.length,10)+1),labels:current.slice(0,10).map(r=>r[4]),points:current.slice(0,10).map(r=>typeof r[14].value==="number"?r[14].value:null)}]};
}

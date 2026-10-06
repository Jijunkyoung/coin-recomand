import { loadUpbitAssets } from "./upbit-assets.ts";

type Asset = Record<string, any>;
type Connection = { configured: boolean; ok: boolean; source?: string; synced_at?: string | null };
const kstDate = (value = new Date()) => new Date(value.getTime() + 9 * 3600000).toISOString().slice(0, 10);
let fxCache: { rate: number; date: string; source: string; cached: number } | null = null;
export async function exchangeRate() {
  if (fxCache && Date.now() - fxCache.cached < 30 * 60 * 1000) return fxCache;
  const response = await fetch("https://api.frankfurter.dev/v2/rate/USD/KRW", { signal: AbortSignal.timeout(8000) });
  if (!response.ok) throw new Error("달러 환율을 조회하지 못했습니다.");
  const data = await response.json(), rate = Number(data.rate);
  if (data.base !== "USD" || data.quote !== "KRW" || !Number.isFinite(rate) || rate <= 0 || !/^\d{4}-\d{2}-\d{2}$/.test(data.date) || data.date > kstDate()) throw new Error("달러 환율 응답이 올바르지 않습니다.");
  fxCache = { rate, date: data.date, source: "https://api.frankfurter.dev/v2/rate/USD/KRW", cached: Date.now() };
  return fxCache;
}

// Runs only after the caller has authenticated the owner or the existing local sync key.
export async function captureAssetHistory(supabase: any, userId: string, stocks: Asset[], connections: Record<string, Connection>, stockWarnings: string[] = []) {
  const capturedAt = new Date().toISOString(), date = kstDate(), warnings = [...stockWarnings];
  const { data: previous, error: previousError } = await supabase.from("asset_portfolio_daily_snapshots").select("positions,fx_rate,fx_date,fx_source").eq("user_id", userId).order("snapshot_date", { ascending: false }).limit(1).maybeSingle();
  if (previousError) throw new Error(`자산기록 읽기 실패: ${previousError.message}`);
  const prior = Array.isArray(previous?.positions) ? previous.positions : [];
  let complete = stockWarnings.length === 0;
  let positions = stocks.map(item => ({ ...item, source_captured_at: connections[item.broker]?.synced_at || capturedAt }));
  for (const [broker, connection] of Object.entries(connections)) {
    if (!connection.configured) continue;
    if (!connection.ok) {
      const saved = prior.filter((item: Asset) => item.broker === broker);
      positions.push(...saved);
      warnings.push(`${broker}: ${saved.length ? "이전 조회자료 사용" : "계좌자료 누락"}`);
      if (!saved.length) complete = false;
    }
    if (connection.ok && connection.synced_at && kstDate(new Date(connection.synced_at)) !== date) warnings.push(`${broker}: 이전 날짜 조회자료 사용`);
  }
  try {
    const coins = await loadUpbitAssets();
    if (coins.configured) positions.push(...coins.positions.map(item => ({ ...item, source_captured_at: capturedAt })));
    else warnings.push("업비트 미연결: 코인 미포함");
  } catch (error) {
    const saved = prior.filter((item: Asset) => item.broker === "upbit");
    positions.push(...saved);
    warnings.push(`업비트: ${error instanceof Error ? error.message : "조회 실패"}${saved.length ? " / 이전 조회자료 사용" : " / 계좌자료 누락"}`);
    if (!saved.length) complete = false;
  }
  positions = [...new Map(positions.map(item => [`${item.broker}:${item.market}:${item.symbol}`, item])).values()];
  let fx = null;
  try { fx = await exchangeRate(); } catch {
    if (previous?.fx_rate > 0 && previous.fx_date && Date.parse(`${date}T00:00:00Z`) - Date.parse(`${previous.fx_date}T00:00:00Z`) <= 7 * 86400000) {
      fx = { rate: previous.fx_rate, date: previous.fx_date, source: previous.fx_source };
      warnings.push("환율 조회 실패: 이전 환율 사용");
    } else warnings.push("환율 누락: 미국주식 원화 환산 불가");
  }
  const amount = (market: string) => positions.filter(item => item.market === market).reduce((sum, item) => sum + Number(item.evaluation_amount || 0), 0);
  const totals = { kr: amount("kr"), us: amount("us"), coin: amount("coin") };
  const snapshot = { user_id: userId, snapshot_date: date, captured_at: capturedAt, positions, totals, fx_rate: fx?.rate || null, fx_date: fx?.date || null, fx_source: fx?.source || null, complete, warnings };
  const { error: saveError } = await supabase.from("asset_portfolio_daily_snapshots").upsert(snapshot, { onConflict: "user_id,snapshot_date" });
  if (saveError) throw new Error(`일별 자산기록 저장 실패: ${saveError.message}`);
  const { data: history, error: historyError } = await supabase.from("asset_portfolio_daily_snapshots").select("snapshot_date,captured_at,positions,totals,fx_rate,fx_date,fx_source,complete,warnings").eq("user_id", userId).order("snapshot_date", { ascending: false }).limit(366);
  if (historyError) throw new Error(`자산기록 조회 실패: ${historyError.message}`);
  return (history || []).reverse();
}

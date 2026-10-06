import { stockChart } from "./stock-chart.ts";
const kstDate = (date = new Date()) => new Date(date.getTime() + 9 * 3600000).toISOString().slice(0, 10);
export function restoreDate(value: unknown) {
  const date = String(value || ""), parsed = Date.parse(`${date}T00:00:00Z`);
  const age = (Date.parse(`${kstDate()}T00:00:00Z`) - parsed) / 86400000;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isFinite(parsed) || new Date(parsed).toISOString().slice(0, 10) !== date || age < 1 || age > 365) throw new Error("누락일은 최근 365일 중 어제까지의 날짜를 선택해 주세요.");
  return date;
}
export async function historicalPrice(item: Record<string, any>, date: string, signal?: AbortSignal) {
  const cutoff = Date.parse(`${date}T15:00:00Z`); // Next midnight in Korea.
  if (item.market === "coin") {
    if (item.symbol === "KRW") return { current_price: 1, price_at: new Date(cutoff).toISOString(), price_note: "원화 잔액: 단가 1원" };
    if (!/^[A-Z0-9]+$/.test(item.symbol)) throw new Error("코인 코드 확인 필요");
    const query = new URLSearchParams({ market: `KRW-${item.symbol}`, count: "2", to: new Date(cutoff).toISOString() });
    const response = await fetch(`https://api.upbit.com/v1/candles/minutes/60?${query}`, { signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(8000)]) : AbortSignal.timeout(8000) });
    if (!response.ok) throw new Error("과거 코인 시세 조회 실패");
    const candles = await response.json();
    const row = Array.isArray(candles) && candles.find(row => Date.parse(row.candle_date_time_utc + "Z") + 3600000 <= cutoff && Number(row.trade_price) > 0);
    if (!row || cutoff - Date.parse(row.candle_date_time_utc + "Z") > 7 * 86400000) throw new Error("해당 날짜 코인 시세 없음");
    const at = new Date(Date.parse(row.candle_date_time_utc + "Z") + 3600000).toISOString();
    return { current_price: Number(row.trade_price), price_at: at, price_note: `업비트 마지막 완료 1시간봉 · ${at}` };
  }
  const chart = await stockChart({ market: item.market, symbol: item.symbol, interval: "1d" }, signal) as { rows: any[] };
  // A US session closing after Korean midnight belongs to the following Korean valuation date.
  const row = [...chart.rows].reverse().find(row => row.timestamp + 6.5 * 3600000 <= cutoff && row.price > 0);
  if (!row || cutoff - row.timestamp > 7 * 86400000) throw new Error("해당 날짜 이전 거래일 종가 없음");
  return { current_price: row.price, price_at: new Date(row.timestamp + 6.5 * 3600000).toISOString(), price_note: `Yahoo Finance ${row.session} 거래일 종가` };
}
export const needsRestore = (row: any) => row?.complete === false || (row?.warnings || []).some((warning: string) => /이전 날짜 조회자료|이전 조회자료|이전 환율|계좌자료 누락|조회 실패|마지막 동기화가/.test(warning));
export async function prepareRestore(db: any, userId: string, value: unknown) {
  const date = restoreDate(value);
  const { data: assets, error } = await db.from("asset_portfolio_daily_snapshots").select("snapshot_date,captured_at,positions,complete,warnings").eq("user_id", userId).order("snapshot_date", { ascending: false }).limit(366);
  if (error) throw new Error("기존 자산기록 조회 실패");
  const existing = (assets || []).find((row: any) => row.snapshot_date === date);
  if (existing && !needsRestore(existing)) throw new Error("이미 정상 기록된 날짜입니다. 기존 기록은 덮어쓰지 않습니다.");
  const { data: stocks, error: stockError } = await db.from("stock_portfolio_daily_snapshots").select("snapshot_date,positions").eq("user_id", userId).order("snapshot_date", { ascending: false }).limit(366);
  if (stockError) throw new Error("기존 주식기록 조회 실패");
  const records = new Map<string, any>();
  for (const row of stocks || []) records.set(row.snapshot_date, row);
  for (const row of assets || []) records.set(row.snapshot_date, row);
  const ordered = [...records.values()].sort((a, b) => a.snapshot_date.localeCompare(b.snapshot_date));
  const reference = ordered.filter(row => row.snapshot_date <= date).at(-1) || ordered[0];
  const positions = (reference?.positions || []).map((item: any) => ({ ...item, current_price: null, price_at: null, price_note: "과거 가격을 직접 입력해 주세요." }));
  const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 35000);
  let index = 0;
  const cache = new Map<string, Promise<any>>();
  let coinQueue = Promise.resolve();
  async function quote(item: any) {
    if (item.market !== "coin") return historicalPrice(item, date, controller.signal);
    const job = coinQueue.then(() => historicalPrice(item, date, controller.signal));
    coinQueue = job.then(() => undefined, () => undefined).then(() => new Promise<void>(resolve => setTimeout(resolve, 150)));
    return job;
  }
  try { await Promise.all(Array.from({ length: 3 }, async () => {
    while (index < positions.length && !controller.signal.aborted) {
      const item = positions[index++], key = `${item.market}:${item.symbol}`;
      if (!cache.has(key)) cache.set(key, quote(item));
      try { Object.assign(item, await cache.get(key)); }
      catch { item.price_note = "과거 가격 조회 실패: 해당 날짜 가격을 직접 입력해 주세요."; }
    }
  })); } finally { clearTimeout(timeout); }
  let fx = null;
  try {
    const response = await fetch(`https://api.frankfurter.dev/v2/rate/USD/KRW?date=${date}`, { signal: AbortSignal.timeout(8000) });
    const data = response.ok ? await response.json() : null;
    if (data?.base === "USD" && data.quote === "KRW" && Number.isFinite(Number(data.rate)) && data.rate > 0 && /^\d{4}-\d{2}-\d{2}$/.test(data.date) && data.date <= date && Date.parse(`${date}T00:00:00Z`) - Date.parse(`${data.date}T00:00:00Z`) <= 7 * 86400000) fx = { rate: data.rate, date: data.date };
  } catch { /* Owner can enter and confirm the historical rate. */ }
  return { snapshot_date: date, replace_captured_at: existing?.captured_at || null, reference_date: reference?.snapshot_date || null, positions, fx };
}
export function restoredSnapshot(userId: string, body: Record<string, any>) {
  const date = restoreDate(body.snapshot_date);
  if (body.confirmed !== true) throw new Error("당시 보유수량과 가격을 확인한 뒤 저장해 주세요.");
  if (!Array.isArray(body.positions) || body.positions.length > 500) throw new Error("보유종목은 최대 500개까지 입력할 수 있습니다.");
  const finite = (value: any, optional = false) => {
    if (optional && (value == null || value === "")) return null;
    if (value == null || value === "" || !["string", "number"].includes(typeof value) || !Number.isFinite(Number(value)) || Number(value) < 0 || Number(value) > 1e15) throw new Error("수량·가격·환율에 올바른 숫자를 입력해 주세요.");
    return Number(value);
  };
  const keys = new Set<string>();
  const positions = body.positions.flatMap((item: any) => {
    const broker = String(item?.broker || ""), market = String(item?.market || ""), symbol = String(item?.symbol || "").trim().toUpperCase();
    if (!(market === "coin" ? broker === "upbit" && /^[A-Z0-9]{1,16}$/.test(symbol) : ["kis", "toss"].includes(broker) && ["us", "kr"].includes(market) && (market === "kr" ? /^[A-Z0-9]{6}$/.test(symbol) : /^[A-Z0-9][A-Z0-9.\-]{0,15}$/.test(symbol)))) throw new Error("증권사·시장·종목코드를 확인해 주세요.");
    const key = `${broker}:${market}:${symbol}`;
    if (keys.has(key)) throw new Error("같은 계좌의 종목이 중복 입력되었습니다.");
    keys.add(key);
    const quantity = finite(item.quantity)!;
    if (quantity === 0) return [];
    const cash = market === "coin" && symbol === "KRW", price = finite(item.current_price)!;
    if (cash && price !== 1) throw new Error("원화 잔액의 가격은 1원으로 입력하고 수량에 잔액을 입력해 주세요.");
    if (!(price > 0)) throw new Error("보유종목 가격은 0보다 커야 합니다.");
    const average = cash ? 1 : finite(item.average_price, true), amount = quantity * price;
    if (!Number.isFinite(amount) || amount > 1e18) throw new Error("평가금액이 입력 범위를 초과했습니다.");
    return [{ broker, market, symbol, name: String(item.name || symbol).slice(0, 100), quantity, average_price: average, current_price: price, evaluation_amount: amount,
      profit_loss: average == null ? null : amount - quantity * average, profit_rate: average && average > 0 ? (price / average - 1) * 100 : null,
      daily_change_rate: null, currency: market === "us" ? "USD" : "KRW", record_source: "manual_restore", source_captured_at: null }];
  });
  const totals = Object.fromEntries(["kr", "us", "coin"].map(market => [market, positions.filter((item: any) => item.market === market).reduce((sum: number, item: any) => sum + item.evaluation_amount, 0)]));
  const fx = finite(body.fx_rate, true), fxDate = String(body.fx_date || date);
  if ((fx != null && (!(fx > 0) || !/^\d{4}-\d{2}-\d{2}$/.test(fxDate) || !Number.isFinite(Date.parse(`${fxDate}T00:00:00Z`)) || new Date(`${fxDate}T00:00:00Z`).toISOString().slice(0, 10) !== fxDate || fxDate > date || Date.parse(`${date}T00:00:00Z`) - Date.parse(`${fxDate}T00:00:00Z`) > 7 * 86400000)) || (totals.us > 0 && !(fx && fx > 0))) throw new Error("미국주식 환산에는 해당 날짜 또는 이전 7일 이내의 환율이 필요합니다.");
  return { user_id: userId, snapshot_date: date, captured_at: new Date().toISOString(), positions, totals, fx_rate: fx, fx_date: fx ? fxDate : null,
    fx_source: fx ? "과거 환율 · 사용자 확인" : null, complete: true, warnings: ["누락일 수동복원: 한국시간 날짜 종료 기준 가격·보유수량 사용자 확인 / 자동 계좌조회 기록과 구분", "주식 계좌 예수금은 총액에서 제외"] };
}
export async function saveRestore(db: any, userId: string, body: Record<string, any>) {
  const snapshot = restoredSnapshot(userId, body);
  if (body.replace_captured_at) {
    const { data: previous, error: readError } = await db.from("asset_portfolio_daily_snapshots").select("captured_at,complete,warnings").eq("user_id", userId).eq("snapshot_date", snapshot.snapshot_date).maybeSingle();
    if (readError) throw new Error("기존 기록 확인에 실패했습니다.");
    if (!previous || previous.captured_at !== body.replace_captured_at || !needsRestore(previous)) throw new Error("기존 기록이 변경되었거나 정상 기록입니다. 과거 시세를 다시 불러와 주세요.");
    const { data: updated, error: updateError } = await db.from("asset_portfolio_daily_snapshots").update(snapshot).eq("user_id", userId).eq("snapshot_date", snapshot.snapshot_date).eq("captured_at", body.replace_captured_at).select("snapshot_date").maybeSingle();
    if (updateError || !updated) throw new Error("기록이 변경되어 복원을 중단했습니다. 과거 시세를 다시 불러와 주세요.");
    return { ok: true, snapshot_date: snapshot.snapshot_date, positions_count: snapshot.positions.length };
  }
  // Insert only for an absent date: unique owner/date protects concurrent writes.
  const { error } = await db.from("asset_portfolio_daily_snapshots").insert(snapshot);
  if (error?.code === "23505") throw new Error("이미 기록된 날짜입니다. 기존 기록은 덮어쓰지 않습니다.");
  if (error) throw new Error("누락일 기록 저장에 실패했습니다. 잠시 후 다시 시도해 주세요.");
  return { ok: true, snapshot_date: snapshot.snapshot_date, positions_count: snapshot.positions.length };
}

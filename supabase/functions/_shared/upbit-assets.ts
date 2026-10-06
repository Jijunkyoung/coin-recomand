const env = (name: string) => (Deno.env.get(name) || "").trim();
const encoder = new TextEncoder();
const base64url = (value: string | Uint8Array) => {
  const bytes = typeof value === "string" ? encoder.encode(value) : value;
  let binary = ""; for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
};
async function jwt(accessKey: string, secretKey: string) {
  const header = base64url(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payload = base64url(JSON.stringify({ access_key: accessKey, nonce: crypto.randomUUID() }));
  const unsigned = `${header}.${payload}`;
  const key = await crypto.subtle.importKey("raw", encoder.encode(secretKey), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return `${unsigned}.${base64url(new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(unsigned))))}`;
}
async function upbitFetch(path: string, authorization = "") {
  const proxy = env("UPBIT_PROXY_URL").replace(/\/$/, "");
  if (!proxy) throw new Error("업비트 고정 IP 프록시가 아직 연결되지 않았습니다.");
  const headers: Record<string, string> = {};
  if (authorization) headers.authorization = `Bearer ${authorization}`;
  if (env("UPBIT_PROXY_TOKEN")) headers["x-upbit-proxy-token"] = env("UPBIT_PROXY_TOKEN");
  const response = await fetch(`${proxy}${path}`, { headers, signal: AbortSignal.timeout(12000) });
  const raw = await response.text();
  let data: unknown; try { data = JSON.parse(raw); } catch { data = null; }
  if (!response.ok || !data) throw new Error(`업비트 조회 실패 (HTTP ${response.status})`);
  return data;
}

export async function loadUpbitAssets() {
  const accessKey = env("UPBIT_ACCESS_KEY"), secretKey = env("UPBIT_SECRET_KEY");
  if (!accessKey && !secretKey) return { configured: false, positions: [] };
  if (!accessKey || !secretKey) throw new Error("업비트 조회 전용 API 키를 모두 등록해 주세요.");
  const accounts = await upbitFetch("/v1/accounts", await jwt(accessKey, secretKey)) as Array<Record<string, unknown>>;
  if (!Array.isArray(accounts)) throw new Error("업비트 보유자산 응답이 올바르지 않습니다.");
  const assets = accounts.filter(item => Number(item.balance || 0) + Number(item.locked || 0) > 0);
  const markets = assets.filter(item => String(item.currency) !== "KRW").map(item => `KRW-${String(item.currency)}`);
  const tickers = markets.length ? await upbitFetch(`/v1/ticker?markets=${encodeURIComponent(markets.join(","))}`) as Array<Record<string, unknown>> : [];
  const tickerMap = new Map(tickers.map(item => [String(item.market).replace(/^KRW-/, ""), item]));
  const positions = assets.map(item => {
    const symbol = String(item.currency), quantity = Number(item.balance || 0) + Number(item.locked || 0);
    const ticker = tickerMap.get(symbol), price = symbol === "KRW" ? 1 : Number(ticker?.trade_price);
    if (!Number.isFinite(price) || price <= 0) throw new Error(`${symbol} 원화 시세를 확인하지 못했습니다.`);
    const average = symbol === "KRW" ? 1 : Number(item.avg_buy_price || 0), amount = quantity * price, cost = quantity * average;
    return { broker: "upbit", market: "coin", symbol, name: symbol === "KRW" ? "원화" : symbol, quantity,
      average_price: average, current_price: price, evaluation_amount: amount, profit_loss: amount - cost,
      profit_rate: cost > 0 ? (amount / cost - 1) * 100 : null,
      daily_change_rate: symbol === "KRW" ? 0 : Number(ticker?.signed_change_rate || 0) * 100, currency: "KRW" };
  }).sort((a, b) => b.evaluation_amount - a.evaluation_amount);
  return { configured: true, positions };
}

import { createClient } from "npm:@supabase/supabase-js@2";

const corsHeaders = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type" };
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
  const signature = new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(unsigned)));
  return `${unsigned}.${base64url(signature)}`;
}
async function upbitFetch(path: string, authorization = "") {
  const proxy = env("UPBIT_PROXY_URL").replace(/\/$/, "");
  if (!proxy) throw new Error("업비트 고정 IP 프록시가 아직 연결되지 않았습니다.");
  const headers: Record<string, string> = {};
  if (authorization) headers.authorization = `Bearer ${authorization}`;
  if (env("UPBIT_PROXY_TOKEN")) headers["x-upbit-proxy-token"] = env("UPBIT_PROXY_TOKEN");
  const response = await fetch(`${proxy}${path}`, { headers });
  const raw = await response.text();
  let data: unknown; try { data = JSON.parse(raw); } catch { data = { error: raw.slice(0, 200) }; }
  if (!response.ok) throw new Error(`업비트 조회 실패 (HTTP ${response.status}): ${JSON.stringify(data).slice(0, 240)}`);
  return data;
}

Deno.serve(async (request) => {
  if (request.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const authorization = request.headers.get("Authorization") || "";
    if (!authorization.startsWith("Bearer ")) throw new Error("로그인이 필요합니다.");
    const serviceKey = env("SUPABASE_SERVICE_ROLE_KEY");
    if (!serviceKey) throw new Error("Supabase 서버 인증값이 설정되지 않았습니다.");
    const supabase = createClient(env("SUPABASE_URL"), serviceKey);
    const { data: { user }, error } = await supabase.auth.getUser(authorization.replace(/^Bearer\s+/i, ""));
    if (error || !user) throw new Error("로그인 세션을 확인할 수 없습니다.");
    const ownerId = env("KIS_OWNER_USER_ID"), ownerEmail = env("KIS_OWNER_EMAIL").toLowerCase();
    const matches = ownerId ? user.id === ownerId : Boolean(ownerEmail && (user.email || "").toLowerCase() === ownerEmail);
    if (!matches) return new Response(JSON.stringify({ error: "이 회원에는 업비트 계좌가 연결되지 않았습니다." }), { status: 403, headers: { ...corsHeaders, "content-type": "application/json" } });
    const accessKey = env("UPBIT_ACCESS_KEY"), secretKey = env("UPBIT_SECRET_KEY");
    if (!accessKey || !secretKey) throw new Error("업비트 조회 전용 API 키가 아직 등록되지 않았습니다.");
    const accounts = await upbitFetch("/v1/accounts", await jwt(accessKey, secretKey)) as Array<Record<string, unknown>>;
    const assets = accounts.filter((item) => Number(item.balance || 0) + Number(item.locked || 0) > 0);
    const markets = assets.filter((item) => String(item.currency) !== "KRW").map((item) => `KRW-${String(item.currency)}`);
    const tickers = markets.length ? await upbitFetch(`/v1/ticker?markets=${encodeURIComponent(markets.join(","))}`) as Array<Record<string, unknown>> : [];
    const tickerMap = new Map(tickers.map((item) => [String(item.market).replace(/^KRW-/, ""), item]));
    const positions = assets.map((item) => {
      const symbol = String(item.currency), quantity = Number(item.balance || 0) + Number(item.locked || 0);
      const ticker = tickerMap.get(symbol), currentPrice = symbol === "KRW" ? 1 : Number(ticker?.trade_price || 0);
      const averagePrice = symbol === "KRW" ? 1 : Number(item.avg_buy_price || 0);
      const evaluationAmount = quantity * currentPrice, purchaseAmount = quantity * averagePrice;
      return { symbol, name: symbol === "KRW" ? "원화" : symbol, quantity, average_price: averagePrice, current_price: currentPrice,
        evaluation_amount: evaluationAmount, profit_loss: evaluationAmount - purchaseAmount,
        profit_rate: purchaseAmount > 0 ? (evaluationAmount / purchaseAmount - 1) * 100 : null,
        daily_change_rate: symbol === "KRW" ? 0 : Number(ticker?.signed_change_rate || 0) * 100, currency: "KRW" };
    }).sort((left, right) => right.evaluation_amount - left.evaluation_amount);
    return new Response(JSON.stringify({ positions, synced_at: new Date().toISOString(), total_evaluation: positions.reduce((sum, item) => sum + item.evaluation_amount, 0) }), { headers: { ...corsHeaders, "content-type": "application/json", "cache-control": "no-store" } });
  } catch (error) {
    return new Response(JSON.stringify({ error: error instanceof Error ? error.message : "업비트 계좌 조회 실패" }), { status: 400, headers: { ...corsHeaders, "content-type": "application/json", "cache-control": "no-store" } });
  }
});

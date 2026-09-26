import { createClient } from "npm:@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type, x-kis-scheduler-key",
};

const env = (name: string) => (Deno.env.get(name) || "").trim();
const textValue = (value: unknown) => String(value ?? "").trim();
const numberValue = (value: unknown) => Number(String(value ?? "0").replaceAll(",", "")) || 0;
const adminKey = () => {
  const secretKeys = env("SUPABASE_SECRET_KEYS");
  if (secretKeys) {
    try {
      const parsed = JSON.parse(secretKeys);
      const key = textValue(parsed.default || Object.values(parsed)[0]);
      if (key) return key;
    } catch { /* fall through to the legacy runtime key */ }
  }
  return env("SUPABASE_SERVICE_ROLE_KEY");
};

type Broker = "kis" | "toss";
type Market = "kr" | "us";
type Currency = "KRW" | "USD";
type Position = {
  broker: Broker;
  market: Market;
  symbol: string;
  name: string;
  quantity: number;
  average_price: number;
  current_price: number;
  evaluation_amount: number;
  profit_loss: number;
  profit_rate: number;
  daily_change_rate?: number | null;
  currency: Currency;
};
type Snapshot = { positions?: Position[]; captured_at?: string; snapshot_date?: string };

function positionKey(item: Position) { return `${item.broker}:${item.market}:${item.symbol}`; }

function marketTotals(positions: Position[]) {
  const result = {
    kr: { evaluation_amount: 0, profit_loss: 0, currency: "KRW" },
    us: { evaluation_amount: 0, profit_loss: 0, currency: "USD" },
  };
  for (const item of positions) {
    result[item.market].evaluation_amount += item.evaluation_amount;
    result[item.market].profit_loss += item.profit_loss;
  }
  return result;
}

function portfolioChanges(current: Position[], baseline: Snapshot | null) {
  const previous = Array.isArray(baseline?.positions) ? baseline.positions : [];
  const previousMap = new Map(previous.map((item) => [positionKey(item), item]));
  const currentMap = new Map(current.map((item) => [positionKey(item), item]));
  const added = current.filter((item) => !previousMap.has(positionKey(item)));
  const removed = previous.filter((item) => !currentMap.has(positionKey(item)));
  const quantity_changes = current.flatMap((item) => {
    const before = previousMap.get(positionKey(item));
    if (!before || before.quantity === item.quantity) return [];
    return [{ broker: item.broker, market: item.market, symbol: item.symbol, name: item.name, before: before.quantity, after: item.quantity, difference: item.quantity - before.quantity }];
  });
  const nowTotals = marketTotals(current), beforeTotals = marketTotals(previous);
  const totals = Object.fromEntries((["kr", "us"] as const).map((market) => [market, {
    ...nowTotals[market],
    evaluation_change: previous.length ? nowTotals[market].evaluation_amount - beforeTotals[market].evaluation_amount : null,
    profit_change: previous.length ? nowTotals[market].profit_loss - beforeTotals[market].profit_loss : null,
  }]));
  return { baseline_at: baseline?.captured_at || null, added, removed, quantity_changes, totals };
}

async function jsonResponse(response: Response) {
  const raw = await response.text();
  try { return { raw, data: JSON.parse(raw) as Record<string, any> }; }
  catch { return { raw, data: {} as Record<string, any> }; }
}

function safeApiDetail(data: Record<string, any>, raw: string, fallback: string) {
  let detail = textValue(data?.error?.message || data.error_description || data.msg1 || data.error || data.msg_cd || raw) || fallback;
  for (const name of ["KIS_APP_KEY", "KIS_APP_SECRET", "TOSSINVEST_CLIENT_ID", "TOSSINVEST_CLIENT_SECRET", "TOSSINVEST_ACCOUNT"]) {
    const secret = env(name);
    if (secret) detail = detail.replaceAll(secret, "[REDACTED]");
  }
  return detail.slice(0, 200);
}

async function kisToken(appKey: string, appSecret: string, baseUrl: string) {
  const response = await fetch(`${baseUrl}/oauth2/tokenP`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ grant_type: "client_credentials", appkey: appKey, appsecret: appSecret }),
  });
  const { raw, data } = await jsonResponse(response);
  if (!response.ok || !data.access_token) throw new Error(`한국투자증권 토큰 발급 실패: ${safeApiDetail(data, raw, `HTTP ${response.status}`)}`);
  return data.access_token as string;
}

async function kisGet(baseUrl: string, path: string, trId: string, params: Record<string, string>, token: string, appKey: string, appSecret: string) {
  const query = new URLSearchParams(params);
  const response = await fetch(`${baseUrl}${path}?${query}`, { headers: {
    authorization: `Bearer ${token}`, appkey: appKey, appsecret: appSecret, tr_id: trId,
    custtype: "P", "content-type": "application/json; charset=utf-8",
  }});
  const { raw, data } = await jsonResponse(response);
  if (!response.ok || String(data.rt_cd ?? "0") !== "0") throw new Error(safeApiDetail(data, raw, "한국투자증권 계좌조회 실패"));
  return data;
}

function domesticPositions(rows: Record<string, unknown>[]): Position[] {
  return rows.flatMap((row) => {
    const quantity = numberValue(row.hldg_qty), symbol = textValue(row.pdno);
    if (!symbol || quantity <= 0) return [];
    return [{ broker: "kis", market: "kr", symbol, name: textValue(row.prdt_name) || symbol, quantity,
      average_price: numberValue(row.pchs_avg_pric), current_price: numberValue(row.prpr),
      evaluation_amount: numberValue(row.evlu_amt), profit_loss: numberValue(row.evlu_pfls_amt),
      profit_rate: numberValue(row.evlu_pfls_rt), currency: "KRW" } satisfies Position];
  });
}

function overseasPositions(rows: Record<string, unknown>[]): Position[] {
  return rows.flatMap((row) => {
    const quantity = numberValue(row.ovrs_cblc_qty || row.hldg_qty), symbol = textValue(row.ovrs_pdno || row.pdno);
    if (!symbol || quantity <= 0) return [];
    return [{ broker: "kis", market: "us", symbol, name: textValue(row.ovrs_item_name || row.prdt_name) || symbol, quantity,
      average_price: numberValue(row.pchs_avg_pric || row.avg_unpr3), current_price: numberValue(row.now_pric2 || row.ovrs_now_pric1),
      evaluation_amount: numberValue(row.ovrs_stck_evlu_amt || row.evlu_amt), profit_loss: numberValue(row.frcr_evlu_pfls_amt || row.evlu_pfls_amt),
      profit_rate: numberValue(row.evlu_pfls_rt), currency: "USD" } satisfies Position];
  });
}

async function loadKisPositions() {
  const appKey = env("KIS_APP_KEY"), appSecret = env("KIS_APP_SECRET"), account = env("KIS_ACCOUNT_NO");
  const productCode = env("KIS_ACCOUNT_PRODUCT_CODE") || "01";
  const configured = Boolean(appKey && appSecret && /^\d{8}$/.test(account) && /^\d{2}$/.test(productCode));
  if (!configured) return { configured, positions: [] as Position[], warnings: [] as string[] };
  const baseUrl = (env("KIS_BASE_URL") || "https://openapi.koreainvestment.com:9443").replace(/\/$/, "");
  const token = await kisToken(appKey, appSecret, baseUrl);
  const domestic = await kisGet(baseUrl, "/uapi/domestic-stock/v1/trading/inquire-balance", "TTTC8434R", {
    CANO: account, ACNT_PRDT_CD: productCode, AFHR_FLPR_YN: "N", OFL_YN: "", INQR_DVSN: "02",
    UNPR_DVSN: "01", FUND_STTL_ICLD_YN: "N", FNCG_AMT_AUTO_RDPT_YN: "N", PRCS_DVSN: "00",
    CTX_AREA_FK100: "", CTX_AREA_NK100: "",
  }, token, appKey, appSecret);
  const positions = domesticPositions(domestic.output1 || []), warnings: string[] = [];
  for (const exchange of ["NASD", "NYSE", "AMEX"]) {
    try {
      const data = await kisGet(baseUrl, "/uapi/overseas-stock/v1/trading/inquire-balance", "TTTS3012R", {
        CANO: account, ACNT_PRDT_CD: productCode, OVRS_EXCG_CD: exchange, TR_CRCY_CD: "USD", CTX_AREA_FK200: "", CTX_AREA_NK200: "",
      }, token, appKey, appSecret);
      positions.push(...overseasPositions(data.output1 || []));
    } catch (error) { warnings.push(`한국투자증권 ${exchange}: ${error instanceof Error ? error.message : "조회 실패"}`); }
  }
  return { configured, positions, warnings };
}

async function tossToken(clientId: string, clientSecret: string) {
  const body = new URLSearchParams({ grant_type: "client_credentials", client_id: clientId, client_secret: clientSecret });
  const response = await fetch("https://openapi.tossinvest.com/oauth2/token", {
    method: "POST", headers: { "content-type": "application/x-www-form-urlencoded", accept: "application/json" }, body,
  });
  const { raw, data } = await jsonResponse(response);
  if (!response.ok || !data.access_token) throw new Error(`토스증권 토큰 발급 실패: ${safeApiDetail(data, raw, `HTTP ${response.status}`)}`);
  return data.access_token as string;
}

async function tossGet(path: string, token: string, account?: string) {
  const headers: Record<string, string> = { authorization: `Bearer ${token}`, accept: "application/json" };
  if (account) headers["X-Tossinvest-Account"] = account;
  const response = await fetch(`https://openapi.tossinvest.com${path}`, { headers });
  const { raw, data } = await jsonResponse(response);
  if (!response.ok) throw new Error(safeApiDetail(data, raw, `토스증권 API HTTP ${response.status}`));
  return data.result;
}

function tossPositions(rows: Record<string, any>[]): Position[] {
  return rows.flatMap((row) => {
    const market = String(row.marketCountry || "").toUpperCase() === "US" ? "us" : "kr";
    const currency = market === "us" ? "USD" : "KRW", symbol = textValue(row.symbol), quantity = numberValue(row.quantity);
    if (!symbol || quantity <= 0) return [];
    return [{ broker: "toss", market, symbol, name: textValue(row.name) || symbol, quantity,
      average_price: numberValue(row.averagePurchasePrice), current_price: numberValue(row.lastPrice),
      evaluation_amount: numberValue(row.marketValue?.amount), profit_loss: numberValue(row.profitLoss?.amount),
      profit_rate: numberValue(row.profitLoss?.rate) * 100, daily_change_rate: numberValue(row.dailyProfitLoss?.rate) * 100,
      currency } satisfies Position];
  });
}

async function loadTossPositions() {
  const clientId = env("TOSSINVEST_CLIENT_ID"), clientSecret = env("TOSSINVEST_CLIENT_SECRET");
  if (Boolean(clientId) !== Boolean(clientSecret)) throw new Error("토스증권 Client ID와 Client Secret을 모두 등록해 주세요.");
  const configured = Boolean(clientId && clientSecret);
  if (!configured) return { configured, positions: [] as Position[] };
  const token = await tossToken(clientId, clientSecret);
  let account = env("TOSSINVEST_ACCOUNT");
  if (!account) {
    const accounts = await tossGet("/api/v1/accounts", token);
    const selected = Array.isArray(accounts) ? (accounts.find((item: Record<string, any>) => item?.accountType === "BROKERAGE") || accounts[0]) : null;
    account = textValue(selected?.accountSeq);
  }
  if (!account) throw new Error("토스증권 종합매매 계좌를 찾지 못했습니다.");
  const overview = await tossGet("/api/v1/holdings", token, account);
  return { configured, positions: tossPositions(Array.isArray(overview?.items) ? overview.items : []) };
}

function kstDate(value = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(value);
  const pick = (type: string) => parts.find((part) => part.type === type)?.value || "";
  return `${pick("year")}-${pick("month")}-${pick("day")}`;
}

Deno.serve(async (request) => {
  if (request.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const authorization = request.headers.get("Authorization") || "", ownerId = env("KIS_OWNER_USER_ID"), ownerEmail = env("KIS_OWNER_EMAIL").toLowerCase();
    const schedulerSecret = env("KIS_SCHEDULER_KEY"), requestApiKey = request.headers.get("apikey") || "", serverAdminKey = adminKey();
    const schedulerMode = Boolean((schedulerSecret && request.headers.get("x-kis-scheduler-key") === schedulerSecret) || (serverAdminKey && requestApiKey === serverAdminKey));
    if (!schedulerMode && !authorization.startsWith("Bearer ")) throw new Error("로그인이 필요합니다.");
    if (!serverAdminKey) throw new Error("Supabase 서버 인증값이 설정되지 않았습니다.");
    const supabase = createClient(env("SUPABASE_URL"), serverAdminKey);
    let userId = ownerId;
    if (!schedulerMode) {
      const accessToken = authorization.replace(/^Bearer\s+/i, "");
      const { data: { user }, error: userError } = await supabase.auth.getUser(accessToken);
      if (userError || !user) throw new Error("로그인 세션을 확인할 수 없습니다.");
      userId = user.id;
      const email = (user.email || "").trim().toLowerCase(), ownerMatches = ownerId ? user.id === ownerId : Boolean(ownerEmail && email === ownerEmail);
      if (!ownerMatches) return new Response(JSON.stringify({ error: "이 회원에는 증권계좌가 연결되지 않았습니다." }), { status: 403, headers: { ...corsHeaders, "content-type": "application/json" } });
    }
    if (!userId) return new Response(JSON.stringify({ error: "증권계좌 소유자 설정이 완료되지 않았습니다." }), { status: 403, headers: { ...corsHeaders, "content-type": "application/json" } });

    const warnings: string[] = [], connections = { kis: { configured: false, ok: false }, toss: { configured: false, ok: false } };
    let positions: Position[] = [];
    try {
      const kis = await loadKisPositions(); connections.kis.configured = kis.configured; connections.kis.ok = kis.configured;
      positions.push(...kis.positions); warnings.push(...kis.warnings);
    } catch (error) { connections.kis.configured = true; warnings.push(`한국투자증권: ${error instanceof Error ? error.message : "조회 실패"}`); }
    try {
      const toss = await loadTossPositions(); connections.toss.configured = toss.configured; connections.toss.ok = toss.configured;
      positions.push(...toss.positions);
    } catch (error) { connections.toss.configured = true; warnings.push(`토스증권: ${error instanceof Error ? error.message : "조회 실패"}`); }
    if (!connections.kis.configured && !connections.toss.configured) throw new Error("연결된 주식 계좌 API가 없습니다.");
    if (!connections.kis.ok && !connections.toss.ok) throw new Error(warnings.join(" · ") || "주식 계좌 조회에 실패했습니다.");

    let unique = [...new Map(positions.map((item) => [positionKey(item), item])).values()];
    const today = kstDate(), { data: previousDaily, error: previousDailyError } = await supabase.from("stock_portfolio_daily_snapshots")
      .select("positions,captured_at,snapshot_date").eq("user_id", userId).lt("snapshot_date", today).order("snapshot_date", { ascending: false }).limit(1).maybeSingle();
    if (previousDailyError) throw new Error(`이전 일별 계좌현황 조회 실패: ${previousDailyError.message}`);
    let baseline = previousDaily as Snapshot | null;
    if (!baseline) {
      const baselineCutoff = new Date(Date.now() - 20 * 60 * 60 * 1000).toISOString();
      const { data: legacy } = await supabase.from("kis_portfolio_snapshots").select("positions,captured_at").eq("user_id", userId)
        .lte("captured_at", baselineCutoff).order("captured_at", { ascending: false }).limit(1).maybeSingle();
      baseline = legacy as Snapshot | null;
    }
    const previousPositions = Array.isArray(baseline?.positions) ? baseline?.positions || [] : [];
    const previousMap = new Map(previousPositions.map((item) => [positionKey(item), item]));
    unique = unique.map((item) => {
      if (item.daily_change_rate != null) return item;
      const previous = previousMap.get(positionKey(item));
      const dailyChangeRate = previous && previous.current_price > 0 ? Math.round(((item.current_price / previous.current_price) - 1) * 10000) / 100 : null;
      return { ...item, daily_change_rate: dailyChangeRate };
    }).sort((left, right) => right.evaluation_amount - left.evaluation_amount);

    const changes = portfolioChanges(unique, baseline), totals = marketTotals(unique), capturedAt = new Date().toISOString();
    const { error: legacySnapshotError } = await supabase.from("kis_portfolio_snapshots").insert({ user_id: userId, positions: unique, totals, captured_at: capturedAt });
    if (legacySnapshotError) throw new Error(`계좌 변동기록 저장 실패: ${legacySnapshotError.message}`);
    const { error: dailySnapshotError } = await supabase.from("stock_portfolio_daily_snapshots").upsert({
      user_id: userId, snapshot_date: today, positions: unique, totals, captured_at: capturedAt,
    }, { onConflict: "user_id,snapshot_date" });
    if (dailySnapshotError) throw new Error(`일별 계좌기록 저장 실패: ${dailySnapshotError.message}`);
    const { data: history, error: historyError } = await supabase.from("stock_portfolio_daily_snapshots")
      .select("snapshot_date,positions,totals,captured_at").eq("user_id", userId).order("snapshot_date", { ascending: false }).limit(366);
    if (historyError) throw new Error(`일별 계좌기록 조회 실패: ${historyError.message}`);

    const holdingsKr = unique.filter((item) => item.market === "kr").map((item) => `${item.symbol}|${item.name}`).join("\n");
    const holdingsUs = unique.filter((item) => item.market === "us").map((item) => `${item.symbol}|${item.name}`).join("\n");
    let mailProfile = null;
    if (schedulerMode) {
      const { data: preferences, error: preferenceError } = await supabase.from("user_preferences").select("holdings_us,holdings_kr,sector_ids,stock_email").eq("user_id", userId).maybeSingle();
      if (preferenceError) throw new Error(`회원 메일 설정 조회 실패: ${preferenceError.message}`);
      const { data: authData, error: authError } = await supabase.auth.admin.getUserById(userId);
      if (authError) throw new Error(`회원 이메일 조회 실패: ${authError.message}`);
      mailProfile = { holdings_us: [holdingsUs, preferences?.holdings_us || ""].filter(Boolean).join("\n"), holdings_kr: [holdingsKr, preferences?.holdings_kr || ""].filter(Boolean).join("\n"), sector_ids: preferences?.sector_ids || [], stock_email: preferences?.stock_email || authData.user?.email || null };
    }

    return new Response(JSON.stringify({ positions: unique, totals, synced_at: capturedAt, snapshot_date: today, warnings, changes, history: (history || []).reverse(), connections, mail_profile: mailProfile }), {
      headers: { ...corsHeaders, "content-type": "application/json", "cache-control": "no-store" },
    });
  } catch (error) {
    return new Response(JSON.stringify({ error: error instanceof Error ? error.message : "계좌 동기화 실패" }), { status: 400, headers: { ...corsHeaders, "content-type": "application/json", "cache-control": "no-store" } });
  }
});

import { createClient } from "npm:@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type, x-kis-scheduler-key",
};

const env = (name: string) => (Deno.env.get(name) || "").trim();
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
const numberValue = (value: unknown) => Number(String(value ?? "0").replaceAll(",", "")) || 0;
const textValue = (value: unknown) => String(value ?? "").trim();

type Position = {
  market: "kr" | "us";
  symbol: string;
  name: string;
  quantity: number;
  average_price: number;
  current_price: number;
  evaluation_amount: number;
  profit_loss: number;
  profit_rate: number;
  daily_change_rate?: number | null;
  currency: "KRW" | "USD";
};

type Snapshot = { positions?: Position[]; captured_at?: string };

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
  const previousMap = new Map(previous.map((item) => [`${item.market}:${item.symbol}`, item]));
  const currentMap = new Map(current.map((item) => [`${item.market}:${item.symbol}`, item]));
  const added = current.filter((item) => !previousMap.has(`${item.market}:${item.symbol}`));
  const removed = previous.filter((item) => !currentMap.has(`${item.market}:${item.symbol}`));
  const quantity_changes = current.flatMap((item) => {
    const before = previousMap.get(`${item.market}:${item.symbol}`);
    if (!before || before.quantity === item.quantity) return [];
    return [{ market: item.market, symbol: item.symbol, name: item.name, before: before.quantity, after: item.quantity, difference: item.quantity - before.quantity }];
  });
  const nowTotals = marketTotals(current), beforeTotals = marketTotals(previous);
  const totals = Object.fromEntries((["kr", "us"] as const).map((market) => [market, {
    ...nowTotals[market],
    evaluation_change: previous.length ? nowTotals[market].evaluation_amount - beforeTotals[market].evaluation_amount : null,
    profit_change: previous.length ? nowTotals[market].profit_loss - beforeTotals[market].profit_loss : null,
  }]));
  return { baseline_at: baseline?.captured_at || null, added, removed, quantity_changes, totals };
}

async function kisToken(appKey: string, appSecret: string, baseUrl: string) {
  const response = await fetch(`${baseUrl}/oauth2/tokenP`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ grant_type: "client_credentials", appkey: appKey, appsecret: appSecret }),
  });
  const raw = await response.text();
  let data: Record<string, unknown> = {};
  try { data = JSON.parse(raw); } catch { /* KIS may return a plain-text gateway error. */ }
  if (!response.ok || !data.access_token) {
    const detail = textValue(data.error_description || data.msg1 || data.error || data.msg_cd || raw);
    const safeDetail = detail.slice(0, 200) || `HTTP ${response.status}`;
    throw new Error(`한국투자증권 토큰 발급 실패: ${safeDetail}`);
  }
  return data.access_token as string;
}

async function kisGet(baseUrl: string, path: string, trId: string, params: Record<string, string>, token: string, appKey: string, appSecret: string) {
  const query = new URLSearchParams(params);
  const response = await fetch(`${baseUrl}${path}?${query}`, {
    headers: {
      authorization: `Bearer ${token}`,
      appkey: appKey,
      appsecret: appSecret,
      tr_id: trId,
      custtype: "P",
      "content-type": "application/json; charset=utf-8",
    },
  });
  const data = await response.json();
  if (!response.ok || String(data.rt_cd ?? "0") !== "0") throw new Error(data.msg1 || data.msg_cd || "한국투자증권 계좌조회 실패");
  return data;
}

function domesticPositions(rows: Record<string, unknown>[]): Position[] {
  return rows.flatMap((row) => {
    const quantity = numberValue(row.hldg_qty);
    const symbol = textValue(row.pdno);
    if (!symbol || quantity <= 0) return [];
    return [{
      market: "kr", symbol, name: textValue(row.prdt_name) || symbol, quantity,
      average_price: numberValue(row.pchs_avg_pric), current_price: numberValue(row.prpr),
      evaluation_amount: numberValue(row.evlu_amt), profit_loss: numberValue(row.evlu_pfls_amt),
      profit_rate: numberValue(row.evlu_pfls_rt), currency: "KRW",
    } satisfies Position];
  });
}

function overseasPositions(rows: Record<string, unknown>[]): Position[] {
  return rows.flatMap((row) => {
    const quantity = numberValue(row.ovrs_cblc_qty || row.hldg_qty);
    const symbol = textValue(row.ovrs_pdno || row.pdno);
    if (!symbol || quantity <= 0) return [];
    const average = numberValue(row.pchs_avg_pric || row.avg_unpr3);
    const current = numberValue(row.now_pric2 || row.ovrs_now_pric1);
    const evaluation = numberValue(row.ovrs_stck_evlu_amt || row.evlu_amt);
    const profit = numberValue(row.frcr_evlu_pfls_amt || row.evlu_pfls_amt);
    return [{
      market: "us", symbol, name: textValue(row.ovrs_item_name || row.prdt_name) || symbol, quantity,
      average_price: average, current_price: current, evaluation_amount: evaluation,
      profit_loss: profit, profit_rate: numberValue(row.evlu_pfls_rt), currency: "USD",
    } satisfies Position];
  });
}

Deno.serve(async (request) => {
  if (request.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const authorization = request.headers.get("Authorization") || "";
    const ownerId = env("KIS_OWNER_USER_ID");
    const ownerEmail = env("KIS_OWNER_EMAIL").toLowerCase();
    const schedulerSecret = env("KIS_SCHEDULER_KEY");
    const requestApiKey = request.headers.get("apikey") || "";
    const serverAdminKey = adminKey();
    // Scheduled jobs already hold a server-only Supabase secret. Accept that
    // credential as well as the dedicated scheduler key so a rotated or
    // mismatched scheduler key cannot silently block the daily stock report.
    const schedulerMode = Boolean(
      (schedulerSecret && request.headers.get("x-kis-scheduler-key") === schedulerSecret) ||
      (serverAdminKey && requestApiKey === serverAdminKey)
    );
    if (!schedulerMode && !authorization.startsWith("Bearer ")) throw new Error("로그인이 필요합니다.");
    if (!serverAdminKey) throw new Error("Supabase 서버 인증값이 설정되지 않았습니다.");
    const supabase = createClient(env("SUPABASE_URL"), serverAdminKey);
    let userId = ownerId;
    if (!schedulerMode) {
      const accessToken = authorization.replace(/^Bearer\s+/i, "");
      const { data: { user }, error: userError } = await supabase.auth.getUser(accessToken);
      if (userError || !user) throw new Error("로그인 세션을 확인할 수 없습니다.");
      userId = user.id;
      const email = (user.email || "").trim().toLowerCase();
      const ownerConfigured = Boolean(ownerId || ownerEmail);
      const idMatches = !ownerId || user.id === ownerId;
      const emailMatches = !ownerEmail || email === ownerEmail;
      if (!ownerConfigured || !idMatches || !emailMatches) return new Response(JSON.stringify({ error: "이 회원에는 증권계좌가 연결되지 않았습니다." }), { status: 403, headers: { ...corsHeaders, "content-type": "application/json" } });
    }
    if (!userId) return new Response(JSON.stringify({ error: "증권계좌 소유자 설정이 완료되지 않았습니다." }), { status: 403, headers: { ...corsHeaders, "content-type": "application/json" } });

    const appKey = env("KIS_APP_KEY"), appSecret = env("KIS_APP_SECRET");
    const account = env("KIS_ACCOUNT_NO"), productCode = env("KIS_ACCOUNT_PRODUCT_CODE") || "01";
    const baseUrl = (env("KIS_BASE_URL") || "https://openapi.koreainvestment.com:9443").replace(/\/$/, "");
    if (!appKey || !appSecret || !/^\d{8}$/.test(account) || !/^\d{2}$/.test(productCode)) throw new Error("한국투자증권 계좌 비밀값 설정이 완료되지 않았습니다.");

    const token = await kisToken(appKey, appSecret, baseUrl);
    const domestic = await kisGet(baseUrl, "/uapi/domestic-stock/v1/trading/inquire-balance", "TTTC8434R", {
      CANO: account, ACNT_PRDT_CD: productCode, AFHR_FLPR_YN: "N", OFL_YN: "", INQR_DVSN: "02",
      UNPR_DVSN: "01", FUND_STTL_ICLD_YN: "N", FNCG_AMT_AUTO_RDPT_YN: "N", PRCS_DVSN: "00",
      CTX_AREA_FK100: "", CTX_AREA_NK100: "",
    }, token, appKey, appSecret);
    const positions = domesticPositions(domestic.output1 || []);
    const overseasErrors: string[] = [];
    for (const exchange of ["NASD", "NYSE", "AMEX"]) {
      try {
        const data = await kisGet(baseUrl, "/uapi/overseas-stock/v1/trading/inquire-balance", "TTTS3012R", {
          CANO: account, ACNT_PRDT_CD: productCode, OVRS_EXCG_CD: exchange, TR_CRCY_CD: "USD",
          CTX_AREA_FK200: "", CTX_AREA_NK200: "",
        }, token, appKey, appSecret);
        positions.push(...overseasPositions(data.output1 || []));
      } catch (error) { overseasErrors.push(`${exchange}: ${error instanceof Error ? error.message : "조회 실패"}`); }
    }
    let unique = [...new Map(positions.map((item) => [`${item.market}:${item.symbol}`, item])).values()];
    const baselineCutoff = new Date(Date.now() - 20 * 60 * 60 * 1000).toISOString();
    const { data: baseline, error: baselineError } = await supabase.from("kis_portfolio_snapshots")
      .select("positions,captured_at").eq("user_id", userId).lte("captured_at", baselineCutoff)
      .order("captured_at", { ascending: false }).limit(1).maybeSingle();
    if (baselineError) throw new Error(`이전 계좌현황 조회 실패: ${baselineError.message}`);
    const previousPositions = Array.isArray((baseline as Snapshot | null)?.positions)
      ? (baseline as Snapshot).positions || []
      : [];
    const previousMap = new Map(previousPositions.map((item) => [`${item.market}:${item.symbol}`, item]));
    unique = unique.map((item) => {
      const previous = previousMap.get(`${item.market}:${item.symbol}`);
      const dailyChangeRate = previous && previous.current_price > 0
        ? Math.round(((item.current_price / previous.current_price) - 1) * 10000) / 100
        : null;
      return { ...item, daily_change_rate: dailyChangeRate };
    });
    const changes = portfolioChanges(unique, baseline as Snapshot | null);
    const holdingsKr = unique.filter((item) => item.market === "kr").map((item) => `${item.symbol}|${item.name}`).join("\n");
    const holdingsUs = unique.filter((item) => item.market === "us").map((item) => `${item.symbol}|${item.name}`).join("\n");
    const { error: saveError } = await supabase.from("user_preferences").upsert({
      user_id: userId, holdings_kr: holdingsKr, holdings_us: holdingsUs, updated_at: new Date().toISOString(),
    }, { onConflict: "user_id" });
    if (saveError) throw new Error(`보유종목 저장 실패: ${saveError.message}`);
    const capturedAt = new Date().toISOString();
    const { error: snapshotError } = await supabase.from("kis_portfolio_snapshots").insert({
      user_id: userId, positions: unique, totals: marketTotals(unique), captured_at: capturedAt,
    });
    if (snapshotError) throw new Error(`계좌 변동기록 저장 실패: ${snapshotError.message}`);

    let mailProfile = null;
    if (schedulerMode) {
      const { data: preferences, error: preferenceError } = await supabase.from("user_preferences")
        .select("holdings_us,holdings_kr,sector_ids,stock_email").eq("user_id", userId).maybeSingle();
      if (preferenceError) throw new Error(`회원 메일 설정 조회 실패: ${preferenceError.message}`);
      const { data: authData, error: authError } = await supabase.auth.admin.getUserById(userId);
      if (authError) throw new Error(`회원 이메일 조회 실패: ${authError.message}`);
      mailProfile = {
        holdings_us: holdingsUs, holdings_kr: holdingsKr,
        sector_ids: preferences?.sector_ids || [],
        stock_email: preferences?.stock_email || authData.user?.email || null,
      };
    }

    return new Response(JSON.stringify({ positions: unique, synced_at: capturedAt, warnings: overseasErrors, changes, mail_profile: mailProfile }), {
      headers: { ...corsHeaders, "content-type": "application/json", "cache-control": "no-store" },
    });
  } catch (error) {
    return new Response(JSON.stringify({ error: error instanceof Error ? error.message : "계좌 동기화 실패" }), {
      status: 400, headers: { ...corsHeaders, "content-type": "application/json", "cache-control": "no-store" },
    });
  }
});

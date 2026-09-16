import { createClient } from "npm:@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

const env = (name: string) => (Deno.env.get(name) || "").trim();
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
  currency: "KRW" | "USD";
};

async function kisToken(appKey: string, appSecret: string, baseUrl: string) {
  const response = await fetch(`${baseUrl}/oauth2/tokenP`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ grant_type: "client_credentials", appkey: appKey, appsecret: appSecret }),
  });
  const data = await response.json();
  if (!response.ok || !data.access_token) throw new Error(data.msg1 || "한국투자증권 토큰 발급 실패");
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
    if (!authorization.startsWith("Bearer ")) throw new Error("로그인이 필요합니다.");
    const supabase = createClient(env("SUPABASE_URL"), env("SUPABASE_ANON_KEY"), {
      global: { headers: { Authorization: authorization } },
    });
    const { data: { user }, error: userError } = await supabase.auth.getUser();
    if (userError || !user) throw new Error("로그인 세션을 확인할 수 없습니다.");
    const ownerId = env("KIS_OWNER_USER_ID");
    if (!ownerId || user.id !== ownerId) return new Response(JSON.stringify({ error: "이 회원에는 증권계좌가 연결되지 않았습니다." }), { status: 403, headers: { ...corsHeaders, "content-type": "application/json" } });

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
    const unique = [...new Map(positions.map((item) => [`${item.market}:${item.symbol}`, item])).values()];
    const holdingsKr = unique.filter((item) => item.market === "kr").map((item) => `${item.symbol}|${item.name}`).join("\n");
    const holdingsUs = unique.filter((item) => item.market === "us").map((item) => `${item.symbol}|${item.name}`).join("\n");
    const { error: saveError } = await supabase.from("user_preferences").upsert({
      user_id: user.id, holdings_kr: holdingsKr, holdings_us: holdingsUs, updated_at: new Date().toISOString(),
    }, { onConflict: "user_id" });
    if (saveError) throw new Error(`보유종목 저장 실패: ${saveError.message}`);

    return new Response(JSON.stringify({ positions: unique, synced_at: new Date().toISOString(), warnings: overseasErrors }), {
      headers: { ...corsHeaders, "content-type": "application/json", "cache-control": "no-store" },
    });
  } catch (error) {
    return new Response(JSON.stringify({ error: error instanceof Error ? error.message : "계좌 동기화 실패" }), {
      status: 400, headers: { ...corsHeaders, "content-type": "application/json", "cache-control": "no-store" },
    });
  }
});

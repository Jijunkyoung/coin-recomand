import { createClient } from "npm:@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type, x-kis-scheduler-key",
};
const env = (name: string) => (Deno.env.get(name) || "").trim();
const adminKey = () => env("SUPABASE_SERVICE_ROLE_KEY");

Deno.serve(async (request) => {
  if (request.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const serviceKey = adminKey();
    const ownerId = env("KIS_OWNER_USER_ID");
    const ownerEmail = env("KIS_OWNER_EMAIL").toLowerCase();
    const requestApiKey = request.headers.get("apikey") || "";
    const schedulerKey = request.headers.get("x-kis-scheduler-key") || "";
    const schedulerMode = Boolean((env("KIS_SCHEDULER_KEY") && schedulerKey === env("KIS_SCHEDULER_KEY")) || (serviceKey && requestApiKey === serviceKey));
    if (!serviceKey) throw new Error("Supabase 서버 인증값이 설정되지 않았습니다.");
    const supabase = createClient(env("SUPABASE_URL"), serviceKey);
    let userId = ownerId;
    if (!schedulerMode) {
      const authorization = request.headers.get("Authorization") || "";
      if (!authorization.startsWith("Bearer ")) throw new Error("로그인이 필요합니다.");
      const { data: { user }, error } = await supabase.auth.getUser(authorization.replace(/^Bearer\s+/i, ""));
      if (error || !user) throw new Error("로그인 세션을 확인할 수 없습니다.");
      const matches = ownerId ? user.id === ownerId : Boolean(ownerEmail && (user.email || "").toLowerCase() === ownerEmail);
      if (!matches) return new Response(JSON.stringify({ error: "이 회원에는 개인 자산 조회 권한이 없습니다." }), { status: 403, headers: { ...corsHeaders, "content-type": "application/json" } });
      userId = user.id;
    }
    if (!userId) throw new Error("계좌 소유자 설정이 완료되지 않았습니다.");
    const { data: preferences, error: preferenceError } = await supabase.from("user_preferences")
      .select("holdings_us,holdings_kr,sector_ids,coin_email,stock_email").eq("user_id", userId).maybeSingle();
    if (preferenceError) throw new Error(`회원 설정 조회 실패: ${preferenceError.message}`);
    const { data: authData, error: authError } = await supabase.auth.admin.getUserById(userId);
    if (authError) throw new Error(`회원 이메일 조회 실패: ${authError.message}`);
    const email = authData.user?.email || null;
    return new Response(JSON.stringify({
      profile: {
        holdings_us: preferences?.holdings_us || "", holdings_kr: preferences?.holdings_kr || "",
        sector_ids: preferences?.sector_ids || [], coin_email: preferences?.coin_email || email,
        stock_email: preferences?.stock_email || email,
      },
    }), { headers: { ...corsHeaders, "content-type": "application/json", "cache-control": "no-store" } });
  } catch (error) {
    return new Response(JSON.stringify({ error: error instanceof Error ? error.message : "회원 설정 조회 실패" }), { status: 400, headers: { ...corsHeaders, "content-type": "application/json" } });
  }
});

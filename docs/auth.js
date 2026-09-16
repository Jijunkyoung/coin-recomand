(function () {
  "use strict";

  const sectors = [
    ["defense", "방산"], ["semiconductor", "반도체"], ["energy", "에너지"],
    ["ai_platform", "AI·플랫폼"], ["mobility", "자동차·모빌리티"], ["bio", "바이오·헬스케어"],
    ["finance", "금융"], ["consumer", "소비·유통"], ["shipbuilding", "조선·기계"],
  ];
  const config = window.COIN_RECOMAND_SUPABASE || {};
  const configured = Boolean(config.url && config.anonKey && window.supabase?.createClient);
  const client = configured ? window.supabase.createClient(config.url, config.anonKey, {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
  }) : null;
  let user = null;
  let profile = null;
  let portfolio = null;
  let portfolioSync = null;

  const escapeHTML = value => String(value ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
  const local = key => localStorage.getItem(key) || "";
  const defaultProfile = () => ({
    holdings_us: local("stock-holdings-us-v1"),
    holdings_kr: local("stock-holdings-kr-v1"),
    sector_ids: local("stock-sectors-v1").split(",").filter(Boolean),
    coin_email: local("coin-signal-email-recipients"),
    stock_email: local("stock-email-recipients-v1"),
  });

  const actions = document.createElement("div");
  actions.id = "authActions";
  actions.className = "auth-actions";
  document.querySelector(".top-actions")?.prepend(actions);
  document.body.insertAdjacentHTML("beforeend", `
    <dialog id="authDialog" class="auth-dialog" aria-labelledby="authTitle">
      <div class="auth-shell">
        <div class="dialog-head"><div><span class="eyebrow">MEMBER ACCOUNT</span><h2 id="authTitle">회원 로그인</h2><p id="authSubtitle">회원별 보유주식과 관심분야를 안전하게 저장합니다.</p></div><button type="button" id="authClose" class="dialog-close" aria-label="닫기">×</button></div>
        <div id="authGuest">
          <div class="auth-tabs" role="tablist"><button type="button" data-auth-mode="login" class="active">로그인</button><button type="button" data-auth-mode="signup">회원가입</button></div>
          <form id="loginForm" class="auth-panel"><label class="auth-field">이메일<input id="loginEmail" type="email" autocomplete="email" required></label><label class="auth-field">비밀번호<input id="loginPassword" type="password" autocomplete="current-password" minlength="8" required></label><button class="auth-submit" type="submit">로그인</button></form>
          <form id="signupForm" class="auth-panel" hidden><label class="auth-field">이메일<input id="signupEmail" type="email" autocomplete="email" required></label><label class="auth-field">비밀번호<input id="signupPassword" type="password" autocomplete="new-password" minlength="8" required></label><label class="auth-field">비밀번호 확인<input id="signupPasswordConfirm" type="password" autocomplete="new-password" minlength="8" required></label><button class="auth-submit" type="submit">확인메일 받고 가입하기</button><p class="auth-help">메일의 인증 링크를 누른 뒤 이 페이지로 돌아오면 로그인이 완료됩니다.</p></form>
        </div>
        <form id="profileForm" class="auth-panel" hidden>
          <p id="profileAccountEmail" class="profile-email"></p>
          <div class="profile-grid"><label class="auth-field">코인 보고서 수신목록<textarea id="profileCoinEmail" rows="3" placeholder="coin@example.com&#10;team@example.com"></textarea></label><label class="auth-field">주식 보고서 수신목록<textarea id="profileStockEmail" rows="3" placeholder="stock@example.com&#10;team@example.com"></textarea></label></div>
          <div class="profile-grid"><label class="auth-field">미국 보유주식<textarea id="profileHoldingsUs" rows="4" placeholder="AAPL|애플&#10;NVDA|엔비디아"></textarea></label><label class="auth-field">국내 보유주식<textarea id="profileHoldingsKr" rows="4" placeholder="005930|삼성전자&#10;000660|SK하이닉스"></textarea></label></div>
          <div class="broker-sync-row"><div><strong>한국투자증권 계좌 자동 동기화</strong><span id="brokerSyncStatus">주식 페이지에 로그인하면 자동으로 갱신합니다.</span></div><button type="button" id="brokerSyncButton">지금 동기화</button></div>
          <label class="auth-field">관심분야</label><div id="profileSectors" class="profile-sectors">${sectors.map(([id,label]) => `<label><input type="checkbox" value="${id}"><span>${label}</span></label>`).join("")}</div>
          <div class="auth-profile-actions"><button type="submit" class="auth-submit">내 설정 저장</button><button type="button" id="logoutButton" class="auth-logout">로그아웃</button></div>
          <p class="auth-help">설정은 로그인한 회원 본인만 읽고 수정할 수 있습니다.</p>
        </form>
        <div id="authConfigNote" class="auth-config-note" hidden>회원 기능 연결 전입니다. 저장소에 <code>SUPABASE_URL</code>과 <code>SUPABASE_ANON_KEY</code>를 등록하고 배포하면 활성화됩니다.</div>
        <p id="authStatus" class="auth-status" aria-live="polite"></p>
      </div>
    </dialog>`);

  const $ = selector => document.querySelector(selector);
  const dialog = $("#authDialog");
  function status(message, error = false) { const node = $("#authStatus"); node.textContent = message; node.classList.toggle("error", error); }
  function setBusy(form, busy) { form.querySelectorAll("input,textarea,button").forEach(node => node.disabled = busy); }
  function showMode(mode) {
    $("#loginForm").hidden = mode !== "login"; $("#signupForm").hidden = mode !== "signup";
    document.querySelectorAll("[data-auth-mode]").forEach(b => b.classList.toggle("active", b.dataset.authMode === mode));
    $("#authTitle").textContent = mode === "signup" ? "회원가입" : "회원 로그인"; status("");
  }
  function syncLocal(p) {
    if (!p) return;
    localStorage.setItem("stock-holdings-us-v1", p.holdings_us || ""); localStorage.setItem("stock-holdings-kr-v1", p.holdings_kr || "");
    localStorage.setItem("stock-sectors-v1", (p.sector_ids || []).join(","));
    if (p.coin_email) localStorage.setItem("coin-signal-email-recipients", p.coin_email);
    if (p.stock_email) localStorage.setItem("stock-email-recipients-v1", p.stock_email);
  }
  function portfolioCacheKey() { return user ? `kis-portfolio-${user.id}` : ""; }
  function dispatchPortfolio() { window.dispatchEvent(new CustomEvent("kis-portfolio-sync", { detail: portfolio })); }
  function setBrokerStatus(message, error = false) { const node = $("#brokerSyncStatus"); if (!node) return; node.textContent = message; node.classList.toggle("error", error); }
  function cachedPortfolio() {
    try { return JSON.parse(sessionStorage.getItem(portfolioCacheKey()) || "null"); } catch { return null; }
  }
  async function functionErrorMessage(error) {
    try { const body = await error?.context?.json(); return body?.error || error.message; } catch { return error?.message || "계좌 동기화 실패"; }
  }
  async function syncBrokerageHoldings({ force = false } = {}) {
    if (!client || !user) throw new Error("로그인이 필요합니다.");
    if (!document.body.dataset.stockMarket && !force) return null;
    const cached = cachedPortfolio();
    if (cached) { portfolio = cached; dispatchPortfolio(); }
    if (!force && cached?.synced_at && Date.now() - Date.parse(cached.synced_at) < 5 * 60 * 1000) {
      setBrokerStatus(`${new Date(cached.synced_at).toLocaleString("ko-KR")} 동기화 완료`); return cached;
    }
    if (portfolioSync) return portfolioSync;
    setBrokerStatus("한국투자증권 계좌를 불러오는 중입니다.");
    portfolioSync = (async () => {
      const { data, error } = await client.functions.invoke("kis-portfolio", { body: {} });
      if (error) throw new Error(await functionErrorMessage(error));
      if (data?.error) throw new Error(data.error);
      portfolio = data;
      sessionStorage.setItem(portfolioCacheKey(), JSON.stringify(data));
      const holdings = { holdings_us: [], holdings_kr: [] };
      for (const item of data.positions || []) holdings[item.market === "us" ? "holdings_us" : "holdings_kr"].push(`${item.symbol}|${item.name}`);
      profile = { ...defaultProfile(), ...(profile || {}), holdings_us: holdings.holdings_us.join("\n"), holdings_kr: holdings.holdings_kr.join("\n") };
      syncLocal(profile); renderProfile(); dispatchPortfolio();
      window.dispatchEvent(new CustomEvent("coin-auth-change", { detail: { user, profile } }));
      setBrokerStatus(`${new Date(data.synced_at).toLocaleString("ko-KR")} 동기화 완료`);
      return data;
    })().catch(error => { setBrokerStatus(error.message, true); throw error; }).finally(() => { portfolioSync = null; });
    return portfolioSync;
  }
  function renderProfile() {
    $("#profileAccountEmail").textContent = `로그인 계정 · ${user?.email || ""}`;
    $("#profileCoinEmail").value = profile?.coin_email || user?.email || ""; $("#profileStockEmail").value = profile?.stock_email || user?.email || "";
    $("#profileHoldingsUs").value = profile?.holdings_us || ""; $("#profileHoldingsKr").value = profile?.holdings_kr || "";
    const selected = profile?.sector_ids || []; $("#profileSectors").querySelectorAll("input").forEach(input => input.checked = selected.includes(input.value));
    if (portfolio?.synced_at) setBrokerStatus(`${new Date(portfolio.synced_at).toLocaleString("ko-KR")} 동기화 완료`);
  }
  function renderActions() {
    if (user) actions.innerHTML = `<span class="auth-user" title="${escapeHTML(user.email)}">${escapeHTML(user.email)}</span><button type="button" class="auth-button primary" id="profileOpen">내 설정</button><button type="button" class="auth-button logout" id="logoutTop">로그아웃</button>`;
    else actions.innerHTML = `<button type="button" class="auth-button" id="loginOpen">로그인</button><button type="button" class="auth-button primary" id="signupOpen">회원가입</button>`;
    $("#loginOpen")?.addEventListener("click", () => openDialog("login")); $("#signupOpen")?.addEventListener("click", () => openDialog("signup")); $("#profileOpen")?.addEventListener("click", () => openDialog("profile"));
    $("#logoutTop")?.addEventListener("click", async event => { const button=event.currentTarget; button.disabled=true; button.textContent="로그아웃 중"; const { error }=await client.auth.signOut(); if(error){button.disabled=false;button.textContent="로그아웃";status(error.message,true);openDialog("profile");} });
  }
  function openDialog(mode) {
    $("#authConfigNote").hidden = configured;
    if (mode === "profile" && user) { $("#authGuest").hidden = true; $("#profileForm").hidden = false; $("#authTitle").textContent = "내 맞춤 설정"; renderProfile(); }
    else { $("#authGuest").hidden = false; $("#profileForm").hidden = true; showMode(mode); }
    dialog.showModal();
  }
  async function loadProfile() {
    if (!client || !user) return;
    const { data, error } = await client.from("user_preferences").select("holdings_us,holdings_kr,sector_ids,coin_email,stock_email").eq("user_id", user.id).maybeSingle();
    if (error) { status(`회원 설정을 불러오지 못했습니다: ${error.message}`, true); return; }
    profile = data || defaultProfile(); syncLocal(profile); renderProfile();
    window.dispatchEvent(new CustomEvent("coin-auth-change", { detail: { user, profile } }));
    syncBrokerageHoldings().catch(() => {});
  }
  async function savePreferences(partial) {
    if (!client || !user) throw new Error("로그인이 필요합니다.");
    const next = { ...defaultProfile(), ...(profile || {}), ...partial, user_id: user.id, updated_at: new Date().toISOString() };
    const { data, error } = await client.from("user_preferences").upsert(next, { onConflict: "user_id" }).select("holdings_us,holdings_kr,sector_ids,coin_email,stock_email").single();
    if (error) throw error; profile = data; syncLocal(profile); renderProfile();
    window.dispatchEvent(new CustomEvent("coin-auth-change", { detail: { user, profile } })); return profile;
  }
  window.CoinAuth = { configured, get user() { return user; }, get profile() { return profile; }, get portfolio() { return portfolio; }, savePreferences, syncBrokerageHoldings, open: openDialog };
  renderActions();
  $("#authClose").addEventListener("click", () => dialog.close()); dialog.addEventListener("click", e => { if (e.target === dialog) dialog.close(); });
  document.querySelectorAll("[data-auth-mode]").forEach(b => b.addEventListener("click", () => showMode(b.dataset.authMode)));
  $("#loginForm").addEventListener("submit", async event => { event.preventDefault(); if (!configured) return status("Supabase 연결 설정이 필요합니다.", true); setBusy(event.currentTarget, true); const { error } = await client.auth.signInWithPassword({ email: $("#loginEmail").value.trim(), password: $("#loginPassword").value }); setBusy(event.currentTarget, false); if (error) return status(error.message, true); status("로그인했습니다."); dialog.close(); });
  $("#signupForm").addEventListener("submit", async event => { event.preventDefault(); const password = $("#signupPassword").value; if (password !== $("#signupPasswordConfirm").value) return status("비밀번호 확인이 일치하지 않습니다.", true); if (!configured) return status("Supabase 연결 설정이 필요합니다.", true); setBusy(event.currentTarget, true); const redirect = `${location.origin}${location.pathname}`; const { data, error } = await client.auth.signUp({ email: $("#signupEmail").value.trim(), password, options: { emailRedirectTo: redirect } }); setBusy(event.currentTarget, false); if (error) return status(error.message, true); status(data.session ? "가입과 로그인이 완료됐습니다." : "확인메일을 보냈습니다. 메일의 인증 링크를 눌러 가입을 완료하세요."); });
  $("#profileForm").addEventListener("submit", async event => { event.preventDefault(); setBusy(event.currentTarget, true); try { await savePreferences({ coin_email: $("#profileCoinEmail").value.trim() || null, stock_email: $("#profileStockEmail").value.trim() || null, holdings_us: $("#profileHoldingsUs").value.trim(), holdings_kr: $("#profileHoldingsKr").value.trim(), sector_ids: [...$("#profileSectors").querySelectorAll("input:checked")].map(x => x.value) }); status("회원별 맞춤 설정을 저장했습니다."); } catch (error) { status(error.message, true); } finally { setBusy(event.currentTarget, false); } });
  $("#logoutButton").addEventListener("click", async () => { await client?.auth.signOut(); dialog.close(); });
  $("#brokerSyncButton").addEventListener("click", async event => { const button=event.currentTarget; button.disabled=true; try { await syncBrokerageHoldings({force:true}); status("계좌 보유현황을 갱신했습니다."); } catch(error) { status(error.message,true); } finally { button.disabled=false; } });
  if (client) {
    client.auth.getSession().then(({ data }) => { user = data.session?.user || null; renderActions(); if (user) loadProfile(); });
    client.auth.onAuthStateChange((_event, session) => { user = session?.user || null; profile = user ? profile : null; portfolio = user ? portfolio : null; renderActions(); if (user) setTimeout(loadProfile, 0); window.dispatchEvent(new CustomEvent("coin-auth-change", { detail: { user, profile } })); });
  }
})();

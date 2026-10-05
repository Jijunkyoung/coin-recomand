// Shared real-candle loading and aggregation for coin and stock detail dialogs.
(() => {
  const cache = new Map(), labels = { "1h": "1시간봉", "4h": "4시간봉", "1d": "일봉", "1w": "주봉" };
  function weekKey(timestamp) {
    const at = new Date(timestamp); at.setUTCHours(0, 0, 0, 0); at.setUTCDate(at.getUTCDate() - (at.getUTCDay() + 6) % 7); return at.toISOString().slice(0, 10);
  }
  function aggregate(rows, interval) {
    if (interval !== "4h" && interval !== "1w") return rows;
    const groups = new Map(), sessionStarts = new Map();
    for (const row of rows) {
      const session = row.session || String(row.date).slice(0, 10);
      if (!sessionStarts.has(session)) sessionStarts.set(session, row.timestamp);
      const key = interval === "1w" ? weekKey(Date.parse(session + "T00:00:00Z")) : `${session}:${Math.floor((row.timestamp - sessionStarts.get(session)) / 14400000)}`;
      const previous = groups.get(key);
      if (previous) { previous.high = Math.max(previous.high, row.high); previous.low = Math.min(previous.low, row.low); previous.price = row.price; previous.volume += row.volume; }
      else groups.set(key, { ...row, date: interval === "1w" ? key : row.date });
    }
    return [...groups.values()];
  }
  async function loadCoin(coin, interval) {
    const market = coin.market || `KRW-${coin.symbol || "BTC"}`, key = `${market}:${interval}`;
    if (!/^KRW-[A-Z0-9]+$/.test(market)) throw new Error("업비트 원화시장 종목코드를 확인할 수 없습니다.");
    const previous = cache.get(key); if (previous && Date.now() - previous.at < 60000) return previous.data;
    const path = { "1h": "minutes/60", "4h": "minutes/240", "1d": "days", "1w": "weeks" }[interval];
    if (!path) throw new Error("지원하지 않는 봉입니다.");
    const result = await window.CoinAuth.coinChart({ market, interval });
    const rows = result.rows; if (!rows?.length) throw new Error("해당 종목의 캔들 자료가 없습니다.");
    const data = { rows, source: "업비트", interval }; cache.set(key, { at: Date.now(), data }); return data;
  }
  async function loadStock(stock, market, interval) {
    const key = `${market}:${stock.symbol}:${interval}`; const previous = cache.get(key);
    if (previous && Date.now() - previous.at < 60000) return previous.data;
    const data = await window.CoinAuth.stockChart({ symbol: stock.symbol, market, interval });
    const rows = aggregate(data.rows, interval); if (!rows.length) throw new Error("해당 봉의 자료가 없습니다.");
    const output = { ...data, rows, interval }; cache.set(key, { at: Date.now(), data: output }); return output;
  }
  function visible(rows, days) {
    if (days === "all") return rows;
    const last = rows.at(-1)?.timestamp || Date.parse(rows.at(-1)?.date || "");
    const cutoff = last - Number(days) * 86400000;
    return rows.filter(row => (row.timestamp || Date.parse(row.date)) >= cutoff);
  }
  function axisNumber(value) {
    if (!Number.isFinite(value)) return "—";
    const magnitude = Math.abs(value); if (magnitude === 0) return "0";
    if (magnitude < .01) return value.toExponential(1);
    return Intl.NumberFormat("ko-KR", { notation: magnitude >= 1000 ? "compact" : "standard", maximumFractionDigits: magnitude < 1 ? 4 : magnitude >= 1000 ? 1 : 2 }).format(value);
  }
  window.ChartData = { axisNumber, labels, aggregate, loadCoin, loadStock, visible };
})();

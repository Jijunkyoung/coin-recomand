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
  function visibleRange(rows, days) {
    const end = rows.length;
    return { start: end - visible(rows, days).length, end };
  }
  function bindChartNavigation(canvas, getView, onRange, onDragStart) {
    let drag = null;
    function cancelDrag() {
      if (!drag) return;
      const { pointerId } = drag;
      drag = null;
      canvas.style.cursor = "";
      if (canvas.hasPointerCapture(pointerId)) canvas.releasePointerCapture(pointerId);
    }
    canvas.addEventListener("pointerdown", event => {
      if (drag || event.button !== 0 || event.pointerType === "touch") return;
      const { plot, range, total } = getView();
      const count = range.end - range.start;
      if (canvas.hidden || !plot || !count || count >= total) return;
      const rect = canvas.getBoundingClientRect();
      const scale = rect.width / plot.width;
      const plotWidth = (plot.width - plot.pad.left - plot.pad.right) * scale;
      const x = event.clientX - rect.left - plot.pad.left * scale;
      if (plotWidth <= 0 || x < 0 || x > plotWidth) return;
      canvas.setPointerCapture(event.pointerId);
      drag = { pointerId: event.pointerId, x: event.clientX, start: range.start, count, total, plotWidth };
      canvas.style.cursor = "grabbing";
      event.preventDefault();
      onDragStart();
    });
    canvas.addEventListener("pointermove", event => {
      if (!drag || event.pointerId !== drag.pointerId) return;
      if (!(event.buttons & 1)) { cancelDrag(); return; }
      const { x, start, count, total, plotWidth } = drag;
      const shift = Math.round((x - event.clientX) * count / plotWidth);
      const next = Math.max(0, Math.min(total - count, start + shift));
      if (next !== getView().range.start) onRange({ start: next, end: next + count });
    });
    for (const name of ["pointerup", "pointercancel", "lostpointercapture"]) {
      canvas.addEventListener(name, event => {
        if (event.pointerId === drag?.pointerId) cancelDrag();
      });
    }
    canvas.addEventListener("wheel", event => {
      if (drag) return;
      if (event.ctrlKey || event.metaKey || !event.deltaY || Math.abs(event.deltaX) > Math.abs(event.deltaY)) return;
      const { plot, range, total } = getView();
      if (canvas.hidden || !plot || total <= 1) return;
      const rect = canvas.getBoundingClientRect();
      if (!rect.width) return;
      const localX = (event.clientX - rect.left) * plot.width / rect.width;
      const anchor = (localX - plot.pad.left) / (plot.width - plot.pad.left - plot.pad.right);
      if (anchor < 0 || anchor > 1) return;
      event.preventDefault();
      const pixels = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? rect.height : 1);
      const count = range.end - range.start, factor = Math.exp(Math.max(-1, Math.min(1, pixels / 420)));
      const scaled = pixels < 0 ? Math.floor(count * factor) : Math.ceil(count * factor);
      const nextCount = Math.max(Math.min(3, count), Math.min(total, scaled));
      if (nextCount === count) return;
      // Keep the same part of the timeline under the pointer, up to the loaded edges.
      const start = Math.max(0, Math.min(total - nextCount, Math.round(range.start + anchor * (count - nextCount))));
      onRange({ start, end: start + nextCount });
    }, { passive: false });
    return { cancelDrag, isDragging: () => drag !== null };
  }
  function axisNumber(value) {
    if (!Number.isFinite(value)) return "—";
    const magnitude = Math.abs(value); if (magnitude === 0) return "0";
    if (magnitude < .01) return value.toExponential(1);
    return Intl.NumberFormat("ko-KR", { notation: magnitude >= 1000 ? "compact" : "standard", maximumFractionDigits: magnitude < 1 ? 4 : magnitude >= 1000 ? 1 : 2 }).format(value);
  }
  window.ChartData = { axisNumber, labels, aggregate, loadCoin, loadStock, visible, visibleRange, bindChartNavigation };
})();

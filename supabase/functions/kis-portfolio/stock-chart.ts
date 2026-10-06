type ChartRow = { timestamp: number; date: string; session: string; open: number; high: number; low: number; price: number; volume: number };
const chartCache = new Map<string, { at: number; data: unknown }>();
export async function stockChart(body: Record<string, unknown>, signal?: AbortSignal) {
  const symbol = String(body.symbol || "").trim().toUpperCase(), market = String(body.market || "");
  const interval = String(body.interval || "1d");
  if (!["us", "kr"].includes(market) || !/^[A-Z0-9][A-Z0-9.\-]{0,15}$/.test(symbol) || (market === "kr" && !/^[A-Z0-9]{6}$/.test(symbol)) || !["1d", "1w", "1h", "4h"].includes(interval)) throw new Error("종목 또는 봉 선택값이 올바르지 않습니다.");
  const hourly = interval === "1h" || interval === "4h", key = `${market}:${symbol}:${hourly}`;
  const cached = chartCache.get(key);
  if (cached && Date.now() - cached.at < 90_000) return cached.data;
  const symbols = market === "kr" ? [`${symbol}.KS`, `${symbol}.KQ`] : [symbol.replace(".", "-")];
  for (const ticker of symbols) {
    for (const host of ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]) {
      if (signal?.aborted) throw new Error("과거 시세 조회 시간 초과: 직접 입력해 주세요.");
      try {
        const query = new URLSearchParams({ interval: hourly ? "60m" : "1d", range: hourly ? "3mo" : "5y", includePrePost: "false" });
        const response = await fetch(`https://${host}/v8/finance/chart/${encodeURIComponent(ticker)}?${query}`, { headers: { "user-agent": "Mozilla/5.0", accept: "application/json" }, signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(8000)]) : AbortSignal.timeout(8000) });
        if (!response.ok) continue;
        const result = (await response.json()).chart?.result?.[0], quote = result?.indicators?.quote?.[0];
        if (!quote || !Array.isArray(result.timestamp)) continue;
        const timezone = result.meta.exchangeTimezoneName || (market === "kr" ? "Asia/Seoul" : "America/New_York");
        const day = new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" });
        const clock = new Intl.DateTimeFormat("ko-KR", { timeZone: timezone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
        const rows: ChartRow[] = result.timestamp.flatMap((timestamp: number, i: number) => {
          const values = [quote.open[i], quote.high[i], quote.low[i], quote.close[i]];
          if (values.some(value => value == null || !Number.isFinite(Number(value)))) return [];
          const at = new Date(timestamp * 1000), session = day.format(at);
          return [{ timestamp: timestamp * 1000, date: session + (hourly ? ` ${clock.format(at)}` : ""), session,
            open: Number(values[0]), high: Number(values[1]), low: Number(values[2]), price: Number(values[3]), volume: Number(quote.volume[i]) || 0 }];
        });
        if (!rows.length) continue;
        const data = { rows, source: "Yahoo Finance", currency: result.meta.currency, timezone, interval: hourly ? "1h" : "1d", fetched_at: new Date().toISOString() };
        if (chartCache.size >= 100) chartCache.delete(chartCache.keys().next().value!);
        chartCache.set(key, { at: Date.now(), data });
        return data;
      } catch { /* try the next public quote endpoint; never manufacture candles */ }
    }
  }
  throw new Error("이 종목의 시세 차트를 가져오지 못했습니다. 잠시 후 다시 시도해 주세요.");
}

export async function coinChart(body: Record<string, unknown>) {
  const market = String(body.market || ""), interval = String(body.interval || "1d");
  const path = ({ "1h": "minutes/60", "4h": "minutes/240", "1d": "days", "1w": "weeks" } as Record<string, string>)[interval];
  if (!/^KRW-[A-Z0-9]+$/.test(market) || !path) throw new Error("코인 또는 봉 선택값이 올바르지 않습니다.");
  const key = `coin:${market}:${interval}`, cached = chartCache.get(key);
  if (cached && Date.now() - cached.at < 30_000) return cached.data;
  const response = await fetch(`https://api.upbit.com/v1/candles/${path}?market=${encodeURIComponent(market)}&count=200`, { signal: AbortSignal.timeout(8000) });
  if (!response.ok) throw new Error("업비트 캔들 조회가 지연되고 있습니다. 잠시 후 다시 선택해 주세요.");
  const candles = await response.json(); if (!Array.isArray(candles) || !candles.length) throw new Error("캔들 자료가 없습니다.");
  const rows = candles.reverse().map(row => ({ timestamp: Date.parse(row.candle_date_time_utc + "Z"), date: row.candle_date_time_kst.replace("T", " ").slice(0, interval.endsWith("h") ? 16 : 10), open: row.opening_price, high: row.high_price, low: row.low_price, price: row.trade_price, volume: row.candle_acc_trade_price }));
  const data = { rows, source: "업비트", interval }; if (chartCache.size >= 100) chartCache.delete(chartCache.keys().next().value!); chartCache.set(key, { at: Date.now(), data }); return data;
}

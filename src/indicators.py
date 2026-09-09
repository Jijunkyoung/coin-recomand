from __future__ import annotations

import math
import statistics
from typing import Iterable, Sequence


def _clean(values: Iterable[float]) -> list[float]:
    return [float(value) for value in values if value is not None and math.isfinite(float(value))]


def sma(values: Sequence[float], period: int) -> float | None:
    clean = _clean(values)
    if period <= 0 or len(clean) < period:
        return None
    return sum(clean[-period:]) / period


def ema_series(values: Sequence[float], period: int) -> list[float]:
    clean = _clean(values)
    if not clean or period <= 0:
        return []
    multiplier = 2 / (period + 1)
    result = [clean[0]]
    for value in clean[1:]:
        result.append((value - result[-1]) * multiplier + result[-1])
    return result


def ema(values: Sequence[float], period: int) -> float | None:
    result = ema_series(values, period)
    return result[-1] if len(result) >= period else None


def rsi(values: Sequence[float], period: int = 14) -> float | None:
    clean = _clean(values)
    if len(clean) <= period:
        return None
    changes = [clean[index] - clean[index - 1] for index in range(1, len(clean))]
    seed = changes[:period]
    avg_gain = sum(max(change, 0) for change in seed) / period
    avg_loss = sum(max(-change, 0) for change in seed) / period
    for change in changes[period:]:
        avg_gain = ((avg_gain * (period - 1)) + max(change, 0)) / period
        avg_loss = ((avg_loss * (period - 1)) + max(-change, 0)) / period
    if avg_loss == 0:
        return 100.0
    relative_strength = avg_gain / avg_loss
    return 100 - (100 / (1 + relative_strength))


def macd(values: Sequence[float]) -> tuple[float | None, float | None, float | None]:
    clean = _clean(values)
    if len(clean) < 35:
        return None, None, None
    fast = ema_series(clean, 12)
    slow = ema_series(clean, 26)
    line = [fast[index] - slow[index] for index in range(len(clean))]
    signal_series = ema_series(line, 9)
    return line[-1], signal_series[-1], line[-1] - signal_series[-1]


def pct_change(values: Sequence[float], days: int) -> float | None:
    clean = _clean(values)
    if days <= 0 or len(clean) <= days or clean[-days - 1] == 0:
        return None
    return ((clean[-1] / clean[-days - 1]) - 1) * 100


def annualized_volatility(values: Sequence[float], lookback: int = 30) -> float | None:
    clean = _clean(values)
    if len(clean) < 3:
        return None
    subset = clean[-(lookback + 1) :]
    returns = [math.log(subset[index] / subset[index - 1]) for index in range(1, len(subset)) if subset[index - 1] > 0]
    if len(returns) < 2:
        return None
    return statistics.stdev(returns) * math.sqrt(365) * 100


def volume_ratio(volumes: Sequence[float], short: int = 7, long: int = 30) -> float | None:
    clean = _clean(volumes)
    if len(clean) < long:
        return None
    recent = sum(clean[-short:]) / short
    baseline = sum(clean[-long:]) / long
    return recent / baseline if baseline else None


def mvrv_z_score(market_caps: Sequence[float], realized_caps: Sequence[float]) -> float | None:
    markets = _clean(market_caps)
    realized = _clean(realized_caps)
    if len(markets) < 30 or not realized:
        return None
    deviation = statistics.pstdev(markets)
    if deviation == 0:
        return None
    return (markets[-1] - realized[-1]) / deviation

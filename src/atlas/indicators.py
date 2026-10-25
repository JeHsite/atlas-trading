"""Technical indicators on a bar DataFrame (columns: open, high, low, close, volume).

Every value at row t uses only data up to and including row t, so a strategy
deciding at the close of t never sees the future. Channel levels are shifted
one bar so "breaks the 20-day high" compares today's close with the previous
20 days.
"""

from __future__ import annotations

import pandas as pd

from atlas.domain import Bar


def bars_to_frame(bars: list[Bar]) -> pd.DataFrame:
    df = pd.DataFrame(
        [
            {
                "ts": b.ts,
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            }
            for b in bars
        ]
    )
    return df.set_index("ts").sort_index() if not df.empty else df


def sma(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(n, min_periods=n).mean()


def ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(series: pd.Series, n: int = 14) -> pd.Series:
    """Wilder's RSI. 100 when there were no losses in the window."""
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    out = 100 - 100 / (1 + gain / loss)
    return out.where(loss != 0, 100.0).where(gain.notna())


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def donchian(df: pd.DataFrame, n: int) -> tuple[pd.Series, pd.Series]:
    """Highest high / lowest low of the previous ``n`` bars (excluding the current one)."""
    upper = df["high"].rolling(n, min_periods=n).max().shift(1)
    lower = df["low"].rolling(n, min_periods=n).min().shift(1)
    return upper, lower


def macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series]:
    line = ema(series, fast) - ema(series, slow)
    return line, line.ewm(span=signal, adjust=False, min_periods=signal).mean()


def bollinger(series: pd.Series, n: int = 20, k: float = 2.0) -> tuple[pd.Series, pd.Series]:
    mid = sma(series, n)
    std = series.rolling(n, min_periods=n).std()
    return mid - k * std, mid + k * std

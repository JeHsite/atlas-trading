"""Rule-based strategies that turn indicators into trade proposals.

These are the deterministic baseline. The LLM layer (phase 3) will add its own
proposals and can veto or annotate these; every proposal carries a ``setup``
name so the learning layer can judge each setup on its own record.
"""

from __future__ import annotations

import math
from typing import Protocol

import pandas as pd

from atlas.domain import Direction, Horizon, Instrument, TradeProposal
from atlas.indicators import atr, donchian, rsi, sma


class Strategy(Protocol):
    name: str
    warmup: int

    def signal(self, df: pd.DataFrame, instrument: Instrument) -> TradeProposal | None:
        """Decide at the close of the last row of ``df``."""
        ...


def _valid(*values: float) -> bool:
    return all(v is not None and not math.isnan(v) and v > 0 for v in values)


class DonchianBreakout:
    """Trend following: buy a close above the previous N-bar high (sell below the low)."""

    def __init__(
        self,
        lookback: int = 20,
        atr_period: int = 14,
        stop_atr: float = 2.0,
        target_r: float = 2.0,
        trend_filter: int = 100,
        allow_short: bool = True,
    ):
        self.name = f"donchian_breakout_{lookback}"
        self.lookback = lookback
        self.atr_period = atr_period
        self.stop_atr = stop_atr
        self.target_r = target_r
        self.trend_filter = trend_filter
        self.allow_short = allow_short
        self.warmup = max(lookback, atr_period, trend_filter) + 1

    def signal(self, df: pd.DataFrame, instrument: Instrument) -> TradeProposal | None:
        if len(df) < self.warmup:
            return None
        upper, lower = donchian(df, self.lookback)
        vol = atr(df, self.atr_period).iloc[-1]
        trend = sma(df["close"], self.trend_filter).iloc[-1]
        close = df["close"].iloc[-1]
        if not _valid(upper.iloc[-1], lower.iloc[-1], vol, trend, close):
            return None

        risk = self.stop_atr * vol
        if close > upper.iloc[-1] and close > trend:
            direction, stop, target = Direction.LONG, close - risk, close + self.target_r * risk
        elif self.allow_short and close < lower.iloc[-1] and close < trend:
            direction, stop, target = Direction.SHORT, close + risk, close - self.target_r * risk
        else:
            return None
        if stop <= 0 or target <= 0:
            return None
        return TradeProposal(
            instrument=instrument,
            direction=direction,
            horizon=Horizon.SWING,
            entry=close,
            stop=stop,
            targets=[target],
            confidence=60,
            thesis=f"{self.lookback}-bar channel breakout in the direction of the "
            f"{self.trend_filter}-bar trend",
            invalidation=f"close back through the stop ({self.stop_atr} ATR)",
            setup=self.name,
        )


class RsiPullback:
    """Mean reversion inside an uptrend: buy a short-term oversold dip above the long SMA."""

    def __init__(
        self,
        rsi_period: int = 2,
        oversold: float = 10.0,
        trend_filter: int = 200,
        atr_period: int = 14,
        stop_atr: float = 1.5,
        target_r: float = 1.5,
    ):
        self.name = f"rsi{rsi_period}_pullback"
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.trend_filter = trend_filter
        self.atr_period = atr_period
        self.stop_atr = stop_atr
        self.target_r = target_r
        self.warmup = max(trend_filter, atr_period, rsi_period) + 1

    def signal(self, df: pd.DataFrame, instrument: Instrument) -> TradeProposal | None:
        if len(df) < self.warmup:
            return None
        close = df["close"].iloc[-1]
        trend = sma(df["close"], self.trend_filter).iloc[-1]
        osc = rsi(df["close"], self.rsi_period).iloc[-1]
        vol = atr(df, self.atr_period).iloc[-1]
        if not _valid(close, trend, vol) or math.isnan(osc):
            return None
        if not (close > trend and osc < self.oversold):
            return None
        risk = self.stop_atr * vol
        if close - risk <= 0:
            return None
        return TradeProposal(
            instrument=instrument,
            direction=Direction.LONG,
            horizon=Horizon.SWING,
            entry=close,
            stop=close - risk,
            targets=[close + self.target_r * risk],
            confidence=58,
            thesis=f"RSI({self.rsi_period}) {osc:.0f} oversold above the "
            f"{self.trend_filter}-bar trend",
            invalidation="trend filter lost or stop hit",
            setup=self.name,
        )

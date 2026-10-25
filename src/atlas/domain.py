"""Core domain types shared by every module.

Monetary values are in the instrument's own currency unless the field name ends
with ``_base`` (the account's base currency, USD by default).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AssetClass(StrEnum):
    EQUITY = "equity"
    ETF = "etf"
    BOND = "bond"
    CRYPTO = "crypto"
    FX = "fx"


class Direction(StrEnum):
    LONG = "long"
    SHORT = "short"


class Horizon(StrEnum):
    INTRADAY = "intraday"
    SWING = "swing"  # days to weeks
    POSITION = "position"  # months
    ALLOCATION = "allocation"  # a year or more


class Instrument(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    asset_class: AssetClass
    venue: str = Field(min_length=1, description="Venue code, e.g. XNYS, XTAE, CRYPTO, FX")
    currency: str = Field(min_length=3, max_length=3)
    country: str | None = Field(default=None, description="ISO-3166 alpha-2 of the issuer")
    sector: str | None = None


class Bar(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    ts: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)

    @field_validator("ts")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return v

    @model_validator(mode="after")
    def _ohlc_consistent(self) -> Bar:
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("inconsistent OHLC values")
        return self


class TradeProposal(BaseModel):
    """A trade idea as produced by the analysis layer. Never executed directly."""

    instrument: Instrument
    direction: Direction
    horizon: Horizon
    entry: float = Field(gt=0)
    stop: float = Field(gt=0)
    targets: list[float] = Field(min_length=1)
    confidence: int = Field(ge=0, le=100)
    thesis: str = Field(min_length=1)
    setup: str = Field(
        default="discretionary",
        min_length=1,
        description="Strategy/setup name; the learning layer keeps statistics per setup",
    )
    catalyst: str | None = None
    invalidation: str | None = None
    key_risks: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _levels_consistent(self) -> TradeProposal:
        if self.direction is Direction.LONG:
            if self.stop >= self.entry:
                raise ValueError("long stop must be below entry")
            if any(t <= self.entry for t in self.targets):
                raise ValueError("long targets must be above entry")
        else:
            if self.stop <= self.entry:
                raise ValueError("short stop must be above entry")
            if any(t >= self.entry for t in self.targets):
                raise ValueError("short targets must be below entry")
        return self

    @property
    def risk_per_unit(self) -> float:
        return abs(self.entry - self.stop)

    @property
    def reward_risk(self) -> float:
        """Reward-to-risk ratio measured to the first target."""
        return abs(self.targets[0] - self.entry) / self.risk_per_unit


class Position(BaseModel):
    instrument: Instrument
    quantity: float = Field(description="Signed: positive is long, negative is short")
    avg_price: float = Field(gt=0)
    last_price: float = Field(gt=0)
    fx_to_base: float = Field(default=1.0, gt=0)

    @property
    def market_value_base(self) -> float:
        return self.quantity * self.last_price * self.fx_to_base


class PortfolioState(BaseModel):
    equity_base: float = Field(gt=0)
    peak_equity_base: float = Field(gt=0)
    day_pnl_base: float = 0.0
    positions: list[Position] = Field(default_factory=list)

    @property
    def drawdown_pct(self) -> float:
        return max(0.0, (self.peak_equity_base - self.equity_base) / self.peak_equity_base * 100)

    @property
    def day_pnl_pct(self) -> float:
        start_of_day = self.equity_base - self.day_pnl_base
        return self.day_pnl_base / start_of_day * 100


class MarketSnapshot(BaseModel):
    """Deterministic market facts the risk engine needs about one instrument."""

    last_price: float = Field(gt=0)
    fx_to_base: float = Field(default=1.0, gt=0)
    avg_daily_value_base: float = Field(ge=0, description="Average daily traded value")
    spread_bps: float = Field(ge=0)
    shortable: bool = False
    tradable_now: bool = True

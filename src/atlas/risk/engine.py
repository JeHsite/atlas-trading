"""Deterministic risk engine.

The analysis layer only *proposes* trades. Every proposal passes through
``evaluate`` which either rejects it or returns an approved, sized quantity.
No LLM output reaches the execution layer without an approved ``RiskDecision``.
"""

from __future__ import annotations

import math
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from atlas.domain import (
    AssetClass,
    Direction,
    MarketSnapshot,
    PortfolioState,
    TradeProposal,
)


class RiskLimits(BaseModel):
    # Account-level circuit breakers
    max_daily_loss_pct: float = Field(default=2.0, gt=0)
    max_drawdown_pct: float = Field(default=10.0, gt=0)

    # Per-trade
    max_risk_per_trade_pct: float = Field(default=0.5, gt=0)
    max_position_pct: float = Field(default=10.0, gt=0)
    min_reward_risk: float = Field(default=1.5, ge=0)
    min_confidence: int = Field(default=55, ge=0, le=100)
    max_entry_deviation_pct: float = Field(default=3.0, gt=0)
    min_order_value_base: float = Field(default=100.0, ge=0)

    # Exposure (percent of equity, gross = sum of absolute market values)
    max_gross_exposure_pct: float = Field(default=150.0, gt=0)
    max_net_exposure_pct: float = Field(default=100.0, gt=0)
    max_sector_pct: float = Field(default=25.0, gt=0)
    max_country_pct: float = Field(default=70.0, gt=0)
    max_asset_class_pct: dict[AssetClass, float] = Field(default_factory=dict)

    # Liquidity
    min_avg_daily_value_base: float = Field(default=1_000_000.0, ge=0)
    max_spread_bps: float = Field(default=30.0, ge=0)
    max_participation_pct: float = Field(
        default=1.0, gt=0, description="Max order value as % of average daily traded value"
    )

    allow_short: bool = True
    fractional_asset_classes: set[AssetClass] = Field(
        default_factory=lambda: {AssetClass.CRYPTO, AssetClass.FX}
    )

    @classmethod
    def from_yaml(cls, path: str | Path) -> RiskLimits:
        with open(path, encoding="utf-8") as f:
            return cls.model_validate(yaml.safe_load(f) or {})


class RiskDecision(BaseModel):
    approved: bool
    quantity: float = 0.0
    order_value_base: float = 0.0
    rejections: list[str] = Field(default_factory=list)
    adjustments: list[str] = Field(default_factory=list)


def _reject(*reasons: str) -> RiskDecision:
    return RiskDecision(approved=False, rejections=list(reasons))


def evaluate(
    proposal: TradeProposal,
    portfolio: PortfolioState,
    snapshot: MarketSnapshot,
    limits: RiskLimits,
    *,
    kill_switch: bool = False,
    risk_multiplier: float = 1.0,
) -> RiskDecision:
    """``risk_multiplier`` comes from the learning layer. It is clamped to
    [0, 1], so learning can shrink or block a setup but never enlarge it."""
    if kill_switch:
        return _reject("kill switch is active")
    risk_multiplier = min(1.0, max(0.0, risk_multiplier))
    if risk_multiplier == 0:
        return _reject(f"setup '{proposal.setup}' is disabled by the learning layer")

    halts = []
    if portfolio.day_pnl_pct <= -limits.max_daily_loss_pct:
        halts.append(f"daily loss {portfolio.day_pnl_pct:.2f}% breached limit")
    if portfolio.drawdown_pct >= limits.max_drawdown_pct:
        halts.append(f"drawdown {portfolio.drawdown_pct:.2f}% breached limit")
    if halts:
        return _reject(*halts)

    inst = proposal.instrument
    rejections = []
    if proposal.confidence < limits.min_confidence:
        rejections.append(f"confidence {proposal.confidence} below {limits.min_confidence}")
    if proposal.reward_risk < limits.min_reward_risk:
        rejections.append(f"reward/risk {proposal.reward_risk:.2f} below {limits.min_reward_risk}")
    if not snapshot.tradable_now:
        rejections.append("instrument is not tradable now")
    if snapshot.avg_daily_value_base < limits.min_avg_daily_value_base:
        rejections.append("insufficient liquidity")
    if snapshot.spread_bps > limits.max_spread_bps:
        rejections.append(f"spread {snapshot.spread_bps:.1f}bps above {limits.max_spread_bps}")
    deviation = abs(proposal.entry - snapshot.last_price) / snapshot.last_price * 100
    if deviation > limits.max_entry_deviation_pct:
        rejections.append(f"entry is {deviation:.2f}% away from last price")
    if proposal.direction is Direction.SHORT:
        if not limits.allow_short:
            rejections.append("short selling disabled")
        elif not snapshot.shortable:
            rejections.append("instrument not shortable")
    if rejections:
        return _reject(*rejections)

    fx = snapshot.fx_to_base
    equity = portfolio.equity_base
    unit_value = proposal.entry * fx
    adjustments: list[str] = []

    # Size from risk budget, then shrink to fit every cap. Each cap is a
    # maximum order value in base currency.
    caps: dict[str, float] = {
        "risk per trade": equity
        * limits.max_risk_per_trade_pct
        * risk_multiplier
        / 100
        / (proposal.risk_per_unit * fx)
        * unit_value,
        "participation": snapshot.avg_daily_value_base * limits.max_participation_pct / 100,
    }

    existing = sum(
        p.market_value_base for p in portfolio.positions if p.instrument.symbol == inst.symbol
    )
    sign = 1 if proposal.direction is Direction.LONG else -1
    # Adding to a position in the same direction consumes the position cap;
    # trading against it is a reduction and is not capped here.
    same_direction_existing = max(0.0, sign * existing)
    caps["position size"] = equity * limits.max_position_pct / 100 - same_direction_existing

    gross = sum(abs(p.market_value_base) for p in portfolio.positions)
    net = sum(p.market_value_base for p in portfolio.positions)
    caps["gross exposure"] = equity * limits.max_gross_exposure_pct / 100 - gross
    caps["net exposure"] = equity * limits.max_net_exposure_pct / 100 - sign * net

    def bucket_exposure(key: str, value: str | None) -> float:
        return sum(
            abs(p.market_value_base)
            for p in portfolio.positions
            if getattr(p.instrument, key) == value
        )

    if inst.sector:
        caps["sector"] = equity * limits.max_sector_pct / 100 - bucket_exposure(
            "sector", inst.sector
        )
    if inst.country:
        caps["country"] = equity * limits.max_country_pct / 100 - bucket_exposure(
            "country", inst.country
        )
    class_limit = limits.max_asset_class_pct.get(inst.asset_class)
    if class_limit is not None:
        caps["asset class"] = equity * class_limit / 100 - bucket_exposure(
            "asset_class", inst.asset_class
        )

    binding, max_value = min(caps.items(), key=lambda kv: kv[1])
    if risk_multiplier < 1:
        adjustments.append(f"risk reduced to {risk_multiplier:.0%} by the learning layer")
    if binding != "risk per trade" and max_value < caps["risk per trade"]:
        adjustments.append(f"size reduced by {binding} limit")

    quantity = max(0.0, max_value) / unit_value
    if inst.asset_class not in limits.fractional_asset_classes:
        quantity = math.floor(quantity)
    order_value = quantity * unit_value

    if quantity <= 0 or order_value < limits.min_order_value_base:
        return RiskDecision(
            approved=False,
            rejections=[f"no capacity left after {binding} limit"],
            adjustments=adjustments,
        )

    return RiskDecision(
        approved=True,
        quantity=quantity * sign,
        order_value_base=order_value,
        adjustments=adjustments,
    )

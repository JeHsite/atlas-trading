"""Paper trading: cost model and the rules for filling and exiting simulated trades.

The same rules drive the backtester and the live demo account, so a backtest
and 1,000 demo trades are judged on identical terms. The rules are
deliberately pessimistic:

- entries fill at the NEXT bar's open (the signal is only known at the close);
- a gap through the stop exits at the open, which can lose more than 1R;
- when one bar touches both stop and target, the stop is assumed hit first;
- every fill pays slippage, half the spread and commission.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from atlas.domain import Bar, Direction, Horizon, Instrument, TradeProposal


class CostModel(BaseModel):
    commission_per_unit: float = Field(default=0.0, ge=0)
    commission_pct: float = Field(default=0.0, ge=0)
    commission_min: float = Field(default=0.0, ge=0)
    spread_bps: float = Field(default=5.0, ge=0)
    slippage_bps: float = Field(default=5.0, ge=0)

    def commission(self, quantity: float, price: float) -> float:
        q = abs(quantity)
        fee = q * self.commission_per_unit + q * price * self.commission_pct / 100
        return max(self.commission_min, fee) if q else 0.0

    def fill_price(self, reference: float, *, buying: bool) -> float:
        adverse = (self.spread_bps / 2 + self.slippage_bps) / 10_000
        return reference * (1 + adverse) if buying else reference * (1 - adverse)


class OpenTrade(BaseModel):
    instrument: Instrument
    setup: str
    direction: Direction
    horizon: Horizon
    quantity: float = Field(gt=0, description="Always positive; direction gives the side")
    entry_ts: datetime
    entry_price: float
    stop: float
    target: float
    fx_to_base: float = 1.0
    entry_commission: float = 0.0
    bars_held: int = 0

    @property
    def initial_risk_base(self) -> float:
        return abs(self.entry_price - self.stop) * self.quantity * self.fx_to_base


class ClosedTrade(BaseModel):
    symbol: str
    asset_class: str
    setup: str
    direction: Direction
    horizon: Horizon
    quantity: float
    entry_ts: datetime
    exit_ts: datetime
    entry_price: float
    exit_price: float
    pnl_base: float
    r_multiple: float
    exit_reason: str

    @property
    def win(self) -> bool:
        return self.pnl_base > 0


def open_trade(
    proposal: TradeProposal, quantity: float, bar: Bar, costs: CostModel, fx_to_base: float = 1.0
) -> OpenTrade:
    """Fill an approved proposal at ``bar``'s open. Stop/target keep their planned prices."""
    long = proposal.direction is Direction.LONG
    price = costs.fill_price(bar.open, buying=long)
    return OpenTrade(
        instrument=proposal.instrument,
        setup=proposal.setup,
        direction=proposal.direction,
        horizon=proposal.horizon,
        quantity=abs(quantity),
        entry_ts=bar.ts,
        entry_price=price,
        stop=proposal.stop,
        target=proposal.targets[0],
        fx_to_base=fx_to_base,
        entry_commission=costs.commission(quantity, price),
    )


def _exit_level(trade: OpenTrade, bar: Bar, *, check_open: bool) -> tuple[float, str] | None:
    long = trade.direction is Direction.LONG
    if check_open:
        if (long and bar.open <= trade.stop) or (not long and bar.open >= trade.stop):
            return bar.open, "stop_gap"
        if (long and bar.open >= trade.target) or (not long and bar.open <= trade.target):
            return bar.open, "target_gap"
    stop_hit = bar.low <= trade.stop if long else bar.high >= trade.stop
    target_hit = bar.high >= trade.target if long else bar.low <= trade.target
    if stop_hit:
        return trade.stop, "stop"
    if target_hit:
        return trade.target, "target"
    return None


def update_trade(
    trade: OpenTrade,
    bar: Bar,
    costs: CostModel,
    *,
    entry_bar: bool = False,
    max_bars: int | None = None,
) -> ClosedTrade | None:
    """Advance an open trade by one bar. Returns the closed trade if it exited."""
    if not entry_bar:
        trade.bars_held += 1
    hit = _exit_level(trade, bar, check_open=not entry_bar)
    if hit is None and max_bars is not None and trade.bars_held >= max_bars:
        hit = (bar.close, "time")
    if hit is None:
        return None
    return close_trade(trade, hit[0], bar.ts, costs, hit[1])


def close_trade(
    trade: OpenTrade, reference: float, ts: datetime, costs: CostModel, reason: str
) -> ClosedTrade:
    long = trade.direction is Direction.LONG
    exit_price = costs.fill_price(reference, buying=not long)
    sign = 1 if long else -1
    gross = (exit_price - trade.entry_price) * trade.quantity * sign
    fees = trade.entry_commission + costs.commission(trade.quantity, exit_price)
    pnl_base = (gross - fees) * trade.fx_to_base
    return ClosedTrade(
        symbol=trade.instrument.symbol,
        asset_class=trade.instrument.asset_class.value,
        setup=trade.setup,
        direction=trade.direction,
        horizon=trade.horizon,
        quantity=trade.quantity,
        entry_ts=trade.entry_ts,
        exit_ts=ts,
        entry_price=trade.entry_price,
        exit_price=exit_price,
        pnl_base=pnl_base,
        r_multiple=pnl_base / trade.initial_risk_base if trade.initial_risk_base else 0.0,
        exit_reason=reason,
    )

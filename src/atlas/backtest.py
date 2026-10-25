"""Bar-by-bar backtester: strategy -> risk engine -> paper fills -> learning.

The loop is the same one the demo account runs live, one instrument and one open trade at a time:
at each bar's close the strategy may propose a trade; the risk engine sizes it
(using the learning layer's multiplier); it fills at the next bar's open; exits
follow ``atlas.paper`` rules; every closed trade is fed back to the learning book
before the next decision.
"""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, Field

from atlas.domain import Bar, Direction, Instrument, MarketSnapshot, PortfolioState
from atlas.indicators import bars_to_frame
from atlas.learning import LearningBook
from atlas.paper import ClosedTrade, CostModel, OpenTrade, open_trade, update_trade
from atlas.risk import RiskLimits, evaluate
from atlas.strategies import Strategy


class BacktestConfig(BaseModel):
    starting_equity_base: float = Field(gt=0)
    fx_to_base: float = Field(default=1.0, gt=0)
    max_bars_held: int | None = Field(default=20, ge=1)
    liquidity_window: int = Field(default=20, ge=1)
    shortable: bool = True


class Metrics(BaseModel):
    trades: int
    win_rate: float
    avg_win_r: float
    avg_loss_r: float
    expectancy_r: float
    profit_factor: float | None
    total_return_pct: float
    max_drawdown_pct: float


class BacktestResult(BaseModel):
    trades: list[ClosedTrade]
    equity_curve: list[float]
    metrics: Metrics
    rejections: dict[str, int]


def compute_metrics(
    trades: list[ClosedTrade], equity_curve: list[float], starting_equity: float
) -> Metrics:
    rs = [t.r_multiple for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    peak, max_dd = starting_equity, 0.0
    for eq in equity_curve:
        peak = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak * 100)
    loss_sum = -sum(losses)
    final = equity_curve[-1] if equity_curve else starting_equity
    return Metrics(
        trades=len(rs),
        win_rate=len(wins) / len(rs) if rs else 0.0,
        avg_win_r=sum(wins) / len(wins) if wins else 0.0,
        avg_loss_r=sum(losses) / len(losses) if losses else 0.0,
        expectancy_r=sum(rs) / len(rs) if rs else 0.0,
        profit_factor=sum(wins) / loss_sum if loss_sum > 0 else None,
        total_return_pct=(final - starting_equity) / starting_equity * 100,
        max_drawdown_pct=max_dd,
    )


def run_backtest(
    bars: list[Bar],
    instrument: Instrument,
    strategy: Strategy,
    limits: RiskLimits,
    costs: CostModel,
    config: BacktestConfig,
    learning: LearningBook | None = None,
) -> BacktestResult:
    df = bars_to_frame(bars)
    value = (df["close"] * df["volume"]).rolling(config.liquidity_window, min_periods=1).mean()
    fx = config.fx_to_base

    equity = peak = config.starting_equity_base
    trades: list[ClosedTrade] = []
    curve: list[float] = []
    rejections: Counter[str] = Counter()
    open_pos: OpenTrade | None = None
    pending = None  # (proposal, quantity) approved at the previous close

    for i, bar in enumerate(bars):
        entered_now = False
        if pending is not None and open_pos is None:
            proposal, qty = pending
            pending = None
            long = proposal.direction is Direction.LONG
            gapped = bar.open <= proposal.stop if long else bar.open >= proposal.stop
            if gapped:
                rejections["gapped through stop before entry"] += 1
            else:
                open_pos = open_trade(proposal, qty, bar, costs, fx)
                entered_now = True

        if open_pos is not None:
            closed = update_trade(
                open_pos, bar, costs, entry_bar=entered_now, max_bars=config.max_bars_held
            )
            if closed is not None:
                trades.append(closed)
                equity += closed.pnl_base
                if learning is not None:
                    learning.record(closed)
                open_pos = None

        unrealized = 0.0
        if open_pos is not None:
            sign = 1 if open_pos.direction is Direction.LONG else -1
            unrealized = (bar.close - open_pos.entry_price) * open_pos.quantity * sign * fx
        marked = equity + unrealized
        peak = max(peak, marked)
        curve.append(marked)

        if open_pos is not None or i + 1 >= len(bars):
            continue
        proposal = strategy.signal(df.iloc[: i + 1], instrument)
        if proposal is None:
            continue
        multiplier = (
            learning.risk_multiplier(proposal.setup, instrument.asset_class.value)
            if learning is not None
            else 1.0
        )
        decision = evaluate(
            proposal,
            PortfolioState(equity_base=marked, peak_equity_base=peak),
            MarketSnapshot(
                last_price=bar.close,
                fx_to_base=fx,
                avg_daily_value_base=float(value.iloc[i]) * fx,
                spread_bps=costs.spread_bps,
                shortable=config.shortable,
            ),
            limits,
            risk_multiplier=multiplier,
        )
        if decision.approved:
            pending = (proposal, abs(decision.quantity))
        else:
            rejections.update(decision.rejections)

    return BacktestResult(
        trades=trades,
        equity_curve=curve,
        metrics=compute_metrics(trades, curve, config.starting_equity_base),
        rejections=dict(rejections),
    )

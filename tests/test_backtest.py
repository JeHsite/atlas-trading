import pytest

from atlas.backtest import BacktestConfig, compute_metrics, run_backtest
from atlas.domain import AssetClass, Direction, Instrument
from atlas.learning import LearningBook, LearningConfig, Status
from atlas.paper import CostModel
from atlas.risk import RiskLimits
from atlas.strategies import DonchianBreakout, RsiPullback
from tests.helpers import make_bars, wave

INST = Instrument(symbol="TEST", asset_class=AssetClass.EQUITY, venue="XNYS", currency="USD")
LIMITS = RiskLimits(min_order_value_base=1, fractional_asset_classes={AssetClass.EQUITY})
COSTS = CostModel(spread_bps=5, slippage_bps=5)
CONFIG = BacktestConfig(starting_equity_base=270)


@pytest.mark.parametrize("strategy", [DonchianBreakout(), RsiPullback()])
def test_strategies_trade_and_equity_adds_up(strategy):
    bars = make_bars(wave(600))
    result = run_backtest(bars, INST, strategy, LIMITS, COSTS, CONFIG)
    assert result.metrics.trades > 3
    assert len(result.equity_curve) == len(bars)
    realized = CONFIG.starting_equity_base + sum(t.pnl_base for t in result.trades)
    expected_return = (realized - CONFIG.starting_equity_base) / CONFIG.starting_equity_base * 100
    if result.equity_curve[-1] == pytest.approx(realized):  # flat at the end
        assert result.metrics.total_return_pct == pytest.approx(expected_return)
    # Each trade risks 0.5% of equity, so no single trade moves equity by 5%
    assert all(abs(t.pnl_base) < 0.05 * CONFIG.starting_equity_base for t in result.trades)


def test_no_lookahead():
    seen = []

    class Spy:
        name = "spy"
        warmup = 0

        def signal(self, df, instrument):
            seen.append(df.index[-1])
            return None

    bars = make_bars(wave(50))
    run_backtest(bars, INST, Spy(), LIMITS, COSTS, CONFIG)
    assert seen == [b.ts for b in bars[:-1]]  # never asked to decide on the last bar


def test_entries_fill_on_next_bar_open():
    bars = make_bars(wave(400))
    result = run_backtest(bars, INST, DonchianBreakout(), LIMITS, COSTS, CONFIG)
    by_ts = {b.ts: i for i, b in enumerate(bars)}
    assert result.trades
    for t in result.trades:
        i = by_ts[t.entry_ts]
        buying = t.direction is Direction.LONG
        assert t.entry_price == pytest.approx(COSTS.fill_price(bars[i].open, buying=buying))


class AlwaysBreakoutLong:
    name = "always_long"
    warmup = 15

    def __init__(self):
        self.inner = DonchianBreakout(lookback=5, trend_filter=10, allow_short=False)

    def signal(self, df, instrument):
        p = self.inner.signal(df, instrument)
        return p.model_copy(update={"setup": self.name}) if p else None


def test_learning_shuts_down_a_losing_setup():
    # Falling, choppy market where every long breakout fails
    closes = [100 * (0.997**i) * (1 + 0.05 * ((i % 7) - 3) / 3) for i in range(800)]
    book = LearningBook(LearningConfig(min_trades=10, prior_trades=5))
    result = run_backtest(
        make_bars(closes), INST, AlwaysBreakoutLong(), LIMITS, COSTS, CONFIG, learning=book
    )
    stats = book.stats("always_long", "equity")
    assert stats.trades == 10  # stopped right after it was judged
    assert stats.status is Status.DISABLED
    assert result.rejections["setup 'always_long' is disabled by the learning layer"] > 0

    # Without learning the same setup keeps losing
    unchecked = run_backtest(make_bars(closes), INST, AlwaysBreakoutLong(), LIMITS, COSTS, CONFIG)
    assert unchecked.metrics.trades > 10
    assert unchecked.metrics.total_return_pct < result.metrics.total_return_pct


def test_compute_metrics():
    from tests.test_learning import closed

    trades = [closed(2), closed(-1), closed(-1), closed(3)]
    m = compute_metrics(trades, [100, 110, 99, 120], 100)
    assert m.win_rate == 0.5
    assert m.expectancy_r == pytest.approx(0.75)
    assert m.profit_factor == pytest.approx(2.5)
    assert m.max_drawdown_pct == pytest.approx(10.0)
    assert m.total_return_pct == pytest.approx(20.0)

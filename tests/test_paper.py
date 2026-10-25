from datetime import UTC, datetime

import pytest

from atlas.domain import AssetClass, Bar, Direction, Horizon, Instrument, TradeProposal
from atlas.paper import CostModel, open_trade, update_trade

INST = Instrument(symbol="X", asset_class=AssetClass.EQUITY, venue="XNYS", currency="USD")
FREE = CostModel(spread_bps=0, slippage_bps=0)


def bar(o, h, lo, c, day=2):
    return Bar(
        symbol="X",
        ts=datetime(2026, 1, day, tzinfo=UTC),
        open=o,
        high=h,
        low=lo,
        close=c,
        volume=1e6,
    )


def proposal(direction=Direction.LONG):
    if direction is Direction.LONG:
        return TradeProposal(
            instrument=INST,
            direction=direction,
            horizon=Horizon.SWING,
            entry=100,
            stop=95,
            targets=[110],
            confidence=60,
            thesis="t",
            setup="s",
        )
    return TradeProposal(
        instrument=INST,
        direction=direction,
        horizon=Horizon.SWING,
        entry=100,
        stop=105,
        targets=[90],
        confidence=60,
        thesis="t",
        setup="s",
    )


def test_commission_minimum_and_adverse_fills():
    costs = CostModel(commission_per_unit=0.005, commission_min=1.0, spread_bps=10, slippage_bps=5)
    assert costs.commission(10, 100) == 1.0
    assert costs.commission(1000, 100) == 5.0
    assert costs.fill_price(100, buying=True) == pytest.approx(100.10)
    assert costs.fill_price(100, buying=False) == pytest.approx(99.90)


def test_stop_hit_is_minus_one_r():
    t = open_trade(proposal(), 10, bar(100, 101, 99, 100, day=1), FREE)
    assert update_trade(t, bar(100, 101, 99, 100, day=1), FREE, entry_bar=True) is None
    closed = update_trade(t, bar(99, 99, 94, 95), FREE)
    assert closed.exit_reason == "stop"
    assert closed.r_multiple == pytest.approx(-1.0)


def test_target_hit_is_plus_two_r():
    t = open_trade(proposal(), 10, bar(100, 101, 99, 100, day=1), FREE)
    closed = update_trade(t, bar(104, 111, 103, 109), FREE)
    assert closed.exit_reason == "target"
    assert closed.r_multiple == pytest.approx(2.0)


def test_same_bar_stop_and_target_assumes_stop():
    t = open_trade(proposal(), 10, bar(100, 101, 99, 100, day=1), FREE)
    closed = update_trade(t, bar(100, 112, 94, 100), FREE)
    assert closed.exit_reason == "stop"


def test_gap_through_stop_loses_more_than_one_r():
    t = open_trade(proposal(), 10, bar(100, 101, 99, 100, day=1), FREE)
    closed = update_trade(t, bar(90, 92, 88, 91), FREE)
    assert closed.exit_reason == "stop_gap"
    assert closed.r_multiple == pytest.approx(-2.0)


def test_short_trade_and_time_exit():
    t = open_trade(proposal(Direction.SHORT), 10, bar(100, 101, 99, 100, day=1), FREE)
    assert update_trade(t, bar(99, 100, 98, 98), FREE, max_bars=2) is None
    closed = update_trade(t, bar(98, 99, 97, 97, day=3), FREE, max_bars=2)
    assert closed.exit_reason == "time"
    assert closed.r_multiple == pytest.approx(0.6)  # 3 points of a 5-point risk


def test_costs_reduce_r():
    costs = CostModel(commission_min=1.0, spread_bps=0, slippage_bps=0)
    t = open_trade(proposal(), 2, bar(100, 101, 99, 100, day=1), costs)  # risk = 10 USD
    closed = update_trade(t, bar(104, 111, 103, 109), costs)
    assert closed.r_multiple == pytest.approx((20 - 2) / 10)

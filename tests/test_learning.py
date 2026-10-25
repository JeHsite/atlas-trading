from datetime import UTC, datetime

import pytest

from atlas.domain import Direction, Horizon
from atlas.learning import LearningBook, LearningConfig, Mistake, Status, TradeReview
from atlas.paper import ClosedTrade
from atlas.risk import evaluate


def closed(r: float, setup: str = "breakout") -> ClosedTrade:
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    return ClosedTrade(
        symbol="X",
        asset_class="equity",
        setup=setup,
        direction=Direction.LONG,
        horizon=Horizon.SWING,
        quantity=1,
        entry_ts=ts,
        exit_ts=ts,
        entry_price=100,
        exit_price=100 + r,
        pnl_base=r * 10,
        r_multiple=r,
        exit_reason="test",
    )


def test_new_setup_is_learning_at_full_risk():
    book = LearningBook()
    for _ in range(10):
        book.record(closed(-1))
    s = book.stats("breakout", "equity")
    assert s.status is Status.LEARNING
    assert s.risk_multiplier == 1.0


def test_losing_setup_is_disabled_after_enough_trades():
    book = LearningBook()
    for r in [-1, -1, 1.5] * 10:  # 30 trades, avg -0.17R
        book.record(closed(r))
    s = book.stats("breakout", "equity")
    assert s.trades == 30
    assert s.win_rate == pytest.approx(1 / 3)
    assert s.shrunk_r == pytest.approx(-5 / 50)
    assert s.status is Status.REDUCED
    assert s.risk_multiplier == 0.5

    for _ in range(10):
        book.record(closed(-1))
    assert book.stats("breakout", "equity").status is Status.DISABLED


def test_winning_setup_never_exceeds_full_risk():
    book = LearningBook(LearningConfig(min_trades=5))
    for _ in range(50):
        book.record(closed(3))
    s = book.stats("breakout", "equity")
    assert s.status is Status.ACTIVE
    assert s.risk_multiplier == 1.0
    assert s.profit_factor is None  # no losses


def test_domains_are_separate():
    book = LearningBook(LearningConfig(min_trades=5))
    for _ in range(10):
        book.record(closed(-1, "breakout"))
        book.record(closed(2, "pullback"))
    assert book.risk_multiplier("breakout", "equity") == 0
    assert book.risk_multiplier("pullback", "equity") == 1
    assert book.risk_multiplier("breakout", "crypto") == 1


def test_prompt_context_includes_recent_lessons():
    book = LearningBook()
    review = TradeReview(
        setup="breakout",
        asset_class="equity",
        symbol="X",
        r_multiple=-1,
        thesis_correct="no",
        mistake=Mistake.NEWS_EVENT,
        lesson="Skip breakouts on CPI release days",
    )
    book.record(closed(-1), review)
    ctx = book.prompt_context("breakout", "equity")
    assert "Skip breakouts on CPI release days" in ctx
    assert "trades=1" in ctx


def test_risk_engine_applies_multiplier(long_proposal, portfolio, snapshot, limits):
    full = evaluate(long_proposal, portfolio, snapshot, limits)
    half = evaluate(long_proposal, portfolio, snapshot, limits, risk_multiplier=0.5)
    assert half.quantity == full.quantity / 2
    assert half.adjustments[0].startswith("risk reduced to 50%")

    blocked = evaluate(long_proposal, portfolio, snapshot, limits, risk_multiplier=0)
    assert not blocked.approved
    assert "disabled by the learning layer" in blocked.rejections[0]

    capped = evaluate(long_proposal, portfolio, snapshot, limits, risk_multiplier=3)
    assert capped.quantity == full.quantity

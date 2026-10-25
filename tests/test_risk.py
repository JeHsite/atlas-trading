import pytest

from atlas.domain import (
    AssetClass,
    Direction,
    Horizon,
    Instrument,
    MarketSnapshot,
    Position,
    TradeProposal,
)
from atlas.risk import evaluate


def test_sizes_by_risk_budget(long_proposal, portfolio, snapshot, limits):
    decision = evaluate(long_proposal, portfolio, snapshot, limits)
    # 0.5% of 100k = 500 risk; 5 per share => 100 shares
    assert decision.approved
    assert decision.quantity == 100
    assert decision.order_value_base == 10_000
    assert decision.adjustments == []


def test_kill_switch_blocks_everything(long_proposal, portfolio, snapshot, limits):
    decision = evaluate(long_proposal, portfolio, snapshot, limits, kill_switch=True)
    assert not decision.approved
    assert decision.rejections == ["kill switch is active"]


def test_daily_loss_halt(long_proposal, portfolio, snapshot, limits):
    portfolio.day_pnl_base = -2_500  # -2.5% of start-of-day equity
    portfolio.equity_base = 97_500
    decision = evaluate(long_proposal, portfolio, snapshot, limits)
    assert not decision.approved
    assert "daily loss" in decision.rejections[0]


def test_drawdown_halt(long_proposal, portfolio, snapshot, limits):
    portfolio.peak_equity_base = 120_000  # ~16.7% drawdown
    decision = evaluate(long_proposal, portfolio, snapshot, limits)
    assert not decision.approved
    assert "drawdown" in decision.rejections[0]


def test_low_confidence_and_poor_reward_risk_rejected(aapl, portfolio, snapshot, limits):
    proposal = TradeProposal(
        instrument=aapl,
        direction=Direction.LONG,
        horizon=Horizon.INTRADAY,
        entry=100.0,
        stop=98.0,
        targets=[101.0],
        confidence=40,
        thesis="weak",
    )
    decision = evaluate(proposal, portfolio, snapshot, limits)
    assert not decision.approved
    assert len(decision.rejections) == 2


def test_short_requires_borrow(aapl, portfolio, snapshot, limits):
    proposal = TradeProposal(
        instrument=aapl,
        direction=Direction.SHORT,
        horizon=Horizon.INTRADAY,
        entry=100.0,
        stop=102.0,
        targets=[95.0],
        confidence=70,
        thesis="failed breakout",
    )
    snapshot.shortable = False
    assert not evaluate(proposal, portfolio, snapshot, limits).approved

    snapshot.shortable = True
    decision = evaluate(proposal, portfolio, snapshot, limits)
    assert decision.approved
    assert decision.quantity < 0


def test_illiquid_and_wide_spread_rejected(long_proposal, portfolio, snapshot, limits):
    snapshot.avg_daily_value_base = 10_000
    snapshot.spread_bps = 80
    decision = evaluate(long_proposal, portfolio, snapshot, limits)
    assert not decision.approved
    assert len(decision.rejections) == 2


def test_stale_entry_rejected(long_proposal, portfolio, snapshot, limits):
    snapshot.last_price = 110.0
    decision = evaluate(long_proposal, portfolio, snapshot, limits)
    assert not decision.approved
    assert "away from last price" in decision.rejections[0]


def test_tight_stop_is_capped_by_position_size(aapl, portfolio, snapshot, limits):
    proposal = TradeProposal(
        instrument=aapl,
        direction=Direction.LONG,
        horizon=Horizon.INTRADAY,
        entry=100.0,
        stop=99.9,  # risk budget alone would allow 5,000 shares = 500k
        targets=[100.5],
        confidence=80,
        thesis="tight scalp",
    )
    decision = evaluate(proposal, portfolio, snapshot, limits)
    assert decision.approved
    assert decision.quantity == 100  # 10% of equity
    assert decision.adjustments == ["size reduced by position size limit"]


def test_sector_cap_reduces_size(long_proposal, portfolio, snapshot, limits):
    msft = Instrument(
        symbol="MSFT",
        asset_class=AssetClass.EQUITY,
        venue="XNAS",
        currency="USD",
        country="US",
        sector="Technology",
    )
    portfolio.positions = [Position(instrument=msft, quantity=50, avg_price=400, last_price=400)]
    # Technology already 20k of a 25k cap
    decision = evaluate(long_proposal, portfolio, snapshot, limits)
    assert decision.approved
    assert decision.quantity == 50
    assert decision.adjustments == ["size reduced by sector limit"]


def test_full_sector_rejects(long_proposal, portfolio, snapshot, limits):
    msft = long_proposal.instrument.model_copy(update={"symbol": "MSFT"})
    portfolio.positions = [Position(instrument=msft, quantity=100, avg_price=250, last_price=250)]
    decision = evaluate(long_proposal, portfolio, snapshot, limits)
    assert not decision.approved
    assert decision.rejections == ["no capacity left after sector limit"]


def test_crypto_fractional_and_class_cap(portfolio, limits):
    btc = Instrument(
        symbol="BTC-USD", asset_class=AssetClass.CRYPTO, venue="CRYPTO", currency="USD"
    )
    proposal = TradeProposal(
        instrument=btc,
        direction=Direction.LONG,
        horizon=Horizon.SWING,
        entry=60_000,
        stop=58_000,
        targets=[66_000],
        confidence=65,
        thesis="trend continuation",
    )
    snap = MarketSnapshot(last_price=60_000, avg_daily_value_base=2e10, spread_bps=1)
    decision = evaluate(proposal, portfolio, snap, limits)
    # Risk budget allows 0.25 BTC (500 / 2000) = 15k, position cap is 10k
    assert decision.approved
    assert decision.quantity == pytest.approx(10_000 / 60_000)
    assert decision.adjustments == ["size reduced by position size limit"]

    eth = btc.model_copy(update={"symbol": "ETH-USD"})
    existing = Position(instrument=eth, quantity=4.8, avg_price=3_000, last_price=3_000)
    portfolio.positions = [existing]  # 14.4k of a 15k crypto cap
    decision = evaluate(proposal, portfolio, snap, limits)
    assert decision.approved
    assert decision.quantity == pytest.approx(0.01)
    assert decision.adjustments == ["size reduced by asset class limit"]


def test_fx_conversion_for_tase_stock(portfolio, limits):
    teva = Instrument(
        symbol="TEVA.TA", asset_class=AssetClass.EQUITY, venue="XTAE", currency="ILS", country="IL"
    )
    proposal = TradeProposal(
        instrument=teva,
        direction=Direction.LONG,
        horizon=Horizon.SWING,
        entry=70.0,
        stop=66.0,
        targets=[80.0],
        confidence=60,
        thesis="guidance raise",
    )
    snap = MarketSnapshot(last_price=70.0, fx_to_base=0.27, avg_daily_value_base=5e7, spread_bps=10)
    decision = evaluate(proposal, portfolio, snap, limits)
    # risk per share in USD = 4 * 0.27 = 1.08 -> 500 / 1.08 = 462.96 -> 462 shares
    assert decision.approved
    assert decision.quantity == 462


def test_invalid_proposal_levels():
    inst = Instrument(symbol="X", asset_class=AssetClass.EQUITY, venue="XNYS", currency="USD")
    with pytest.raises(ValueError):
        TradeProposal(
            instrument=inst,
            direction=Direction.LONG,
            horizon=Horizon.SWING,
            entry=100,
            stop=105,
            targets=[110],
            confidence=60,
            thesis="bad stop",
        )

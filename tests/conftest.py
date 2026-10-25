from pathlib import Path

import pytest

from atlas.domain import (
    AssetClass,
    Direction,
    Horizon,
    Instrument,
    MarketSnapshot,
    PortfolioState,
    TradeProposal,
)
from atlas.risk import RiskLimits

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def limits() -> RiskLimits:
    return RiskLimits.from_yaml(ROOT / "config" / "risk.yaml")


@pytest.fixture
def aapl() -> Instrument:
    return Instrument(
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        venue="XNAS",
        currency="USD",
        country="US",
        sector="Technology",
    )


@pytest.fixture
def portfolio() -> PortfolioState:
    return PortfolioState(equity_base=100_000, peak_equity_base=100_000)


@pytest.fixture
def snapshot() -> MarketSnapshot:
    return MarketSnapshot(last_price=100.0, avg_daily_value_base=5e9, spread_bps=2, shortable=True)


@pytest.fixture
def long_proposal(aapl: Instrument) -> TradeProposal:
    return TradeProposal(
        instrument=aapl,
        direction=Direction.LONG,
        horizon=Horizon.SWING,
        entry=100.0,
        stop=95.0,
        targets=[110.0, 120.0],
        confidence=70,
        thesis="Breakout above resistance after earnings beat",
    )

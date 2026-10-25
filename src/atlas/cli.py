"""Command line: ``uv run atlas backtest data/SPY_1d.csv --symbol SPY``."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from atlas.account import AccountConfig
from atlas.backtest import BacktestConfig, run_backtest
from atlas.data import CsvPriceProvider, Timeframe
from atlas.domain import AssetClass, Instrument
from atlas.learning import LearningBook
from atlas.risk import RiskLimits
from atlas.strategies import DonchianBreakout, RsiPullback

STRATEGIES = {"donchian": DonchianBreakout, "rsi_pullback": RsiPullback}


def _backtest(args: argparse.Namespace) -> None:
    config_dir = Path(args.config_dir)
    account = AccountConfig.from_yaml(config_dir / "account.yaml")
    limits = RiskLimits.from_yaml(config_dir / "risk.yaml")
    asset_class = AssetClass(args.asset_class)
    venue = "CRYPTO" if asset_class is AssetClass.CRYPTO else args.venue
    instrument = Instrument(
        symbol=args.symbol, asset_class=asset_class, venue=venue, currency="USD", country=None
    )

    csv = Path(args.csv)
    symbol, timeframe = csv.stem.rsplit("_", 1)
    bars = CsvPriceProvider(csv.parent).get_bars(
        symbol, Timeframe(timeframe), datetime(1970, 1, 1, tzinfo=UTC), datetime.now(UTC)
    )
    book = LearningBook(account.learning)
    is_crypto = asset_class is AssetClass.CRYPTO
    # Crypto has no shorting through the demo broker; the strategies stay long-only there.
    strategy = STRATEGIES[args.strategy]()
    if is_crypto and hasattr(strategy, "allow_short"):
        strategy.allow_short = False
    result = run_backtest(
        bars,
        instrument,
        strategy,
        limits,
        account.cost_model(asset_class),
        BacktestConfig(
            starting_equity_base=account.starting_equity_base,
            max_bars_held=args.max_bars,
            shortable=not is_crypto,
        ),
        learning=book,
    )

    m = result.metrics
    pf = f"{m.profit_factor:.2f}" if m.profit_factor is not None else "n/a"
    print(f"{instrument.symbol} · {strategy.name} · {len(bars)} bars")
    print(f"trades          {m.trades}")
    print(f"win rate        {m.win_rate:.1%}")
    print(f"avg win / loss  {m.avg_win_r:+.2f}R / {m.avg_loss_r:+.2f}R")
    print(f"expectancy      {m.expectancy_r:+.3f}R per trade")
    print(f"profit factor   {pf}")
    print(f"return          {m.total_return_pct:+.2f}%")
    print(f"max drawdown    {m.max_drawdown_pct:.2f}%")
    for s in book.all_stats():
        print(f"learning        {s.setup}/{s.asset_class}: {s.status.value} (x{s.risk_multiplier})")
    if result.rejections:
        print("rejections:")
        for reason, count in sorted(result.rejections.items(), key=lambda kv: -kv[1]):
            print(f"  {count:5d}  {reason}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="atlas")
    sub = parser.add_subparsers(dest="command", required=True)

    bt = sub.add_parser("backtest", help="Backtest a strategy on a CSV of bars")
    bt.add_argument("csv", help="Path to <SYMBOL>_<timeframe>.csv")
    bt.add_argument("--symbol", required=True)
    bt.add_argument("--asset-class", default="equity", choices=["equity", "etf", "crypto"])
    bt.add_argument("--venue", default="XNYS")
    bt.add_argument("--strategy", default="donchian", choices=sorted(STRATEGIES))
    bt.add_argument("--max-bars", type=int, default=20)
    bt.add_argument("--config-dir", default="config")
    bt.set_defaults(func=_backtest)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()

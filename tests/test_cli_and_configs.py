from atlas.account import AccountConfig
from atlas.cli import main
from atlas.domain import AssetClass
from atlas.risk import RiskLimits
from tests.conftest import ROOT
from tests.helpers import make_bars, wave


def test_repo_configs_load():
    limits = RiskLimits.from_yaml(ROOT / "config" / "risk.yaml")
    assert AssetClass.EQUITY in limits.fractional_asset_classes
    account = AccountConfig.from_yaml(ROOT / "config" / "account.yaml")
    assert account.mode == "paper"
    assert account.starting_equity_base == 1000 * account.fx_to_base
    assert account.cost_model(AssetClass.CRYPTO).commission_pct > 0


def test_cli_backtest(tmp_path, capsys):
    rows = ["ts,open,high,low,close,volume"]
    rows += [
        f"{b.ts.isoformat()},{b.open},{b.high},{b.low},{b.close},{b.volume}"
        for b in make_bars(wave(500))
    ]
    csv = tmp_path / "TEST_1d.csv"
    csv.write_text("\n".join(rows))
    main(["backtest", str(csv), "--symbol", "TEST", "--config-dir", str(ROOT / "config")])
    out = capsys.readouterr().out
    assert "win rate" in out
    assert "expectancy" in out

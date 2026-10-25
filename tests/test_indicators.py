import pandas as pd
import pytest

from atlas.indicators import atr, bars_to_frame, donchian, rsi, sma
from tests.helpers import make_bars


def test_sma_and_rsi_basics():
    s = pd.Series([1.0, 2, 3, 4, 5, 6, 7, 8])
    assert sma(s, 4).iloc[-1] == pytest.approx(6.5)
    assert sma(s, 4).iloc[2] != sma(s, 4).iloc[2]  # NaN during warmup
    assert rsi(s, 3).iloc[-1] == 100  # no losses at all


def test_rsi_stays_in_range():
    s = pd.Series([10, 11, 9, 12, 8, 13, 7, 14, 9, 10, 11, 8.0])
    values = rsi(s, 3).dropna()
    assert ((values >= 0) & (values <= 100)).all()


def test_atr_of_constant_range():
    bars = make_bars([100.0] * 30, spread=0.01)
    assert atr(bars_to_frame(bars), 14).iloc[-1] == pytest.approx(2.0, rel=1e-6)


def test_donchian_excludes_current_bar():
    closes = [100.0] * 25 + [150.0]
    df = bars_to_frame(make_bars(closes, spread=0.0))
    upper, _ = donchian(df, 20)
    assert upper.iloc[-1] == pytest.approx(100.0)  # today's 150 high is not included
    assert df["close"].iloc[-1] > upper.iloc[-1]

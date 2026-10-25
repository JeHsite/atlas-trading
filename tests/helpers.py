import math
from datetime import UTC, datetime, timedelta

from atlas.domain import Bar


def make_bars(closes: list[float], symbol: str = "TEST", spread: float = 0.01) -> list[Bar]:
    """Daily bars whose open is the previous close and whose range is +-spread."""
    start = datetime(2024, 1, 1, 21, tzinfo=UTC)
    bars = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        bars.append(
            Bar(
                symbol=symbol,
                ts=start + timedelta(days=i),
                open=o,
                high=max(o, c) * (1 + spread),
                low=min(o, c) * (1 - spread),
                close=c,
                volume=1_000_000,
            )
        )
        prev = c
    return bars


def wave(n: int, base: float = 100.0, drift: float = 0.002, amp: float = 0.06) -> list[float]:
    """Uptrending series with a ~40-bar cycle, so breakouts and pullbacks both occur."""
    return [base * (1 + drift) ** i * (1 + amp * math.sin(i / 6.4)) for i in range(n)]

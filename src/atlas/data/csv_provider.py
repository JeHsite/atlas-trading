"""Offline price provider reading ``<root>/<SYMBOL>_<timeframe>.csv``.

Used for tests and backtests on downloaded history. Expected columns:
ts (ISO-8601 with offset), open, high, low, close, volume.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from atlas.data.base import Timeframe
from atlas.domain import Bar


class CsvPriceProvider:
    def __init__(self, root: str | Path):
        self._root = Path(root)

    def get_bars(
        self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> list[Bar]:
        path = self._root / f"{symbol}_{timeframe.value}.csv"
        if not path.exists():
            raise FileNotFoundError(path)
        bars = []
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                ts = datetime.fromisoformat(row["ts"])
                if start <= ts < end:
                    bars.append(
                        Bar(
                            symbol=symbol,
                            ts=ts,
                            open=float(row["open"]),
                            high=float(row["high"]),
                            low=float(row["low"]),
                            close=float(row["close"]),
                            volume=float(row["volume"]),
                        )
                    )
        return sorted(bars, key=lambda b: b.ts)

"""Interfaces every data adapter implements.

Concrete adapters (Interactive Brokers, CCXT, FRED, SEC EDGAR, central-bank
feeds) live next to this module and are swapped through configuration.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, Field

from atlas.domain import Bar


class Timeframe(StrEnum):
    M5 = "5m"
    H1 = "1h"
    D1 = "1d"
    W1 = "1w"


class Document(BaseModel):
    """A piece of external text: news item, filing, transcript or speech."""

    id: str
    source: str
    published_at: datetime
    title: str
    body: str
    url: str | None = None
    symbols: list[str] = Field(default_factory=list)
    kind: str = Field(description="news | filing | transcript | speech | macro_release")


class PriceProvider(Protocol):
    def get_bars(
        self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> list[Bar]: ...


class DocumentProvider(Protocol):
    def get_documents(
        self, since: datetime, symbols: list[str] | None = None
    ) -> list[Document]: ...

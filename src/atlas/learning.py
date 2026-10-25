"""Learning after every trade.

Each closed trade is recorded under its domain: (setup, asset class). Two kinds
of learning come out of the record:

1. Numbers: win rate, average R and a shrunk expectancy per domain. The shrunk
   expectancy decides a risk multiplier that the risk engine applies. It can
   only shrink (0.5) or stop (0) a setup, never enlarge it, so a lucky streak
   cannot raise risk.
2. Lessons: a short structured post-mortem per trade (written by a model in
   phase 3). Recent lessons of the same domain are fed back into the analyst
   prompt. Lessons never change limits; only the numbers do.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from atlas.paper import ClosedTrade

Domain = tuple[str, str]  # (setup, asset_class)


class LearningConfig(BaseModel):
    prior_trades: int = Field(
        default=20, ge=0, description="Pseudo-trades at 0R pulling small samples toward zero"
    )
    min_trades: int = Field(default=30, ge=1, description="Trades before a domain is judged")
    reduce_below_r: float = Field(default=0.0, description="Shrunk expectancy that halves risk")
    disable_below_r: float = Field(default=-0.15, description="Shrunk expectancy that stops it")
    reduced_multiplier: float = Field(default=0.5, gt=0, lt=1)


class Status(StrEnum):
    LEARNING = "learning"  # not enough trades yet
    ACTIVE = "active"
    REDUCED = "reduced"
    DISABLED = "disabled"


class SetupStats(BaseModel):
    setup: str
    asset_class: str
    trades: int
    wins: int
    win_rate: float
    avg_r: float
    shrunk_r: float
    profit_factor: float | None
    status: Status
    risk_multiplier: float


class Mistake(StrEnum):
    NONE = "none"
    ENTRY_TIMING = "entry_timing"
    STOP_TOO_TIGHT = "stop_too_tight"
    STOP_TOO_WIDE = "stop_too_wide"
    AGAINST_REGIME = "against_regime"
    NEWS_EVENT = "news_event"
    LIQUIDITY = "liquidity"
    THESIS_WRONG = "thesis_wrong"
    EXECUTION = "execution"


class TradeReview(BaseModel):
    """Structured post-mortem of one closed trade."""

    setup: str
    asset_class: str
    symbol: str
    r_multiple: float
    thesis_correct: Literal["yes", "partly", "no"]
    mistake: Mistake
    lesson: str = Field(min_length=1, max_length=300)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LearningBook:
    def __init__(self, config: LearningConfig | None = None):
        self.config = config or LearningConfig()
        self._trades: dict[Domain, list[ClosedTrade]] = defaultdict(list)
        self._reviews: dict[Domain, list[TradeReview]] = defaultdict(list)

    def record(self, trade: ClosedTrade, review: TradeReview | None = None) -> SetupStats:
        domain = (trade.setup, trade.asset_class)
        self._trades[domain].append(trade)
        if review is not None:
            self._reviews[domain].append(review)
        return self.stats(*domain)

    def stats(self, setup: str, asset_class: str) -> SetupStats:
        trades = self._trades.get((setup, asset_class), [])
        cfg = self.config
        n = len(trades)
        rs = [t.r_multiple for t in trades]
        wins = sum(1 for t in trades if t.win)
        gains = sum(r for r in rs if r > 0)
        losses = -sum(r for r in rs if r < 0)
        shrunk = sum(rs) / (n + cfg.prior_trades) if n + cfg.prior_trades else 0.0

        if n < cfg.min_trades:
            status, mult = Status.LEARNING, 1.0
        elif shrunk < cfg.disable_below_r:
            status, mult = Status.DISABLED, 0.0
        elif shrunk < cfg.reduce_below_r:
            status, mult = Status.REDUCED, cfg.reduced_multiplier
        else:
            status, mult = Status.ACTIVE, 1.0

        return SetupStats(
            setup=setup,
            asset_class=asset_class,
            trades=n,
            wins=wins,
            win_rate=wins / n if n else 0.0,
            avg_r=sum(rs) / n if n else 0.0,
            shrunk_r=shrunk,
            profit_factor=gains / losses if losses else None,
            status=status,
            risk_multiplier=mult,
        )

    def risk_multiplier(self, setup: str, asset_class: str) -> float:
        return self.stats(setup, asset_class).risk_multiplier

    def all_stats(self) -> list[SetupStats]:
        return [self.stats(*d) for d in sorted(self._trades)]

    def prompt_context(self, setup: str, asset_class: str, max_lessons: int = 5) -> str:
        """Track record and recent lessons for one domain, for the analyst prompt."""
        s = self.stats(setup, asset_class)
        lines = [
            f'<track_record setup="{setup}" asset_class="{asset_class}">',
            f"trades={s.trades} win_rate={s.win_rate:.0%} avg_r={s.avg_r:+.2f} "
            f"shrunk_r={s.shrunk_r:+.2f} status={s.status.value}",
        ]
        for r in self._reviews.get((setup, asset_class), [])[-max_lessons:]:
            lines.append(f"- {r.symbol} {r.r_multiple:+.2f}R [{r.mistake.value}] {r.lesson}")
        lines.append("</track_record>")
        return "\n".join(lines)

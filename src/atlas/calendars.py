"""Market-hours checks per venue, driven by config/markets.yaml."""

from __future__ import annotations

from datetime import date, datetime, time
from functools import cache
from pathlib import Path
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd
import yaml

_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_NEW_YORK = ZoneInfo("America/New_York")


class MarketCalendar:
    def __init__(self, venues: dict[str, dict]):
        self._venues = venues

    @classmethod
    def from_yaml(cls, path: str | Path) -> MarketCalendar:
        with open(path, encoding="utf-8") as f:
            return cls(yaml.safe_load(f)["venues"])

    @property
    def venues(self) -> list[str]:
        return list(self._venues)

    def is_open(self, venue: str, at: datetime) -> bool:
        if at.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        cfg = self._venue(venue)
        kind = cfg["calendar"]
        if kind == "always_open":
            return True
        if kind == "fx":
            return _fx_open(at)
        if kind == "custom":
            return _custom_open(cfg, at)
        return _xcal(kind).is_trading_minute(pd.Timestamp(at).tz_convert("UTC").floor("min"))

    def _venue(self, venue: str) -> dict:
        try:
            return self._venues[venue]
        except KeyError:
            raise KeyError(f"unknown venue {venue!r}") from None


@cache
def _xcal(code: str) -> xcals.ExchangeCalendar:
    return xcals.get_calendar(code)


def _fx_open(at: datetime) -> bool:
    ny = at.astimezone(_NEW_YORK)
    weekday, t = ny.weekday(), ny.time()
    five_pm = time(17, 0)
    if weekday == 5:  # Saturday
        return False
    if weekday == 6:  # Sunday
        return t >= five_pm
    if weekday == 4:  # Friday
        return t < five_pm
    return True


def _custom_open(cfg: dict, at: datetime) -> bool:
    local = at.astimezone(ZoneInfo(cfg["tz"]))
    holidays = {date.fromisoformat(str(d)) for d in cfg.get("holidays", [])}
    if local.date() in holidays:
        return False
    hours = cfg["hours"].get(_WEEKDAYS[local.weekday()])
    if not hours:
        return False
    open_t, close_t = (time.fromisoformat(h) for h in hours)
    return open_t <= local.time() < close_t

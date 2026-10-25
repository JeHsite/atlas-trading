from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from atlas.calendars import MarketCalendar
from tests.conftest import ROOT

NY = ZoneInfo("America/New_York")
TLV = ZoneInfo("Asia/Jerusalem")


@pytest.fixture(scope="module")
def cal() -> MarketCalendar:
    return MarketCalendar.from_yaml(ROOT / "config" / "markets.yaml")


def test_every_configured_venue_builds(cal):
    now = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
    for venue in cal.venues:
        cal.is_open(venue, now)


def test_nyse_regular_hours(cal):
    assert cal.is_open("XNYS", datetime(2026, 10, 21, 10, 0, tzinfo=NY))
    assert not cal.is_open("XNYS", datetime(2026, 10, 21, 16, 30, tzinfo=NY))
    assert not cal.is_open("XNYS", datetime(2026, 10, 24, 12, 0, tzinfo=NY))  # Saturday


def test_nyse_holiday(cal):
    assert not cal.is_open("XNYS", datetime(2026, 11, 26, 12, 0, tzinfo=NY))  # Thanksgiving


def test_tase_monday_to_friday(cal):
    assert cal.is_open("XTAE", datetime(2026, 10, 19, 12, 0, tzinfo=TLV))  # Monday
    assert cal.is_open("XTAE", datetime(2026, 10, 23, 11, 0, tzinfo=TLV))  # Friday
    assert not cal.is_open("XTAE", datetime(2026, 10, 25, 12, 0, tzinfo=TLV))  # Sunday


def test_crypto_always_open(cal):
    assert cal.is_open("CRYPTO", datetime(2026, 10, 25, 3, 0, tzinfo=UTC))


def test_fx_weekend(cal):
    assert not cal.is_open("FX", datetime(2026, 10, 24, 12, 0, tzinfo=NY))  # Saturday
    assert not cal.is_open("FX", datetime(2026, 10, 25, 16, 0, tzinfo=NY))  # Sunday early
    assert cal.is_open("FX", datetime(2026, 10, 25, 18, 0, tzinfo=NY))  # Sunday evening
    assert not cal.is_open("FX", datetime(2026, 10, 23, 17, 30, tzinfo=NY))  # Friday close


def test_naive_datetime_rejected(cal):
    with pytest.raises(ValueError):
        cal.is_open("XNYS", datetime(2026, 10, 21, 10, 0))


def test_unknown_venue(cal):
    with pytest.raises(KeyError):
        cal.is_open("NOPE", datetime(2026, 10, 21, 10, 0, tzinfo=UTC))

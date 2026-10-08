"""Tests for the pure Weekend Saver rules."""

from datetime import date, datetime, timedelta

import pytest

from custom_components.edf_weekend_saver.scheme import (
    PeakSummary,
    ServicePeriod,
    free_hours_for_percentage,
    group_slots,
    is_peak_hour,
    next_band,
    redemption_period_for,
    summarise,
    validate_slot,
)


def test_service_period_dates():
    october = ServicePeriod.for_month(2026, 10)
    assert october == ServicePeriod(date(2026, 10, 5), date(2026, 10, 30))
    assert october.redemption_start == date(2026, 10, 31)
    assert october.redemption_end_exclusive == date(2026, 11, 28)
    # A period can finish in the following month.
    assert ServicePeriod.for_month(2026, 11).end == date(2026, 12, 4)
    assert ServicePeriod.for_month(2026, 9).end == date(2026, 10, 2)


def test_period_containing_and_navigation():
    assert ServicePeriod.containing(date(2026, 10, 21)).key == "2026-10"
    # Thu 1 Oct is before the first Monday, so still in September's period.
    assert ServicePeriod.containing(date(2026, 10, 1)).key == "2026-09"
    # Sat 5 Dec falls between November's and December's periods.
    assert ServicePeriod.containing(date(2026, 12, 5)).key == "2026-11"
    assert ServicePeriod.for_month(2026, 1).previous().key == "2025-12"
    assert ServicePeriod.for_month(2026, 12).next().key == "2027-01"


def test_redemption_period_for():
    assert redemption_period_for(date(2026, 10, 21)).key == "2026-09"
    assert redemption_period_for(date(2026, 10, 3)).key == "2026-09"
    assert redemption_period_for(date(2026, 10, 31)).key == "2026-10"
    october = ServicePeriod.for_month(2026, 10)
    assert october.in_redemption_window(date(2026, 11, 22))
    assert not october.in_redemption_window(date(2026, 11, 23))  # Monday
    assert not october.in_redemption_window(date(2026, 11, 28))  # after 4 weeks


@pytest.mark.parametrize(
    ("percent", "hours"),
    [
        (None, 0),
        (0, 25),
        (8.99, 25),
        (9, 15),
        (11.99, 15),
        (12, 10),
        (15, 5),
        (17.99, 5),
        (18, 0),
        (40, 0),
    ],
)
def test_bands(percent, hours):
    assert free_hours_for_percentage(percent) == hours


def test_next_band():
    assert next_band(5) is None
    assert next_band(10) == (9.0, 25)
    assert next_band(13) == (12.0, 15)
    assert next_band(25) == (18.0, 5)


def test_peak_hours():
    wed = datetime(2026, 10, 21)
    assert not is_peak_hour(wed.replace(hour=15, minute=59))
    assert is_peak_hour(wed.replace(hour=16))
    assert is_peak_hour(wed.replace(hour=18, minute=59))
    assert not is_peak_hour(wed.replace(hour=19))
    assert not is_peak_hour(datetime(2026, 10, 24, 17))  # Saturday


def test_summary_maths():
    under = PeakSummary(peak_kwh=5, total_kwh=100)
    assert under.percentage == 5
    assert under.free_hours == 25
    headroom = under.headroom_kwh()
    assert (5 + headroom) / (100 + headroom) == pytest.approx(0.09)
    assert under.off_peak_needed_kwh() == 0

    over = PeakSummary(peak_kwh=18, total_kwh=100)
    assert over.headroom_kwh() < 0
    assert over.off_peak_needed_kwh() == pytest.approx(100)
    assert PeakSummary(0, 0).percentage is None


def test_summarise():
    day = datetime(2026, 10, 21)
    hourly = {day + timedelta(hours=h): 1.0 for h in range(24)}
    summary = summarise(hourly)
    assert summary.total_kwh == 24
    assert summary.peak_kwh == 3


def test_group_slots():
    sat = datetime(2026, 10, 31)
    starts = [sat.replace(hour=h) for h in (9, 10, 11, 13)] + [sat.replace(hour=9)]
    assert group_slots(starts) == [(sat.replace(hour=9), 3), (sat.replace(hour=13), 1)]


def test_validate_slot():
    sat = datetime(2026, 10, 31)
    assert validate_slot(sat.replace(hour=0)) is None
    assert validate_slot(sat.replace(hour=14)) is None
    assert validate_slot(sat.replace(hour=15)) == "outside_redemption_hours"
    assert validate_slot(sat.replace(hour=9, minute=30)) == "not_on_hour"
    assert validate_slot(datetime(2026, 10, 30, 9)) == "outside_redemption_hours"

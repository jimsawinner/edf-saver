"""Rules of the EDF Weekend Saver scheme.

Pure Python with no Home Assistant imports so it can be unit tested on its own.

Summary of the published terms:

* A *service period* starts on the first Monday of each month and ends on the
  Friday following the last Monday of that month.
* The *peak period* is 16:00-19:00, Monday to Friday.
* The share of the service period's electricity used during the peak period
  decides how many free hours are awarded (see ``BANDS``).
* Free hours are redeemed between 00:00 and 15:00 on Saturdays and Sundays in
  the four weeks starting on the first Saturday after the service period ends.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta

PEAK_START_HOUR = 16
PEAK_END_HOUR = 19
REDEMPTION_START_HOUR = 0
REDEMPTION_END_HOUR = 15
REDEMPTION_WEEKS = 4

# (upper bound of peak share in percent, exclusive, free hours awarded)
BANDS: tuple[tuple[float, int], ...] = (
    (9.0, 25),
    (12.0, 15),
    (15.0, 10),
    (18.0, 5),
)
TARGET_PERCENT = BANDS[0][0]


def free_hours_for_percentage(percent: float | None) -> int:
    """Return the free hours awarded for a peak share."""
    if percent is None:
        return 0
    for upper, hours in BANDS:
        if percent < upper:
            return hours
    return 0


def next_band(percent: float | None) -> tuple[float, int] | None:
    """Return the band above the current one (lower percent, more hours)."""
    if percent is None:
        return BANDS[0]
    better = None
    for upper, hours in BANDS:
        if percent < upper:
            return better
        better = (upper, hours)
    return better


def is_peak_hour(moment: datetime) -> bool:
    """Return True if a local datetime falls inside the weekday peak period."""
    return moment.weekday() < 5 and PEAK_START_HOUR <= moment.hour < PEAK_END_HOUR


def is_redemption_hour(moment: datetime) -> bool:
    """Return True if a local datetime is within the weekend free-hour window."""
    return moment.weekday() >= 5 and REDEMPTION_START_HOUR <= moment.hour < REDEMPTION_END_HOUR


def _first_weekday(year: int, month: int, weekday: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


@dataclass(frozen=True)
class ServicePeriod:
    """A monthly service period, inclusive of both dates."""

    start: date
    end: date

    @classmethod
    def for_month(cls, year: int, month: int) -> ServicePeriod:
        start = _first_weekday(year, month, 0)
        end = _last_weekday(year, month, 0) + timedelta(days=4)
        return cls(start, end)

    @classmethod
    def containing(cls, day: date) -> ServicePeriod:
        """Return the period containing ``day``, or the latest one before it."""
        period = cls.for_month(day.year, day.month)
        if day >= period.start:
            return period
        return period.previous()

    def previous(self) -> ServicePeriod:
        if self.start.month == 1:
            return ServicePeriod.for_month(self.start.year - 1, 12)
        return ServicePeriod.for_month(self.start.year, self.start.month - 1)

    def next(self) -> ServicePeriod:
        if self.start.month == 12:
            return ServicePeriod.for_month(self.start.year + 1, 1)
        return ServicePeriod.for_month(self.start.year, self.start.month + 1)

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end

    @property
    def key(self) -> str:
        """Stable identifier, e.g. ``2026-10``."""
        return f"{self.start.year:04d}-{self.start.month:02d}"

    @property
    def end_exclusive(self) -> date:
        return self.end + timedelta(days=1)

    @property
    def redemption_start(self) -> date:
        """First Saturday after the period ends."""
        return self.end + timedelta(days=(5 - self.end.weekday()) % 7 or 7)

    @property
    def redemption_end_exclusive(self) -> date:
        return self.redemption_start + timedelta(weeks=REDEMPTION_WEEKS)

    def in_redemption_window(self, day: date) -> bool:
        return self.redemption_start <= day < self.redemption_end_exclusive and day.weekday() >= 5


def redemption_period_for(day: date) -> ServicePeriod:
    """Return the service period whose free hours are redeemed around ``day``.

    This is the most recent period that has already ended. Its redemption
    window may already be over if ``day`` falls in a gap between windows.
    """
    period = ServicePeriod.containing(day)
    if period.contains(day):
        period = period.previous()
    return period


@dataclass(frozen=True)
class PeakSummary:
    """Consumption split for a service period."""

    peak_kwh: float
    total_kwh: float

    @property
    def off_peak_kwh(self) -> float:
        return self.total_kwh - self.peak_kwh

    @property
    def percentage(self) -> float | None:
        if self.total_kwh <= 0:
            return None
        return self.peak_kwh / self.total_kwh * 100

    @property
    def free_hours(self) -> int:
        return free_hours_for_percentage(self.percentage)

    def headroom_kwh(self, target_percent: float = TARGET_PERCENT) -> float:
        """Peak kWh that could still be used while staying under the target.

        Negative when already over: the absolute value is how much peak use
        should have been avoided. Using ``x`` more peak kWh keeps the share
        below ``t`` while ``peak + x < t * (total + x)``.
        """
        share = target_percent / 100
        return (share * self.total_kwh - self.peak_kwh) / (1 - share)

    def off_peak_needed_kwh(self, target_percent: float = TARGET_PERCENT) -> float:
        """Extra off-peak kWh that would bring the share down to the target."""
        share = target_percent / 100
        return max(0.0, self.peak_kwh / share - self.total_kwh)


def summarise(hourly: Mapping[datetime, float]) -> PeakSummary:
    """Split hourly consumption (keyed by local hour start) into peak/total."""
    peak = 0.0
    total = 0.0
    for start, kwh in hourly.items():
        total += kwh
        if is_peak_hour(start):
            peak += kwh
    return PeakSummary(round(peak, 4), round(total, 4))


def group_slots(slot_starts: Iterable[datetime]) -> list[tuple[datetime, int]]:
    """Group hourly slot starts into (start, hours) runs of consecutive hours."""
    groups: list[tuple[datetime, int]] = []
    for start in sorted(set(slot_starts)):
        if groups:
            first, hours = groups[-1]
            if first + timedelta(hours=hours) == start:
                groups[-1] = (first, hours + 1)
                continue
        groups.append((start, 1))
    return groups


def validate_slot(start: datetime) -> str | None:
    """Return an error key if ``start`` can't be a free-electricity hour."""
    if start.minute or start.second or start.microsecond:
        return "not_on_hour"
    if not is_redemption_hour(start):
        return "outside_redemption_hours"
    return None

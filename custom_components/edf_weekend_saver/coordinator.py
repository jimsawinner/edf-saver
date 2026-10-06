"""Coordinator that turns recorder statistics into Weekend Saver progress."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ENERGY_SENSOR,
    CONF_UNIT_RATE,
    DEFAULT_UNIT_RATE,
    DOMAIN,
    STORAGE_VERSION,
    UPDATE_INTERVAL,
)
from .scheme import (
    PeakSummary,
    ServicePeriod,
    is_peak_hour,
    redemption_period_for,
    summarise,
)

_LOGGER = logging.getLogger(__name__)

HOUR = timedelta(hours=1)
# Long-term statistics for an hour are compiled a few minutes after it ends.
FINALISE_AFTER = timedelta(hours=2)

type EdfWeekendSaverConfigEntry = ConfigEntry[EdfWeekendSaverCoordinator]


@dataclass
class SaverData:
    """Snapshot of scheme progress."""

    period: ServicePeriod
    period_active: bool
    summary: PeakSummary
    previous_period: ServicePeriod
    previous_summary: PeakSummary
    redemption_period: ServicePeriod
    awarded_hours: int
    awarded_is_estimate: bool
    booked_hours: int
    window_free_kwh: float
    window_savings: float
    lifetime_free_kwh: float
    lifetime_savings: float
    next_slot: datetime | None
    slot_starts: list[datetime] = field(default_factory=list)

    @property
    def unbooked_hours(self) -> int:
        return max(0, self.awarded_hours - self.booked_hours)


class EdfWeekendSaverCoordinator(DataUpdateCoordinator[SaverData]):
    """Fetch hourly consumption and work out Weekend Saver progress."""

    config_entry: EdfWeekendSaverConfigEntry

    def __init__(self, hass: HomeAssistant, entry: EdfWeekendSaverConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        # Hourly slot start (local ISO string) -> finalised kWh, or None.
        self._slots: dict[str, float | None] = {}
        # Service period key -> free hours EDF actually awarded.
        self._awarded: dict[str, int] = {}
        self._summary_cache: dict[str, PeakSummary] = {}

    @property
    def statistic_id(self) -> str:
        return self.config_entry.options.get(
            CONF_ENERGY_SENSOR, self.config_entry.data[CONF_ENERGY_SENSOR]
        )

    @property
    def unit_rate(self) -> float:
        """Unit rate in pence per kWh."""
        return float(
            self.config_entry.options.get(
                CONF_UNIT_RATE,
                self.config_entry.data.get(CONF_UNIT_RATE, DEFAULT_UNIT_RATE),
            )
        )

    async def async_load(self) -> None:
        """Load booked slots and awarded hours from storage."""
        if stored := await self._store.async_load():
            self._slots = dict(stored.get("slots", {}))
            self._awarded = {k: int(v) for k, v in stored.get("awarded", {}).items()}
        # Peak and free hours change on the hour, so refresh entities then.
        self.config_entry.async_on_unload(
            async_track_time_change(self.hass, self._on_hour, minute=0, second=0)
        )

    @callback
    def _on_hour(self, _now: datetime) -> None:
        self.async_update_listeners()
        self.hass.async_create_task(self.async_request_refresh())

    @callback
    def _save(self) -> None:
        self._store.async_delay_save(lambda: {"slots": self._slots, "awarded": self._awarded}, 1)

    # ------------------------------------------------------------------
    # Free-hour bookings

    def slot_starts(self) -> list[datetime]:
        return sorted(dt_util.as_local(datetime.fromisoformat(s)) for s in self._slots)

    def is_free_now(self, now: datetime | None = None) -> bool:
        now = dt_util.as_local(now or dt_util.now())
        hour = now.replace(minute=0, second=0, microsecond=0)
        return hour.isoformat() in self._slots

    async def async_book(self, starts: list[datetime]) -> None:
        for start in starts:
            self._slots.setdefault(dt_util.as_local(start).isoformat(), None)
        self._save()
        await self.async_refresh()

    async def async_cancel(self, starts: list[datetime]) -> None:
        for start in starts:
            self._slots.pop(dt_util.as_local(start).isoformat(), None)
        self._save()
        await self.async_refresh()

    async def async_set_awarded(self, period: ServicePeriod, hours: int | None) -> None:
        if hours is None:
            self._awarded.pop(period.key, None)
        else:
            self._awarded[period.key] = hours
        self._save()
        await self.async_refresh()

    # ------------------------------------------------------------------
    # Statistics

    async def _hourly(self, start: datetime, end: datetime) -> dict[datetime, float]:
        """Return kWh used per local hour between ``start`` and ``end``.

        Completed hours come from long-term statistics; the hour in progress
        (and any not yet compiled) is filled in from 5-minute statistics.
        """
        if end <= start:
            return {}
        recorder = get_instance(self.hass)
        stat_id = self.statistic_id
        units = {"energy": "kWh"}
        types: set = {"change"}
        result: dict[datetime, float] = {}

        def add(rows: list[dict[str, Any]]) -> datetime | None:
            last_end = None
            for row in rows:
                row_start = row["start"]
                row_start = (
                    dt_util.utc_from_timestamp(row_start)
                    if isinstance(row_start, (int, float))
                    else row_start
                )
                hour = dt_util.as_local(row_start).replace(minute=0, second=0, microsecond=0)
                result[hour] = result.get(hour, 0.0) + (row.get("change") or 0.0)
                row_end = row.get("end")
                if isinstance(row_end, (int, float)):
                    row_end = dt_util.utc_from_timestamp(row_end)
                last_end = row_end or row_start
            return last_end

        hourly = await recorder.async_add_executor_job(
            statistics_during_period,
            self.hass,
            start,
            end,
            {stat_id},
            "hour",
            units,
            types,
        )
        covered_until = add(hourly.get(stat_id, [])) or start
        if covered_until < end:
            short = await recorder.async_add_executor_job(
                statistics_during_period,
                self.hass,
                covered_until,
                end,
                {stat_id},
                "5minute",
                units,
                types,
            )
            add(short.get(stat_id, []))
        return result

    async def _period_summary(self, period: ServicePeriod, now: datetime) -> PeakSummary:
        if cached := self._summary_cache.get(period.key):
            return cached
        tz = dt_util.get_default_time_zone()
        start = datetime.combine(period.start, datetime.min.time(), tz)
        end = datetime.combine(period.end_exclusive, datetime.min.time(), tz)
        summary = summarise(await self._hourly(start, min(end, now)))
        if now >= end + FINALISE_AFTER:
            self._summary_cache[period.key] = summary
        return summary

    async def _slot_kwh(self, now: datetime) -> dict[datetime, float]:
        """Return kWh used in each booked slot that has started."""
        started = [s for s in self.slot_starts() if s <= now]
        pending = [s for s in started if self._slots[s.isoformat()] is None]
        usage: dict[datetime, float] = {s: self._slots[s.isoformat()] or 0.0 for s in started}
        if pending:
            hourly = await self._hourly(min(pending), min(max(pending) + HOUR, now))
            changed = False
            for slot in pending:
                kwh = round(hourly.get(slot, 0.0), 4)
                usage[slot] = kwh
                if now >= slot + HOUR + FINALISE_AFTER:
                    self._slots[slot.isoformat()] = kwh
                    changed = True
            if changed:
                self._save()
        return usage

    async def _async_update_data(self) -> SaverData:
        now = dt_util.now()
        today = now.date()
        try:
            period = ServicePeriod.containing(today)
            summary = await self._period_summary(period, now)
            previous = period.previous()
            previous_summary = await self._period_summary(previous, now)
            redemption = redemption_period_for(today)
            redemption_summary = (
                summary
                if redemption == period
                else previous_summary
                if redemption == previous
                else await self._period_summary(redemption, now)
            )
            slot_usage = await self._slot_kwh(now)
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Error reading statistics for {self.statistic_id}: {err}") from err

        slots = self.slot_starts()
        window_slots = [s for s in slots if redemption.in_redemption_window(s.date())]
        window_kwh = sum(slot_usage.get(s, 0.0) for s in window_slots)
        lifetime_kwh = sum(slot_usage.values())
        rate = self.unit_rate / 100

        awarded = self._awarded.get(redemption.key)
        upcoming = [s for s in slots if s + HOUR > now]

        return SaverData(
            period=period,
            period_active=period.contains(today),
            summary=summary,
            previous_period=previous,
            previous_summary=previous_summary,
            redemption_period=redemption,
            awarded_hours=awarded if awarded is not None else redemption_summary.free_hours,
            awarded_is_estimate=awarded is None,
            booked_hours=len(window_slots),
            window_free_kwh=round(window_kwh, 3),
            window_savings=round(window_kwh * rate, 2),
            lifetime_free_kwh=round(lifetime_kwh, 3),
            lifetime_savings=round(lifetime_kwh * rate, 2),
            next_slot=upcoming[0] if upcoming else None,
            slot_starts=slots,
        )


def peak_now(now: datetime | None = None) -> bool:
    """Return True during the weekday 16:00-19:00 peak."""
    return is_peak_hour(dt_util.as_local(now or dt_util.now()))

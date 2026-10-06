"""Calendar of booked free-electricity hours.

Events can be added and removed from the Home Assistant calendar UI, so the
hours chosen in the EDF app can be mirrored here without any YAML.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.calendar import (
    EVENT_END,
    EVENT_START,
    CalendarEntity,
    CalendarEntityFeature,
    CalendarEvent,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import hourly_slots
from .const import DOMAIN
from .coordinator import EdfWeekendSaverConfigEntry
from .entity import EdfWeekendSaverEntity
from .scheme import group_slots

SUMMARY = "EDF free electricity"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EdfWeekendSaverConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([FreeHoursCalendar(entry.runtime_data, "free_hours")])


def _event(start: datetime, hours: int) -> CalendarEvent:
    return CalendarEvent(
        start=start,
        end=start + timedelta(hours=hours),
        summary=SUMMARY,
        description=f"{hours} free hour{'s' if hours != 1 else ''} (EDF Weekend Saver)",
        uid=start.isoformat(),
    )


class FreeHoursCalendar(EdfWeekendSaverEntity, CalendarEntity):
    """Booked free hours as calendar events."""

    _attr_supported_features = (
        CalendarEntityFeature.CREATE_EVENT | CalendarEntityFeature.DELETE_EVENT
    )

    def _events(self) -> list[CalendarEvent]:
        return [
            _event(start, hours) for start, hours in group_slots(self.coordinator.data.slot_starts)
        ]

    @property
    def event(self) -> CalendarEvent | None:
        now = dt_util.now()
        for event in self._events():
            if event.end > now:
                return event
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [
            event for event in self._events() if event.end > start_date and event.start < end_date
        ]

    async def async_create_event(self, **kwargs: Any) -> None:
        start, end = kwargs[EVENT_START], kwargs[EVENT_END]
        if not isinstance(start, datetime) or not isinstance(end, datetime):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="all_day_not_supported"
            )
        hours = round((end - start).total_seconds() / 3600)
        if hours < 1:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="whole_hours_only"
            )
        await self.coordinator.async_book(hourly_slots(start, hours))

    async def async_delete_event(
        self,
        uid: str,
        recurrence_id: str | None = None,
        recurrence_range: str | None = None,
    ) -> None:
        start = dt_util.as_local(datetime.fromisoformat(uid))
        for first, hours in group_slots(self.coordinator.data.slot_starts):
            if first == start:
                await self.coordinator.async_cancel(
                    [first + timedelta(hours=i) for i in range(hours)]
                )
                return
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="event_not_found")

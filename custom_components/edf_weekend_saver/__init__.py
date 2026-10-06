"""EDF Weekend Saver integration."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_HOURS,
    ATTR_START,
    DOMAIN,
    SERVICE_BOOK_FREE_HOURS,
    SERVICE_CANCEL_FREE_HOURS,
)
from .coordinator import EdfWeekendSaverConfigEntry, EdfWeekendSaverCoordinator
from .scheme import validate_slot

PLATFORMS = [Platform.BINARY_SENSOR, Platform.CALENDAR, Platform.NUMBER, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SLOT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_START): cv.datetime,
        vol.Optional(ATTR_HOURS, default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=15)),
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
    }
)


def hourly_slots(start: datetime, hours: int) -> list[datetime]:
    """Expand a booking into the hourly slots it covers, validating each."""
    if start.tzinfo is None:
        start = start.replace(tzinfo=dt_util.get_default_time_zone())
    start = dt_util.as_local(start)
    slots = [start + timedelta(hours=i) for i in range(hours)]
    for slot in slots:
        if error := validate_slot(slot):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key=error,
                translation_placeholders={"time": slot.strftime("%a %d %b %H:%M")},
            )
    return slots


def _coordinator(hass: HomeAssistant, call: ServiceCall) -> EdfWeekendSaverCoordinator:
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    if entry_id := call.data.get(ATTR_CONFIG_ENTRY_ID):
        entries = [entry for entry in entries if entry.entry_id == entry_id]
    if len(entries) != 1:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="entry_not_found")
    return entries[0].runtime_data


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register services."""

    async def book(call: ServiceCall) -> None:
        slots = hourly_slots(call.data[ATTR_START], call.data[ATTR_HOURS])
        await _coordinator(hass, call).async_book(slots)

    async def cancel(call: ServiceCall) -> None:
        start = call.data[ATTR_START]
        if start.tzinfo is None:
            start = start.replace(tzinfo=dt_util.get_default_time_zone())
        slots = [start + timedelta(hours=i) for i in range(call.data[ATTR_HOURS])]
        await _coordinator(hass, call).async_cancel(slots)

    hass.services.async_register(DOMAIN, SERVICE_BOOK_FREE_HOURS, book, SLOT_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CANCEL_FREE_HOURS, cancel, SLOT_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: EdfWeekendSaverConfigEntry) -> bool:
    """Set up EDF Weekend Saver from a config entry."""
    coordinator = EdfWeekendSaverCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: EdfWeekendSaverConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: EdfWeekendSaverConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

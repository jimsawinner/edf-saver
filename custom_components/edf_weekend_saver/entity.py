"""Base entity for EDF Weekend Saver."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN
from .coordinator import EdfWeekendSaverCoordinator


class EdfWeekendSaverEntity(CoordinatorEntity[EdfWeekendSaverCoordinator]):
    """Entity attached to the Weekend Saver service device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EdfWeekendSaverCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=DEFAULT_NAME,
            manufacturer="EDF",
            model="Weekend Saver",
            entry_type=DeviceEntryType.SERVICE,
        )

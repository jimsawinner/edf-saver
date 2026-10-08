"""Binary sensors for EDF Weekend Saver."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import EdfWeekendSaverConfigEntry, EdfWeekendSaverCoordinator, peak_now
from .entity import EdfWeekendSaverEntity
from .scheme import TARGET_PERCENT


@dataclass(frozen=True, kw_only=True)
class SaverBinarySensorDescription(BinarySensorEntityDescription):
    is_on_fn: Callable[[EdfWeekendSaverCoordinator], bool | None]


def _on_target(coordinator: EdfWeekendSaverCoordinator) -> bool | None:
    percent = coordinator.data.summary.percentage
    return None if percent is None else percent < TARGET_PERCENT


DESCRIPTIONS = (
    SaverBinarySensorDescription(
        key="peak_period",
        is_on_fn=lambda c: peak_now(),
    ),
    SaverBinarySensorDescription(
        key="free_electricity",
        is_on_fn=lambda c: c.is_free_now(),
    ),
    SaverBinarySensorDescription(
        key="on_target",
        is_on_fn=_on_target,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EdfWeekendSaverConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        SaverBinarySensor(entry.runtime_data, description) for description in DESCRIPTIONS
    )


class SaverBinarySensor(EdfWeekendSaverEntity, BinarySensorEntity):
    """Weekend Saver binary sensor."""

    entity_description: SaverBinarySensorDescription

    def __init__(
        self,
        coordinator: EdfWeekendSaverCoordinator,
        description: SaverBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.is_on_fn(self.coordinator)

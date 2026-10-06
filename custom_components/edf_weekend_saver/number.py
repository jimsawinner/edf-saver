"""Number entity for the free hours EDF awarded."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import EdfWeekendSaverConfigEntry
from .entity import EdfWeekendSaverEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EdfWeekendSaverConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([AwardedHoursNumber(entry.runtime_data, "awarded_hours")])


class AwardedHoursNumber(EdfWeekendSaverEntity, NumberEntity):
    """Free hours available this redemption window.

    Defaults to the estimate from the last service period; set it to the
    figure shown in the EDF app to override.
    """

    _attr_native_min_value = 0
    _attr_native_max_value = 25
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = UnitOfTime.HOURS

    @property
    def native_value(self) -> float:
        return self.coordinator.data.awarded_hours

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        return {
            "estimated": data.awarded_is_estimate,
            "service_period": data.redemption_period.key,
        }

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_awarded(
            self.coordinator.data.redemption_period, int(value)
        )

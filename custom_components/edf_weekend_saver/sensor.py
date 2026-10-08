"""Sensors for EDF Weekend Saver."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import EdfWeekendSaverConfigEntry, EdfWeekendSaverCoordinator, SaverData
from .entity import EdfWeekendSaverEntity
from .scheme import TARGET_PERCENT, next_band


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def _period_attrs(data: SaverData) -> dict[str, Any]:
    summary = data.summary
    better = next_band(summary.percentage)
    return {
        "service_period_start": data.period.start.isoformat(),
        "service_period_end": data.period.end.isoformat(),
        "service_period_active": data.period_active,
        "peak_kwh": summary.peak_kwh,
        "total_kwh": summary.total_kwh,
        "free_hours_on_track_for": summary.free_hours,
        "next_band_percent": better[0] if better else None,
        "next_band_free_hours": better[1] if better else None,
    }


def _window_attrs(data: SaverData) -> dict[str, Any]:
    period = data.redemption_period
    return {
        "earned_in_service_period": period.key,
        "redemption_start": period.redemption_start.isoformat(),
        "redemption_end": (period.redemption_end_exclusive - timedelta(days=1)).isoformat(),
        "awarded_hours": data.awarded_hours,
        "awarded_is_estimate": data.awarded_is_estimate,
    }


@dataclass(frozen=True, kw_only=True)
class SaverSensorDescription(SensorEntityDescription):
    value_fn: Callable[[SaverData], Any]
    attrs_fn: Callable[[SaverData], dict[str, Any]] | None = None


ENERGY = {
    "device_class": SensorDeviceClass.ENERGY,
    "native_unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
    "suggested_display_precision": 2,
}
MONEY = {
    "device_class": SensorDeviceClass.MONETARY,
    "native_unit_of_measurement": "GBP",
    "suggested_display_precision": 2,
}
HOURS = {"native_unit_of_measurement": UnitOfTime.HOURS}

DESCRIPTIONS: tuple[SaverSensorDescription, ...] = (
    SaverSensorDescription(
        key="peak_percentage",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        value_fn=lambda d: _round(d.summary.percentage),
        attrs_fn=_period_attrs,
    ),
    SaverSensorDescription(
        key="peak_energy",
        **ENERGY,
        value_fn=lambda d: d.summary.peak_kwh,
    ),
    SaverSensorDescription(
        key="total_energy",
        **ENERGY,
        value_fn=lambda d: d.summary.total_kwh,
    ),
    SaverSensorDescription(
        key="peak_headroom",
        **ENERGY,
        value_fn=lambda d: _round(d.summary.headroom_kwh(TARGET_PERCENT)),
        attrs_fn=lambda d: {
            "target_percent": TARGET_PERCENT,
            "off_peak_needed_kwh": _round(d.summary.off_peak_needed_kwh(TARGET_PERCENT)),
        },
    ),
    SaverSensorDescription(
        key="projected_free_hours",
        **HOURS,
        value_fn=lambda d: d.summary.free_hours,
    ),
    SaverSensorDescription(
        key="previous_peak_percentage",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        value_fn=lambda d: _round(d.previous_summary.percentage),
        attrs_fn=lambda d: {
            "service_period_start": d.previous_period.start.isoformat(),
            "service_period_end": d.previous_period.end.isoformat(),
            "peak_kwh": d.previous_summary.peak_kwh,
            "total_kwh": d.previous_summary.total_kwh,
            "free_hours": d.previous_summary.free_hours,
        },
    ),
    SaverSensorDescription(
        key="booked_free_hours",
        **HOURS,
        value_fn=lambda d: d.booked_hours,
        attrs_fn=_window_attrs,
    ),
    SaverSensorDescription(
        key="unbooked_free_hours",
        **HOURS,
        value_fn=lambda d: d.unbooked_hours,
        attrs_fn=_window_attrs,
    ),
    SaverSensorDescription(
        key="next_free_slot",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.next_slot,
    ),
    SaverSensorDescription(
        key="free_energy_used",
        **ENERGY,
        value_fn=lambda d: d.window_free_kwh,
        attrs_fn=_window_attrs,
    ),
    SaverSensorDescription(
        key="savings_this_window",
        **MONEY,
        value_fn=lambda d: d.window_savings,
        attrs_fn=_window_attrs,
    ),
    SaverSensorDescription(
        key="lifetime_savings",
        **MONEY,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: d.lifetime_savings,
        attrs_fn=lambda d: {"free_kwh": d.lifetime_free_kwh},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EdfWeekendSaverConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(SaverSensor(entry.runtime_data, description) for description in DESCRIPTIONS)


class SaverSensor(EdfWeekendSaverEntity, SensorEntity):
    """Weekend Saver sensor."""

    entity_description: SaverSensorDescription

    def __init__(
        self,
        coordinator: EdfWeekendSaverCoordinator,
        description: SaverSensorDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)

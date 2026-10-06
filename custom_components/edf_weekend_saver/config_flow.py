"""Config flow for EDF Weekend Saver."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector
import voluptuous as vol

from .const import CONF_ENERGY_SENSOR, CONF_UNIT_RATE, DEFAULT_NAME, DEFAULT_UNIT_RATE, DOMAIN

ENERGY_UNITS = {"Wh", "kWh", "MWh"}


def _schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_ENERGY_SENSOR, default=defaults.get(CONF_ENERGY_SENSOR, vol.UNDEFINED)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor", device_class=SensorDeviceClass.ENERGY
                )
            ),
            vol.Required(
                CONF_UNIT_RATE, default=defaults.get(CONF_UNIT_RATE, DEFAULT_UNIT_RATE)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=200,
                    step=0.01,
                    unit_of_measurement="p/kWh",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
    )


def _validate(hass: HomeAssistant, user_input: dict[str, Any]) -> dict[str, str]:
    state = hass.states.get(user_input[CONF_ENERGY_SENSOR])
    if state is None:
        return {CONF_ENERGY_SENSOR: "entity_not_found"}
    if state.attributes.get("state_class") not in (
        SensorStateClass.TOTAL,
        SensorStateClass.TOTAL_INCREASING,
    ):
        return {CONF_ENERGY_SENSOR: "no_statistics"}
    if state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) not in ENERGY_UNITS:
        return {CONF_ENERGY_SENSOR: "bad_unit"}
    return {}


class EdfWeekendSaverConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_ENERGY_SENSOR])
            self._abort_if_unique_id_configured()
            if not (errors := _validate(self.hass, user_input)):
                return self.async_create_entry(title=DEFAULT_NAME, data=user_input)
        return self.async_show_form(
            step_id="user", data_schema=_schema(user_input or {}), errors=errors
        )

    @staticmethod
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return EdfWeekendSaverOptionsFlow()


class EdfWeekendSaverOptionsFlow(OptionsFlow):
    """Change the energy sensor or unit rate."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not (errors := _validate(self.hass, user_input)):
                return self.async_create_entry(data=user_input)
        defaults = {**self.config_entry.data, **self.config_entry.options, **(user_input or {})}
        return self.async_show_form(step_id="init", data_schema=_schema(defaults), errors=errors)

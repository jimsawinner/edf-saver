"""Integration tests for EDF Weekend Saver."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.edf_weekend_saver.const import (
    CONF_ENERGY_SENSOR,
    CONF_UNIT_RATE,
    DOMAIN,
)
from custom_components.edf_weekend_saver.scheme import is_peak_hour

LONDON = ZoneInfo("Europe/London")
SOURCE = "sensor.grid_import"
# Wednesday 21 October 2026, 17:30 - inside a peak period.
NOW = datetime(2026, 10, 21, 17, 30, tzinfo=LONDON)


def usage(hour: datetime) -> float:
    """Synthetic household: 0.2 kWh/h at peak, 0.5 kWh/h otherwise."""
    return 0.2 if is_peak_hour(hour.astimezone(LONDON)) else 0.5


def fake_statistics(hass, start, end, ids, period, units, types):
    """Mimic recorder statistics: hourly rows lag the current hour."""
    step = timedelta(hours=1) if period == "hour" else timedelta(minutes=5)
    now = NOW
    limit = now.replace(minute=0) if period == "hour" else now
    rows = []
    cursor = start
    while cursor < min(end, limit) and cursor + step <= limit:
        rows.append(
            {
                "start": cursor.timestamp(),
                "end": (cursor + step).timestamp(),
                "change": usage(cursor) * step / timedelta(hours=1),
            }
        )
        cursor += step
    return {SOURCE: rows} if rows else {}


@pytest.fixture
async def setup(hass: HomeAssistant, recorder_mock, freezer):
    await hass.config.async_set_time_zone("Europe/London")
    freezer.move_to(NOW)
    hass.states.async_set(
        SOURCE,
        "1234.5",
        {"state_class": "total_increasing", "unit_of_measurement": "kWh", "device_class": "energy"},
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ENERGY_SENSOR: SOURCE, CONF_UNIT_RATE: 25.0},
        unique_id=SOURCE,
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.edf_weekend_saver.coordinator.statistics_during_period",
        side_effect=fake_statistics,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        yield entry


async def test_config_flow(hass: HomeAssistant, recorder_mock):
    hass.states.async_set(SOURCE, "1", {"state_class": "measurement", "unit_of_measurement": "kWh"})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ENERGY_SENSOR: SOURCE, CONF_UNIT_RATE: 24.5}
    )
    assert result["errors"] == {CONF_ENERGY_SENSOR: "no_statistics"}

    hass.states.async_set(
        SOURCE, "1", {"state_class": "total_increasing", "unit_of_measurement": "kWh"}
    )
    with patch("custom_components.edf_weekend_saver.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ENERGY_SENSOR: SOURCE, CONF_UNIT_RATE: 24.5}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_ENERGY_SENSOR: SOURCE, CONF_UNIT_RATE: 24.5}


async def test_progress_sensors(hass: HomeAssistant, setup):
    # October's period started Mon 5 Oct. 12 full weekdays + today, so far.
    start = datetime(2026, 10, 5, tzinfo=LONDON)
    hour = start
    peak = total = 0.0
    while hour < NOW:
        kwh = usage(hour) * (0.5 if hour == NOW.replace(minute=0) else 1)
        total += kwh
        if is_peak_hour(hour):
            peak += kwh
        hour += timedelta(hours=1)

    pct = hass.states.get("sensor.edf_weekend_saver_peak_usage")
    assert float(pct.state) == pytest.approx(round(peak / total * 100, 2))
    assert pct.attributes["service_period_start"] == "2026-10-05"
    assert pct.attributes["service_period_end"] == "2026-10-30"
    assert float(hass.states.get("sensor.edf_weekend_saver_total_energy").state) == pytest.approx(
        total, abs=0.01
    )
    assert hass.states.get("sensor.edf_weekend_saver_projected_free_hours").state == "25"
    assert float(hass.states.get("sensor.edf_weekend_saver_peak_headroom").state) > 0

    assert hass.states.get("binary_sensor.edf_weekend_saver_peak_period").state == "on"
    assert hass.states.get("binary_sensor.edf_weekend_saver_on_target").state == "on"
    assert hass.states.get("binary_sensor.edf_weekend_saver_free_electricity").state == "off"

    # September's result decides the free hours redeemable now.
    awarded = hass.states.get("number.edf_weekend_saver_free_hours_awarded")
    assert awarded.state == "25"
    assert awarded.attributes["estimated"] is True
    assert awarded.attributes["service_period"] == "2026-09"


async def test_booking_and_override(hass: HomeAssistant, setup):
    await hass.services.async_call(
        DOMAIN,
        "book_free_hours",
        {"start": "2026-10-24 09:00:00", "hours": 3},
        blocking=True,
    )
    assert hass.states.get("sensor.edf_weekend_saver_booked_free_hours").state == "3"
    assert hass.states.get("sensor.edf_weekend_saver_unbooked_free_hours").state == "22"
    assert (
        hass.states.get("sensor.edf_weekend_saver_next_free_hour").state
        == "2026-10-24T08:00:00+00:00"
    )

    calendar = hass.states.get("calendar.edf_weekend_saver_free_hours")
    assert calendar.attributes["start_time"] == "2026-10-24 09:00:00"
    assert calendar.attributes["end_time"] == "2026-10-24 12:00:00"

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "book_free_hours", {"start": "2026-10-23 09:00:00"}, blocking=True
        )
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "book_free_hours", {"start": "2026-10-24 14:00:00", "hours": 2}, blocking=True
        )

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.edf_weekend_saver_free_hours_awarded", "value": 15},
        blocking=True,
    )
    assert hass.states.get("sensor.edf_weekend_saver_unbooked_free_hours").state == "12"

    await hass.services.async_call(
        DOMAIN, "cancel_free_hours", {"start": "2026-10-24 10:00:00", "hours": 2}, blocking=True
    )
    assert hass.states.get("sensor.edf_weekend_saver_booked_free_hours").state == "1"


async def test_calendar_create_delete(hass: HomeAssistant, setup):
    await hass.services.async_call(
        "calendar",
        "create_event",
        {
            "entity_id": "calendar.edf_weekend_saver_free_hours",
            "summary": "Free",
            "start_date_time": "2026-10-25 07:00:00",
            "end_date_time": "2026-10-25 09:00:00",
        },
        blocking=True,
    )
    assert hass.states.get("sensor.edf_weekend_saver_booked_free_hours").state == "2"
    coordinator = setup.runtime_data
    calendar = hass.data["calendar"].get_entity("calendar.edf_weekend_saver_free_hours")
    events = await calendar.async_get_events(hass, NOW, NOW + timedelta(days=7))
    assert len(events) == 1
    await calendar.async_delete_event(events[0].uid)
    assert coordinator.data.booked_hours == 0


async def test_savings_from_past_slots(hass: HomeAssistant, setup, freezer):
    coordinator = setup.runtime_data
    # Book Saturday 10 Oct 09:00-11:00 (in September's redemption window).
    await coordinator.async_book(
        [datetime(2026, 10, 10, 9, tzinfo=LONDON), datetime(2026, 10, 10, 10, tzinfo=LONDON)]
    )
    data = coordinator.data
    assert data.booked_hours == 2
    assert data.window_free_kwh == pytest.approx(1.0)
    assert data.window_savings == pytest.approx(0.25)
    assert data.lifetime_savings == pytest.approx(0.25)
    assert hass.states.get("sensor.edf_weekend_saver_total_savings").state == "0.25"

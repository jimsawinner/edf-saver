"""End-to-end check against real recorder statistics (no mocking)."""

from datetime import datetime, timedelta

from homeassistant.components.recorder.models import StatisticMeanType
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.edf_weekend_saver.const import CONF_ENERGY_SENSOR, DOMAIN
from custom_components.edf_weekend_saver.scheme import is_peak_hour

from .test_integration import LONDON, NOW, SOURCE


async def test_reads_real_statistics_in_wh(hass: HomeAssistant, freezer):
    await hass.config.async_set_time_zone("Europe/London")
    freezer.move_to(NOW)
    hass.states.async_set(
        SOURCE,
        "1",
        {"state_class": "total_increasing", "unit_of_measurement": "Wh", "device_class": "energy"},
    )
    # 1 kWh every hour, except 0.1 kWh in peak hours, recorded in Wh.
    start = datetime(2026, 10, 1, tzinfo=LONDON)
    stats, total, hour = [], 0.0, start
    peak = in_period = 0.0
    while hour < NOW.replace(minute=0):
        kwh = 0.1 if is_peak_hour(hour) else 1.0
        total += kwh * 1000
        stats.append({"start": hour, "state": total, "sum": total})
        if hour >= datetime(2026, 10, 5, tzinfo=LONDON):
            in_period += kwh
            peak += kwh if is_peak_hour(hour) else 0
        hour += timedelta(hours=1)
    metadata = {
        "mean_type": StatisticMeanType.NONE,
        "has_sum": True,
        "name": None,
        "source": "recorder",
        "statistic_id": SOURCE,
        "unit_class": "energy",
        "unit_of_measurement": "Wh",
    }
    async_import_statistics(hass, metadata, stats)
    await async_wait_recording_done(hass)

    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ENERGY_SENSOR: SOURCE}, unique_id=SOURCE)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    summary = entry.runtime_data.data.summary
    assert summary.total_kwh == pytest.approx(in_period)
    assert summary.peak_kwh == pytest.approx(peak)
    state = hass.states.get("sensor.edf_weekend_saver_peak_usage")
    assert float(state.state) == pytest.approx(round(peak / in_period * 100, 2))

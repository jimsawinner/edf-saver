"""Check the bundled blueprints produce valid automations."""

from pathlib import Path
import shutil

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
import pytest

BLUEPRINTS = Path(__file__).parent.parent / "blueprints" / "automation" / "edf_weekend_saver"

INPUTS = {
    "run_during_free_electricity.yaml": {
        "free_sensor": "binary_sensor.edf_weekend_saver_free_electricity",
        "targets": {"entity_id": "switch.immersion"},
    },
    "avoid_peak.yaml": {
        "peak_sensor": "binary_sensor.edf_weekend_saver_peak_period",
        "targets": {"entity_id": "switch.dehumidifier"},
    },
    "peak_usage_warning.yaml": {
        "peak_usage_sensor": "sensor.edf_weekend_saver_peak_usage",
        "notify_actions": [{"action": "persistent_notification.create", "data": {"message": "x"}}],
    },
}


@pytest.mark.parametrize("name", sorted(INPUTS))
async def test_blueprint_valid(hass: HomeAssistant, name: str):
    target = Path(hass.config.path("blueprints/automation/edf_weekend_saver"))
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy(BLUEPRINTS / name, target / name)
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "id": "test",
                "use_blueprint": {"path": f"edf_weekend_saver/{name}", "input": INPUTS[name]},
            }
        },
    )
    await hass.async_block_till_done()
    state = hass.states.async_all("automation")[0]
    assert state.state == "on", state

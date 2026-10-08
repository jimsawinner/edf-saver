# EDF Weekend Saver for Home Assistant

A [HACS](https://hacs.xyz) custom integration for EDF customers on **Weekend Saver** (formerly Sunday Saver). It tracks how much of your electricity you use in the weekday 4–7pm peak, shows which reward band you're on course for, keeps a record of the free weekend hours you've booked, works out what they've saved you, and gives you entities and blueprints to run devices around peak and free hours.

> Not affiliated with or endorsed by EDF. The scheme rules below come from EDF's published terms; check the EDF app for your official results.

## How Weekend Saver works

| Peak share (Mon–Fri 4–7pm ÷ all use in the service period) | Free hours |
|---|---|
| under 9% | **25** |
| 9% to under 12% | 15 |
| 12% to under 15% | 10 |
| 15% to under 18% | 5 |
| 18% or more | 0 |

* A **service period** runs from the first Monday of the month to the Friday after the month's last Monday.
* Free hours are used **00:00–15:00 on Saturdays and Sundays** during the four weeks starting the Saturday after the service period ends. You pick the hours in the EDF app.

## Where the data comes from

EDF has no public customer API, so the integration reads your consumption from **any Home Assistant energy sensor that records long-term statistics**. This is the same kind of sensor the Energy dashboard uses, for example:

* a Hildebrand Glow / Glowmarkt smart meter display (CAD), or the Glow DCC cloud integration
* a CT clamp (Shelly EM, Emporia, etc.)
* any `kWh` sensor with `state_class: total` or `total_increasing`

The integration reads hourly statistics from the recorder, so it **backfills history from before you installed it** and isn't affected by restarts.

You enter your chosen free hours yourself, either from the calendar or with a service call (see below).

## Installation

1. HACS → ⋮ → *Custom repositories* → add `https://github.com/jimsawinner/edf-saver` as an **Integration**.
2. Install **EDF Weekend Saver** and restart Home Assistant.
3. *Settings → Devices & services → Add integration → EDF Weekend Saver*.
4. Pick your electricity import sensor and enter your unit rate (p/kWh, used to value the free electricity).

## Entities

| Entity | What it shows |
|---|---|
| `sensor.…_peak_usage` | Peak share so far this service period (%) and the next band to aim for |
| `sensor.…_peak_energy` / `_total_energy` | kWh used at peak / in total this period |
| `sensor.…_peak_headroom` | Peak kWh you can still use and stay under 9% (negative = over) |
| `sensor.…_projected_free_hours` | Free hours you're on track for |
| `sensor.…_last_period_peak_usage` | Last service period's result |
| `number.…_free_hours_awarded` | Free hours available now. Estimated from last period; set it to the figure in the EDF app to override |
| `sensor.…_booked_free_hours` / `_unbooked_free_hours` | Hours booked in the current redemption window / still to book |
| `sensor.…_next_free_hour` | Start of your next free hour |
| `sensor.…_free_energy_used` | kWh used during free hours this window |
| `sensor.…_savings_this_month` / `_total_savings` | £ saved this window / all time |
| `binary_sensor.…_peak_period` | On during weekday 4–7pm |
| `binary_sensor.…_free_electricity` | On during a booked free hour |
| `binary_sensor.…_on_target` | On while you're under 9% |
| `calendar.…_free_hours` | Your booked free hours |

## Booking your free hours

After choosing hours in the EDF app, copy them into Home Assistant:

* **Calendar:** open the *Free hours* calendar and add an event (e.g. Saturday 09:00–12:00). Delete the event to cancel it.
* **Action:**
  ```yaml
  action: edf_weekend_saver.book_free_hours
  data:
    start: "2026-10-31 09:00:00"
    hours: 3
  ```
  `edf_weekend_saver.cancel_free_hours` takes the same fields.

Hours must start on the hour, on a Saturday or Sunday, and finish by 15:00.

## Controlling devices

Import the blueprints (*Settings → Automations → Blueprints → Import*), using the raw GitHub URLs of:

* [`run_during_free_electricity.yaml`](blueprints/automation/edf_weekend_saver/run_during_free_electricity.yaml): turn on an EV charger, immersion heater, battery charge mode etc. when free hours start, and off when they end.
* [`avoid_peak.yaml`](blueprints/automation/edf_weekend_saver/avoid_peak.yaml): pause devices during 4–7pm on weekdays.
* [`peak_usage_warning.yaml`](blueprints/automation/edf_weekend_saver/peak_usage_warning.yaml): get a notification if your peak share rises past a level you choose.

You can also use the binary sensors and calendar directly as automation triggers.

## Dashboard

[`dashboards/weekend_saver.yaml`](dashboards/weekend_saver.yaml) is a ready-made dashboard built from core cards only (no extra frontend plugins). It has a banded gauge for your peak share, your free hours with the calendar, and your savings. Paste it into a new dashboard's raw configuration editor.

## Limitations

* Results are estimates from your own meter data. EDF's half-hourly smart meter data is authoritative and may differ slightly, so set **Free hours awarded** from the app if they disagree.
* The terms don't say how bank holidays are treated, so they're counted as normal weekdays.
* Hourly statistics are compiled shortly after each hour, and the hour in progress uses 5-minute statistics. Figures update every 5 minutes.

## Development

```bash
pip install -r requirements_test.txt
ruff check .
pytest
```

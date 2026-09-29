# home-battery-optimiser

Pyscript automations for Home Assistant that manage a GivEnergy home battery (via GivTCP). Each night the automations set the battery's charge and discharge schedule from tomorrow's solar forecast (Solcast API) and temperature forecast (Home Assistant's weather data), and estimate how much energy the air conditioning and a Vaillant heat pump will use. They also pre-charge the battery ahead of Axle Energy Virtual Power Plant events. The automation sets Home Assistant settings over MQTT and the heat pump settings are set over ebusd.

## What it does

| File | Purpose |
|---|---|
| `main.py` | Schedules the daily jobs (forecast, resets, BST adjustment, split discharge). Jobs are set for different times using cron functions, which can be personalised for your own home setup. |
| `battery_forecast.py` | Uses Solcast solar and HA weather forecasts to set tomorrow's overnight battery charge target, using a formula which accounts for heat pump usage and aircon usage amongst other things. The parameters for this formula can be personalised. |
| `custom_axle.py` | Polls the Axle Energy VPP API hourly and pre-charges the battery before an event along with setting settings for the axle event (shelly switch and charge rate). |
| `daily_reset.py` | Resets inverter, Shelly and heat pump settings each night, ensuring system operates normally post Axle event. |
| `time_change.py` | Shifts the overnight charge window depending on whether it is BST or GMT. |

## Setup

1. Install the pyscript integration in Home Assistant.
2. Copy these files into your `config/pyscript/` folder.
3. Copy `secrets_config.example.py` to `secrets_config.py` and add your Axle API key, Solcast API key and Solcast site ID.
4. Fill in the entity IDs at the top of each file: replace `<inverter_serial>` with your GivTCP inverter serial, and set `<your_shelly_switch>` and `<your_heat_pump_opmode_sensor>` to your own entities.

## Credits

The code that fetches events from the Axle Energy API (`AxleApi` in `custom_axle.py`) is based on [`api.py`](https://github.com/deanhalllincoln/ha-axle-vpp/blob/main/custom_components/axle_vpp/api.py) from [deanhalllincoln/ha-axle-vpp](https://github.com/deanhalllincoln/ha-axle-vpp). Used with permission ([ha-axle-vpp#27](https://github.com/deanhalllincoln/ha-axle-vpp/issues/27)). Thanks to Dean for making it available.

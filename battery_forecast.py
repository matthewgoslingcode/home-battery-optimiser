from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

# Kept out of git, see secrets_config.example.py
from secrets_config import SOLCAST_API_KEY, SOLCAST_SITE_ID

CHARGE_TARGET_SOC_1_ENTITY = "number.givtcp_<inverter_serial>_charge_target_soc_1"
MINIMUM_SOC_ENTITY = "number.givtcp_<inverter_serial>_discharge_target_soc_1"
DISCHARGE_WINDOW_START_ENTITY = "select.givtcp_<inverter_serial>_discharge_start_time_slot_1"
DISCHARGE_WINDOW_END_ENTITY = "select.givtcp_<inverter_serial>_discharge_end_time_slot_1"
HEAT_PUMP_OPMODE_ENTITY = "sensor.<your_heat_pump_opmode_sensor>"


class Forecaster:
    def __init__(self):
        """Set up the system parameters used by the battery model."""

        self.start_1 = 0
        self.start_2 = 0
        self.start_percentage = 0

        # Parameters based on our system, alter for your own

        self.heat_loss = 10
        self.max_heating_outside_temp = 18
        self.cop_min = 2.5
        self.cop_max = 4.0
        self.min_cooling_temp = 25
        self.max_cooling_temp = 35
        self.min_cooling_load = 0.25
        self.max_cooling_load = 1
        self.min_battery_capacity = 0.54
        self.max_battery_capacity = 13.5
        self.baseload_am = 0.4
        self.baseload_pm = 1

        # The model assumes no aircon use in the morning but this can be
        # adjusted in this line:

        self.aircon_adj_am = 0

    @pyscript_compile
    def fetch_solar_forecast(self):
        """Fetch the next 48 hours of solar forecasts from Solcast."""

        url = f"https://api.solcast.com.au/rooftop_sites/{SOLCAST_SITE_ID}/forecasts"
        headers = {"Authorization": f"Bearer {SOLCAST_API_KEY}"}
        params = {"format": "json", "hours": 48}

        # Raise err after 15 seconds
        resp = requests.get(url, headers=headers, params=params, timeout=15)

        # Raises err if there is one, otherwise nothing
        resp.raise_for_status()
        return resp.json()["forecasts"]

    def fetch_temperature_forecast(self, entity_id="weather.forecast_home"):
        """Get the hourly weather forecast from Home Assistant."""

        # Getting temp forecast using HA's own local data
        result = weather.get_forecasts(
            entity_id=entity_id, type="hourly", blocking=True, return_response=True
        )
        forecast_list = result[entity_id]["forecast"]
        return forecast_list

    def tomorrow_forecast_split_solar(self, forecasts):
        """Total tomorrow's solar forecast (kWh), split into am and pm."""

        # Retrieve time zone
        tz = ZoneInfo(hass.config.time_zone)

        # Get tomorrow from 48hr period retrieved
        tomorrow_local = (datetime.now(tz) + timedelta(days=1)).date()

        morning_total = 0
        afternoon_total = 0

        for f in forecasts:
            # Coordinated universal time
            ts_utc = datetime.fromisoformat(f["period_end"].replace("Z", "+00:00"))
            # Convert time zone to HA time zone
            ts_local = ts_utc.astimezone(tz)

            # Check forecast is tomorrow's
            if ts_local.date() == tomorrow_local:

                # Divide by 2 for half hour intervals
                energy = f["pv_estimate"] * 0.5
                if ts_local.hour < 12:
                    morning_total += energy
                else:
                    afternoon_total += energy

        return {
            "morning": morning_total,
            "afternoon": afternoon_total,
            "total": morning_total + afternoon_total,
        }

    def decide_strategy(self, expected_kwh, expected_temperatures):
        """Apply a safety factor to the solar forecast and get the target."""

        # Solar and temperature values

        kwh_total = expected_kwh["total"]
        kwh_morning = expected_kwh["morning"]
        kwh_afternoon = expected_kwh["afternoon"]
        seven_temp = expected_temperatures.get("07:00")
        eleven_temp = expected_temperatures.get("11:00")
        three_temp = expected_temperatures.get("15:00")

        # Check values are returned, if not raise err

        if None in (seven_temp, eleven_temp, three_temp):
            raise ValueError(f"Missing expected temperature reading(s): {expected_temperatures}")

        # Adjust solar by safety factor 0.85, assumes slight overestimate by
        # forecaster

        mean_solar_am = 0.85 * kwh_morning
        mean_solar_total = 0.85 * kwh_total

        return self.battery_formula(
            self.heat_loss,
            self.max_heating_outside_temp,
            self.cop_min,
            self.cop_max,
            self.min_cooling_temp,
            self.max_cooling_temp,
            self.min_cooling_load,
            self.max_cooling_load,
            self.min_battery_capacity,
            self.max_battery_capacity,
            self.baseload_am,
            self.baseload_pm,
            seven_temp,
            eleven_temp,
            three_temp,
            mean_solar_am,
            mean_solar_total,
            self.aircon_adj_am,
        )

    def tomorrow_temps_at_times(self):
        """Get tomorrow's forecast temperatures at 07:00, 11:00 and 15:00."""

        tz = ZoneInfo(hass.config.time_zone)
        # Defining tomorrow
        tomorrow_local = (datetime.now(tz) + timedelta(days=1)).date()
        target_hours = {7: "07:00", 11: "11:00", 15: "15:00"}

        forecast_list = self.fetch_temperature_forecast(entity_id="weather.forecast_home")

        temps = {}

        # Construct temps dictionary
        for entry in forecast_list:
            ts_local = datetime.fromisoformat(entry["datetime"]).astimezone(tz)
            if ts_local.date() == tomorrow_local and ts_local.hour in target_hours:
                label = target_hours[ts_local.hour]
                temps[label] = entry["temperature"]

        return temps

    def battery_formula(
        self,
        heat_loss,
        max_heating_outside_temp,
        cop_min,
        cop_max,
        min_cooling_temp,
        max_cooling_temp,
        min_cooling_load,
        max_cooling_load,
        min_battery_capacity,
        max_battery_capacity,
        baseload_am,
        baseload_pm,
        seven_temp,
        eleven_temp,
        three_temp,
        mean_solar_am,
        mean_solar_total,
        aircon_adj_am,
    ):
        """Estimate the overnight charge target (%) from loads and solar."""

        if three_temp < min_cooling_temp:
            aircon_adj_pm = 0
        else:
            aircon_adj_pm = 6 * (
                min_cooling_load
                + (three_temp - min_cooling_temp)
                / (max_cooling_temp - min_cooling_temp)
                * max_cooling_load
            )

        # Calculate heating load for morning and afternoon

        # If heating is off
        if hass.states.get(HEAT_PUMP_OPMODE_ENTITY).state == "off":
            heat_pump_adj_am = 0
            heat_pump_adj_pm = 0
        # If heating is on
        else:
            # First calculate heat loss at 7am, 11am, and 3pm by interpolating
            # between "heat_loss" at -3 outside and zero at
            # "max_heating_outside_temp":
            max_temp = max_heating_outside_temp
            temp_range = max_temp - (-3)  # Span from -3°C to max_heating_outside_temp

            heat_loss_seven = max(0, heat_loss * (max_temp - seven_temp) / temp_range)
            heat_loss_eleven = max(0, heat_loss * (max_temp - eleven_temp) / temp_range)
            heat_loss_three = max(0, heat_loss * (max_temp - three_temp) / temp_range)

            # Then interpolate COP in the same fashion:

            cop_seven = cop_min + (cop_max - cop_min) * (seven_temp - (-3)) / temp_range
            cop_eleven = cop_min + (cop_max - cop_min) * (eleven_temp - (-3)) / temp_range
            cop_three = cop_min + (cop_max - cop_min) * (three_temp - (-3)) / temp_range

            # At each time, the heat pump power is heat_loss divided by COP – we
            # then apply that heat loss for a four hour window around the
            # sampled time:

            heat_pump_adj_am = 4 * heat_loss_seven / cop_seven + 2 * heat_loss_eleven / cop_eleven
            heat_pump_adj_pm = 2 * heat_loss_eleven / cop_eleven + 4 * heat_loss_three / cop_three

        # Now use these to calculate the overnight state of charge
        # Most loads are in the afternoon so we look at a morning percentage
        # first to look at how low the battery could be charged for the
        # morning solar to get it to 100% by lunchtime – we can at least
        # reduce the charge to this level to leave solar capacity.
        # We then separately do a whole day test to compare solar against
        # outflows to determine the level of battery needed.

        self.start_1 = (
            (
                max_battery_capacity
                - min_battery_capacity
                + 6 * baseload_am
                + aircon_adj_am
                + heat_pump_adj_am
                - mean_solar_am
            )
            / max_battery_capacity
        ) * 100
        self.start_2 = (
            (
                max_battery_capacity
                - min_battery_capacity
                + 6 * baseload_am
                + 6 * baseload_pm
                + aircon_adj_am
                + aircon_adj_pm
                + heat_pump_adj_am
                + heat_pump_adj_pm
                - mean_solar_total
            )
            / max_battery_capacity
        ) * 100
        self.start_percentage = round(min(self.start_1, self.start_2))
        # Min value will always be at least 10%
        self.start_percentage = max(10, min(100, self.start_percentage))

        return self.start_percentage

    def apply_battery_forecast(self):
        """Run the forecast and set tomorrow's charge and discharge targets."""

        log.info("Running")
        try:
            # Calling functions

            forecasts = task.executor(self.fetch_solar_forecast)
            temperature_forecasts = self.tomorrow_temps_at_times()
            solar_split = self.tomorrow_forecast_split_solar(forecasts)

            log.info(
                f"Morning: {solar_split['morning']:.1f} kWh, "
                f"Afternoon: {solar_split['afternoon']:.1f} kWh, "
                f"Total: {solar_split['total']:.1f} kWh"
            )

            # Setting battery value using formula

            battery_soc_1 = self.decide_strategy(solar_split, temperature_forecasts)

            # Set value of charge target soc 1 in HA

            number.set_value(entity_id=CHARGE_TARGET_SOC_1_ENTITY, value=battery_soc_1)

            # Set discharge window

            select.select_option(entity_id=DISCHARGE_WINDOW_START_ENTITY, option="01:00:00")
            select.select_option(entity_id=DISCHARGE_WINDOW_END_ENTITY, option="03:00:00")

            # Set discharge minimum

            number.set_value(entity_id=MINIMUM_SOC_ENTITY, value=battery_soc_1)

        except Exception as e:
            log.error(f"Battery forecast automation failed: {e}")
            persistent_notification.create(title="Battery Forecast FAILED", message=str(e))

from datetime import datetime
from datetime import timedelta

import aiohttp
import homeassistant.util.dt as dt_util

# Kept out of git, see secrets_config.example.py
from secrets_config import AXLE_API_KEY

# Entities that control inverter's charge slot
CHARGE_SLOT_START_ENTITY = "select.givtcp_<inverter_serial>_charge_start_time_slot_2"
CHARGE_SLOT_END_ENTITY = "select.givtcp_<inverter_serial>_charge_end_time_slot_2"
BATTERY_CHARGE_RATE_ENTITY = "number.givtcp_<inverter_serial>_battery_charge_rate"
SHELLY_ENTITY = "switch.<your_shelly_switch>"


# The Axle API client below (AxleApi and async_get_event) is based on the
# work of deanhalllincoln:
# https://github.com/deanhalllincoln/ha-axle-vpp/blob/main/custom_components/axle_vpp/api.py
class AxleApi:
    """
    Production API client for Axle Energy VPP events.

    Fetches real event data from Axle and formats it for the
    coordinator/sensors.
    """

    # Add axle API here
    BASE_URL = "https://api.axle.energy/vpp/home-assistant/event"

    def __init__(self, token: str):
        """Store the API token and build the request headers."""

        self.token = token
        self.headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}

    async def async_get_event(self) -> dict | None:
        """
        Fetch the latest VPP event from Axle.

        Returns:
            dict with keys: start_time, end_time, import_export, updated_at
            or None if no event is active.
        Raises:
            Exception on network or API errors.
        """
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(self.BASE_URL) as resp:
                    if resp.status != 200:
                        raise Exception(f"Axle API returned status {resp.status}")
                    data = await resp.json()
        except Exception as err:
            raise Exception(f"Error fetching Axle API: {err}") from err

        # If API request returns nothing or missing start_time, treat as no event
        if not data or "start_time" not in data:
            return None

        # Map API response to coordinator format
        event = {
            "start_time": data.get("start_time"),  # ISO 8601 string
            "end_time": data.get("end_time"),  # ISO 8601 string
            "import_export": data.get("import_export", 0),  # Default to 0
            "updated_at": data.get("updated_at", datetime.utcnow().isoformat() + "Z"),
        }

        return event

    def run_axle(self):
        """Prepare the battery if an Axle event starts within 4 hours."""

        response = self.get_response()

        if response is None:
            log.info("No active Axle event")
            return

        # Format into datetime object for doing maths

        self.start_time = self.parse_iso(response["start_time"])
        self.end_time = self.parse_iso(response["end_time"])

        time_until_event = self.start_time - dt_util.utcnow()

        if timedelta(0) < time_until_event < timedelta(hours=4):

            # Set max battery charge rate for axle event

            number.set_value(entity_id=BATTERY_CHARGE_RATE_ENTITY, value=6000)

            # Set shelly off

            switch.turn_off(entity_id=SHELLY_ENTITY)

            start, end = self.find_start_end_times()
            self.set_charge_window(start, end)

        else:
            log.info("Outside 4 hours nothing executed")

    def find_start_end_times(self):
        """Work out a charge window ending 5 minutes before the event."""

        duration = self.end_time - self.start_time

        # Cap the charge duration at 2 hours, or the event duration if shorter
        max_charge_duration = timedelta(hours=2)
        charge_duration = min(duration, max_charge_duration)

        # Safety buffer, stop charging 5 mins before event starts
        safety_buffer = timedelta(minutes=5)

        # Charge window ends exactly when the event starts
        charge_window_end = self.start_time - safety_buffer
        charge_window_start = charge_window_end - charge_duration

        # Convert to local time for display / use in HA services
        charge_start_local = dt_util.as_local(charge_window_start)
        charge_end_local = dt_util.as_local(charge_window_end)

        # Format to HA friendly
        self.charge_start_hhmmss = charge_start_local.strftime("%H:%M:00")
        self.charge_end_hhmmss = charge_end_local.strftime("%H:%M:00")

        return self.charge_start_hhmmss, self.charge_end_hhmmss

    def set_charge_window(self, start, end):
        """Write the charge window start and end times to the inverter."""

        log.info(f"Charge window: {start} - {end}")

        # Set charge window

        select.select_option(entity_id=CHARGE_SLOT_START_ENTITY, option=start)
        select.select_option(entity_id=CHARGE_SLOT_END_ENTITY, option=end)

    @staticmethod
    def parse_iso(ts: str) -> datetime:
        """Convert an ISO 8601 timestamp string into a datetime."""
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))

    def get_response(self):
        """Fetch the current Axle event, or None if the request fails."""
        try:
            response = await self.async_get_event()
            return response
        except Exception as err:
            log.error(f"Failed to fetch Axle event: {err}")
            return


@time_trigger("cron(0 */1 * * *)")  # Every hour
def use_axle():
    """Check for Axle events every hour."""

    axle_api = AxleApi(AXLE_API_KEY)
    axle_api.run_axle()

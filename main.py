from battery_forecast import Forecaster
from daily_reset import DailyReseter
from time_change import TimeChange

battery_forecaster = Forecaster()
daily_reseter = DailyReseter()
time_changer = TimeChange()

DISCHARGE_START_2_ENTITY = "select.givtcp_<inverter_serial>_discharge_start_time_slot_2"
DISCHARGE_END_2_ENTITY = "select.givtcp_<inverter_serial>_discharge_end_time_slot_2"
DISCHARGE_MINIMUM_SOC_2_ENTITY = "number.givtcp_<inverter_serial>_discharge_target_soc_2"
HEAT_PUMP_OPMODE_ENTITY = "sensor.<your_heat_pump_opmode_sensor>"


@time_trigger("cron(0 21 * * *)")
def run_forecast():
    """Set tomorrow's battery charge target at 21:00."""
    battery_forecaster.apply_battery_forecast()

@time_trigger("cron(50 23 * * *)")
def daily_reset():
    """Reset the daily settings at 23:50."""
    daily_reseter.reset_settings()

@time_trigger("cron(0 6 * * *)")
def heat_pump_reset():
    """Lower the hot water target temperature at 06:00."""
    daily_reseter.set_daily_heat_pump()


# Should definitely catch the hour change and be changed before next
# charge window
@time_trigger("cron(55 23 * * *)")
def apply_time_change():
    """Adjust the overnight charge window for BST at 23:55."""
    time_changer.adjust_charge_slot_for_bst()


@time_trigger("cron(45 23 * * *)")
def check_split_discharge():
    """Set a second discharge window at 23:45 if it is needed."""
    if state.get(HEAT_PUMP_OPMODE_ENTITY) == "auto" and battery_forecaster.start_2 > 200:
        if time_changer.end_str is not None:
            select.select_option(entity_id=DISCHARGE_START_2_ENTITY, option=time_changer.end_str)
            select.select_option(entity_id=DISCHARGE_END_2_ENTITY, option="17:00:00")
            number.set_value(entity_id=DISCHARGE_MINIMUM_SOC_2_ENTITY, value=50)
        else:
            log.info("Split discharge not available")
    else:
        log.info("Split discharge not available")

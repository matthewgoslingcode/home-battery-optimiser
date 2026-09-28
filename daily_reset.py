BATTERY_CHARGE_RATE_ENTITY = "number.givtcp_<inverter_serial>_battery_charge_rate"
CHARGE_SLOT_START_ENTITY_2 = "select.givtcp_<inverter_serial>_charge_start_time_slot_2"
CHARGE_SLOT_END_ENTITY_2 = "select.givtcp_<inverter_serial>_charge_end_time_slot_2"

ECO_MODE_ENTITY = "switch.givtcp_<inverter_serial>_eco_mode"

# Enable AC charge upper %
ENABLE_CHARGE_TARGET_ENTITY = "switch.givtcp_<inverter_serial>_enable_charge_target"

# Enable DC discharge
ENABLE_DISCHARGE_SCHEDULE_ENTITY = "switch.givtcp_<inverter_serial>_enable_discharge_schedule"

# Background target SOC out of windows
TARGET_SOC_ENTITY = "number.givtcp_<inverter_serial>_target_soc"

# AC charge enable
ENABLE_CHARGE_SCHEDULE_ENTITY = "switch.givtcp_<inverter_serial>_enable_charge_schedule"

# Shelly switch for heat pump
SHELLY_ENTITY = "switch.<your_shelly_switch>"


class DailyReseter:
    def reset_settings(self):
        """Restore the inverter, Shelly and heat pump to daily defaults."""

        # Reset charge window 2
        select.select_option(entity_id=CHARGE_SLOT_START_ENTITY_2, option="00:00:00")
        select.select_option(entity_id=CHARGE_SLOT_END_ENTITY_2, option="00:00:00")

        # Reset battery charge rate
        number.set_value(entity_id=BATTERY_CHARGE_RATE_ENTITY, value=4449)

        # Reset shelly
        switch.turn_on(entity_id=SHELLY_ENTITY)

        # Daily switches post axle
        switch.turn_on(entity_id=ECO_MODE_ENTITY)
        switch.turn_on(entity_id=ENABLE_CHARGE_TARGET_ENTITY)
        switch.turn_on(entity_id=ENABLE_DISCHARGE_SCHEDULE_ENTITY)
        switch.turn_on(entity_id=ENABLE_CHARGE_SCHEDULE_ENTITY)

        # Background target SOC reset
        number.set_value(entity_id=TARGET_SOC_ENTITY, value=100)

        # Reset heat pump
        mqtt.publish(topic="ebusd/700/HwcTempDesired/set", payload="60", qos=1, retain=False)

    def set_daily_heat_pump(self):
        """Set the hot water target temperature to 50°C."""

        mqtt.publish(topic="ebusd/700/HwcTempDesired/set", payload="50", qos=1, retain=False)

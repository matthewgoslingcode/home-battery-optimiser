from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


class TimeChange:
    def __init__(self):
        """Set the desired charge window and the inverter entities."""

        # bst 3-6
        # gmt 2-5

        self.desired_start = time(2, 00)
        self.desired_end = time(5, 00)

        # Entities that control inverter's charge slot 1

        self.charge_slot_start_entity = "select.givtcp_<inverter_serial>_charge_start_time_slot_1"
        self.charge_slot_end_entity = "select.givtcp_<inverter_serial>_charge_end_time_slot_1"

        self.start_str = "00:00:00"
        self.end_str = "00:00:00"

    def is_currently_bst(self):
        """Return True if the UK is currently on British Summer Time."""
        # Returns True if UK is currently in British Summer Time
        # UTC is GMT
        tz = ZoneInfo("Europe/London")
        now_local = datetime.now(tz)
        # If one hour ahead of GMT/UTC then it is BST
        return now_local.utcoffset() == timedelta(hours=1)

    def shift_time(self, t, hours):
        """Return the time shifted by the given number of hours."""
        # Pass in a time and number of hours you want to shift the time by
        # Date is arbitrary, only hours and minutes are extracted from
        # datetime object
        dummy_date = datetime(2000, 1, 1, t.hour, t.minute)
        shifted = dummy_date + timedelta(hours=hours)
        return shifted.time()  # Just time, date is irrelevant

    def adjust_charge_slot_for_bst(self):
        """Set the overnight charge window, an hour later in BST."""

        try:
            bst_active = self.is_currently_bst()

            if bst_active:
                # Want 3-6 so plus one to desired time
                target_start = self.shift_time(self.desired_start, 1)
                target_end = self.shift_time(self.desired_end, 1)
            else:
                target_start = self.desired_start
                target_end = self.desired_end

            self.start_str = target_start.strftime("%H:%M:%S")
            self.end_str = target_end.strftime("%H:%M:%S")

            # set charge window 1

            select.select_option(entity_id=self.charge_slot_start_entity, option=self.start_str)
            select.select_option(entity_id=self.charge_slot_end_entity, option=self.end_str)

            log.info(
                f"BST check: BST={bst_active}. "
                f"Set charge slot to {self.start_str}-{self.end_str} "
                f"(desired local: {self.desired_start.strftime('%H:%M:%S')}-"
                f"{self.desired_end.strftime('%H:%M:%S')})"
            )

        except Exception as e:
            log.error(f"Failed to adjust charge slot for BST: {e}")
            persistent_notification.create(
                title="Charge Slot BST Adjustment FAILED", message=str(e)
            )

from enum import Enum

WRAP_LOW = 60 * 2000
WRAP_HIGH = 2**32 - 60 * 2000

TICKS_PER_SECOND = 25000


LOCATION_CSV_NAME = 'sensor-locations.csv'


class SensorStatus(Enum):
    GOOD = 0
    BAD = 1
    INACTIVE = 2


###
# Data Format:
#
# channel_id -> sample_value
##


class DataSource(object):
    def __init__(self, hardware_state):
        super().__init__()
        self.hardware_state = hardware_state
        self.is_streaming = False

    def set_developer_mode(self, developer_mode):
        self._developer_mode = developer_mode

    def _report_raw_cmd_resp(self, msg):
        pass

    def _report_data_available(self, data):
        pass

    def _report_data_underrun(self, samples, mem):
        pass

    def _report_sensor_status(self, status):
        pass

    def _report_update_progress(self, chassis_name, progress, msg_type, msg):
        pass

    def _report_chassis_status(self, chassis_name, status):
        pass

    def _report_sensor_status_changed(self):
        pass

    def _report_chassis_connection_change(self, chassis_id, changed):
        pass

    def _report_password_response(self, chassis_name, resp):
        pass

    def _report_closed_loop(self, is_closed):
        pass

    def _handle_chassis_connections(self, num, total):
        pass

    def _handle_chassis_disconnect(self, reason):
        pass

    def _handle_blink_state_changed(self, chassis_id, sensor_id, color, blink_state):
        pass

    def get_channel_names(self):
        return [ch.name for ch in self.get_channels()]

    def get_sensor_names(self):
        return [s.name for s in self.hardware_state.get_sensors()]

    def get_sensor_from_name(self, name):
        for s in self.hardware_state.get_sensors():
            if name == s.name:
                return s
        return None

    def get_sensors(self):
        return self.hardware_state.get_sensors()

    def get_sensor(self, chassis_id, sensor_id):
        return self.hardware_state.get_sensor(chassis_id, sensor_id)

    def get_sensors_dict(self):
        return self.hardware_state.get_sensors_dict()

    def get_sensors_good(self):
        sensor_status = []
        for s in self.hardware_state.get_sensors():
            if s.sensor_id == 0:
                continue  # Don't include chassis
            if not s.is_active():
                sensor_status.append(SensorStatus.INACTIVE)
            elif s.good():
                sensor_status.append(SensorStatus.GOOD)
            else:
                sensor_status.append(SensorStatus.BAD)
        return sensor_status

    def get_channels(self):
        return self.hardware_state.get_channels()

    def all_versions_equal(self):
        return True

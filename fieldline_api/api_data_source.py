import logging

from pycore.network_data_source import NetworkDataSource
import net_protocol_pb2 as proto
from .fieldline_datatype import FieldLineDataType, FieldLineSensorStatusType


class ApiDataSource(NetworkDataSource):
    def __init__(self, callback, interfaces, prefix, counter_lock, counter, hardware_state):
        self.callback = callback
        self.counter_lock = counter_lock
        self.counter = counter
        self.hardware_state = hardware_state
        super(ApiDataSource, self).__init__(interfaces, prefix, self.counter_lock, self.counter, self.hardware_state)
        self.t = None
        self.is_running = False
        self.chassis_mapping = {}
        self._zeroconf_name_to_chassis_name = {}
        self.services = {}
        self.waiting_on_sensors = []
        self.chassis_id_counter = 0
        self.sensor_status_dict = {}

    def connect_to_devices(self, ip_list):
        chassis_dict = {}
        for i, ip in enumerate(ip_list):
            chassis_name = "%s:7777" % ip
            chassis_dict[chassis_name] = i
        self.connect_chassis_list(chassis_dict)

    def get_sensor_state(self, chassis_id, sensor_id):
        for s in self.get_sensors():
            if s.chassis_id == chassis_id and s.sensor_id == sensor_id:
                if s.get_color() == 9 and s.get_blink_state() == 1:
                    return FieldLineSensorStatusType.SENSOR_READY
                if s.get_color() == 6 and s.get_blink_state() == 1:
                    return FieldLineSensorStatusType.SENSOR_FINE_ZEROED
                elif s.get_color() == 6 and s.get_blink_state() == 2:
                    return FieldLineSensorStatusType.SENSOR_FINE_ZEROING
                elif s.get_color() == 5 and s.get_blink_state() == 1:
                    return FieldLineSensorStatusType.SENSOR_COARSE_ZEROED
                elif s.get_color() == 5 and s.get_blink_state() == 2:
                    return FieldLineSensorStatusType.SENSOR_COARSE_ZEROING
                elif s.get_blink_state() == 2:
                    return FieldLineSensorStatusType.SENSOR_RESTARTING
                elif s.get_color() == 4 and s.get_blink_state() == 1:
                    return FieldLineSensorStatusType.SENSOR_RESTARTED
                elif s.get_blink_state == 4:
                    return FieldLineSensorStatusType.SENSOR_ERROR
        return None

    # Override
    def update_state(self, msg=None):
        logging.info("update_state called")
        super().update_state(msg)
        logging.info("chassis_name %s waiting %s" % (msg.chassis_name, self.waiting_on_sensors))
        if msg.type == proto.StatusPacket.SENSOR_STATUS and msg.chassis_name in self.waiting_on_sensors:
            self.waiting_on_sensors.remove(msg.chassis_name)
            msg_chassis_id = self.chassis_name_to_id[msg.chassis_name]
            sensor_list = []
            for s in self.get_sensors():
                if s.chassis_id == msg_chassis_id and s.present:
                    sensor_list.append(s.sensor_id)
            self.callback.callback_sensors_available(msg_chassis_id, sensor_list)
        elif msg.type == proto.StatusPacket.SENSOR_STATE:
            logging.info("SENSOR_STATE %s" % msg)
            for sc in msg.sensor_state:
                if msg.chassis_name in self.chassis_name_to_id:
                    chassis_id = self.chassis_name_to_id[msg.chassis_name]
                    if sc.state == proto.SensorState.RESTART:
                        self.callback.callback_restart_begin(chassis_id, sc.sensor_id)
                    elif sc.state == proto.SensorState.RESTART_COMPLETE:
                        self.callback.callback_restart_complete(chassis_id, sc.sensor_id)
                    elif sc.state == proto.SensorState.COARSE_ZERO:
                        self.callback.callback_coarse_zero_begin(chassis_id, sc.sensor_id)
                    elif sc.state == proto.SensorState.COARSE_ZERO_COMPLETE:
                        self.callback.callback_coarse_zero_complete(chassis_id, sc.sensor_id)
                    elif sc.state == proto.SensorState.FINE_ZERO:
                        self.callback.callback_fine_zero_begin(chassis_id, sc.sensor_id)
                    elif sc.state == proto.SensorState.FINE_ZERO_COMPLETE:
                        self.callback.callback_fine_zero_complete(chassis_id, sc.sensor_id)
                    elif sc.state == proto.SensorState.READY:
                        self.callback.callback_sensor_ready(chassis_id, sc.sensor_id)
                    elif sc.state == proto.SensorState.ERROR:
                        self.callback.callback_sensor_error(chassis_id, sc.sensor_id, "error")
                    elif sc.state == proto.SensorState.SOFT_ERROR:
                        self.callback.callback_sensor_error(chassis_id, sc.sensor_id, "soft error")

    def handle_chassis_added(self, chassis_name):
        if chassis_name in self.chassis_name_to_id:
            self.connect_chassis(chassis_name)

    # Override
    def handle_chassis_connected(self, chassis_name):
        logging.info("handle_chassis_connected %s" % chassis_name)
        self.update_chassis_connections()
        self.waiting_on_sensors.append(chassis_name)
        self.callback.callback_chassis_connected(chassis_name, self.chassis_name_to_id[chassis_name])

    # Override
    def handle_chassis_removed(self, chassis_name):
        logging.info("Chassis %s removed" % chassis_name)
        if chassis_name in self.chassis_name_to_id:
            self.callback.callback_chassis_disconnected(self.chassis_name_to_id[chassis_name])
            del self.chassis_name_to_id[chassis_name]

    def is_service_running(self):
        return self.is_running

    # Override
    def start(self):
        self.is_streaming = True
        super().start()

    # Override
    def stop(self):
        self.is_streaming = False
        super().stop()

    def start_datatype(self, chassis_id, sensor_list, datatype, freq=1000):
        self.configure_datatype(chassis_id, sensor_list, datatype, freq)

    def stop_datatype(self, chassis_id, sensor_list, datatype):
        self.configure_datatype(chassis_id, sensor_list, datatype, 0)

    def configure_datatype(self, chassis_id, sensor_list, datatype, freq=1000):
        channel_configs = {datatype: (freq, 1.0)}
        chassis_name = None
        for c_name, c_id in self.chassis_name_to_id.items():
            if c_id == chassis_id:
                chassis_name = c_name
                break
        if chassis_name is not None:
            for s in sensor_list:
                self.configure_sensor_list(chassis_name, s, channel_configs)

    def start_adc(self, chassis_id, freq=1000):
        self.configure_datatype(chassis_id, [0], 0, freq)

    def stop_adc(self, chassis_id):
        self.configure_datatype(chassis_id, [0], 0, 0)

    def _report_data_available(self, sample_list):
        self.callback.callback_data_available(sample_list)

    def _parse_frame_data(self, frame_data):
        out_data = {}
        for chassis_id, data_packet in frame_data.items():
            if chassis_id not in out_data:
                out_data[chassis_id] = []
            for data_frame in data_packet.data:
                datatype = data_frame.datatype
                sensor_id = data_frame.sensor
                dt = None
                if 28 == datatype:
                    dt = FieldLineDataType.DATA_BZ
                elif 35 == datatype:
                    dt = FieldLineDataType.DATA_BY
                elif 37 == datatype:
                    dt = FieldLineDataType.DATA_BX

                if dt is not None:
                    out_data[chassis_id].append((sensor_id, dt, data_frame.val))
        return out_data

    def _handle_blink_state_changed(self, chassis_id, sensor_id, color, blink_state):
        self.callback.callback_led_changed(chassis_id, sensor_id, color, blink_state)

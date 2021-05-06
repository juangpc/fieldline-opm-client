import os
import csv
from collections import defaultdict, OrderedDict
import logging
import math

from pycore.sensor import SensorInfo, ChannelInfo
from pycore import common


class HardwareState(object):
    def __init__(self, csv_path):
        super(HardwareState, self).__init__()
        self.csv_locations = self._load_csv_locations(csv_path)
        self._sensors = {}
        self.CHASSIS_SENSOR_NUM = common.MAX_SENSORS_PER_CHASSIS + 1
        self._channel_list = []  # list of all channels, used for performance improvments
        self._channel_dict = {}

    def clear(self):
        logging.info("Hardware state clear")
        self._sensors = {}
        self._channel_list = []  # list of all channels, used for performance improvments
        self._channel_dict = {}

    def add_chassis(self, chassis_id):
        if chassis_id not in self._sensors:
            logging.info(f"Adding chassis {chassis_id}")
            self._sensors[chassis_id] = [None] * self.CHASSIS_SENSOR_NUM

            for sensor_id in range(0, self.CHASSIS_SENSOR_NUM):
                self._add_new_sensor(chassis_id, sensor_id)

    def remove_chassis(self, chassis_id):
        if chassis_id in self._sensors:
            logging.info(f"Removing {chassis_id}")
            del self._sensors[chassis_id]
        self._update_channel_list()

    def has_active_channels(self, chassis_id):
        ret = False
        try:
            ret = any([x.is_active() for x in self._sensors[chassis_id]])
        except KeyError:
            pass
        return ret

    def get_sensor(self, chassis_id, sensor_id):
        if chassis_id not in self._sensors:
            return None

        if sensor_id >= len(self._sensors[chassis_id]):
            return None

        return self._sensors[chassis_id][sensor_id]

    def get_sensors(self):
        all_sensors = []
        s = OrderedDict(sorted(self._sensors.items()))
        for chassis_id, sensors in s.items():
            for s in sensors:
                if s:
                    all_sensors.append(s)
        return all_sensors

    def get_sensors_dict(self):
        sensor_dict = {}
        for chassis_id, sensors in self._sensors.items():
            for s in sensors:
                sensor_dict[(chassis_id, s.sensor_id)] = s
        return sensor_dict

    def get_channels(self):
        return self._channel_list

    def get_channel_dict(self):
        return self._channel_dict

    def _update_channel_list(self):
        channels = []
        for s in self.get_sensors():
            channels += s.get_channels()
        self._channel_list = channels
        self._channel_dict = {}

        for i, c in enumerate(self._channel_list):
            self._channel_dict[c.name] = {'calibration': c.calibration, 'idx': i}

    def get_channel_by_name(self, channel_name):
        for c in self.get_channels():
            if c.name == channel_name:
                return c
        return None

    def get_channels_by_chassis_id(self, chassis_id):
        channels = []
        if chassis_id in self._sensors:
            for s in self._sensors[chassis_id]:
                channels += s.get_channels()
        return channels

    def configure_channel_list(self, chassis_id, channel_list):
        remove_list = self.get_channels_by_chassis_id(chassis_id)
        new_list = []
        existing_list = []
        for ch in channel_list:
            found = False
            for i, r in enumerate(remove_list):
                if chassis_id == r.chassis_id and ch['sensor_id'] == r.sensor_id and ch['data_type'] == int(r.data_type):
                    del remove_list[i]
                    found = True
                    break
            if not found:
                new_list.append(ch)
            else:
                existing_list.append(ch)
        for r in remove_list:
            logging.info("configure_channel_list remove chassis: %d sensor: %d datatype: %s" % (r.chassis_id, r.sensor_id, r.data_type))
            ret = self.remove_channel(r.chassis_id, r.sensor_id, r.data_type)
            self._handle_channel_changed(ret)
        for n in new_list:
            logging.info("configure_channel_list add chassis: %d sensor: %d datatype: %d" % (n['chassis_id'], n['sensor_id'], n['data_type']))
            ret = self.add_channel(**n)
            self._handle_channel_changed(ret)
        for e in existing_list:
            self.update_channel_calibration(**e)
        self._update_channel_list()

    def add_channel(self, chassis_id, sensor_id, data_type, frequency, calibration):
        sensor_info = self.get_sensor(chassis_id, sensor_id)
        data_type_name = str(data_type)
        if sensor_id == 0 and data_type == 0:
            calibration = float(5 / (2 ** 24))
        new_channel = ChannelInfo(
            chassis_id=chassis_id,
            sensor_id=sensor_id,
            data_type=data_type_name,
            sample_freq=frequency,
            ch_type='mag',
            calibration=calibration)
        sensor_info.add_channel(new_channel)
        channel_data = new_channel.data()
        return channel_data

    def remove_channel(self, chassis_id, sensor_id, data_type):
        sensor_info = self.get_sensor(chassis_id, sensor_id)
        channel_data = {
            'name': sensor_info.get_channel_name(data_type),
            'sensor': sensor_info.name,
            'sample_freq': 0
        }
        sensor_info.remove_data_type(data_type)
        return channel_data

    def update_channel_calibration(self, chassis_id, sensor_id, data_type, frequency, calibration):
        sensor_info = self.get_sensor(chassis_id, sensor_id)
        channel = sensor_info.update_channel_calibration(data_type, calibration)
        channel_data = channel.data()
        return channel_data

    def configure_channel(self, chassis_id, sensor_id, data_type, frequency, calibration):
        sensor_info = self.get_sensor(chassis_id, sensor_id)
        if sensor_info is None:
            logging.error(f"Sensor {chassis_id}:{sensor_id} does not exist")
            return
        if frequency != 0:
            channel_data = self.add_channel(chassis_id, sensor_id, data_type, frequency, calibration)
        else:
            channel_data = self.remove_channel(chassis_id, sensor_id, data_type)
        self._handle_channel_changed(channel_data)
        self._update_channel_list()

    def _handle_channel_changed(self, channel_data):
        pass

    def _add_new_sensor(self, chassis_id, sensor_id):
        if sensor_id != 0:
            try:
                loc = self.csv_locations[str(chassis_id)][str(sensor_id)]
            except KeyError:
                loc = (2 * ((sensor_id - 1) % 4) - 3,
                       2 * (math.floor((16 - sensor_id) / 4)) - 3,
                       4 - (2 * chassis_id),
                       0, 0, 0, 0, 0, 0, 0, 0, 0)
                logging.debug("Sensor_id %d on chassis %d not found in CSV, assigning a default location" % (sensor_id, chassis_id))
        else:
            loc = (0, 0, 0)

        sensor = self._sensors[chassis_id][sensor_id]
        if not sensor:
            sensor_name = "%02d:%02d" % (chassis_id, sensor_id)
            sensor = SensorInfo(name=sensor_name,
                                chassis_id=chassis_id,
                                sensor_id=sensor_id,
                                location=loc
                                )
        else:
            if not sensor.is_location_equal(loc):
                sensor.set_location(loc)

        self._sensors[chassis_id][sensor_id] = sensor

    def _load_csv_locations(self, path):
        # The CSV should have these 14 columns:
        # chassis_num,sensor_num,x,y,z,b1x,b1y,b1z,b2x,b2y,b2z,b3x,b3y,b3z
        csv_locations = defaultdict(dict)
        if os.path.exists(path):
            logging.info("Using sensor location CSV file: %s" % path)
            with open(path) as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    csv_locations[row['chassis_num']][row['sensor_num']] = (
                        float(row['x']), float(row['y']), float(row['z']),
                        float(row['b1x']), float(row['b1y']), float(row['b1z']),
                        float(row['b2x']), float(row['b2y']), float(row['b2z']),
                        float(row['b3x']), float(row['b3y']), float(row['b3z']))
        # else:
        #     logging.warning("CSV location file not found at %s" % path)
        return csv_locations

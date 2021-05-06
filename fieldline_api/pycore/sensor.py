import numpy as np
import logging
import time


DATA_WINDOW_SEC = 3


class SensorInfo:
    def __init__(self, name, location, chassis_id=None, sensor_id=None):
        self.name = name
        self.chassis_id = chassis_id
        self.sensor_id = sensor_id
        self.channels = {}
        self.color = 0
        self.blink_state = 0
        self.set_location(location)
        self.last_data_time = 0  # Epoch
        self.selected = False
        self.present = False
        self.fields = [0.0, 0.0, 0.0]
        self.zerod = False
        self.card_serial = None
        self.sensor_serial = None

    def __del__(self):
        for c in self.channels:
            del c

    def set_present(self, p):
        self.present = p

    def add_channel(self, channel):
        logging.info("Adding channel %s at freq %d" % (channel.name, channel.sample_freq))
        if channel.sample_freq == 0:
            logging.info("Channel has a sample frequency of 0 Hz, not adding to sensor")
            if channel.name in self.channels:
                del self.channels[channel.name]
        if channel.name in self.channels:
            channel.set_plotting(self.channels[channel.name].get_plotting())
        self.channels[channel.name] = channel
        channel.location = self.location

    def get_channel_names(self):
        return list(self.channels.keys())

    def get_channels(self):
        return list(self.channels.values())

    def is_location_equal(self, loc):
        if len(loc) == 3:
            loc = np.array(list(loc) + [0] * 9)
        else:
            loc = np.array(loc)
        return np.array_equal(self.location, loc)

    def set_plotting(self, plotting):
        logging.info(f"set_plotting {self.sensor_id}: {plotting}")
        for channel in self.channels.values():
            channel.set_plotting(plotting)

    def get_plotting(self):
        return any([c.get_plotting() for c in self.channels.values()])

    def set_color(self, color):
        self.color = color

    def get_color(self):
        return self.color

    def set_blink_state(self, blink):
        self.blink_state = blink

    def get_blink_state(self):
        return self.blink_state

    def set_fields(self, x, y, z):
        self.fields = [x, y, z]

    def set_location(self, location):
        if len(location) == 3:
            self.location = np.array(list(location) + [0] * 9)
        else:
            self.location = np.array(location)

    def remove_channel(self, channel_name):
        if channel_name not in self.channels:
            logging.error(f"Tried to remove channel {channel_name}, does not belong this sensor {self.channels}")
            return
        logging.info("removing channel %s " % channel_name)
        del self.channels[channel_name]

    def remove_data_type(self, data_type):
        channel_name = self.get_channel_name(data_type)
        self.remove_channel(channel_name)

    def update_channel_calibration(self, data_type, calibration):
        channel_name = self.get_channel_name(data_type)
        channel = None
        if channel_name in self.channels:
            channel = self.channels[channel_name]
            channel.calibration = calibration
        return channel

    def get_channel_name(self, data_type):
        return "%s:%s" % (self.name, data_type)

    def add_data_point(self, channel, value):
        self.last_data_time = time.time()
        if channel not in self.channels:
            logging.warn(f"{self.name} received data ({channel}) that I shouldn't have")

    def is_active(self):
        return (len(self.channels) > 0)

    def good(self):
        if not self.is_active():
            # No active channels
            return True
        else:
            if (time.time() - self.last_data_time) > DATA_WINDOW_SEC:
                # Have not recieved data from a the sensor in DATA_WINDOW_SEC
                return False
            return True

    def set_selected(self, select):
        self.selected = select

    def get_selected(self):
        return self.selected

    @property
    def is_chassis(self):
        return self.sensor_id == 0


class ChannelInfo:
    def __init__(self, sample_freq, ch_type, name=None, chassis_id=None, sensor_id=None, data_type=None, location=None, calibration=1.0):
        self.sample_freq = sample_freq
        self.ch_type = ch_type
        self.chassis_id = chassis_id
        self.sensor_id = sensor_id
        self.data_type = data_type
        self.calibration = calibration
        self._plotting = False
        self.s_name = None
        if location is not None:
            if len(location) == 3:
                self.location = np.array(list(location) + [0] * 9)
            else:
                self.location = np.array(location)

        if name is not None:
            self.name = name
        elif self.sensor_id is not None and self.chassis_id is not None:
            self.name = self.sensor_name + ":%s" % self.data_type
        else:
            self.name = None

    @property
    def sensor_name(self):
        if self.s_name:
            return self.s_name
        else:
            return "%02d:%02d" % (self.chassis_id, self.sensor_id)

    @sensor_name.setter
    def sensor_name(self, val):
        self.s_name = val

    @property
    def data_index(self):
        return self.data_type

    def get_plotting(self):
        return self._plotting

    def set_plotting(self, plotting):
        self._plotting = plotting

    def data(self):
        return {
            'name': self.name,
            'sensor': self.sensor_name,
            'sample_freq': self.sample_freq
        }

import threading
import logging
import netifaces

from .api_data_source import ApiDataSource
from pycore.hardware_state import HardwareState
from .fieldline_datatype import FieldLineWaveType
import net_protocol_pb2 as proto


class FieldLineService:
    def __init__(self, callback=None, prefix=""):
        """
            callback - required callback class
                       should be of type FieldLineCallback
        """
        self.counter_lock = threading.Lock()
        self.counter = []
        self.counter.append(0)
        self.hardware_state = HardwareState("")
        logging.info("Initializing FieldLine Service")
        self.callback = callback
        self.prefix = prefix
        self.data_source = None
        interfaces = netifaces.interfaces()
        self.network_interfaces = []
        for i in interfaces:
            logging.info("interface %s" % i)
            if i.startswith('lo'):
                continue
            iface = netifaces.ifaddresses(i).get(netifaces.AF_INET)
            if iface is not None:
                for j in iface:
                    ip_addr = j['addr']
                    logging.info("address %s" % ip_addr)
                    self.network_interfaces.append(ip_addr)
        logging.info("network interfaces: %s" % self.network_interfaces)
        self.is_running = False

    def start(self):
        """Start FieldLine service and begin checking for chassis."""
        logging.info("Starting FieldLine Service")
        self.is_running = True
        self.data_source = ApiDataSource(self.callback, self.network_interfaces, self.prefix, self.counter_lock, self.counter, self.hardware_state)
        self.data_source.start_monitor()

    def stop(self):
        """Stop FieldLine service and stop checking for chassis."""
        print("Stopping FieldLine Service")
        self.is_running = False
        self.data_source.shutdown(block=True)
        self.data_source = None

    def connect(self, ip_list):
        self.data_source.connect_to_devices(ip_list)

    def get_chassis_list(self):
        return self.data_source.get_chassis_list()

    def is_service_running(self):
        """Returns True if service is running, False if not"""
        return self.is_running

    def start_bz(self, chassis_id, sensor_list):
        """
            Start streaming BZ data

            chassis_id - unique ID of chassis
            sensor_list - list of sensors to start data
        """
        self.data_source.start_datatype(chassis_id, sensor_list, 28)

    def stop_bz(self, chassis_id, sensor_list):
        """
            Stop streaming BZ data

            chassis_id - unique ID of chassis
            sensor_list - lost of sensors to stop data
        """
        self.data_source.stop_datatype(chassis_id, sensor_list, 28)

    def start_adc(self, chassis_id):
        """
            Start ADC from chassis

            chassis_id - unique ID of chassis
        """
        self.data_source.start_adc(chassis_id)

    def stop_adc(self, chassis_id):
        """
            Stop ADC from chassis

            chassis_id - unique ID of chassis
        """
        self.data_source.stop_adc(chassis_id)

    def start_data(self):
        """
            Begin streaming data through API
        """
        self.data_source.start()

    def stop_data(self):
        """
            Stop streaming data through API
        """
        self.data_source.stop()

    def turn_off_sensor(self, chassis_id, sensor_id):
        """
            Turn off sensor
            Note: can be performed anytime

            chassis_id - unique ID of chassis
            sensor_id - ID of sensor
        """
        self.data_source.send_logic_command([(chassis_id, sensor_id, proto.LogicMessage.LOGIC_SENSOR_OFF), ])

    def restart_sensor(self, chassis_id, sensor_id):
        """
            Restart the sensor
            Note: can be performed anytime

            chassis_id - unique ID of chassis
            sensor_id - ID of sensor
        """
        self.data_source.send_logic_command([(chassis_id, sensor_id, proto.LogicMessage.LOGIC_SENSOR_RESTART), ])

    def coarse_zero_sensor(self, chassis_id, sensor_id):
        """
            Coarse zero sensor
            Note: can only be performed after restart is complete

            chassis_id - unique ID of chassis
            sensor_id - unique ID of sensor
        """
        self.data_source.send_logic_command([(chassis_id, sensor_id, proto.LogicMessage.LOGIC_SENSOR_COARSE_ZERO), ])

    def fine_zero_sensor(self, chassis_id, sensor_id):
        """
            Fine zero sensor
            Note: can only be performed after coarse zero is complete

            chassis_id - unique ID of chassis
            sensor_id - unique ID of sensor
        """
        self.data_source.send_logic_command([(chassis_id, sensor_id, proto.LogicMessage.LOGIC_SENSOR_FINE_ZERO), ])

    def set_bz_wave(self, chassis_id, sensor_id, wave_type, freq=None, amplitude=None):
        """
            Apply a known magnetic field to the BZ coil (e.g. sine wave)

            chassis_id - unique ID of chassis
            sensor_id - unique ID of sensor
            wave_type - FieldLineWaveType (WAVE_OFF, WAVE_RAMP, WAVE_SINE)
            freq - frequency of wave
            amplitude - amplitude of wave (nT)
        """
        if wave_type == FieldLineWaveType.WAVE_OFF:
            self.data_source.set_wave_off(chassis_id, sensor_id)
        elif wave_type == FieldLineWaveType.WAVE_RAMP:
            self.data_source.set_wave_ramp(chassis_id, sensor_id, freq, amplitude)
        elif wave_type == FieldLineWaveType.WAVE_SINE:
            self.data_source.set_wave_sine(chassis_id, sensor_id, freq, amplitude)

    def set_closed_loop(self, enable):
        """
            Turn closed loop on or off

            enable - True or False for on or off
        """
        self.data_source.set_closed_loop(enable)

    def get_fields(self, chassis_id, sensor_id):
        """
            Get the fields for a sensor

            chassis_id - unique ID of chassis
            sensor_id - unique ID of sensor
        """
        for s in self.data_source.get_sensors():
            if s.chassis_id == chassis_id and s.sensor_id == sensor_id:
                return s.fields
        return None

    def get_serial_numbers(self, chassis_id, sensor_id):
        """
            Get the card and sensor serial number for a sensor

            chassis_id - unique ID of chassis
            sensor_id - unique ID of sensor
        """
        for s in self.data_source.get_sensors():
            if s.chassis_id == chassis_id and s.sensor_id == sensor_id:
                return (s.card_serial,s.sensor_serial)

    def get_version(self, chassis_id):
        """
            Get the build version

            chassis_id - unique ID of chassis
        """
        return self.data_source.get_chassis_version(chassis_id)

    def get_sensor_state(self, chassis_id, sensor_id):
        """
            Get the current state of the sensor

            chassis_id - unique ID of chassis
            sensor_id  - ID of sensor
        """
        return self.data_source.get_sensor_state(chassis_id, sensor_id)

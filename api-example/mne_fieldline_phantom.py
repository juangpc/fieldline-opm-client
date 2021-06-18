import queue

import mne_fieldline_config as config

class PhantomConnector:

    def __init__(self):
        self.new_sensors = {}
        self.sensors_ready = {}
        self.restarted_sensors = {}
        self.coarse_zero_sensors = {}
        self.fine_zero_sensors = {}
        self.chassis_id_to_name = {}
        self.all_sensors_list = []
        self.valid_sensors_list = []
        self.data_q = queue.Queue()

        self.moc_sensor_list = config.working_sensors
        self.moc_chassis_ip_list = []
        self.moc_sensors = {}

class PhantomService:

        def __init__(self, connector, prefix):
            self.connector = connector
            self.prefix = prefix
            self.is_running = False

        def turn_off_sensors(self, chassis, sensor):
            pass

        def is_service_running(self):
            return self.is_running

        def start(self):
            self.is_running = True

        def stop(self):
            self.is_running = False

        def restart_sensor(self, chassis, sensor):
            pass

        def coarse_zero_sensor(self, chassis, sensor):
            pass

        def fine_zero_sensor(self, chassis, sensor):
            pass

        def start_data(self):
            pass

        def stop_data(self):
            pass

        def connect(self, chassis_ip_list):
            self.connector.moc_chassis_ip_list = chassis_ip_list
            index_list = []
            i = 0
            for ip in chassis_ip_list:
                index_list.append(i)
                i += 1
            self.moc_sensors = dict(zip(index_list, self.connector.moc_sensor_list))
        
        def get_sensor_state(self, chassis, sensor):
            pass

        def get_version(self, chassis):
            pass

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

class PhantomService:

        def __init__(self, connector, prefix):
        self.connector = connector
        self.prefix = prefix

        def turn_off_sensors(chassis, sensor):
            pass

        def is_service_running():
            pass

        def start():
            pass

        def stop():
            pass

        def restart_sensor(chassis, sensor):
            pass

        def coarse_zero_sensor(chassis, sensor):
            pass

        def fine_zero_sensor(chassis, sensor):
            pass

        def start_data():
            pass

        def stop_data():
            pass

        def connect(chassis_ip_list):
            pass
        
        def get_sensor_state(chassis, sensor):
            pass

        def get_version(chassis):
            pass


            



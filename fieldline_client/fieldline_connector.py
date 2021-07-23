import sys
from fieldline_api.fieldline_callback import FieldLineCallback


class FieldLineConnector(FieldLineCallback):
    def __init__(self):
        super().__init__()
        # custom below
        self.new_sensors = {}
        self.sensors_ready = {}
        self.restarted_sensors = {}
        self.coarse_zero_sensors = {}
        self.fine_zero_sensors = {}
        self.chassis_id_to_name = {}
        self.all_sensors_list = []
        self.valid_sensors_list = []

    # required callback
    def callback_chassis_connected(self, chassis_name, chassis_id):
        self.chassis_id_to_name[chassis_id] = chassis_name
        print(f"CONNECTOR Chassis {chassis_name} with ID {chassis_id} connected")
        sys.stdout.flush()

    # required callback
    def callback_chassis_disconnected(self, chassis_id):
        print(f"CONNECTOR Chassis {self.chassis_id_to_name[chassis_id]} disconnected")
        sys.stdout.flush()
        del self.chassis_id_to_name[chassis_id]

    # required callback
    def callback_sensors_available(self, chassis_id, sensor_list):
        print(f"CONNECTOR Chassis {self.chassis_id_to_name[chassis_id]} has sensors {sensor_list}")
        sys.stdout.flush()
        # self.new_sensors[chassis_id] = [[s, False] for s in sensor_list]
        self.sensors_ready[chassis_id] = sensor_list
        for s in sensor_list:
            if s not in self.all_sensors_list:
                self.all_sensors_list.append((chassis_id, s))

    # required callback
    def callback_sensor_ready(self, chassis_id, sensor_id):
        print(f"CONNECTOR Chassis {self.chassis_id_to_name[chassis_id]} sensor {sensor_id} ready")
        sys.stdout.flush()
        for s in self.new_sensors[chassis_id]:
            if s[0] == sensor_id:
                s[1] = True
        if False not in [s[1] for s in self.new_sensors[chassis_id]]:
            self.sensors_ready[chassis_id] = [s2[0] for s2 in self.new_sensors[chassis_id]]
            del self.new_sensors[chassis_id]

    # required callback
    def callback_restart_begin(self, chassis_id, sensor_id):
        print(f"CONNECTOR Chassis {self.chassis_id_to_name[chassis_id]} sensor {sensor_id} restart")
        sys.stdout.flush()

    # required callback
    def callback_restart_complete(self, chassis_id, sensor_id):
        print(f"CONNECTOR Chassis {self.chassis_id_to_name[chassis_id]} sensor {sensor_id} restart complete")
        sys.stdout.flush()
        if chassis_id not in self.restarted_sensors:
            self.restarted_sensors[chassis_id] = []
        self.restarted_sensors[chassis_id].append(sensor_id)

    # required_callback
    def callback_coarse_zero_begin(self, chassis_id, sensor_id):
        print(f"CONNECTOR Chassis {self.chassis_id_to_name[chassis_id]} sensor {sensor_id} coarse zero")
        sys.stdout.flush()

    # required callback
    def callback_coarse_zero_complete(self, chassis_id, sensor_id):
        print(f"CONNECTOR Chassis {self.chassis_id_to_name[chassis_id]} sensor {sensor_id} coarse zero complete")
        sys.stdout.flush()
        if chassis_id not in self.coarse_zero_sensors:
            self.coarse_zero_sensors[chassis_id] = []
        self.coarse_zero_sensors[chassis_id].append(sensor_id)

    # required_callback
    def callback_fine_zero_begin(self, chassis_id, sensor_id):
        print(f"CONNECTOR Chassis {self.chassis_id_to_name[chassis_id]} sensor {sensor_id} fine zero")
        sys.stdout.flush()

    # required_callback
    def callback_fine_zero_complete(self, chassis_id, sensor_id):
        print(f"CONNECTOR Chassis {self.chassis_id_to_name[chassis_id]} sensor {sensor_id} fine zero complete")
        sys.stdout.flush()
        if chassis_id not in self.fine_zero_sensors:
            self.fine_zero_sensors[chassis_id] = []
        self.fine_zero_sensors[chassis_id].append(sensor_id)

    # required callback
    def callback_sensor_error(self, chassis_id, sensor, msg):
        print(f"CONNECTOR Chassis {self.chassis_id_to_name[chassis_id]} sensor {sensor} returned error: {msg}")
        for i, s in enumerate(self.valid_sensors_list):
            if s[0] == chassis_id and s[1] == sensor:
                del self.valid_sensors_list[i]
                break


    # custom functions below
    def has_new_sensors(self):
        return len(self.new_sensors.keys()) > 0

    def get_new_sensors(self):
        ret = self.new_sensors
        self.new_sensors = {}
        return ret

    def set_all_sensors_valid(self):
        self.valid_sensors_list = self.all_sensors_list

    def has_sensors_ready(self):
        return len(self.sensors_ready.keys()) > 0

    def get_sensors_ready(self):
        ret = self.sensors_ready
        self.sensors_ready = {}
        return ret

    def has_restarted_sensors(self):
        return len(self.restarted_sensors.keys()) > 0

    def get_restarted_sensors(self):
        ret = self.restarted_sensors
        self.restarted_sensors = {}
        return ret

    def get_num_restarted_sensors(self):
        return sum([len(s) for s in self.restarted_sensors.values()])

    def has_coarse_zero_sensors(self):
        return len(self.coarse_zero_sensors.keys()) > 0

    def get_coarse_zero_sensors(self):
        ret = self.coarse_zero_sensors
        self.coarse_zero_sensors = {}
        return ret

    def get_num_coarse_zero_sensors(self):
        return sum([len(s) for s in self.coarse_zero_sensors.values()])

    def has_fine_zero_sensors(self):
        return len(self.fine_zero_sensors.keys()) > 0

    def get_fine_zero_sensors(self):
        ret = self.fine_zero_sensors
        self.fine_zero_sensors = {}
        return ret

    def get_num_fine_zero_sensors(self):
        return sum([len(s) for s in self.fine_zero_sensors.values()])

    def num_sensors(self):
        return len(self.all_sensors_list)

    def num_valid_sensors(self):
        return len(self.valid_sensors_list)

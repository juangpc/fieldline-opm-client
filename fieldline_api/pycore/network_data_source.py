import threading
import zeroconf as zc
import socket
from collections import defaultdict
import logging
import json
from multiprocessing import Queue, Event
import queue
import time
import random

from pycore.interprocess_data import InterprocessDataPacketQueue
from pycore.data_source import DataSource
from pycore.network_client import NetworkClient
# import pycore.net_protocol_pb2 as proto
import net_protocol_pb2 as proto
from pycore import common


def recursive_defaultdict():
    """
    defaultdict that supports an arbitrary number of levels
    """
    return defaultdict(recursive_defaultdict)


class NetworkDataSource(DataSource):
    PORT = 7777
    def __init__(self, interfaces, zeroconf_prefix, counter_lock, counter, hardware_state, developer_mode=False):
        DataSource.__init__(self, hardware_state)
        self.counter_lock = counter_lock
        self.counter = counter
        self.interfaces = interfaces
        self.zeroconf_prefix = zeroconf_prefix
        self.zeroconf = None
        self.shutting_down = False
        self.services = {}
        self.services_lock = threading.RLock()
        self.last_timestamp = None
        self.sensor_config = recursive_defaultdict()
        self.status_msgs = {}
        self._zeroconf_name_to_chassis_name = {}
        self._chassis_name_to_zeroconf_name = {}
        self.chassis_name_to_id = {}
        self.last_connected = common.read_chassis_config()
        self.streaming_sources = {}
        self.closed_loop_enabled = False
        self.closed_loop_expected = False

        self.frame_q_lock = threading.Lock()
        self.RESET_THRESH = 1000
        self.SYNC_THRESH = 100
        self.reset_frame_buffer()
        self.frame_buffer = {}
        self.max_frame_buffer_size = 100

        self.discovered_devices = {}
        self.available_devices = {}
        self.non_multi_devices = {}
        self.expect_device_reboot = {}
        self.update_chassis_version = {}
        self.num_expected_devices = 0
        self.prev_num_expected = 0
        self.startup_complete = False
        self.reconnect_list = []
        self.previously_connected = []
        self.waiting_on_reconnects = False
        self.manual_ips = common.get_user_pref('ip_list', [])
        self.update_connections = False

        self._developer_mode = developer_mode
        self._developer_mode_password = None
        self.stream_thread = None

    def __del__(self):
        self.shutdown(True)

    def reset_frame_buffer(self):
        with self.frame_q_lock:
            self.frame_q = {}
            self.frames_syncd = False
            self.no_sync = True
            self.last_frame = 0
            self.frames_expected_dict = {}
            self.frame_reset_pending = False
            self.frame_delta = None
            self.sync_active = {}
            self.last_ts = {}
            self.log_sync_error = True

    def restart_zeroconf(self):
        if self.zeroconf:
            logging.info("Stopping zeroconf")
            self.zeroconf.close()
            self.zeroconf = None
        logging.info("Starting zeroconf")
        self._zeroconf_name_to_chassis_name = {}
        self.zeroconf = zc.Zeroconf(self.interfaces)
        self.browser = zc.ServiceBrowser(self.zeroconf, "_http._tcp.local.",
                                         handlers=[self.on_zeroconf_service_state_change])

    def set_developer_mode(self, value):
        super(NetworkDataSource, self).set_developer_mode(value)
        if value:
            self.send_sensor_config_req()
        else:
            self.disable_chassis_developer_mode()

    def is_datatype_valid(self, sensor, data_type):
        if self._developer_mode:
            return True
        else:
            if sensor == 0:
                return data_type in common.CHASSIS_ACTIVE_REGISTERS.values()
            else:
                return data_type in common.ACTIVE_REGISTERS.values()

    def update_expected_chassis(self, chassis_name_to_id):
        self.last_connected = {}
        self.chassis_name_to_id = chassis_name_to_id
        for chassis_name, chassis_id in chassis_name_to_id.items():
            self.set_chassis_id(chassis_name, chassis_id)
        self.update_chassis_connections()

    def is_chassis_expected(self, chassis_name):
        return chassis_name in self.chassis_name_to_id

    def is_config_mismatch(self):
        with self.services_lock:
            total = []
            for chassis_name, svc in self.services.items():
                if svc.is_connected and chassis_name in self.discovered_devices:
                    total.append(self.discovered_devices[chassis_name]['total'])
            totals_match = all([t == self.num_expected_devices for t in total])
            ret = len(total) != self.num_expected_devices or not totals_match
            logging.info("config_mismatch totals: %s num_expected: %d ret: %s" % (total, self.num_expected_devices, ret))
            return ret

    def startup(self, cb=None):
        self.chassis_name_to_id = self.last_connected
        self.num_expected_devices = len(self.last_connected)
        self.prev_num_expected = self.num_expected_devices
        all_connected = True
        for name, chassis_id in self.last_connected.items():
            c = name.split(":")
            if cb:
                cb(f"Attempting connection to {c[0]}")
            connected = self.connect_req(c[0], int(c[1]))
            if not connected:
                all_connected = False
        if all_connected:
            for name, chassis_id in self.last_connected.items():
                c = name.split(":")
                if cb:
                    cb(f"Connecting to {c[0]}")
                self.connect_chassis(name)
                self.hardware_state.add_chassis(chassis_id)
        else:
            logging.info("Failure to connect to all previously connected devices")
        for name in self.manual_ips:
            device_name = "%s:%d" % (name, NetworkDataSource.PORT)
            if device_name not in self.available_devices:
                if cb:
                    cb(f"Attempting connection to {name}")
                self.connect_req(name, NetworkDataSource.PORT)
        startup_error = False
        for name, chassis_id in self.last_connected.items():
            if name not in self.discovered_devices or self.discovered_devices[name]['total'] != self.num_expected_devices:
                startup_error = True
        self.startup_complete = True
        if startup_error:
            if cb:
                cb(f"Connection failures, resuming startup")
            self.stop_services()
            # self.report_error("Startup config error")

    def start_monitor(self):
        self.monitor_thread = threading.Thread(target=self._monitor_thread)
        self.monitor_thread.start()
        self.restart_zeroconf()

    def get_chassis_names(self):
        return list(self.chassis_name_to_id.keys())

    def get_chassis_name_from_id(self, c_id):
        for name, chassis_id in self.chassis_name_to_id.items():
            if chassis_id == c_id:
                return name
        return None

    def get_chassis_list(self):
        ret = []
        for ch in self.discovered_devices.keys():
            sp = ch.split(":")
            ret.append(sp[0])
        return ret

    @property
    def active_services(self):
        active_services = {}
        with self.services_lock:
            for chassis_name, v in self.services.items():
                if self.is_chassis_expected(chassis_name):
                    active_services[chassis_name] = v
        return active_services

    def get_available_device_info(self):
        available_devices = {}
        logging.info("AVAILBLE %s" % self.available_devices)
        with self.services_lock:
            for chassis_name in self.available_devices.keys():
                if chassis_name in self.services:
                    if self.services[chassis_name].is_connected:
                        available_devices[chassis_name] = self.discovered_devices[chassis_name]
                elif chassis_name in self.discovered_devices:
                    available_devices[chassis_name] = self.discovered_devices[chassis_name]
                if chassis_name in available_devices:
                    available_devices[chassis_name]['address'] = self.available_devices[chassis_name]['address']
                    available_devices[chassis_name]['port'] = self.available_devices[chassis_name]['port']
        return available_devices

    def disable_channel(self, chassis, sensor, data_type):
        logging.info("Disabling sensor %s %s %s" % (chassis, sensor, data_type))
        self.configure_sensor(chassis, sensor, data_type, 0)

    def configure_sensor(self, chassis, sensor, data_type, frequency, calibration=1.0):
        logging.info(f"Sensor configured: chassis={chassis} sensor={sensor}, data_type={data_type}, frequency={frequency} hz, calibration={calibration}")
        if not self.is_datatype_valid(sensor, int(data_type)):
            logging.warn(f"Data {data_type} is not valid")
            return
        self.sensor_config[chassis][sensor][data_type] = frequency
        chassis_id = self.chassis_name_to_id[chassis]
        active_before = self.hardware_state.has_active_channels(chassis_id)
        self.hardware_state.configure_channel(
            chassis_id,
            sensor,
            data_type,
            frequency,
            calibration
        )
        active_after = self.hardware_state.has_active_channels(chassis_id)
        if self.is_streaming and active_before == False and active_after == True:
            with self.services_lock:
                self.services[chassis].start_streaming()
        elif active_before == True and active_after == False:
            with self.services_lock:
                self.services[chassis].stop_streaming()
            with self.frame_q_lock:
                if chassis_id in self.frame_q:
                    logging.info("Chassis %d no longer has channels, removing from frame q" % chassis_id)
                    del self.frame_q[chassis_id]

    def configure_sensor_list(self, chassis, sensor, channel_configs):
        channel_list = []
        for data_type, config in channel_configs.items():
            frequency, calibration = config
            self.configure_sensor(
                chassis=chassis,
                sensor=int(sensor),
                data_type=data_type,
                frequency=frequency,
                calibration=calibration
            )
            channel_list.append((int(sensor), data_type, frequency))
        chassis_id = self.chassis_name_to_id[chassis]
        sensor_name = "%02d:%02d" % (int(chassis_id), int(sensor))
        sensor_obj = self.get_sensor_from_name(sensor_name)

        for channel in sensor_obj.get_channels():
            if int(channel.data_index) not in channel_configs.keys():
                logging.info("NOT IN KEYS %s %s" % (channel.data_index, channel_configs.keys()))
                self.disable_channel(chassis, sensor, int(channel.data_index))
                channel_list.append((int(sensor), int(channel.data_index), 0))
        logging.info("channel lists: %s" % channel_list)

        with self.services_lock:
            if chassis in self.services:
                self.services[chassis].cmd_config_sensor_list(channel_list)

    def send_logic_module_command(self, chassis_id, sensor_id, data):
        chassis = self.get_chassis_name_from_id(chassis_id)
        self.send_raw_command(chassis, sensor_id, 260, data)

    def send_raw_command(self, chassis, sensor, address, data):
        if chassis not in self.active_services:
            logging.error(f"{chassis} is not a registered chassis, can not send raw command")
            return
        self.active_services[chassis].cmd_raw(sensor_num=sensor, register_address=address, data=data)

    def send_raw_command_by_chassis_id(self, chassis_id, sensor, address, data):
        chassis_name = None
        for c, c_id in self.chassis_name_to_id.items():
            if chassis_id == c_id:
                chassis_name = c
        if chassis_name is not None:
            self.send_raw_command(chassis_name, sensor, address, data)

    def send_logic_command(self, cmd_list):
        cmd_by_chassis = {}
        for c in cmd_list:
            chassis = self.get_chassis_name_from_id(c[0])
            if not chassis:
                continue
            if chassis not in cmd_by_chassis:
                cmd_by_chassis[chassis] = []
            cmd_by_chassis[chassis].append((c[1], c[2]))
        for chassis, l in cmd_by_chassis.items():
            if chassis not in self.active_services:
                logging.error(f"{chassis} is not a registered chassis, can not send logic command")
                continue
            self.active_services[chassis].cmd_logic(l)

    def send_one_time_read(self, chassis, sensor, address):
        if chassis not in self.active_services:
            logging.error(f"{chassis} is not a registered chassis, can not send one time read")
            return
        self.active_services[chassis].cmd_one_time_read(sensor_num=sensor, register_address=address)

    def save_sensor_config(self, filename):
        with open(filename, 'w') as f:
            json.dump(self.sensor_config, f)
        logging.info(f"Saved sensor configuration to {filename}")

    def load_sensor_config(self, filename):
        with open(filename, 'r') as f:
            sensor_config_from_file = json.load(f)

        channel_configs = {}
        for chassis, config in sensor_config_from_file.items():
            for sensor, dt_freq in config.items():
                for data_type, frequency in dt_freq.items():
                    self.configure_sensor(chassis, sensor, data_type, frequency)
                    if chassis not in channel_configs:
                        channel_configs[chassis] = []
                    channel_configs[chassis].append((int(sensor), int(data_type), int(frequency)))
        with self.services_lock:
            for chassis, channel_list in channel_configs.items():
                if chassis in self.services:
                    self.services[chassis].cmd_config_sensor_list(channel_list)

    def quick_sensor_config(self, num_sensors, data_type, frequency, force=False):
        chassis_id_list = {}
        for svc in self.active_services.values():
            chassis_id_list[svc.chassis_id] = svc.chassis_name
        sensors = self.get_sensors()
        channel_configs = {}
        for sensor in sensors:
            if sensor.chassis_id in chassis_id_list.keys() and sensor.present and ((frequency > 0 and sensor.zerod) or (frequency == 0) or force):
                self.configure_sensor(chassis_id_list[sensor.chassis_id], sensor.sensor_id, data_type, frequency)
                if chassis_id_list[sensor.chassis_id] not in channel_configs:
                    channel_configs[chassis_id_list[sensor.chassis_id]] = []
                channel_configs[chassis_id_list[sensor.chassis_id]].append((sensor.sensor_id, data_type, frequency))
        logging.info("quick sensor configs: %s" % channel_configs)
        with self.services_lock:
            for chassis, channel_list in channel_configs.items():
                if chassis in self.services:
                    self.services[chassis].cmd_config_sensor_list(channel_list)

    def send_update_command(self, uri):
        self.update_chassis_version = {}
        for chassis_name, chassis in self.active_services.items():
            self.update_chassis_version[chassis_name] = None
            self.expect_device_reboot[chassis_name] = self.discovered_devices[chassis_name]
            logging.info("Before update properties for %s: %s" % (chassis_name, self.discovered_devices[chassis_name]))
            if 'zeroconf' not in self.discovered_devices[chassis_name]:
                logging.info("Waiting for %s to update" % chassis_name)
            chassis.cmd_update(uri)

    def verify_post_update(self):
        ret = True
        vals_to_check = ['num', 'total', 'master', 'serial']
        for chassis_name, prop in self.expect_device_reboot.items():
            chassis_ok = True
            if chassis_name not in self.discovered_devices:
                chassis_ok = False
            else:
                for v in vals_to_check:
                    if prop[v] != self.discovered_devices[chassis_name][v]:
                        logging.error("chassis %s current val for %s of %s does not match original %s" % (chassis_name, v, prop[v], self.discovered_devices[chassis_name][v]))
                        chassis_ok = False
            if not chassis_ok:
                ret = False
                logging.error("verify update failed for chassis %s" % chassis_name)
        return ret

    def send_commit_command(self):
        self.update_chassis_version = {}
        for chassis_name, chassis in self.active_services.items():
            chassis.cmd_commit()

    def complete_update(self):
        for chassis_name, chassis in self.active_services.items():
            del self.expect_device_reboot[chassis_name]

    def send_reboot_command(self):
        for _, chassis in self.active_services.items():
            chassis.cmd_reboot()

    def send_password(self, password):
        self._developer_mode_password = password
        for _, chassis in self.active_services.items():
            chassis.cmd_send_password(password)

    def send_sensor_config_req(self):
        for _, chassis in self.active_services.items():
            chassis.cmd_sensor_config_req()

    def disable_chassis_developer_mode(self):
        for _, chassis in self.active_services.items():
            chassis.cmd_disable_developer_mode()

    def get_chassis_version(self, chassis_id):
        for c_name, c_id in self.chassis_name_to_id.items():
            if chassis_id == c_id and c_name in self.discovered_devices:
                return self.discovered_devices[c_name]['version']
        return None

    def get_update_info(self):
        ret = [None for i in range(len(self.chassis_name_to_id))]
        for chassis_name, chassis_id in self.chassis_name_to_id.items():
            version = None
            if chassis_name not in self.non_multi_devices:
                version = self.discovered_devices[chassis_name]['version']
            ret[chassis_id] = (chassis_name, version)
        return ret

    def all_versions_equal(self):
        if len(self.chassis_name_to_id) == 0:
            return True
        else:
            first_version = None
            for chassis_name, chassis_id in self.chassis_name_to_id.items():
                if chassis_name in self.expect_device_reboot:
                    continue
                elif chassis_name in self.non_multi_devices:
                    continue
                v = self.discovered_devices[chassis_name]['version']
                if not first_version:
                    first_version = v
                elif first_version != v:
                    return False
        return True

    def num_connections(self):
        with self.services_lock:
            return len(self.services)

    def stop_services(self, chassis_list=None):
        logging.info("Stopping services %s" % chassis_list)
        with self.services_lock:
            if chassis_list is None:
                chassis_list = list(self.services.keys())
            for svc in chassis_list:
                self.services[svc].shutdown()
            for svc in chassis_list:
                self.services[svc].wait()
                chassis_id = self.services[svc].chassis_id
                del self.services[svc]
                self.hardware_state.remove_chassis(chassis_id)
            self.update_chassis_connections()
        logging.info("Services are stopped")

    def shutdown(self, block=False):
        logging.info("Shutdown start")
        self.shutting_down = True
        self.stop()
        logging.info("Shutdown stop done")
        self.stop_services()
        logging.info("Shutdown stop_services done")

        if self.zeroconf is not None:
            if block:
                logging.info("Waiting for zeroconf to close...")
                self.zeroconf.close()
                logging.info("closed")
            else:
                t = threading.Thread(target=self.zeroconf.close)
                t.daemon = True
                t.start()

    def reset_chassis(self, chassis):
        self.active_services[chassis].cmd_reset()

    def ident_chassis(self, chassis, is_on):
        with self.services_lock:
            if chassis in self.services.keys():
                self.services[chassis].cmd_ident(is_on)
            elif chassis in self.discovered_devices.keys():
                logging.info("Chassis %s ident %s" % (chassis, is_on))
                chassis_properties = self.discovered_devices[chassis]
                NetworkClient.send_ident_request(is_on, chassis_properties['address'], chassis_properties['port'])
            else:
                logging.info("ident_chassis unable to find %s" % chassis)

    def attempt_connections(self, chassis_list):
        if chassis_list:
            logging.info("Attempting connections: %s" % chassis_list)
            for c in chassis_list:
                self.connect_req(c)
            logging.info("Attempting connections complete")

    def connect_req(self, chassis, port=7777):
        chassis_name = "%s:%d" % (chassis, port)
        connected = False
        with self.services_lock:
            if chassis_name in self.services.keys():
                logging.info("Already connected to chassis: %s" % chassis)
            else:
                if chassis_name not in self.available_devices:
                    logging.info("Chassis %s not found in available devices" % chassis_name)
                    self.available_devices[chassis_name] = {}
                    device_properties = self.available_devices[chassis_name]
                    device_properties['address'] = chassis
                    device_properties['port'] = port
                    device_properties['connected'] = False
                logging.info("Attempting connect req to %s" % chassis)
                ret = NetworkClient.send_connect_req(chassis, port)
                if ret is not None:
                    connected = True
                    self.update_state(ret)
                    self.handle_chassis_added(chassis_name)
                logging.info("Connect req to %s: %s" % (chassis_name, ("Success" if ret is not None else "Failed")))
        return connected

    def connect_chassis_list(self, chassis_name_to_id):
        self.chassis_name_to_id = chassis_name_to_id
        self.last_connected = chassis_name_to_id
        disconnect_list = []
        with self.services_lock:
            for chassis_name in self.services.keys():
                if chassis_name not in self.chassis_name_to_id:
                    disconnect_list.append(chassis_name)
                    self.previously_connected.append(chassis_name)
            self.stop_services(chassis_list=disconnect_list)
            self.hardware_state.clear()
            self._handle_chassis_connections(0, 0)
            self.waiting_on_reconnects = True
            for chassis_name, chassis_id in chassis_name_to_id.items():
                self.hardware_state.add_chassis(chassis_id)
                if chassis_name in self.services:
                    self.services[chassis_name].chassis_id = self.chassis_name_to_id[chassis_name]
                    self.reconnect_list.append(chassis_name)
                    self.services[chassis_name].force_reconnect()
                else:
                    self.connect_chassis(chassis_name)
            self.num_expected_devices = len(self.chassis_name_to_id)
            self.prev_num_expected = self.num_expected_devices
        self.restart_zeroconf()

    def connect_chassis(self, chassis_name):
        if chassis_name in self.available_devices.keys():
            if chassis_name is None:
                logging.error("Trying to connect to chassis with None name")
                return
            elif not self.is_chassis_expected(chassis_name):
                logging.error(f"{chassis_name} is NOT expected, skipping")
            chassis_properties = self.available_devices[chassis_name]
            name = "Fieldline-%s-%d" % (chassis_properties['address'], chassis_properties['port'])
            name += "-%s" % str(random.randint(1000,9999))
            logging.info("Connecting to device: %s queue: %s" % (chassis_name, name))

            data_queue = InterprocessDataPacketQueue(name, True)
            new_service = NetworkClient(
                address=chassis_properties['address'],
                port=chassis_properties['port'],
                status_callback=self.update_state,
                raw_cmd_resp_callback=self._report_raw_cmd_resp,
                data_queue=data_queue,
                cmd_queue=Queue(),
                status_queue=Queue(),
                resp_queue=Queue(),
                shutdown_queue=Queue(),
                password_queue=Queue(),
                password_callback=self.password_callback,
                logger=logging,
                streaming_event=Event(),
                shutdown_event=Event(),
                done_event=Event()
            )
            new_service.chassis_name = chassis_name
            with self.services_lock:
                self.services[chassis_name] = new_service
                self.set_chassis_id(chassis_name, self.chassis_name_to_id[chassis_name])
                new_service.start()
            self.update_chassis_connections()
            self.handle_chassis_connected(chassis_name)

    def on_zeroconf_service_state_change(self, zeroconf, service_type, name, state_change):
        if not name.startswith('%sFieldline' % self.zeroconf_prefix):
            return
        if self.shutting_down:
            logging.warn("Ignoring state change.. shutting down")
            return

        # logging.info("ZeroConf discovery reports service %s of type %s %s" % (name, service_type, state_change))

        if state_change == zc.ServiceStateChange.Added:
            info = zeroconf.get_service_info(service_type, name)
            chassis_name = None
            properties = {}
            if info.properties:
                logging.info("PROPERTIES ARE: ")
                for key, value in info.properties.items():
                    try:
                        key = key.decode("utf-8")
                        value = value.decode("utf-8")
                    except Exception:
                        continue
                    logging.info("key %s val %s" % (key, value))
                    if key == "name":
                        chassis_name = value
                    else:
                        properties[key] = value
            old_type_device = "master" not in properties
            use_addr = None
            if len(info.addresses) == 1:
                use_addr = info.addresses[0]
            elif len(info.addresses) > 1:
                logging.info("Multiple addresses in info: %s" % info.addresses)
                use_addr = info.addresses[0]
            else:
                logging.error("No address found in info: %s" % info)
                return

            host, port = socket.inet_ntoa(use_addr), int(info.port)
            properties['address'] = host
            properties['port'] = port
            properties['zeroconf'] = name
            properties['closed_loop'] = None
            properties['num'] = int(properties['num'])
            properties['total'] = int(properties['total'])
            old_type_device = "master" not in properties
            if old_type_device:
                self.non_multi_devices[chassis_name] = True
                logging.info("Single chassis device %s" % chassis_name)
            chassis_name = "%s:%d" % (host, port)
            if not old_type_device and (not properties['serial'].endswith('17') or not properties['master'].endswith('17')):
                logging.error("chassis %s invalid serial: %s master: %s" % (chassis_name, properties['serial'], properties['master']))
                return
            if chassis_name not in self.available_devices or 'msgversion' not in properties or chassis_name in self.previously_connected:
                if chassis_name in self.previously_connected:
                    logging.info(f"chassis {chassis_name} was previously connected")
                    self.previously_connected.remove(chassis_name)
                self.available_devices[chassis_name] = {}
                device_properties = self.available_devices[chassis_name]
                device_properties['address'] = host
                device_properties['port'] = port
                device_properties['connected'] = False
                device_properties['zeroconf'] = name
                if 'msgversion' not in properties:
                    logging.info("Old type device %s" % host)
                    self.discovered_devices[chassis_name] = properties
                    self.update_chassis_connections()
                elif chassis_name not in self.discovered_devices:
                    connected = self.connect_req(host, port=port)
                    if not connected:
                        logging.error("chassis %s unable to connect" % chassis_name)
                        self.discovered_devices[chassis_name] = properties
                        self.handle_chassis_added(chassis_name)
                return

    def handle_chassis_added(self, chassis_name):
        pass

    def handle_chassis_connected(self, chassis_name):
        pass

    def handle_chassis_removed(self, chassis_name):
        pass

    def is_chassis_configured(self, chassis_name):
        with self.services_lock:
            return self.services[chassis_name].chassis_name != 'unknown' and \
                self.services[chassis_name].chassis_name in self.chassis_name_to_id

    def reset_connections(self, reason):
        self.restart_zeroconf()
        self.update_chassis_connections()
        self._handle_chassis_disconnect(reason)

    def report_error(self, error_msg):
        if self.startup_complete and not self.waiting_on_reconnects:
            self._handle_device_error(error_msg)

    def _monitor_thread(self):
        num_connected = 0
        logging.info("Start monitor thread")
        while not self.shutting_down:
            total_samples_available = 0
            free_memory = []
            prev_connected = num_connected
            num_connected = 0
            with self.services_lock:
                for i, (name, svc) in enumerate(self.services.items()):
                    svc_connected = svc.is_connected
                    # logging.info(f"chassis {name} connected: {svc_connected}")
                    if not svc_connected:
                        if self.available_devices[name]['connected']:
                            self.available_devices[name]['connected'] = False
                            if name in self.discovered_devices and name not in self.reconnect_list:
                                self.previously_connected.append(name)
                                del self.discovered_devices[name]
                            logging.info(f"Chassis {name} is disconnected")
                            if name not in self.expect_device_reboot not in self.reconnect_list:
                                # self.hardware_state.remove_chassis(svc.chassis_id)
                                self.report_error("Chassis disconnected")
                            if name in self.reconnect_list:
                                self.reconnect_list.remove(name)
                    else:
                        if name in self.discovered_devices:
                            num_connected += 1
                        if not self.available_devices[name]['connected']:
                            self.available_devices[name]['connected'] =  True
                            logging.info(f"Chassis {name} is connected")
                            # self.hardware_state.add_chassis(svc.chassis_id)
                            if name not in self.expect_device_reboot:
                                self.update_chassis_connections()
                    total_samples_available += self.services[name].num_samples_available()
                    free_memory.append(self.services[name].available_data_buf())
                if prev_connected != num_connected or self.prev_num_expected != self.num_expected_devices or self.update_connections:
                    if num_connected == self.num_expected_devices:
                        self.waiting_on_reconnects = False
                    self.prev_num_expected = self.num_expected_devices
                    self._handle_chassis_connections(num_connected, self.num_expected_devices)
                    self.update_connections = False
                if len(free_memory):
                    avg_samples_per_chassis = total_samples_available / len(self.active_services) if len(self.active_services) else 0
                    self._report_data_underrun(int(avg_samples_per_chassis), min(free_memory))
            time.sleep(1)

    def set_chassis_id(self, chassis_name, chassis_id):
        with self.services_lock:
            if chassis_name not in self.services:
                logging.error(f"{chassis_name} is not a recognized chassis")
                return
            self.services[chassis_name].chassis_id = chassis_id

    def password_callback(self, chassis_name, msg):
        if msg.dev_mode.enable:
            if msg.dev_mode.valid:
                self._report_password_response(chassis_name, True)
            else:
                self._report_password_response(chassis_name, False)

    def update_state(self, msg=None):
        with self.services_lock:
            if msg is not None:
                msg_chassis_id = None
                chassis_name = msg.chassis_name
                msg_chassis_id = None
                if chassis_name in self.chassis_name_to_id:
                    msg_chassis_id = self.chassis_name_to_id[chassis_name]
                self._report_chassis_status(chassis_name, msg.status)
                if msg.type == proto.StatusPacket.SYSTEM_STATUS:
                    # logging.info("SYSTEM STATUS: %s" % msg)
                    prev_status = None
                    if chassis_name in self.discovered_devices:
                        prev_status = self.discovered_devices.pop(chassis_name)
                    self.discovered_devices[chassis_name] = {}
                    d = self.discovered_devices[chassis_name]
                    if prev_status and prev_status['num'] != msg.system_status.num:
                        logging.info("Chassis %s num prev: %d after: %d" % (chassis_name, prev_status['num'], msg.system_status.num))
                    d['num'] = msg.system_status.num
                    if prev_status and prev_status['total'] != msg.system_status.total:
                        logging.info("Chassis %s total prev: %d after: %d" % (chassis_name, prev_status['total'], msg.system_status.total))
                    d['total'] = msg.system_status.total
                    if chassis_name in self.last_connected and chassis_name not in self.expect_device_reboot and d['total'] != self.num_expected_devices:
                        logging.info("Chassis %s number of expected devices updated to: %d" % (chassis_name, d['total']))
                        self.report_error("Chassis config mismatch")
                    if prev_status and prev_status['version'] != msg.system_status.version:
                        logging.info("Chassis %s version prev: %s after: %s" % (chassis_name, prev_status['version'], msg.system_status.version))
                    d['version'] = msg.system_status.version
                    if chassis_name in self.update_chassis_version:
                        self.update_chassis_version[chassis_name] = d['version']
                    if prev_status and prev_status['master'] != msg.system_status.master:
                        logging.info("Chassis %s master prev: %s after: %s" % (chassis_name, prev_status['master'], msg.system_status.master))
                    d['master'] = msg.system_status.master
                    if prev_status and prev_status['serial'] != msg.system_status.serial:
                        logging.info("Chassis %s serial prev: %s after: %s" % (chassis_name, prev_status['serial'], msg.system_status.serial))
                    d['serial'] = msg.system_status.serial
                    d['address'] = self.available_devices[chassis_name]['address']
                    d['port'] = self.available_devices[chassis_name]['port']
                    if prev_status is not None and 'closed_loop' in prev_status:
                        d['closed_loop'] = prev_status['closed_loop']
                    else:
                        d['closed_loop'] = None
                    if not self.is_config_mismatch():
                        self.report_error('')
                        self.update_connections = True
                if msg.HasField('chassis_status'):
                    if msg.chassis_status.HasField('closed_loop') and chassis_name in self.discovered_devices:
                        self.discovered_devices[chassis_name]['closed_loop'] = msg.chassis_status.closed_loop
                        self.check_closed_loop()
                if msg_chassis_id is not None:
                    if msg.type in (proto.StatusPacket.PROGRESS,):
                        self._report_update_progress(chassis_name, msg.progress, msg.type, msg.progress_msg)
                    elif msg.type == proto.StatusPacket.SENSOR_LED:
                        logging.debug("Got a SENSOR_LED message")
                        for s in self.get_sensors():
                            for sc in msg.sensor_led:
                                if sc.sensor_id == s.sensor_id and msg_chassis_id == s.chassis_id:
                                    current_color = s.get_color()
                                    current_blink = s.get_blink_state()
                                    s.set_color(sc.color)
                                    s.set_blink_state(sc.blink_state)
                                    s.zerod = (sc.color == 6 and sc.blink_state == 1)
                                    if current_color != sc.color or current_blink != sc.blink_state:
                                        self._handle_blink_state_changed(s.chassis_id, s.sensor_id, sc.color, sc.blink_state)
                        self._report_sensor_status_changed()
                    elif msg.type == proto.StatusPacket.SENSOR_CONFIG:
                        # logging.info("Got a SENSOR_CONFIG %s" % msg)
                        channel_list = []
                        for sc in msg.sensor_config:
                            if sc.HasField("calibration"):
                                calibration = sc.calibration
                            else:
                                calibration = 1.0
                            channel_list.append({'chassis_id': msg_chassis_id,
                                                 'sensor_id': sc.sensor,
                                                 'data_type': sc.datatype,
                                                 'frequency': sc.freq,
                                                 'calibration': calibration
                                                })
                        self.hardware_state.configure_channel_list(msg_chassis_id, channel_list)
                    elif msg.type == proto.StatusPacket.SENSOR_STATUS:
                        logging.debug("Got a SENSOR_STATUS message")
                        for s in self.get_sensors():
                            for sc in msg.sensor_status:
                                if sc.sensor_id == s.sensor_id and msg_chassis_id == s.chassis_id:
                                    if s.present != sc.sensor_connected:
                                        logging.info("Sensor [%d:%d] connected changed to %s" % (s.chassis_id, sc.sensor_id, sc.sensor_connected))
                                    s.present = sc.sensor_connected
                                    s.card_serial = sc.sensor_card_serial_num
                                    if sc.HasField('sensor_serial_num'):
                                        s.sensor_serial = sc.sensor_serial_num
                                    else:
                                        s.sensor_serial = None
                        self._report_sensor_status_changed()
                    elif msg.type == proto.StatusPacket.SENSOR_STATE:
                        for sc in msg.sensor_state:
                            logging.debug("Got SENSOR_STATE %d %s" % (sc.sensor_id, proto.SensorState.EnumStateType.Name(sc.state)))
                    elif msg.type == proto.StatusPacket.SENSOR_FIELD:
                        logging.debug("Got a SENSOR_FIELD message")
                        for s in self.get_sensors():
                            for sc in msg.sensor_field:
                                if sc.sensor_id == s.sensor_id and msg_chassis_id == s.chassis_id:
                                    # logging.info("Updating fields chassis: %d sensor: %d x: %d y: %d z: %d" % (s.chassis_id, s.sensor_id, sc.field_x, sc.field_y, sc.field_z))
                                    s.set_fields(sc.field_x, sc.field_y, sc.field_z)
                        self._report_sensor_status_changed()

    def update_chassis_connections(self):
        connected = set()

        with self.services_lock:
            for svc in self.services.values():
                if svc.chassis_name in self.chassis_name_to_id:
                    if svc.is_connected:
                        connected.add(svc.chassis_name)
                    svc.cmd_sensor_config_req()
                    if self._developer_mode_password:
                        svc.cmd_send_password(self._developer_mode_password)
                    if self.is_streaming:
                        # If the gui is already streaming send the start cmd to the new chassis
                        svc.start_streaming()
                    self._report_chassis_connection_change(svc.chassis_id, True)
                else:
                    with self.frame_q_lock:
                        if svc.chassis_id in self.frame_q:
                            del self.frame_q[svc.chassis_id]
                    self._report_chassis_connection_change(svc.chassis_id, False)
            self.streaming_sources = {svc.chassis_id: svc for svc in self.active_services.values()}


    def _read_next_data_frame(self, sources):
        with self.frame_q_lock:
            for chassis_id in sources.keys():
                if chassis_id not in self.frame_q:
                    logging.info("New chassis_id %d for frame data" % chassis_id)
                    self.frame_q[chassis_id] = None
                    self.last_ts[chassis_id] = None
                    if len(self.frame_q) > 1:
                        self.frames_syncd = False
                        self.frame_reset_pending = True
                        self.sync_active[chassis_id] = True
                    else:
                        self.frames_syncd = True

                if self.frame_q[chassis_id] is not None:
                    continue

                try:
                    data_item = sources[chassis_id].data_queue.get(block=True, timeout=0.01)
                    self.frame_q[chassis_id] = {'timestamp': data_item.timestamp, 'data': data_item}
                    if data_item.timestamp == 1:
                        self.no_sync = False
                        if chassis_id not in self.sync_active:
                            logging.info("chassis %d sync detected ts %d" % (chassis_id, data_item.timestamp))
                            self.sync_active[chassis_id] = True
                            self.frame_reset_pending = True
                            self.frames_syncd = False
                        else:
                            logging.info("chassis %d sync detected while active ts %d" % (chassis_id, data_item.timestamp))
                    elif self.last_ts[chassis_id] is not None:
                        if data_item.timestamp < self.last_ts[chassis_id]:
                            logging.warning("chassis [%d] new ts: %d less than last ts: %d" % (chassis_id, data_item.timestamp, self.last_ts[chassis_id]))
                    self.last_ts[chassis_id] = data_item.timestamp
                except queue.Empty:
                    continue

    def _build_frame(self):
        with self.frame_q_lock:
            if len(self.frame_q) == 0:
                time.sleep(0.01)
                return
            channel_dict = self.hardware_state.get_channel_dict()
            out_data = defaultdict(dict)
            ts_list = []
            for chassis_id, q in self.frame_q.items():
                ts = None
                if q:
                    ts = q['timestamp']
                ts_list.append(ts)
            # logging.info("tslist %s" % (ts_list))
            skip = any(e is None for e in ts_list)
            if skip:
                return
            equal = all(e == ts_list[0] for e in ts_list)

            chassis_to_send = []
            if self.no_sync:
                if not equal:
                    min_ts = min(ts_list)
                    for chassis_id in self.frame_q.keys():
                        if self.frame_q[chassis_id]['timestamp'] == min_ts:
                            logging.debug("Dropping timestamp for startup sync")
                            self.frame_q[chassis_id] = None
                    return out_data
                else:
                    logging.info("Got startup sync %s" % ts_list)
                    self.frames_syncd = True
                    self.no_sync = False
            elif self.frame_reset_pending:
                if equal:
                    self.frame_reset_pending = False
                    self.sync_active = {}
                    self.frames_syncd = True
                    logging.info("Frames are syncd %s" % ts_list)
                else:
                    for chassis_id, f in self.frame_q.items():
                        do_add = False
                        if chassis_id not in self.sync_active:
                            do_add = True
                        if do_add:
                            chassis_to_send.append(chassis_id)
            if self.frames_syncd:
                chassis_to_send = [i for i in self.frame_q.keys()]

            for chassis_id in chassis_to_send:
                data = self.frame_q[chassis_id]['data'].data

                for data_frame in data:
                    sensor_id = data_frame.sensor
                    sensor = self.hardware_state.get_sensor(chassis_id, sensor_id)
                    if sensor is None:
                        logging.error(f"Received data for {sensor_id} which does not exist")
                        continue

                    datatype = data_frame.datatype
                    ch_name = '%02d:%02d:%s' % (chassis_id, sensor_id, datatype)
                    if ch_name not in channel_dict:
                        continue

                    sensor.add_data_point(ch_name, data_frame.val)
                    out_data[ch_name]['data'] = data_frame.val
                    out_data[ch_name]['sensor'] = sensor.name
                    out_data[ch_name]['idx'] = channel_dict[ch_name]['idx']
                    out_data[ch_name]['sensor_id'] = sensor.sensor_id
                    out_data[ch_name]['data_type'] = int(datatype)
                    out_data[ch_name]['calibration'] = channel_dict[ch_name]['calibration']
                    out_data[ch_name]['timestamp'] = self.frame_q[chassis_id]['timestamp']
                self.frame_q[chassis_id] = None
            return out_data

    def _read_data_queue_thread(self):
        out_list = []
        while self.is_streaming:
            t1 = time.time()

            self._read_next_data_frame(self.streaming_sources)
            out_data = self._build_frame()

            if out_data:
                self.update_count += 1
                out_list.append(out_data)
                if len(out_list) >= 10:
                    #with self.counter_lock:
                    #    self.counter[0] += 1
                    self._report_data_available(out_list)
                    out_list = []
            self.total_time += (time.time() - t1)
            if (self.update_count % common.PERFORMANCE_LOGGING_PERIOD == 0):
                # logging.info(f"Avg read_thread time is {self.total_time / common.PERFORMANCE_LOGGING_PERIOD}")
                self.total_time = 0
                self.update_count = 0
        logging.info("Exiting the read_data_queue thread!")

    def start(self):
        # Clear out any old stale data from the data queue
        for svc in self.active_services.values():
            svc.clear_data_queue()
        self.reset_frame_buffer()

        self.update_count = 1
        self.total_time = 0

        for svc in self.active_services.values():
            svc.start_streaming()

        self.stream_thread = threading.Thread(target=self._read_data_queue_thread)
        self.stream_thread.daemon = True
        self.stream_thread.start()

    def stop(self):
        logging.info("network data source stop")
        for svc in self.active_services.values():
            svc.stop_streaming()
        self.is_streaming = False
        logging.info("Waiting on stream thread")
        if self.stream_thread and self.stream_thread.is_alive():
            self.stream_thread.join(timeout=5)
        logging.info("Stream thread stopped")
        logging.info("network data source stop done")

    def set_wave_off(self, chassis_id, sensor_id):
        name = self.get_chassis_name_from_id(chassis_id)
        if name not in self.active_services:
            logging.error(f"{name} is not a registered chassis, can not send wave command")
            return
        self.active_services[name].cmd_wave_off(sensor_list=[sensor_id, ])

    def set_wave_ramp(self, chassis_id, sensor_id, freq, amp):
        self.set_wave_off(chassis_id, sensor_id)
        name = self.get_chassis_name_from_id(chassis_id)
        if name not in self.active_services:
            logging.error(f"{name} is not a registered chassis, can not send wave command")
            return
        self.active_services[name].cmd_wave(sensor_list=[(sensor_id, proto.WaveMessage.WAVE_RAMP, amp, freq), ])

    def set_wave_sine(self, chassis_id, sensor_id, freq, amp):
        self.set_wave_off(chassis_id, sensor_id)
        name = self.get_chassis_name_from_id(chassis_id)
        if name not in self.active_services:
            logging.error(f"{name} is not a registered chassis, can not send wave command")
            return
        self.active_services[name].cmd_wave(sensor_list=[(sensor_id, proto.WaveMessage.WAVE_SINE, amp, freq), ])

    def set_closed_loop(self, is_on):
        self.closed_loop_expected = is_on
        for svc in self.active_services.values():
            svc.cmd_closed_loop(is_on)
        for d in self.discovered_devices.values():
            d['closed_loop'] = None

    def check_closed_loop(self):
        unknowns = False
        all_closed = True
        all_open = True
        with self.services_lock:
            for chassis_name in self.active_services.keys():
                if chassis_name not in self.discovered_devices:
                    return
                if self.discovered_devices[chassis_name]['closed_loop'] is None:
                    unknowns = True
                elif not self.discovered_devices[chassis_name]['closed_loop']:
                    all_closed = False
                elif self.discovered_devices[chassis_name]['closed_loop']:
                    all_open = False
            if not unknowns:
                if not all_open and not all_closed:
                    self.set_closed_loop(False)
                elif all_closed:
                    self._report_closed_loop(True)
                elif all_open:
                    self._report_closed_loop(False)

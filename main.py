from fieldline_connector import FieldLineConnector
from fieldline_api.fieldline_service import FieldLineService
from fieldline_api.fieldline_datatype import FieldLineWaveType

import logging
import argparse
import queue
import time
import sys
import signal
import sys


# if __name__ == "__main__":
stop_flag = False
# parser = argparse.ArgumentParser()
# parser.add_argument('-v', '--verbose', action='store_true', default=False, help="Include debug-level logs.")
# args = parser.parse_args()

stream_handler = logging.StreamHandler()
logging.basicConfig(
    format='%(asctime)s %(levelname)s %(threadName)s(%(process)d) %(message)s [%(filename)s:%(lineno)d]',
    datefmt='%m/%d/%Y %I:%M:%S %p',
    level=logging.DEBUG if args.verbose else logging.ERROR,
    handlers=[stream_handler]
)
logging.info("Starting FieldLine service main")

# ip_list = ['10.1.10.164']
ip_list = ['192.168.2.42','192.168.2.47']
fConnector = FieldLineConnector()
fService = FieldLineService(fConnector, prefix="")
def signal_handler(signal, frame):
    global stop_flag
    logging.info("SIGNAL handler")
    stop_flag = True
signal.signal(signal.SIGINT, signal_handler)

# Start listening for FieldLine devices
fService.start()
# Enable data streaming
fService.start_data()
# Wait for devices to be discovered
time.sleep(2)
# Return list of IPs of chassis discovered
chassis_list = fService.get_chassis_list()
logging.info(f"Discovered chassis list: {chassis_list}")
logging.info(f"Expected IP list: {ip_list}")
all_found = True
for ip in ip_list:
    if ip not in chassis_list:
        all_found = False
if not all_found:
    logging.error("Not all expected chassis discovered")
    # Stop all services and shut down cleanly
    fService.stop()
    sys.exit()
# Connect to list of IPs
fService.connect(ip_list)
my_chassis = None
while fService.get_sensor_state(0,1) is None:
    time.sleep(1)

while not stop_flag:
    # logging.info(fService.get_sensor_state(0, 1))
    if fConnector.has_sensors_ready():
        sensors = fConnector.get_sensors_ready()
        fConnector.set_all_sensors_valid()
        for c, s in sensors.items():
            if not my_chassis:
                my_chassis = c
                #logging.info(f"Starting ADC on chassis {my_chassis}")
                #fService.start_adc(c)
            logging.info(f"Chassis {c} got new sensors {s}")
            for sensor in s:
                fService.restart_sensor(c, sensor)
    elif fConnector.has_restarted_sensors() and fConnector.num_valid_sensors() == fConnector.get_num_restarted_sensors():
        sensors = fConnector.get_restarted_sensors()
        for c, s in sensors.items():
            logging.info(f"Chassis {c} got restarted sensors {s}")
            for sensor in s:
                fService.coarse_zero_sensor(c, sensor)
    elif fConnector.has_coarse_zero_sensors() and fConnector.num_valid_sensors() == fConnector.get_num_coarse_zero_sensors():
        sensors = fConnector.get_coarse_zero_sensors()
        for c, s in sensors.items():
            logging.info(f"Chassis {c} got coarse zero sensors {s}")
            for sensor in s:
                fService.fine_zero_sensor(c, sensor)
    elif fConnector.has_fine_zero_sensors() and fConnector.num_valid_sensors() == fConnector.get_num_fine_zero_sensors():
        sensors = fConnector.get_fine_zero_sensors()
        #for c, s in sensors.items():
        #    logging.info(f"Chassis {c} got fine zero sensors {s}")
        #    fService.start_bz(c, s)
        #    for sensor in s:
        #        fService.set_bz_wave(c, sensor, FieldLineWaveType.WAVE_SINE, 1, 1)
    try:
        data = fConnector.data_q.get(True, 0.01)
        #logging.info(f"DATA {data}")
    except queue.Empty:
        continue
if fService.is_service_running():
    fService.stop()

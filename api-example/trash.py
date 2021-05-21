from fieldline_connector import FieldLineConnector
from fieldline_api.fieldline_service import FieldLineService
from fieldline_api.fieldline_datatype import FieldLineWaveType

import queue
import time
import threading

measure_flag = True
measure_flag_lock = threading.Lock()

working_chassis = [0, 1]
broken_sensors = [(2, 16),()]
working_sensors = [(1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15),
                   (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14)]

ip_list = ['192.168.111.103','192.168.111.102']

fConnector = FieldLineConnector()
fService = FieldLineService(fConnector, prefix="")

def num_working_sensors():
    num_sens = 0
    for ch in working_chassis:
        num_sens += len(working_sensors[ch])
    return num_sens

def init_connection():
    fService.start()
    print ("fService started.")
    time.sleep(.5)
    fService.connect(ip_list)
    while fService.get_sensor_state(0,1) is None:
        time.sleep(1)
    print ("fService connected.")

def num_restarted_sensors():
    num_sens = 0
    if fConnector.restarted_sensors:
        for sensors_in_chassis in fConnector.restarted_sensors.values():
            num_sens += len(sensors_in_chassis)
    return num_sens

def num_coarse_zeroed_sensors():
    num_sens = 0
    if fConnector.coarse_zero_sensors:
        for sensors_in_chassis in fConnector.coarse_zero_sensors.values():
            num_sens += len(sensors_in_chassis)
    return num_sens

def num_fine_zeroed_sensors():
    num_sens = 0
    if fConnector.fine_zero_sensors:
        for sensors_in_chassis in fConnector.fine_zero_sensors.values():
            num_sens += len(sensors_in_chassis)
    return num_sens

def wait_for_restart_to_finish():
    while (num_restarted_sensors() < num_working_sensors()):
        time.sleep(.1)

def wait_for_coarse_zero_to_finish():
    while (num_coarse_zeroed_sensors() < num_working_sensors()):
        time.sleep(.1)

def wait_for_fine_zero_to_finish():
    while (num_fine_zeroed_sensors() < num_working_sensors()):
        time.sleep(.1)

def turn_off_all_broken_sensors():
    for ch in working_chassis:
        for s in broken_sensors[ch]:
            fService.turn_off_sensor(ch, s)

def continue_measurement(*argv):
    global measure_flag
    global measure_flag_lock
    if len(argv) == 0:
        measure_flag_lock.acquire()
        stopFlag = measure_flag
        measure_flag_lock.release()
        return stopFlag
    if len(argv) == 1 and type(argv[0]) is bool:
        measure_flag_lock.acquire()
        measure_flag = argv[0]
        measure_flag_lock.release()
        return continue_measurement()

def end_measurement():
    if fService.is_service_running():
        fService.stop()
        continue_measurement(False)

def restart_all_working_sensors():
    for ch in working_chassis:
        for s in working_sensors[ch]:
            fService.restart_sensor(ch, s)
            time.sleep(.1)
    wait_for_restart_to_finish()
    print("All sensors restarted.")

def coarse_zero_all_working_sensors():
    for ch in working_chassis:
        for s in working_sensors[ch]:
            fService.coarse_zero_sensor(ch, s)
            time.sleep(.1)
    wait_for_coarse_zero_to_finish()
    print("All sensors coarse-zeroed.")

def fine_zero_all_working_sensors():
    for ch in working_chassis:
        for s in working_sensors[ch]:
            fService.fine_zero_sensor(ch, s)
            time.sleep(.1)
    wait_for_fine_zero_to_finish()
    print("All sensors fine-zeroed.")

def init_sensors():
    turn_off_all_broken_sensors()
    restart_all_working_sensors()
    coarse_zero_all_working_sensors()
    fine_zero_all_working_sensors()

def start_acquisition():
    fService.start_data()
    print("fService data started.")
    time.sleep(1)
    d = threading.Thread(target=data_retreiver_thread, daemon=True)
    d.start()

def parse_data(data):
    for dd in data:
        for sensor_data in dd.keys():
            sensor_data[]
    # for dict in data:
    #     dict['00:01:28'][data]
    #     values.append(data)
    #     pass

def data_retreiver_thread():
    f = open("test123.txt", "a")
    while continue_measurement():
        data = fConnector.data_q.get(True, 0.01)

        f.write(str(data))

        # print(f'Working on {item} ...')
        # time.sleep(1)
        # print(f'Finished {item}')
        fConnector.data_q.task_done()
    f.close()

def stop_acquisition():
    if fService.is_service_running():
        fService.stop()
    fConnector.data_q.join()
    continue_measurement(False)
    print("Measurement stopped.")


init_connection()

init_sensors()

start_acquisition()
time.sleep(15)
stop_acquisition()

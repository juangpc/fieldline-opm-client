# mne_fieldline_connector
# gabrielbmotta, juangpc
from fieldline_connector import FieldLineConnector
from fieldline_api.fieldline_service import FieldLineService
from fieldline_api.fieldline_datatype import FieldLineWaveType

import queue
import time
import threading
import numpy
import FieldTrip

measure_flag = True
measure_flag_lock = threading.Lock()
process_data_flag = False
process_data_flag_lock = threading.Lock()

default_sample_freq = 1000
working_chassis = [0, 1]
broken_sensors = [(2, 6, 16),()]
working_sensors = [(1, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15),
                   (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14)]

ip_list = ['192.168.111.103','192.168.111.102']

fConnector = FieldLineConnector()
fService = FieldLineService(fConnector, prefix="")

ft_client = FieldTrip.Client()
ft_IP = 'localhost'
ft_port = 1972
ft_data_type = FieldTrip.DATATYPE_FLOAT32

def num_working_sensors():
    num_sens = 0
    for ch in working_chassis:
        num_sens += len(working_sensors[ch])
    return num_sens

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

def process_data(*argv):
    global process_data_flag
    global process_data_flag_lock
    if len(argv) == 0:
        process_data_flag_lock.acquire()
        stopFlag = process_data_flag
        process_data_flag_lock.release()
        return stopFlag
    if len(argv) == 1 and type(argv[0]) is bool:
        process_data_flag_lock.acquire()
        process_data_flag = argv[0]
        process_data_flag_lock.release()
        return process_data()

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

def create_channel_key_list():
    channel_key_list = []
    for chassis in working_chassis:
        for sensors in working_sensors[chassis]:
            key = str(chassis).zfill(2) + ':' + str(sensors).zfill(2) + ':' + str(28).zfill(2)
            channel_key_list.append(key)
    return channel_key_list

def connect_to_fieldtrip_buffer():
    ft_client.connect(ft_IP, ft_port)

def init_ft_header():
    ft_client.putHeader(num_working_sensors(), default_sample_freq, ft_data_type)

def test_data_to_ft():
    arr_data = nunmpy.zeros((200,num_working_sensors()), dtype=numpy.single)
    ft_client.putData(arr_data)

def init_sensors():
    turn_off_all_broken_sensors()
    restart_all_working_sensors()
    coarse_zero_all_working_sensors()
    fine_zero_all_working_sensors()

def init_acquisition():
    connect_to_fieldtrip_buffer()
    init_ft_header()
    fService.start_data()
    print("fService data started.")
    time.sleep(1)
    acquisition_thread = threading.Thread(target=data_retreiver_thread, daemon=True)
    acquisition_thread.start()
    # acquisition_thread_dalayed_stopper = threading.Thread(target=delayed_data_retriever_stopper,args=[ttime], daemon=True)
    # acquisition_thread_dalayed_stopper.start()


def parse_data(data):
    channels = create_channel_key_list()
    chunk = numpy.zeros((len(data),num_working_sensors()), dtype=numpy.single)
    for sample_i in range(len(data)):
        for ch_i, channel in enumerate(channels):
            chunk[sample_i, ch_i] = data[0][channel]["data"] * data[0][channel]["calibration"] * 1000000;
    ft_client.putData(chunk)
    print("Writing to buffer")


# def delayed_data_retriever_stopper(t):
#     time.sleep(t)
#     stop_acquisition()
#     time.sleep(.5)
    
def data_retreiver_thread():
    while continue_measurement():
        data = fConnector.data_q.get(True, 0.01)
        if process_data():
            parse_data(data)
        fConnector.data_q.task_done()

def init_connection():
    fService.start()
    print ("fService started.")
    time.sleep(.5)
    fService.connect(ip_list)
    while fService.get_sensor_state(0,1) is None:
        time.sleep(1)
    print ("fService connected.")
    for chassis in working_chassis:
        version = fService.get_version(chassis)
        print("Connection with chassis: " + str(chassis) + "... OK")
        print("Chassis version" + version)
    print("---")

def start_acquisition():
    process_data(True)

def stop_acquisition():
    process_data(False)
    
def stop_service():
    process_data(False)
    continue_measurement(False)
    fConnector.data_q.join()
    if fService.is_service_running():
        fService.stop()

if __name__ == "__main__":
    
    init_connection()

    # init_sensors()

    # init_acquisition()
    # time.sleep(15)
    # stop_acquisition()


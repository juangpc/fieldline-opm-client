# mne_fieldline_connector
# gabrielbmotta, juangpc

import mne_fieldline_config as config
# import mne_fieldline_tools as tools

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
working_chassis = config.working_chassis
broken_sensors = config.broken_sensors
working_sensors = config.working_sensors
channel_key_list = []

ip_list = config.ip_list

if(config.use_phantom):
    import mne_fieldline_phantom as spooky
    fConnector = spooky.PhantomConnector()
    fService = spooky.PhantomService(fConnector, prefix="")
else:
    from fieldline_connector import FieldLineConnector
    from fieldline_api.fieldline_service import FieldLineService
    from fieldline_api.fieldline_datatype import FieldLineWaveType

    fConnector = FieldLineConnector()
    fService = FieldLineService(fConnector, prefix="")

ft_client = FieldTrip.Client()
ft_IP = config.ft_IP
ft_port = config.ft_port
ft_data_type = FieldTrip.DATATYPE_FLOAT32

data_stream_multiplier = 1


class fieldline_phantom:

    def __init__(self, num_sensors, sample_frequency):
        self.num_sensors = num_sensors
        self.sample_frequency = sample_frequency
        self.num_samples = 200
        self.ft_client = FieldTrip.Client()
        self.send_data_flag = False
        self.send_data_flag_lock = threading.Lock()
        self.send_data_thread = threading.Thread(target=self.data_producer_routine, daemon = True)
    
    def __del__(self):
        self.send_data_thread.join()

    def connect(self, ip = 'localhost', port = 1972):
        ft_IP = ip
        ft_port = port
        self.ft_client.connect(ft_IP, ft_port)
        self.ft_client.putHeader(self.num_sensors, self.sample_frequency, FieldTrip.DATATYPE_FLOAT32)
        self.send_data_thread.start()

    def start(self):
        self.send_data_flag_lock.acquire()
        self.send_data_flag = True
        self.send_data_flag_lock.release()

    def stop(self):
        self.send_data_flag_lock.acquire()
        self.send_data_flag = False
        self.send_data_flag_lock.release()

    def data_producer_routine(self):
        while True:
            if self.send_data_flag:
                data = numpy.random.rand(self.num_samples, self.num_sensors).astype(numpy.float32) * 1e-12
                self.ft_client.putData(data)

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

def measure(*argv):
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
        return measure()

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
        measure(False)

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

def connect_to_fieldtrip_buffer():
    ft_client.connect(ft_IP, ft_port)
    if ft_client.isConnected:
        print("Fieldtrip Client connected")

def init_ft_header():
    if ft_client.isConnected:
        ft_client.putHeader(num_working_sensors(), default_sample_freq, ft_data_type)
        header = ft_client.getHeader()
        if header.nChannels == num_working_sensors():
            print("Fieldtrip header initialized")


def test_data_to_ft():
    arr_data = nunmpy.zeros((200,num_working_sensors()), dtype=numpy.single)
    ft_client.putData(arr_data)

def init_sensors():
    if num_fine_zeroed_sensors() < num_working_sensors():
        force_init_sensors()

def create_channel_key_list(channel_list):
    channel_key_list = []
    for chassis in channel_list:
        for sensors in working_sensors[chassis]:
            key = str(chassis).zfill(2) + ':' + str(sensors).zfill(2) + ':' + str(28).zfill(2)
            channel_key_list.append(key)
    return channel_key_list

def force_init_sensors():
    turn_off_all_broken_sensors()
    restart_all_working_sensors()
    coarse_zero_all_working_sensors()
    fine_zero_all_working_sensors()
    global channel_key_list
    channel_key_list = create_channel_key_list(working_chassis)

def are_sensors_ready():
    return num_fine_zeroed_sensors() == num_working_sensors()

def init_acquisition():
    if measure() is not True:
        fService.start_data()
        print("fService data started.")
        measure(True)
        time.sleep(1)
        acquisition_thread = threading.Thread(target=data_retreiver_thread, daemon=True)
        acquisition_thread.start()
        # acquisition_thread_dalayed_stopper = threading.Thread(target=delayed_data_retriever_stopper,args=[ttime], daemon=True)
        # acquisition_thread_dalayed_stopper.start()

def parse_data(data):
    global channel_key_list
    global data_stream_multiplier
    chunk = numpy.zeros((len(data),num_working_sensors()), dtype=numpy.single)
    for sample_i in range(len(data)):
        for ch_i, channel in enumerate(channel_key_list):
            chunk[sample_i, ch_i] = data[0][channel]["data"] * data[0][channel]["calibration"] * data_stream_multiplier;
    ft_client.putData(chunk)
    # print("Writing to buffer")

# def delayed_data_retriever_stopper(t):
#     time.sleep(t)
#     stop_acquisition()
#     time.sleep(.5)
    
def data_retreiver_thread():
    while measure():
        data = fConnector.data_q.get()
        parse_data(data)
        fConnector.data_q.task_done()

def init_fieldline_connection():
    if fService.is_service_running() is not True:
        fService.start()
        print ("Fieldline service started.")
        time.sleep(.5)
        fService.connect(ip_list)
        while fService.get_sensor_state(0,1) is None:
            time.sleep(1)
        print ("Fieldline service connected.")
        for chassis in working_chassis:
            version = fService.get_version(chassis)
            print("Connection with chassis: " + str(chassis) + "... OK")
            print("Chassis " + str(version))
        print("---")

def init_fieldtrip_connection():
    connect_to_fieldtrip_buffer()
    init_ft_header()


# def start_acquisition():
#     process_data(True)
#     measure(True)

# def stop_acquisition():
#     process_data(False)
#     measure(False)

def stop_measurement():
    if measure() is True:
        process_data(False)
        measure(False)
        fConnector.data_q.join()
        fService.stop_data()
    
def stop_service():
    if fService.is_service_running():
        fService.stop()

if __name__ == "__main__":
    
    init_fieldline_connection()
    init_sensors()

    init_acquisition()
    # time.sleep(15)
    # stop_acquisition()


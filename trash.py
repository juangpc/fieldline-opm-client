from fieldline_connector import FieldLineConnector
from fieldline_api.fieldline_service import FieldLineService
from fieldline_api.fieldline_datatype import FieldLineWaveType

import queue
import time
import threading, queue
import time

# [(0, 1), (0, 3), (0, 4), (0, 5), (0, 6), (0, 7), (0, 8), (0, 9), (0, 10), (0, 11), (0, 12), (0, 13), (0, 14), (0, 15), (1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (1, 6), (1, 7), (1, 8), (1, 9), (1, 10), (1, 11), (1, 12), (1, 13), (1, 14)]
# %%
stopMeasurement = False

values = []   

def parse_dictionary_data(dictionary_data):
    # for dict in dictionary_data:
        # dict['00:01:28'][data]
        values.append(dictionary_data)

def DataRetreiverThread():
    global stopMeasurement
    while not stopMeasurement:
        data = q.get()
        parse_dictrionary_data(data)
        # print(f'Working on {item} ...')
        # time.sleep(1)
        # print(f'Finished {item}')
        q.task_done()

def init_instrumentation():
    global working_chassis = [0, 1]
    global broken_sensors = [(2, 16),()]
    global working_sensors = [(1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15),
                              (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14)]
    global ip_list = ['192.168.2.42','192.168.2.47']
    global fConnector = FieldLineConnector()
    
    global fService = FieldLineService(fConnector, prefix="")
    global func_dict = { 
            'start':fService.start,
            'start_data':fService.start_data,
            'turn_off_sensor':fService.turn_off_sensor,
            'restart_sensor':fService.restart_sensor,
            'coarse_zero_sensor':fService.coarse_zero_sensor,
            'fine_zero_sensor':fService.fine_zero_sensor,
            'check_all_sensors_restarted':check_all_sensors_restarted
        }

def for_all_valid_sensors(f):
    for ch in working_chassis:
        for s in working_sensors[ch]:
            func_dict[f](ch, s)

def turn_off_broken_sensors():
    for ch in working_chassis:
        for s in broken_sensors[ch]:
            fService.turn_off_sensor(ch, s)

def end_measurement():
    if fService.is_service_running():
        fService.stop()
        stopMeasurement = True

# %%

    init_instrumentation()

    # time.sleep(2)

# %%

    fService.start()
    print ("fService started.")

    # time.sleep(2)

    # fService.start_data()
    # print("fService data started.")

    # time.sleep(2)

# %%

    fService.connect(ip_list)
    print ("fService ip list connected")

    # time.sleep(2)

# %%

    for_all_valid_sensors('restart_sensor')

    # time.sleep(2)

# %%

    for_all_valid_sensors('coarse_zero_sensor')
    
    # time.sleep(2)

# %%

    for_all_valid_sensors('fine_zero_sensor')
    # time.sleep(2)
    
# %%

    threading.Thread(target=DataRetreiverThread, daemon=True).start()


# turn-on the worker thread
init_measurement()

time.sleep(2)

end_measurement()


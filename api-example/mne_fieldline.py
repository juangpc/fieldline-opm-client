import mne_fieldline_lib as lib

def set_config_file(*argv):
    print(argv)

def connect():
    lib.init_fieldline_connection()
    lib.init_fieldtrip_connection()
    lib.init_sensors()

def start_measurement():
    if lib.are_sensors_ready():
        lib.init_aquisition()
    else:
        print("Sensors are not initialized")

def stop_measurement():
    lib.stop_measurement()

def disconnect():
    lib.stop_service()

class main_runner:
    def __init__(self):
        connect()
        init_sensors()

    def __del__(self):
        stop_measurement()
        disconnect()

if __name__ == "__main__":
    mr = main_runner()
    input("Press any key to stop")
    

import mne_fieldline_lib as lib

def connect():
    lib.init_fieldline_connection()
    lib.init_fieldtrip_connection()
    lib.init_sensors()

def start_measurement():
    if lib.are_sensors_ready():
        lib.init_acquisition()
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
        pass

    def __del__(self):
        print("Destructor called") 
        stop_measurement()
        disconnect()
        
if __name__ == "__main__":
    mr = main_runner()
    
    continue_loop = True
    while(continue_loop):
        print("Commands:")
        print("\tStart Measurment - start")
        print("\tStop Measurement - stop")
        print("\tDisconnect and exit - exit")
        command = input("Select command: ")
        if command == "start":
            print("Starting measurement...")
            start_measurement()
        elif command == "stop":
            print("Stopping measurement...")
            stop_measurement()
        elif command == "exit":
            print("Exiting program.")
            continue_loop = False

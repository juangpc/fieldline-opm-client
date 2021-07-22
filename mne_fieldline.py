import mne_fieldline_lib as lib

def connect():
    print("About to Connect")
    lib.init_fieldline_connection()
    lib.init_fieldtrip_connection()

def tune_sensors():
    lib.init_sensors()

def start_measurement():
    lib.init_acquisition()
    # if lib.are_sensors_ready():
    #     lib.init_acquisition()
    # else:
    #     print("Sensors are not initialized")

def stop_measurement():
    lib.stop_measurement()

def disconnect():
    lib.stop_service()

def print_commands():
    print("Commands:")
    print("\tInitialize sensors - init")
    print("\tStart Measurment - start")
    print("\tStop Measurement - stop")
    print("\tDisconnect and exit - exit")

if __name__ == "__main__":
    connect()

    print("\t ************************************************")
    print("\t ************************************************")
    print("\t ******                                   *******")
    print("\t ******             IMPORTANT             *******")
    print("\t ******                                   *******")
    print("\t ******     MAKE SURE YOU INITIALIZE      *******")
    print("\t ******   THE SENSORS BEFORE YOU START    *******")
    print("\t ******                                   *******")
    print("\t ************************************************")
    print("\t ************************************************")

    continue_loop = True
    while(continue_loop):

        print_commands()

        command = input("Select command: ")
        if command == "start":
            print("Starting measurement...")
            start_measurement()
        elif command == "stop":
            print("Stopping measurement...")
            stop_measurement()
        elif command == "init":
            tune_sensors()
        elif command == "exit":
            print("Exiting program.")
            continue_loop = False
            print("Destructor called")

    stop_measurement()
    disconnect()

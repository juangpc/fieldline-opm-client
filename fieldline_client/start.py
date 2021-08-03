from .lib import (init_fieldline_connection, init_sensors,
                  init_acquisition, stop_measurement,
                  stop_service, init_fieldtrip_connection)

def connect():
    print("About to Connect")
    init_fieldline_connection()
    init_fieldtrip_connection()

def tune_sensors():
    init_sensors()

def start_measurement():
    init_acquisition()
    # if are_sensors_ready():
    #     init_acquisition()
    # else:
    #     print("Sensors are not initialized")

def stop_measurement():
    stop_measurement()

def disconnect():
    stop_service()

def print_commands():
    print("Commands:")
    print("\tInitialize sensors - init")
    print("\tStart Measurment - start")
    print("\tStop Measurement - stop")
    print("\tDisconnect and exit - exit")

def main():
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

if __name__ == '__main__':
    main()

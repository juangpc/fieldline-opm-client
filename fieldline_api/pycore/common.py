import csv
import appdirs
import pathlib
import os
import json

try:
    from app_version import APP_VERSION
except Exception:
    APP_VERSION = "unknown"

MAX_SENSORS_PER_CHASSIS = 16

CHASSIS_CONFIG_CSV_NAME = '.last-chassis-config-used'
USER_PREF_FILENAME = '.user-preferences'

PERFORMANCE_LOGGING_PERIOD = 60000


ACTIVE_REGISTERS = {
    "B_Z_Open": 28,
    "B_Z_Closed": 50
}

CHASSIS_ACTIVE_REGISTERS = {
    "Analog In": 0
}


def read_chassis_config(csv_path=None):
    chassis_name_to_id = {}
    if csv_path is None:
        csv_path = os.path.join(get_app_data_dir(), CHASSIS_CONFIG_CSV_NAME)
    if os.path.exists(csv_path):
        with open(csv_path) as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                chassis_name_to_id[row['chassis_name']] = int(row['chassis_id'])
    return chassis_name_to_id


def write_chassis_config(chassis_name_to_id, csv_path=None):
    if csv_path is None:
        csv_path = os.path.join(get_app_data_dir(), CHASSIS_CONFIG_CSV_NAME)
    with open(csv_path, 'w') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=['chassis_name', 'chassis_id'])
        writer.writeheader()
        for chassis_name, chassis_id in chassis_name_to_id.items():
            writer.writerow({'chassis_name': chassis_name,
                             'chassis_id': chassis_id})


def get_app_data_dir():
    # Cross-platform way to get application data folder, e.g.
    #   * Unix:    ~/.local/share/Recorder/sensor-locations.csv
    #   * Mac:     /Users/username/Library/Application Support/Recorder
    #   * Windows: C:\Users\username\AppData\Local\FieldLine\Recorder
    directory = appdirs.user_data_dir(appname='Recorder', appauthor='FieldLine')
    pathlib.Path(directory).mkdir(parents=True, exist_ok=True)
    return directory


def get_log_dir():
    log_dir = os.path.join(get_app_data_dir(), "Logs")
    pathlib.Path(log_dir).mkdir(parents=True, exist_ok=True)
    return log_dir


def get_sensor_config_path():
    return os.path.join(get_app_data_dir(), "sensor_config.json")


def update_user_pref(field, value):
    prefs = {}
    path = os.path.join(get_app_data_dir(), USER_PREF_FILENAME)
    if os.path.exists(path):
        mode = 'r+'
    else:
        mode = 'a+'
    with open(path, mode) as f:
        try:
            prefs = json.load(f)
        except json.decoder.JSONDecodeError:
            pass
        prefs[field] = value
        f.seek(0)
        json.dump(prefs, f)
        f.truncate()


def get_user_pref(field, default_value=None):
    prefs = {}

    try:
        with open(os.path.join(get_app_data_dir(), USER_PREF_FILENAME), 'r') as f:
            prefs = json.load(f)
    except (FileNotFoundError, json.decoder.JSONDecodeError):
        pass

    return prefs[field] if field in prefs else default_value


def get_enable_developer_mode():
    p = pathlib.Path(os.path.join(get_app_data_dir(), "enable-developer-mode"))
    if p.exists():
        with p.open() as f:
            password = f.read().strip()
        return True, password
    return False, None

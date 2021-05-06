from enum import Enum


class FieldLineDataType(Enum):
    DATA_BZ = 0
    DATA_BY = 1
    DATA_BX = 2


class FieldLineWaveType(Enum):
    WAVE_OFF = 0
    WAVE_RAMP = 1
    WAVE_SINE = 2

class FieldLineSensorStatusType(Enum):
    SENSOR_OFF = 0
    SENSOR_RESTARTING = 1
    SENSOR_RESTARTED = 2
    SENSOR_COARSE_ZEROING = 3
    SENSOR_COARSE_ZEROED = 4
    SENSOR_FINE_ZEROING = 5
    SENSOR_FINE_ZEROED = 6
    SENSOR_ERROR = 7
    SENSOR_READY = 8

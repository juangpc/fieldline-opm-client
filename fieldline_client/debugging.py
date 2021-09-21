working_chassis = [0, 1]
broken_sensors = [(2, 6, 16),()]
working_sensors = [(1, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15),
                   (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14)]

#### FIELDTRIP BUFFER SETTINGS
ft_IP = 'localhost'
ft_port = 1972

channel_names = []
for chassis in working_chassis:
        for s in working_sensors[chassis]:
                label = 'OPM' + '|' + str(chassis) + '|' + str(s)
                print(label)
                channel_names.append(label)
                
num_working_sensors = len(working_sensors[0]) + len(working_sensors[1])


import numpy as np
from FieldTrip import Client, DATATYPE_FLOAT32
import time

ft_client = Client()

ft_client.connect(ft_IP, ft_port)

if ft_client.isConnected:
        print("Fieldtrip Client connected")



ft_client.putHeader(len(channel_names), 1000, DATATYPE_FLOAT32, channel_names)

header = ft_client.getHeader()
print(header)

data = np.random.rand(1000, len(channel_names)).astype(np.float32) * 1e-12

ft_client.putData(data)


while True:
  data = np.random.rand(1000, len(channel_names)).astype(np.float32) * 1e-12
  ft_client.putData(data)
  time.sleep(1)
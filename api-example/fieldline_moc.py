
#fieldlinemoc
import numpy
import threading
import FieldTrip



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
                data = numpy.random.rand(self.num_samples, self.num_sensors).astype(numpy.float32)
                self.ft_client.putData(data)


import queue


class FieldLineCallback:
    def __init__(self):
        # data_q is required
        # main way data is passed to client program
        # as written the queue is unbounded and if client is unable to keep up, the queue will continue to grow.
        self.data_q = queue.Queue()

    def callback_chassis_connected(self, chassis_name, chassis_id):
        """
            Required callback

            Called when new chassis is discovered.

            chassis_name - human readable name for chassis
            chassis_id - unique integer ID of chassis. Beyond this call, chassis will always be identified by this ID.
        """
        pass

    def callback_chassis_disconnected(self, chassis_id):
        """
            Required callback

            Called when chassis has disconnected.

            chassis_id - unique integer ID of chassis.
        """
        pass

    def callback_sensors_available(self, chassis_id, sensor_list):
        """
            Required callback

            Called when list of sensors for chassis has been received.

            chassis_id - unique integer ID of chassis.
        """
        pass

    def callback_sensor_ready(self, chassis_id, sensor_id):
        """
            Required callback

            Called when sensor has been initialized and is ready to be restarted.

            chassis_id - unique integer ID of chassis.
            sensor_id - sensor number
        """
        pass

    def callback_restart_begin(self, chassis_id, sensor_id):
        """
            Required callback

            Called when restart of a sensor has begun.

            chassis_id - unique integer ID of chassis.
            sensor_id - sensor number
        """
        pass

    def callback_restart_complete(self, chassis_id, sensor_id):
        """
            Required callback

            Called when restart of a sensor is completed.

            chassis_id - unique integer ID of chassis.
            sensor_id - sensor number
        """
        pass

    def callback_coarse_zero_begin(self, chassis_id, sensor_id):
        """
            Required callback

            Called when coarse zero of a sensor has begun.

            chassis_id - unique integer ID of chassis.
            sensor_id - sensor number
        """
        pass

    def callback_coarse_zero_complete(self, chassis_id, sensor_id):
        """
            Required callback

            Called when coarse zero of a sensor is completed.

            chassis_id - unique integer ID of chassis.
            sensor_id - sensor number
        """
        pass

    def callback_fine_zero_begin(self, chassis_id, sensor_id):
        """
            Required callback

            Called when fine zero of a sensor has begun.

            chassis_id - unique integer ID of chassis.
            sensor_id - sensor number
        """
        pass

    def callback_fine_zero_complete(self, chassis_id, sensor_id):
        """
            Required callback

            Called when fine zero of a sensor is completed.

            chassis_id - unique integer ID of chassis.
            sensor_id - sensor number
        """
        pass

    def callback_sensor_error(self, chassis_id, sensor_id, msg):
        """
            Required callback

            Called when sensor startup or zero has encountered an error.

            chassis_id - unique integer ID of chassis.
            sensor_id - sensor number
            msg - any error message given
        """
        pass

    def callback_led_changed(self, chassis_id, sensor_id, color, blink_state):
        """
            Required callback

            Called when LED changes

            chassis_id - unique integer ID of chassis.
            sensor_id - sensor number
            color - color of LED
            blink_state - state of LED
        """
        pass

    def callback_data_available(self, sample_list):
        """
            Required callback

            Called when new list of 10 data samples is available

            sample_list - list of 10 samples
        """
        self.data_q.put(sample_list)

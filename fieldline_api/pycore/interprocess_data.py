from multiprocessing.shared_memory import SharedMemory
from multiprocessing import Semaphore, Value, Event
import struct
from collections import namedtuple
import queue
import threading
import logging

DataPacket = namedtuple("DataPacket", ["timestamp", "data"])
DataFrame = namedtuple("DataFrame", ["sensor", "datatype", "val"])


class InterprocessDataPacketQueue():
    def __init__(self, name, create, shared_value=None, semaphore=None, clear_event=None, clear_done_event=None):
        self.buffer_size = (2 ** 26)
        self.running = True
        if create:
            self.free_memory = Value("d", self.buffer_size)
            self.sem = Semaphore(0)
            self.clear_event = Event()
            self.clear_done_event = Event()
        else:
            self.free_memory = shared_value
            self.sem = semaphore
            self.clear_event = clear_event
            self.clear_done_event = clear_done_event
            clear_thread = threading.Thread(target=self._wait_for_clear)
            clear_thread.start()

        self.write_index = 0
        self.read_index = 0
        self.name = name
        self.created = create
        self.shm = SharedMemory(name=name, create=create, size=self.buffer_size)

    def close(self):
        self.shm.close()
        if self.created:
            self.shm.unlink()
        self.running = False

    def _wait_for_clear(self):
        while self.running:
            if self.clear_event.wait(timeout=2):
                self.read_index = 0
                self.write_index = 0
                self.clear_event.clear()
                logging.info("did wait_for_clear")
                self.clear_done_event.set()

    def get_available_memory(self):
        return self._available_bytes()

    def put(self, packet):
        if self._packet_size(packet) > self._available_bytes():
            raise queue.Full(f"Buffer {self.name} does not have enough room to write")

        self._write_ui32(packet.timestamp)
        self._write_i32(len(packet.data))
        write_bytes = bytes()
        for data_frame in packet.data:
            write_bytes += struct.pack("iii", data_frame.sensor, data_frame.datatype, data_frame.val)
        self.free_memory.value -= (8 + (len(packet.data) * 12))
        self._write_bytearray(write_bytes)
        self.sem.release()

    def get(self, block=True, timeout=None):
        if not self.sem.acquire(block, timeout):
            raise queue.Empty
        timestamp = self._read_ui32()
        data_length = self._read_i32()
        data = []
        for i in range(data_length):
            read_bytes = self._read_bytearray(12)
            sensor, datatype, val = struct.unpack("iii", read_bytes)
            data.append(
                DataFrame(
                    sensor=sensor,
                    datatype=datatype,
                    val=val
                )
            )
        self.free_memory.value += 8 + (data_length * 12)
        return DataPacket(timestamp=timestamp, data=data)

    def qsize(self):
        return self.sem.get_value()

    def clear(self):
        logging.info("clear queue")
        self.read_index = 0
        self.write_index = 0
        self.free_memory.value = self.buffer_size
        while self.sem.acquire(block=False):
            pass
        self.clear_event.set()
        if self.clear_done_event.wait(timeout=2):
            logging.info("clear queue complete")
            self.clear_done_event.clear()
        else:
            logging.warning("clear done timed out")

    def _packet_size(self, packet):
        return 8 + (12 * len(packet.data))

    def _available_bytes(self):
        return self.free_memory.value

    def _read_bytearray(self, length):
        wrapped_bytes_len = (self.read_index + length) - self.buffer_size
        if wrapped_bytes_len > 0:
            read_bytes = self.shm.buf[self.read_index:].tobytes()
            read_bytes += self.shm.buf[:wrapped_bytes_len].tobytes()
            self.read_index = wrapped_bytes_len
        else:
            read_bytes = self.shm.buf[self.read_index:self.read_index + length].tobytes()
            self.read_index += length
        return read_bytes

    def _read_i32(self):
        read_bytes = self._read_bytearray(4)
        return struct.unpack("i", read_bytes)[0]

    def _read_ui32(self):
        read_bytes = self._read_bytearray(4)
        return struct.unpack("I", read_bytes)[0]

    def _write_ui32(self, write_int):
        write_bytes = struct.pack("I", write_int)
        self._write_bytearray(write_bytes)

    def _write_i32(self, write_int):
        write_bytes = struct.pack("i", write_int)
        self._write_bytearray(write_bytes)

    def _write_bytearray(self, write_bytes):
        num_bytes = len(write_bytes)
        wrapped_bytes_len = (self.write_index + num_bytes) - self.buffer_size
        if wrapped_bytes_len > 0:
            first_byte_length = num_bytes - wrapped_bytes_len
            self.shm.buf[self.write_index:] = write_bytes[:first_byte_length]
            self.shm.buf[:wrapped_bytes_len] = write_bytes[first_byte_length:]
            self.write_index = wrapped_bytes_len
        else:
            self.shm.buf[self.write_index:self.write_index + num_bytes] = write_bytes
            self.write_index = self.write_index + num_bytes

from multiprocessing import Process
import logging
from logging.handlers import RotatingFileHandler
import os
import threading
import time
import socket
import queue
import ssl


from pycore.fieldline_message import parse_message, write_header, read_header, Msgtype, HEADER_LENGTH
# import pycore.net_protocol_pb2 as proto
import net_protocol_pb2 as proto
from pycore import common
from pycore.interprocess_data import InterprocessDataPacketQueue

HB_INTERVAL = 1


class DataError(Exception):
    pass


def _protobuf_proc(address, port, status_cb, resp_cb, data_queue_name, shared_value, semaphore, clear_event, clear_done_event, cmd_queue, status_queue, resp_queue, shutdown_queue, password_queue, password_callback, log_level, streaming_event, shutdown_event, done_event):
    directory = common.get_log_dir()
    filename = "fieldline-recorder-worker-%s-%d.log" % (address, port)
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s %(threadName)s(%(process)d) %(message)s [%(filename)s:%(lineno)d]',
        '%m/%d/%Y %I:%M:%S %p'
    )
    handler = RotatingFileHandler(os.path.join(directory, filename), maxBytes=200000, backupCount=10)
    handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt='%(asctime)s %(levelname)s %(threadName)s(%(process)d) %(message)s [%(filename)s:%(lineno)d]',
        datefmt='%m/%d/%Y %I:%M:%S %p'
    )
    handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)

    logger = logging.getLogger(filename)
    logger.addHandler(handler)
    logger.addHandler(stream_handler)
    logger.setLevel(log_level)
    logger.info(f"Worker Proccess for {address}:{port} {common.APP_VERSION} is starting.")

    data_queue = InterprocessDataPacketQueue(data_queue_name, False, shared_value, semaphore, clear_event, clear_done_event)
    # Recreate NetworkClient object in new process as windows does not support copy on write
    # the parameters to this function are pickled for use in the new process
    client = NetworkClient(
        address=address,
        port=port,
        status_callback=status_cb,
        raw_cmd_resp_callback=resp_cb,
        data_queue=data_queue,
        cmd_queue=cmd_queue,
        status_queue=status_queue,
        resp_queue=resp_queue,
        password_queue=password_queue,
        password_callback=password_callback,
        shutdown_queue=shutdown_queue,
        logger=logger,
        streaming_event=streaming_event,
        shutdown_event=shutdown_event,
        done_event=done_event
    )
    logger.info(f"Process client created for {address}")
    data_t = threading.Thread(target=client.data_thread)
    data_t.daemon = True
    data_t.start()
    logger.info(f"Process started data thread for {address}")

    def shutdown_monitor():
        client.protobuf_shutdown_q.get(block=True)
        client.done.set()

    shutdown_t = threading.Thread(target=shutdown_monitor)
    shutdown_t.start()

    shutdown_t.join()
    data_t.join(timeout=5.0)
    if data_t.is_alive():
        logger.error("data_t thread still running after timeout")
    client.data_queue.close()
    # remaining_threads = [t.getName() for t in threading.enumerate()]
    # if len(remaining_threads):
    #     logger.warning(f"Threads still running after joins {remaining_threads}")


class NetworkClient(object):
    def __init__(self, address, port, status_callback, raw_cmd_resp_callback, data_queue, cmd_queue, status_queue, resp_queue, shutdown_queue, password_queue, password_callback, logger, streaming_event, shutdown_event, done_event):
        super(NetworkClient, self).__init__()
        self.address = address
        self.port = port
        self.connected = False
        self.done = done_event
        self.done.set()
        self.data_queue = data_queue
        self.cmd_queue = cmd_queue
        self.status_queue = status_queue
        self.raw_cmd_resp_queue = resp_queue
        self.password_queue = password_queue
        self.protobuf_shutdown_q = shutdown_queue
        self.last_status = None
        self.socket = None
        self.ssl_socket = None
        self.ssl_connected = False
        self.status_callback = status_callback
        self.raw_cmd_resp_callback = raw_cmd_resp_callback
        self.password_callback = password_callback
        self.chassis_name = 'unknown'
        self.chassis_id = None
        self.logger = logger
        self.protobuf_proc = None
        self.streaming_data = streaming_event
        self.shutdown_event = shutdown_event
        self.server_version = None
        self.waiting_for_password_validation = False
        self.monitor_process_thread = None
        self.hb_lock = threading.RLock()

    def num_samples_available(self):
        return self.data_queue.qsize()

    def available_data_buf(self):
        return self.data_queue.get_available_memory()

    def _read_status(self):
        while self.protobuf_proc:
            try:
                msg = self.status_queue.get(block=True, timeout=0.25)
            except queue.Empty:
                continue

            self.last_status = msg
            self.chassis_name = msg.chassis_name
            if self.server_version != msg.version:
                logging.info("Chassis %s on version %s" % (self.chassis_name, msg.version))
            self.server_version = msg.version
            if self.status_callback:
                self.status_callback(msg)
        logging.info("_read_status exited")

    def _read_raw_cmd_resp(self):
        while self.protobuf_proc:
            try:
                msg = self.raw_cmd_resp_queue.get(block=True, timeout=0.25)
            except queue.Empty:
                continue

            if self.raw_cmd_resp_callback:
                logging.info("Raw Response 0x%x" % (msg.raw_cmd.register_address))
                self.raw_cmd_resp_callback(msg)
        logging.info("_read_raw_cmd_resp exited")

    def _read_password_resp(self):
        while self.protobuf_proc:
            try:
                msg = self.password_queue.get(block=True, timeout=0.25)
            except queue.Empty:
                continue
            if self.password_callback:
                if msg.dev_mode.enable and not self.waiting_for_password_validation:
                    return
                self.waiting_for_password_validation = False
                self.password_callback(self.chassis_name, msg)
        logging.info("_read_password_resp exited")

    def start_streaming(self):
        self.logger.info("Start Streaming")
        self.streaming_data.set()

    def stop_streaming(self):
        self.logger.info("Stop Streaming")
        self.streaming_data.clear()
        self.clear_data_queue()

    def clear_data_queue(self):
        self.data_queue.clear()

    def start(self):
        self.logger.info("start client %s" % self.address)
        time.sleep(0.5)
        self.protobuf_proc = Process(
            target=_protobuf_proc, args=(
                self.address,
                self.port,
                None,
                None,
                self.data_queue.name,
                self.data_queue.free_memory,
                self.data_queue.sem,
                self.data_queue.clear_event,
                self.data_queue.clear_done_event,
                self.cmd_queue,
                self.status_queue,
                self.raw_cmd_resp_queue,
                self.protobuf_shutdown_q,
                self.password_queue,
                None,
                logging.getLogger().getEffectiveLevel(),
                self.streaming_data,
                self.shutdown_event,
                self.done
            )
        )
        self.protobuf_proc.start()

        self.status_thread = threading.Thread(target=self._read_status)
        self.status_thread.daemon = True
        self.status_thread.start()

        self.raw_cmd_resp_thread = threading.Thread(target=self._read_raw_cmd_resp)
        self.raw_cmd_resp_thread.daemon = True
        self.raw_cmd_resp_thread.start()

        self.password_resp_thread = threading.Thread(target=self._read_password_resp)
        self.password_resp_thread.daemon = True
        self.password_resp_thread.start()

        self.monitor_process_thread = threading.Thread(target=self._monitor_process)
        self.monitor_process_thread.start()
        self.logger.info("client started %s" % self.address)
        self.cmd_request_status()

    def _monitor_process(self):
        self.protobuf_proc.join()
        logging.info(f"Protobuf process for {self.address} has exited")
        self.protobuf_proc = None
        self.data_queue.close()

    def stop(self):
        logging.info(f"stop {self.address}")
        self.done.set()
        logging.info(f"stop {self.address} complete")

    def force_reconnect(self):
        logging.info(f"force reconnect {self.address}")
        self.done.set()

    def shutdown(self):
        logging.info(f"shutdown {self.address}")
        self.shutdown_event.set()
        self.done.set()
        self.protobuf_shutdown_q.put('time... to die')
        logging.info(f"shutdown {self.address} waiting on threads")
        if self.raw_cmd_resp_thread:
            self.raw_cmd_resp_thread.join()
        if self.password_resp_thread:
            self.password_resp_thread.join()
        if self.monitor_process_thread:
            self.monitor_process_thread.join()
        logging.info(f"shutdown {self.address} complete")

    def wait(self):
        logging.info(f"Waiting for {self.address} to finish")
        if self.monitor_process_thread:
            self.monitor_process_thread.join()
            logging.info("join complete")
        logging.info(f"Chassis has finished {self.address}")

    def hb_thread(self):
        MAX_HEARTBEATS = 4
        missed_hearbeats = 0
        self.received_msg = True
        while not self.done.is_set() and not self.hb_expired.is_set():
            with self.hb_lock:
                if self.received_msg:
                    self.received_msg = False
                    missed_hearbeats = 0
                else:
                    missed_hearbeats += 1
                    if missed_hearbeats > MAX_HEARTBEATS:
                        self.logger.warn("Timeout waiting for heartbeat. Closing connection.")
                        self.hb_expired.set()
                        continue
                    self.cmd_request_status()

            time.sleep(HB_INTERVAL)

    def reset_hb_time(self):
        with self.hb_lock:
            self.received_msg = True

    @staticmethod
    def _read_socket_bytes(ssl_socket, num_bytes):
        try:
            recv_msg = bytearray()
            while len(recv_msg) < num_bytes:
                len_before = len(recv_msg)
                try:
                    recv_msg += ssl_socket.recv(num_bytes - len_before)
                except BlockingIOError:
                    continue
                if len(recv_msg) == len_before:
                    logging.info("Read 0 bytes...")
                    raise DataError("Could not read data from socket.")

        except socket.timeout:
            # logging.info("Socket timeout")
            return None
        return recv_msg

    def _read_msg(self):
        header = NetworkClient._read_socket_bytes(self.ssl_socket, HEADER_LENGTH)
        if header is None:
            return
        msgtype, msglen = read_header(header)

        data = NetworkClient._read_socket_bytes(self.ssl_socket, msglen)

        msg = parse_message(msgtype, data)

        if msgtype == Msgtype.DATA.value:
            self.reset_hb_time()
            if self.streaming_data.is_set():
                self.data_queue.put(msg)
        elif msgtype == Msgtype.STATUS.value:
            # self.logger.debug("Got STATUS msg")
            self.reset_hb_time()
            self.status_queue.put(msg)
        elif msgtype == Msgtype.CMD.value:
            self.logger.debug("Got CMD msg")
            self.reset_hb_time()
            # We get CMD messages as responses to raw_cmd sends
            if msg.HasField('raw_cmd'):
                self.raw_cmd_resp_queue.put(msg)
            elif msg.HasField('dev_mode'):
                self.password_queue.put(msg)
            else:
                self.logger.warn("Got a CMD message, but did not have raw_cmd field, ignoring")
        else:
            self.logger.warn(f"Unknown message type: {msgtype}")
            raise DataError(f"Unknown message type: {msgtype}")

    @staticmethod
    def send_one_time_command(packet, address, port, expect_response=None):
        ret = None
        context = ssl._create_unverified_context()
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conn.settimeout(5)
        ssl_conn = context.wrap_socket(conn, server_hostname=address)
        try:
            ssl_conn.connect((address, port))
        except:
            return ret
        msg = packet.SerializeToString()
        ssl_conn.sendall(write_header(Msgtype.CMD.value, len(msg)) + msg)
        if expect_response is not None:
            resp = None
            result_type = None
            while result_type != expect_response:
                header = NetworkClient._read_socket_bytes(ssl_conn, HEADER_LENGTH)
                if header is None:
                    return
                msgtype, msglen = read_header(header)

                data = NetworkClient._read_socket_bytes(ssl_conn, msglen)

                ret = parse_message(msgtype, data)
                if msgtype == Msgtype.STATUS.value:
                    result_type = ret.type
        ssl_conn.close()
        conn.close()
        return ret

    @staticmethod
    def send_ident_request(is_on, address, port):
        packet = NetworkClient.create_ident_packet(is_on)
        NetworkClient.send_one_time_command(packet, address, port)

    @staticmethod
    def send_connect_req(address, port):
        packet = proto.CmdPacket()
        packet.cmd = proto.CmdPacket.SYSTEM_STATUS_REQ
        ret = NetworkClient.send_one_time_command(packet, address, port, expect_response=proto.StatusPacket.SYSTEM_STATUS)
        return ret

    @staticmethod
    def create_ident_packet(is_on):
        packet = proto.CmdPacket()
        packet.cmd = proto.CmdPacket.IDENT_REQ
        packet.chassis_ident = is_on
        return packet

    @property
    def is_connected(self):
        return not self.done.is_set()

    def data_thread(self):
        self.hb_expired = threading.Event()
        NUM_RETRIES = 30
        retries = NUM_RETRIES
        ORIG_DELAY = 1
        NEW_DELAY = 5
        connect_delay = ORIG_DELAY
        heartbeat_thread = None
        cmd_thread = None
        reconnecting = False
        self.logger.info("Starting data thread for %s" % self.address)
        while not self.shutdown_event.is_set():
            self.hb_expired.clear()
            if reconnecting:
                self.logger.info(f"Trying to reconnect to {self.address}")
                reconnecting = False
            context = ssl._create_unverified_context()
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(3)
            self.ssl_socket = context.wrap_socket(self.socket, server_hostname=self.address)
            try:
                # self.logger.info("Connecting to %s:%s" % (self.address, self.port))
                self.ssl_socket.connect((self.address, self.port))
                self.ssl_connected = True
                self.logger.info("Connected to %s:%s" % (self.address, self.port))
            except ConnectionRefusedError as e:
                # self.logger.info("Connection refused: %s" % self.address)
                pass
            except socket.timeout:
                # self.logger.info("Connection socket timeout: %s" % self.address)
                pass
            except OSError as e:
                # self.logger.info("Connection OSError: %s" % e)
                pass
            except Exception as e:
                error = "Error connecting to %s:%s: %s" % (self.address, self.port, str(e))
                self.logger.error(error, exc_info=True)
            if not self.ssl_connected:
                if retries > 0:
                    retries -= 1
                    if retries == 0:
                        connect_delay = NEW_DELAY
                        self.logger.info("Device %s not found, increasing reconnect delay" % self.address)
                if not self.shutdown_event.is_set():
                    time.sleep(connect_delay)
                continue
            connect_delay = ORIG_DELAY
            retries = NUM_RETRIES
            self.done.clear()
            cmd_thread = threading.Thread(target=self.cmd_thread)
            cmd_thread.start()
            heartbeat_thread = threading.Thread(target=self.hb_thread)
            heartbeat_thread.start()

            self.last_hb_recv = time.time()
            self.cmd_system_status()

            while not self.done.is_set() and not self.hb_expired.is_set():
                try:
                    self._read_msg()
                except queue.Full:
                    self.logger.error("Memory buffer full, stopping streaming", exc_info=True)
                    self.stop_streaming()
                    continue
                except DataError as de:
                    self.logger.info("Connection closed: %s" % de)
                    self.stop()
                    break
                except Exception:
                    self.logger.error("Closing connection", exc_info=True)
                    self.stop()
                    break
            self.logger.info(f"Msg read loop ended: {self.address}")
            if self.ssl_socket is not None:
                try:
                    self.ssl_socket.close()
                    self.socket.close()
                except Exception:
                    self.logger.warn("Problem shutting down socket", exc_info=True)
            if self.hb_expired.is_set():
                self.stop()
            self.logger.info(f"After hb stop {self.address}")
            if heartbeat_thread:
                heartbeat_thread.join()
                heartbeat_thread = None
            self.logger.info(f"After hb thread join {self.address}")
            if cmd_thread:
                cmd_thread.join()
                cmd_thread = None
            self.logger.info(f"After cmd thread join {self.address}")
            self.ssl_connected = False
            self.socket = None
            self.ssl_socket = None
            reconnecting = True
            time.sleep(connect_delay)
        self.logger.info("Exiting subprocess data thread!")

    def cmd_thread(self):
        # Wait for the socket to be created
        while not self.ssl_connected and not self.done.is_set():
            time.sleep(0.1)
        while not self.done.is_set():
            try:
                cmd = self.cmd_queue.get(block=True, timeout=0.25)
            except queue.Empty:
                continue
            # Retry sending a message in case the socket is not open yet
            retry_count = 0
            while retry_count < 3 and not self.done.is_set():
                try:
                    self.ssl_socket.sendall(write_header(Msgtype.CMD.value, len(cmd)) + cmd)
                    break
                except OSError:
                    pass
                except Exception:
                    logging.exception("Could not send command")
                    retry_count += 1
        logging.info(f"cmd thread done: {self.address}")

    def _send_cmd(self, cmd, **kwargs):
        packet = proto.CmdPacket()
        packet.cmd = cmd
        for k, v in kwargs.items():
            setattr(packet, k, v)
        self._send_packet(packet)

    def _send_packet(self, packet):
        msg = packet.SerializeToString()
        self.cmd_queue.put(msg)

    def cmd_request_status(self):
        self._send_cmd(proto.CmdPacket.STATUS_REQ)

    def cmd_config_sensor_list(self, channel_list):
        packet = proto.CmdPacket()
        packet.cmd = proto.CmdPacket.CONFIG_LIST
        for c in channel_list:
            config_item = packet.config_list.add()
            config_item.sensor_id = c[0]
            config_item.datatype = c[1]
            config_item.freq = c[2]

        self._send_packet(packet)

    def cmd_reset(self):
        self._send_cmd(proto.CmdPacket.RESET_FPGA)

    def cmd_sensor_config_req(self):
        self._send_cmd(proto.CmdPacket.SENSOR_CONFIG_REQ)

    def cmd_update(self, uri):
        self._send_cmd(proto.CmdPacket.UPDATE, uri=uri)

    def cmd_commit(self):
        self._send_cmd(proto.CmdPacket.UPDATE_COMMIT)

    def cmd_reboot(self):
        self._send_cmd(proto.CmdPacket.REBOOT)

    def cmd_system_status(self):
        self._send_cmd(proto.CmdPacket.SYSTEM_STATUS_REQ)

    def cmd_raw(self, sensor_num, register_address, data):
        # TODO: don't send a new raw command until we get a response from the previous
        # TODO: keep track of register_address so we know which GUI row to populate when the response comes back
        logging.info(f"Sending RAW cmd to {self.address}: {self.port}; "
                     f"sensor_num={sensor_num}, register_address={hex(register_address)}, data={hex(data)}")
        packet = proto.CmdPacket()
        packet.cmd = proto.CmdPacket.RAW_CMD
        raw_cmd_body = packet.raw_cmd
        raw_cmd_body.all_sensors = False
        raw_cmd_body.sensor_num = sensor_num
        raw_cmd_body.register_address = register_address
        raw_cmd_body.data = data
        self._send_packet(packet)

    def cmd_wave_off(self, sensor_list):
        packet = proto.CmdPacket()
        packet.cmd = proto.CmdPacket.WAVE_REQ
        for s in sensor_list:
            wave_item = packet.wave_req.add()
            wave_item.sensor_id = s
            wave_item.type = proto.WaveMessage.WAVE_OFF
        self._send_packet(packet)

    def cmd_wave(self, sensor_list):
        packet = proto.CmdPacket()
        packet.cmd = proto.CmdPacket.WAVE_REQ
        for s in sensor_list:
            wave_item = packet.wave_req.add()
            wave_item.sensor_id = s[0]
            wave_item.type = s[1]
            wave_item.amp = s[2]
            wave_item.freq = s[3]
        self._send_packet(packet)

    def cmd_logic(self, sensor_list):
        packet = proto.CmdPacket()
        packet.cmd = proto.CmdPacket.LOGIC_REQ
        for s in sensor_list:
            logic_item = packet.logic_req.add()
            logic_item.sensor_id = s[0]
            logic_item.type = s[1]
        self._send_packet(packet)

    def cmd_one_time_read(self, sensor_num, register_address):
        packet = proto.CmdPacket()
        packet.cmd = proto.CmdPacket.ONE_TIME_READ_REQ
        raw_cmd_body = packet.raw_cmd
        raw_cmd_body.all_sensors = False
        raw_cmd_body.sensor_num = sensor_num
        raw_cmd_body.register_address = register_address
        raw_cmd_body.data = 0  # Data is not used but required
        self._send_packet(packet)

    def cmd_send_password(self, password):
        cmd_packet = proto.CmdPacket()
        cmd_packet.cmd = proto.CmdPacket.DEV_MODE_REQ
        dev_mode_packet = cmd_packet.dev_mode
        dev_mode_packet.password = password
        dev_mode_packet.enable = True
        self._send_packet(cmd_packet)
        self.waiting_for_password_validation = True

    def cmd_disable_developer_mode(self):
        cmd_packet = proto.CmdPacket()
        cmd_packet.cmd = proto.CmdPacket.DEV_MODE_REQ
        dev_mode_packet = cmd_packet.dev_mode
        dev_mode_packet.enable = False
        self._send_packet(cmd_packet)

    def cmd_ident(self, is_on):
        cmd_packet = NetworkClient.create_ident_packet(is_on)
        self._send_packet(cmd_packet)

    def cmd_closed_loop(self, is_on):
        cmd_packet = proto.CmdPacket()
        cmd_packet.cmd = proto.CmdPacket.CLOSED_LOOP_REQ
        cmd_packet.closed_loop = is_on
        self._send_packet(cmd_packet)

from enum import Enum
import struct
# import pycore.net_protocol_pb2 as proto
import net_protocol_pb2 as proto
import logging


class Msgtype(Enum):
    CMD = 1
    STATUS = 2
    DATA = 3


# The following two functions should always get changed together.
# It defines how we read and write headers.
# We are using 2 bytes for Message Type and 2 bytes for Length.
# If updating, check HEADER_LENGTH below
def write_header(msg_type, length):
    return struct.pack('>HH', msg_type, length)


def read_header(hdr):
    return struct.unpack('>HH', hdr)


# If changing, check read/write header functions above
HEADER_LENGTH = 4


def parse_message(msgtype, data):
    packet = None
    if msgtype == Msgtype.DATA.value:
        packet = proto.DataPacket()
    elif msgtype == Msgtype.STATUS.value:
        packet = proto.StatusPacket()
    elif msgtype == Msgtype.CMD.value:
        packet = proto.CmdPacket()
    else:
        logging.error("Got an unsupported packet type")
    if packet:
        packet.ParseFromString(data)
    return packet


SERVICE_NAME_ENV = 'FIELDLINE_SERVICE_NAME'

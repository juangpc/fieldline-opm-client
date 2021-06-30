
def create_channel_key_list(channel_list):
    channel_key_list = []
    for chassis in channel_list:
        for sensors in working_sensors[chassis]:
            key = str(chassis).zfill(2) + ':' + str(sensors).zfill(2) + ':' + str(28).zfill(2)
            channel_key_list.append(key)
    return channel_key_list
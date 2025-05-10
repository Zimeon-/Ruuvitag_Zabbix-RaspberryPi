import json
import re
import os
import time
import socket
import subprocess
from collections import defaultdict
import threading

from ruuvitag_sensor.ruuvi import RuuviTagSensor, RunFlag

# Load tag metadata from config
def load_ruuvitags():
    with open("/home/ruuvi/Ruuvitag/ruuvitags.json") as f:
        return json.load(f)

# Load config and build MAC-to-name mapping
ruuvitags = load_ruuvitags()
mac_to_name = {
    tag["mac"].lower().replace(":", ""): tag["name"] for tag in ruuvitags["config"]
}
configured_macs = list(mac_to_name.keys())

# Storage for collected sensor data
sensor_data_store = defaultdict(list)

# Handler to process incoming sensor data
def handle_data(found_data):
    mac, data = found_data
    mac = mac.lower().replace(":", "")
    if mac in mac_to_name:
        sensor_data_store[mac].append(data)

# Start scanning
print("Starting Bluetooth scan for 10 seconds...")
run_flag = RunFlag()
thread = threading.Thread(target=RuuviTagSensor.get_data, kwargs={
    'callback': handle_data,
    'run_flag': run_flag
})
thread.start()

# Collect for 30 seconds
time.sleep(30)
run_flag.running = False
thread.join()
print("Data collection complete.")

# Function to average numeric values
def average_values(data_list):
    if not data_list:
        return {}
    numeric_keys = [k for k in data_list[0] if isinstance(data_list[0][k], (int, float))]
    avg = {}
    for key in numeric_keys:
        values = [entry[key] for entry in data_list if key in entry and isinstance(entry[key], (int, float))]
        if values:
            avg[key] = sum(values) / len(values)
    return avg

# Write to Zabbix sender file
epoch_time = int(time.time())
zbxfile = f"/tmp/ruuvisender-{epoch_time}.data"
zbxhostname = socket.gethostname()

with open(zbxfile, "w") as f:
    for mac, samples in sensor_data_store.items():
        avg_data = average_values(samples)
        tag_name = mac_to_name.get(mac, mac)
        for key, value in avg_data.items():
            f.write(f"{zbxhostname} ruuvitag.{key}[{tag_name}] {value}\n")

# Send data to Zabbix
cmd = f"/usr/bin/zabbix_sender -c /etc/zabbix/zabbix_agent2.conf -i {zbxfile}"
proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
out, _ = proc.communicate()
output = out.decode("utf-8")

# Handle Zabbix sender output
zbxr = re.findall(r"failed: (\d+)", output)
zbxt = re.findall(r"total: (\d+)", output)

if zbxr and int(zbxr[0]) == 0:
    print(f"No Errors Detected, removing temporary file {zbxfile}")
    os.remove(zbxfile)
elif zbxt and int(zbxt[0]) == 0:
    print(f"Nothing sent to Zabbix Server, use {zbxfile} to debug.")
    with open(zbxfile, "a") as f:
        f.write(f"ZBX Sender:\n{output}")
else:
    print(f"Errors in Zabbix sender. Use {zbxfile} to debug.")
    with open(zbxfile, "a") as f:
        f.write(f"ZBX Sender:\n{output}")

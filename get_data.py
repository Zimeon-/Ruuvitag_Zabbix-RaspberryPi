#!/home/ruuvi/Ruuvitag/venv/bin/python3
# Standard library imports
import asyncio
import glob
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from bleak import BleakError
from bleak.exc import BleakDBusError
from collections import defaultdict
from datetime import datetime

# Third-party imports
from ruuvitag_sensor.ruuvi import RuuviTagSensor
import ruuvitag_sensor.log


ruuvitag_sensor.log.enable_console()
#Define Logfile
epoch_time = int(time.time())
# Format: YYYY-MM-DD
timestamp = datetime.now().strftime("%Y-%m-%d")
zbxlog = f"/tmp/ruuvisender-{timestamp}.log"

def log(message, filename=zbxlog):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(filename, "a", buffering=1) as f:
        f.write(line + "\n")

def cleanup_old_logs(log_dir="/tmp", pattern="ruuvisender-*.log", max_files=7):
    # List all matching log files
    log_files = glob.glob(os.path.join(log_dir, pattern))
    if len(log_files) <= max_files:
        return  # nothing to do

    # Sort by modification time, oldest first
    log_files.sort(key=lambda f: os.path.getmtime(f))

    # Delete oldest files if more than max_files
    files_to_delete = log_files[:-max_files]
    for f in files_to_delete:
        try:
            os.remove(f)
            log(f"Deleted old log file: {f}", zbxlog)
        except Exception as e:
            log(f"Failed to delete {f}: {e}", zbxlog)

# Load tag metadata from config
def load_ruuvitags():
    log("Loading ruuvitags.json configuration")
    with open("/home/ruuvi/Ruuvitag/ruuvitags.json") as f:
        return json.load(f)

# Build MAC-to-name mapping
ruuvitags = load_ruuvitags()
mac_to_name = {tag["mac"].lower().replace(":", ""): tag["name"] for tag in ruuvitags["config"]}

# Storage for collected sensor data
sensor_data_store = defaultdict(list)

def reset_hci0():
    """Reset hci0 safely and ensure it comes back up."""
    log("Resetting Bluetooth adapter hci0...")
    for cmd in [
        ["sudo", "hciconfig", "hci0", "down"],
        ["sudo", "hciconfig", "hci0", "reset"],
        ["sudo", "hciconfig", "hci0", "up"]
    ]:
        subprocess.run(cmd, check=True)

    # Wait until hci0 is up
    for i in range(10):
        result = subprocess.run(["hciconfig", "hci0"], capture_output=True, text=True)
        if "UP RUNNING" in result.stdout:
            log("Bluetooth adapter hci0 is up.")
            return
        log("Waiting for hci0 to come up...")
        time.sleep(1)
    log("Warning: hci0 did not come up after reset!")

def reset_bluetooth():
    log("Resetting bluetoothd...")
    subprocess.run(["sudo", "systemctl", "restart", "bluetooth"])

def handle_exit(sig, frame):
    log("Received signal, exiting cleanly...")
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_exit)
signal.signal(signal.SIGINT, handle_exit)

async def collect_data(duration=20, retries=2):
    data = {}
    unknown_tags = set()
    attempt = 0

    while attempt <= retries:
        log(f"Starting Bluetooth scan for {duration} seconds (attempt {attempt + 1})...")
        task = asyncio.create_task(_scan_task(data))
        try:
            await asyncio.sleep(duration)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                log("Scan task completed, flushing data...")
            break  # success
        except (BleakError, BleakDBusError) as e:
            log(f"Bluetooth scan error: {e}")
            if attempt < retries:
                log("Attempting to reset hci0 and retry...")
                reset_hci0()
                attempt += 1
                continue
            else:
                log("Max retries reached, aborting scan.")
                raise

    log(f"Data collection complete. Found {len(data)} tags.")
    return data, unknown_tags

async def _scan_task(data_store):
    try:
        async for mac, sensor_data in RuuviTagSensor.get_data_async():
            mac_clean = mac.lower().replace(":", "")
            log(f"Found {mac}: {sensor_data}")
            if mac_clean in mac_to_name:
                data_store[mac_clean] = sensor_data
            else:
                log(f"Warning: Found tag {mac} not in configuration file!", zbxlog)
                unknown_tags.add(mac)
    except asyncio.CancelledError:
        log("Scan task was cancelled.")
        raise

def write_zabbix_file(sensor_data_store, zbxfile, zbxhostname, mac_to_name):
    total_metrics = 0
    with open(zbxfile, "w") as f:
        for mac, data in sensor_data_store.items():
            tag_name = mac_to_name.get(mac, mac)
            numeric_items = {k: v for k, v in data.items() if isinstance(v, (int, float))}
            log(f"Preparing data for tag {tag_name} ({len(numeric_items)} metrics).")
            for key, value in numeric_items.items():
                f.write(f"{zbxhostname} ruuvitag.{key}[{tag_name}] {value}\n")
            total_metrics += len(numeric_items)

    log(f"Finished writing Zabbix file: {len(sensor_data_store)} tags, {total_metrics} metrics total.")

async def main():
    cleanup_old_logs()  # keep only 7 most recent logs
    # Write to Zabbix sender file
    zbxfile = f"/tmp/ruuvisender-{epoch_time}.data"
    zbxhostname = socket.gethostname()
    try:
        data, unknown_tags = await collect_data()
    except bleak.exc.BleakDBusError as e:
        if "InProgress" in str(e):
            log("Scan already in progress. Resetting adapter...")
            reset_hci0()
            await asyncio.sleep(1)  # allow time for adapter to settle
            data, unknown_tags = await collect_data()
        else:
            log("Unkown bleak.exc.BleakDBusError")
    if unknown_tags:
        log(f"Summary: {len(unknown_tags)} unknown tags detected: {', '.join(unknown_tags)}")
    # If no tags were collected, reset Bluetooth and retry once
    if len(data) == 0:
        log("Error: No RuuviTag data collected! Attempting Bluetooth reset and retry...")
        reset_bluetooth()
        time.sleep(2)  # short pause before retry
        data, unknown_tags = await collect_data()
        if len(data) == 0:
            log("Error: Still no RuuviTag data after Bluetooth reset. Exiting.")
            sys.exit(1)
        else:
            log(f"Recovered: Collected data from {len(data)} tags after Bluetooth reset.")
    else:
        log(f"Collected data from {len(data)} tags.")

    # Write the data to Zabbix file
    write_zabbix_file(data, zbxfile, zbxhostname, mac_to_name)

    # Send data to Zabbix
    cmd = f"/usr/bin/zabbix_sender -c /etc/zabbix/zabbix_agent2.conf -i {zbxfile}"
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    out, _ = proc.communicate()
    retcode = proc.wait()
    output = out.decode("utf-8")

    # Print Zabbix sender result
    if retcode != 0:
        log(f"Zabbix sender exited with code {retcode}")
    else:
        zbxr_failed = re.findall(r"failed: (\d+)", output)
        zbxr_processed = re.findall(r"processed: (\d+)", output)
        failed_count = int(zbxr_failed[0]) if zbxr_failed else 0
        processed_count = int(zbxr_processed[0]) if zbxr_processed else 0
        if failed_count > 0:
            log(f"Zabbix sender failed: {failed_count} items failed")
        elif processed_count == 0:
           log(f"Zabbix sender had nothing to process: {failed_count} items sent")
        else:
            log(f"Zabbix sender completed successfully. {processed_count} items sent.")
            os.remove(zbxfile)

if __name__ == "__main__":
    asyncio.run(main())

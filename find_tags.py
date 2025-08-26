#!/home/ruuvi/Ruuvitag/venv/bin/python3
"""
Find RuuviTags
"""
import asyncio
from ruuvitag_sensor.ruuvi import RuuviTagSensor
import ruuvitag_sensor.log

ruuvitag_sensor.log.enable_console()

async def main():
    sensors = await RuuviTagSensor.find_ruuvitags_async()
    for sensor in sensors:
        print(sensor.mac, sensor.update, sensor.data)

if __name__ == "__main__":
    asyncio.run(main())

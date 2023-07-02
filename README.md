# Ruuvitag_Zabbix-RaspberryPi
Ruuvitag Sensor datacollection to Zabbix with RaspberryPi Debian

How to use?

0. Follow the installation guide in https://github.com/ttu/ruuvitag-sensor to get the Ruuvitag python package functional. You can test ruuvitag functionality with the find_tags.py python script.
> With earlier RaspberryPi devices without built-in Bluetooth, you can use the Asus BT-500 USB Bluetooth dongle. Tested with Raspberry Pi 3 and Debian.
1. Install zabbix-agent or zabbix-agent2 and zabbix-sender
2. Import Zabbix Template
3. Clone git repository to /home/ruuvi/Ruuvitag and add u+x to the python files. Files in my example owned by the user ruuvi.
4. Configure your ruuvitags to the ruuvitags.json file (Bluetooth Mac, Zabbix Itemkey (Unique, without spaces or special characters), Displayname)
> To find your Ruuvitags, you can run the find_tags.py python file manually. Example output below:
```
ruuvi@ruuvi:~/Ruuvitag $ python find_tags.py
Finding RuuviTags. Stop with Ctrl+C.
Start receiving broadcasts (device hci0)
FYI: Calling a process with sudo: hciconfig hci0 reset
FYI: Spawning process with sudo: hcitool -i hci0 lescan2 --duplicates --passive
FYI: Spawning process with sudo: hcidump -i hci0 --raw
F3:B5:BD:53:F8:9D
{'data_format': 5, 'humidity': 45.3, 'temperature': 24.38, 'pressure': 980.96, 'acceleration': 1016.8343031192447, 'acceleration_x': -36, 'acceleration_y': -20, 'acceleration_z': 1016, 'tx_power': 4, 'battery': 3101, 'movement_counter': 70, 'measurement_sequence_number': 27397, 'mac': 'aabbcc443355'}
DE:8C:F1:D8:E2:D4
{'data_format': 5, 'humidity': 51.04, 'temperature': 23.23, 'pressure': 981.06, 'acceleration': 1053.7703734685276, 'acceleration_x': 52, 'acceleration_y': -32, 'acceleration_z': 1052, 'tx_power': 4, 'battery': 3083, 'movement_counter': 29, 'measurement_sequence_number': 27431, 'mac': 'aabbcc662244'}
^CStop receiving broadcasts
```
5. Add the following user parameters to your Zabbix agent configuration file

>Ruuvitag Key
>UserParameter=ruuvitag.get,python /home/ruuvi/Ruuvitag/get_data.py
>UserParameter=ruuvitag.discover,python /home/ruuvi/Ruuvitag/discover_tags.py

5. Add the following cron to the user ruuvi with #crontab -e
> */1 * * * * python /etc/zabbix/scripts/ruuvitag/get_data.py
6. Verify functionality with Zabbix.
> You can run the ruuvitag discovery manually in Zabbix frontend. This should create the neccessary items based on your ruuvitags.json file defined earlier.

Note: These scripts assume that they are located in "/home/ruuvi/Ruuvitag/" directory. If you choose to save them somewhere else, remember to change these hardcoded paths.

#!/bin/bash
# Startet den Sensor-Dienst im Hintergrund
cd /home/max/genesis
python3 -m host.sensor_dienst.dienst &
echo $! > /tmp/genesis_sensor_dienst.pid
echo "Sensor-Dienst gestartet (PID: $!)"

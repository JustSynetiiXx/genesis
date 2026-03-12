#!/bin/bash
# Sendet Schlaf-Signal und faehrt VM herunter
cd /home/max/genesis
python3 -m host.signale.schlaf
echo "Schlaf-Signal gesendet."
sleep 3
# Optional: VM herunterfahren
# virsh shutdown genesis-vm
echo "Gute Nacht, Genesis."

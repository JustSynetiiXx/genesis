#!/bin/bash
# Startet VM und loescht Schlaf-Signal
cd /home/max/genesis
# Optional: VM starten
# virsh start genesis-vm
# Schlaf-Signal entfernen
> /home/max/genesis/shared/signal.txt
echo "Guten Morgen, Genesis."

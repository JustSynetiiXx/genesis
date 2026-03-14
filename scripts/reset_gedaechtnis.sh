#!/bin/bash
echo "WARNUNG: Löscht ALLE Genesis-Erfahrungen (Kurzzeit + Langzeit + Heartbeat)"
echo "Genesis muss gestoppt sein!"
read -p "Sicher? (ja/nein): " antwort
if [ "$antwort" = "ja" ]; then
    rm -f /var/lib/genesis/kurzzeit.db
    rm -f /var/lib/genesis/langzeit.db
    rm -f /var/lib/genesis/heartbeat.db
    rm -f /opt/genesis/shared/genesis_status.json
    rm -f /opt/genesis/shared/genesis_log.txt
    echo "Gedächtnis gelöscht. Genesis startet als Neugeborenes."
else
    echo "Abgebrochen."
fi

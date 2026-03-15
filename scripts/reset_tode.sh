#!/bin/bash
# Reset-Tode: Löscht falsche Tode aus heartbeat.db für alle Genesis-Instanzen.
# Löscht NUR die Tode-Tabelle, NICHT Langzeit oder Kurzzeit.

set -e

DB_PFADE=(
    "/var/lib/genesis/langzeit.db"
    "/var/lib/genesis-2/langzeit.db"
    "/var/lib/genesis-3/langzeit.db"
)

echo "=== Genesis: Tode zurücksetzen ==="
echo ""
echo "Folgende Datenbanken werden bereinigt:"
for db in "${DB_PFADE[@]}"; do
    if [ -f "$db" ]; then
        count=$(sqlite3 "$db" "SELECT COUNT(*) FROM tode;" 2>/dev/null || echo "0")
        echo "  $db — $count Einträge in 'tode'"
    else
        echo "  $db — nicht gefunden (übersprungen)"
    fi
done

echo ""
read -p "Wirklich alle Tode löschen? (ja/nein): " antwort

if [ "$antwort" != "ja" ]; then
    echo "Abgebrochen."
    exit 0
fi

echo ""
for db in "${DB_PFADE[@]}"; do
    if [ -f "$db" ]; then
        sqlite3 "$db" "DELETE FROM tode;"
        echo "✓ $db — Tode gelöscht"
    fi
done

echo ""
echo "Fertig. Alle Tode-Einträge wurden entfernt."
echo "Langzeit- und Kurzzeit-Daten sind unverändert."

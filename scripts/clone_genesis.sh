#!/usr/bin/env bash
# clone_genesis.sh — Erstellt einen Klon einer Genesis-Instanz.
#
# Kopiert die Datenbanken und Shared-Verzeichnisse einer Quell-Instanz
# in die Verzeichnisse einer Ziel-Instanz. Optional: ohne Gedächtnis
# (frischer Klon mit gleichem Entwicklungsstand).
#
# Nutzung:
#   ./scripts/clone_genesis.sh genesis-1 genesis-2          # Voller Klon
#   ./scripts/clone_genesis.sh genesis-1 genesis-2 --frisch  # Ohne Gedächtnis
#
# Voraussetzung: Beide Instanzen müssen gestoppt sein!

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Argumente ---
if [ $# -lt 2 ]; then
    echo "Nutzung: $0 <quelle> <ziel> [--frisch]"
    echo ""
    echo "  quelle:   Name der Quell-Instanz (z.B. genesis-1)"
    echo "  ziel:     Name der Ziel-Instanz (z.B. genesis-2)"
    echo "  --frisch: Klon ohne Gedächtnis (leere DBs, gleiche Phase)"
    echo ""
    echo "Verfügbare Instanzen: genesis-1, genesis-2, genesis-3"
    exit 1
fi

QUELLE="$1"
ZIEL="$2"
FRISCH=false

if [ "${3:-}" = "--frisch" ]; then
    FRISCH=true
fi

# --- Instanz-Pfade (synchron mit vm/config_instances.py) ---
declare -A DB_PFADE
declare -A SHARED_PFADE

DB_PFADE["genesis-1"]="/var/lib/genesis/"
DB_PFADE["genesis-2"]="/var/lib/genesis-2/"
DB_PFADE["genesis-3"]="/var/lib/genesis-3/"

SHARED_PFADE["genesis-1"]="/opt/genesis/shared/"
SHARED_PFADE["genesis-2"]="/opt/genesis/shared-2/"
SHARED_PFADE["genesis-3"]="/opt/genesis/shared-3/"

# Prüfen ob Instanzen existieren
if [ -z "${DB_PFADE[$QUELLE]+x}" ]; then
    echo "FEHLER: Quell-Instanz '$QUELLE' nicht bekannt."
    exit 1
fi

if [ -z "${DB_PFADE[$ZIEL]+x}" ]; then
    echo "FEHLER: Ziel-Instanz '$ZIEL' nicht bekannt."
    exit 1
fi

if [ "$QUELLE" = "$ZIEL" ]; then
    echo "FEHLER: Quelle und Ziel dürfen nicht identisch sein."
    exit 1
fi

QUELLE_DB="${DB_PFADE[$QUELLE]}"
QUELLE_SHARED="${SHARED_PFADE[$QUELLE]}"
ZIEL_DB="${DB_PFADE[$ZIEL]}"
ZIEL_SHARED="${SHARED_PFADE[$ZIEL]}"

echo "=== Genesis Klon ==="
echo "Quelle: $QUELLE (DB: $QUELLE_DB, Shared: $QUELLE_SHARED)"
echo "Ziel:   $ZIEL (DB: $ZIEL_DB, Shared: $ZIEL_SHARED)"
echo "Modus:  $([ "$FRISCH" = true ] && echo 'Frisch (ohne Gedächtnis)' || echo 'Voller Klon')"
echo ""

# Sicherheitsabfrage
read -rp "Fortfahren? Ziel-Verzeichnisse werden überschrieben! (j/n) " antwort
if [ "$antwort" != "j" ]; then
    echo "Abgebrochen."
    exit 0
fi

# --- Ziel-Verzeichnisse erstellen ---
echo "Erstelle Verzeichnisse..."
mkdir -p "$ZIEL_DB"
mkdir -p "$ZIEL_SHARED"

if [ "$FRISCH" = true ]; then
    # Frischer Klon: Nur Sensordaten kopieren, leere DBs
    echo "Frischer Klon — kopiere nur Sensor-Konfiguration..."

    # Sensoren.bin kopieren (falls vorhanden)
    if [ -f "${QUELLE_SHARED}sensoren.bin" ]; then
        cp "${QUELLE_SHARED}sensoren.bin" "${ZIEL_SHARED}sensoren.bin"
        echo "  sensoren.bin kopiert"
    fi

    # Leere DBs werden von Genesis beim Start automatisch erstellt
    echo "  DBs werden beim Start automatisch erstellt"

else
    # Voller Klon: Alles kopieren
    echo "Voller Klon — kopiere Datenbanken..."

    # Datenbanken kopieren
    for db_datei in kurzzeit.db langzeit.db heartbeat.db; do
        if [ -f "${QUELLE_DB}${db_datei}" ]; then
            cp "${QUELLE_DB}${db_datei}" "${ZIEL_DB}${db_datei}"
            echo "  $db_datei kopiert"
        fi
        # WAL und SHM auch kopieren
        for suffix in -wal -shm; do
            if [ -f "${QUELLE_DB}${db_datei}${suffix}" ]; then
                cp "${QUELLE_DB}${db_datei}${suffix}" "${ZIEL_DB}${db_datei}${suffix}"
            fi
        done
    done

    echo "Kopiere Shared-Verzeichnis..."
    # sensoren.bin kopieren
    if [ -f "${QUELLE_SHARED}sensoren.bin" ]; then
        cp "${QUELLE_SHARED}sensoren.bin" "${ZIEL_SHARED}sensoren.bin"
        echo "  sensoren.bin kopiert"
    fi
fi

# Signal-Datei NICHT kopieren (jede Instanz bekommt eigene Signale)
# Status-Datei NICHT kopieren (wird von Genesis automatisch geschrieben)

echo ""
echo "=== Klon '$ZIEL' erstellt ==="
echo ""
echo "Starten mit:"
echo "  python3 -m vm.genesis.leben --instance $ZIEL"
echo ""
echo "WICHTIG: Den Umgebungs-Dienst (host/umgebung_dienst/) nur einmal starten!"
echo "         Er erkennt alle Instanzen automatisch."

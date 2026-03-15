#!/bin/bash
# Wrapper der einen Stresstest startet UND Test-Marker schreibt.
#
# Nutzung:
#   ./scripts/starte_test.sh cpu|ram|kombi [dauer_sekunden]
#
# Schreibt TEST_START und TEST_ENDE Marker in shared/test_marker.txt

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJEKT_DIR="$(dirname "$SCRIPT_DIR")"
MARKER_DATEI="${PROJEKT_DIR}/shared/test_marker.txt"
# Auf dem VPS: /opt/genesis/shared/test_marker.txt
MARKER_DATEI_PROD="/opt/genesis/shared/test_marker.txt"

TESTTYP="${1:-cpu}"
DAUER="${2:-600}"

# Marker-Datei wählen (Prod falls vorhanden, sonst lokal)
if [ -d "/opt/genesis/shared" ]; then
    MARKER="$MARKER_DATEI_PROD"
else
    mkdir -p "${PROJEKT_DIR}/shared"
    MARKER="$MARKER_DATEI"
fi

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "TEST_START:${TESTTYP}:${TIMESTAMP}:${DAUER}" >> "$MARKER"
echo "Test gestartet: ${TESTTYP} (${DAUER}s)"

cleanup() {
    TIMESTAMP_ENDE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    echo "TEST_ENDE:${TESTTYP}:${TIMESTAMP_ENDE}" >> "$MARKER"
    echo "Test beendet: ${TESTTYP}"
}
trap cleanup EXIT

case "$TESTTYP" in
    cpu)
        python3 "${SCRIPT_DIR}/stress_cpu.py" --dauer "$DAUER"
        ;;
    ram)
        python3 "${SCRIPT_DIR}/stress_ram.py" --dauer "$DAUER"
        ;;
    kombi)
        python3 "${SCRIPT_DIR}/stress_kombi.py" --dauer "$DAUER"
        ;;
    *)
        echo "Unbekannter Testtyp: $TESTTYP"
        echo "Nutzung: $0 cpu|ram|kombi [dauer_sekunden]"
        exit 1
        ;;
esac

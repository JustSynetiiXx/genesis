"""Eltern-Interface: Sendet Signale an Genesis über das Shared Directory."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from host.sensor_dienst.config import SHARED_VERZEICHNIS, SIGNAL_DATEI

SIGNAL_BEFEHLE: dict[str, str] = {
    "schlaf": "SLEEP",
    "gut": "GOOD",
    "schlecht": "BAD",
}


def sende_signal(befehl: str, shared_pfad: Path = SHARED_VERZEICHNIS) -> None:
    """Schreibt ein Signal in die Signal-Datei."""
    signal_name = SIGNAL_BEFEHLE.get(befehl)
    if signal_name is None:
        print(f"Unbekannter Befehl: {befehl}")
        print(f"Verfügbar: {', '.join(SIGNAL_BEFEHLE.keys())}, status")
        return

    signal_pfad = shared_pfad / SIGNAL_DATEI
    signal_pfad.parent.mkdir(parents=True, exist_ok=True)
    zeitstempel = time.time()
    signal_pfad.write_text(f"{signal_name} {zeitstempel}\n")
    print(f"Signal gesendet: {signal_name} ({zeitstempel})")


def zeige_status(shared_pfad: Path = SHARED_VERZEICHNIS) -> None:
    """Zeigt den aktuellen Inhalt der Signal-Datei."""
    signal_pfad = shared_pfad / SIGNAL_DATEI
    try:
        inhalt = signal_pfad.read_text().strip()
        if inhalt:
            print(f"Aktuelles Signal: {inhalt}")
        else:
            print("Kein Signal aktiv.")
    except FileNotFoundError:
        print("Signal-Datei existiert nicht.")


def main() -> None:
    """CLI-Einstiegspunkt."""
    if len(sys.argv) < 2:
        print("Verwendung: python -m host.ekg.eltern <befehl>")
        print(f"Befehle: {', '.join(SIGNAL_BEFEHLE.keys())}, status")
        sys.exit(1)

    befehl = sys.argv[1].lower()
    if befehl == "status":
        zeige_status()
    else:
        sende_signal(befehl)


if __name__ == "__main__":
    main()

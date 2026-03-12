"""Schlaf-Signal: Schreibt SLEEP-Signal in die Signal-Datei."""
from __future__ import annotations

import time
from pathlib import Path

from host.sensor_dienst.config import SHARED_VERZEICHNIS, SIGNAL_DATEI


def sende_schlaf_signal(shared_pfad: Path = SHARED_VERZEICHNIS) -> None:
    """Schreibt 'SLEEP <zeitstempel>' in die Signal-Datei."""
    signal_pfad = shared_pfad / SIGNAL_DATEI
    signal_pfad.parent.mkdir(parents=True, exist_ok=True)
    zeitstempel = time.time()
    signal_pfad.write_text(f"SLEEP {zeitstempel}\n")
    print(f"Schlaf-Signal gesendet: SLEEP {zeitstempel}")


def lese_signal(shared_pfad: Path = SHARED_VERZEICHNIS) -> tuple[str, float] | None:
    """Liest und parst die Signal-Datei.

    Returns:
        Tuple (signal_name, zeitstempel) oder None wenn kein Signal.
    """
    signal_pfad = shared_pfad / SIGNAL_DATEI
    try:
        inhalt = signal_pfad.read_text().strip()
        if not inhalt:
            return None
        teile = inhalt.split(maxsplit=1)
        name = teile[0]
        zeitstempel = float(teile[1]) if len(teile) > 1 else time.time()
        return (name, zeitstempel)
    except (FileNotFoundError, ValueError):
        return None


def sende_signal(name: str, shared_pfad: Path = SHARED_VERZEICHNIS) -> None:
    """Schreibt ein beliebiges Signal in die Signal-Datei."""
    signal_pfad = shared_pfad / SIGNAL_DATEI
    signal_pfad.parent.mkdir(parents=True, exist_ok=True)
    zeitstempel = time.time()
    signal_pfad.write_text(f"{name} {zeitstempel}\n")


if __name__ == "__main__":
    sende_schlaf_signal()

#!/usr/bin/env python3
"""RAM-Stresstest für Genesis.

Belegt eine konfigurierbare Menge RAM durch eine Liste mit Zufallsdaten.

Nutzung:
    python3 scripts/stress_ram.py --mb 1000 --dauer 600
"""

from __future__ import annotations

import argparse
import signal
import sys
import time


_running: bool = True


def _signal_handler(sig: int, frame: object) -> None:
    """Beendet den Stress-Test sauber bei Ctrl+C."""
    global _running
    _running = False


def stress_ram(mb: int, dauer: int) -> None:
    """Belegt RAM für die angegebene Dauer.

    Args:
        mb: Megabyte RAM zu belegen.
        dauer: Dauer in Sekunden.
    """
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    print(f"RAM-Stress gestartet ({mb} MB, {dauer}s)")

    # Belege RAM: 1 MB = 1024 * 1024 Bytes
    # Verwende bytearray-Blöcke à 1 MB
    bloecke: list[bytearray] = []
    for _ in range(mb):
        bloecke.append(bytearray(1024 * 1024))
        if not _running:
            break

    print(f"RAM belegt: {len(bloecke)} MB")

    start: float = time.time()
    while _running and (time.time() - start) < dauer:
        time.sleep(0.5)

    # Speicher freigeben
    bloecke.clear()
    print("RAM-Stress beendet")


def main() -> None:
    """Hauptfunktion."""
    parser = argparse.ArgumentParser(description="RAM-Stresstest für Genesis")
    parser.add_argument("--mb", type=int, default=1000, help="MB RAM zu belegen (Standard: 1000)")
    parser.add_argument("--dauer", type=int, default=600, help="Dauer in Sekunden (Standard: 600)")
    args = parser.parse_args()
    stress_ram(args.mb, args.dauer)


if __name__ == "__main__":
    main()

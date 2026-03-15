#!/usr/bin/env python3
"""CPU-Stresstest für Genesis.

Erzeugt ~50% CPU-Last auf einem Kern durch Busy-Loop mit sleep-Pausen.

Nutzung:
    python3 scripts/stress_cpu.py --dauer 600
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


def stress_cpu(dauer: int) -> None:
    """Erzeugt ~50% CPU-Last für die angegebene Dauer.

    Args:
        dauer: Dauer in Sekunden.
    """
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    print(f"CPU-Stress gestartet ({dauer}s)")
    start: float = time.time()

    while _running and (time.time() - start) < dauer:
        # ~50% Last: 10ms rechnen, 10ms schlafen
        ende_burst: float = time.time() + 0.01
        while time.time() < ende_burst:
            _ = sum(i * i for i in range(100))
        time.sleep(0.01)

    print("CPU-Stress beendet")


def main() -> None:
    """Hauptfunktion."""
    parser = argparse.ArgumentParser(description="CPU-Stresstest für Genesis")
    parser.add_argument("--dauer", type=int, default=600, help="Dauer in Sekunden (Standard: 600)")
    args = parser.parse_args()
    stress_cpu(args.dauer)


if __name__ == "__main__":
    main()

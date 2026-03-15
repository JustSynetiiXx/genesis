#!/usr/bin/env python3
"""Kombinations-Stresstest für Genesis.

Startet CPU- und RAM-Stress gleichzeitig als Subprozesse.

Nutzung:
    python3 scripts/stress_kombi.py --dauer 600 --mb 1000
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


_SCRIPT_DIR: Path = Path(__file__).resolve().parent


def stress_kombi(dauer: int, mb: int) -> None:
    """Startet CPU und RAM Stress gleichzeitig.

    Args:
        dauer: Dauer in Sekunden.
        mb: Megabyte RAM zu belegen.
    """
    print(f"Kombi-Stress gestartet (CPU + {mb} MB RAM, {dauer}s)")

    cpu_proc = subprocess.Popen(
        [sys.executable, str(_SCRIPT_DIR / "stress_cpu.py"), "--dauer", str(dauer)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    ram_proc = subprocess.Popen(
        [sys.executable, str(_SCRIPT_DIR / "stress_ram.py"), "--mb", str(mb), "--dauer", str(dauer)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    def _cleanup(sig: int, frame: object) -> None:
        """Beendet beide Subprozesse sauber."""
        cpu_proc.terminate()
        ram_proc.terminate()

    signal.signal(signal.SIGINT, _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)

    # Warte auf beide Prozesse
    cpu_proc.wait()
    ram_proc.wait()

    print("Kombi-Stress beendet")


def main() -> None:
    """Hauptfunktion."""
    parser = argparse.ArgumentParser(description="Kombinations-Stresstest für Genesis")
    parser.add_argument("--dauer", type=int, default=600, help="Dauer in Sekunden (Standard: 600)")
    parser.add_argument("--mb", type=int, default=1000, help="MB RAM zu belegen (Standard: 1000)")
    args = parser.parse_args()
    stress_kombi(args.dauer, args.mb)


if __name__ == "__main__":
    main()

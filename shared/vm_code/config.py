"""Konfiguration für das Genesis-System (VM-seitig).

Alle konfigurierbaren Parameter für das Neugeborene.
"""

from __future__ import annotations

from pathlib import Path


# --- Pfade ---
SHARED_DIR: Path = Path("/mnt/shared")
SENSOR_DATEI: str = "sensoren.bin"
SIGNAL_DATEI: str = "signal.txt"
STATUS_DATEI: str = "genesis_status.json"
DB_VERZEICHNIS: Path = Path("/var/lib/genesis")

# --- Timing ---
LOOP_INTERVALL: float = 1.0          # Sekunden zwischen Loops (Standard)
WACHPHASE_SEKUNDEN: int = 30         # Sekunden nur Fühlen am Anfang
HEARTBEAT_INTERVALL: int = 5         # Sekunden zwischen Heartbeat-Updates

# --- Natürlicher Verfall ---
VERFALL_MB_PRO_TICK: int = 1         # MB Cache-Wachstum pro Loop-Iteration

# --- Lernen ---
LERNSCHWELLE_STARK: float = 0.3      # |delta| > 0.3 → sofort gelernt
LERNSCHWELLE_MITTEL: float = 0.1     # |delta| > 0.1 → braucht Wiederholungen
WIEDERHOLUNGEN_MITTEL: int = 3       # Wiederholungen für mittlere Signale
WIEDERHOLUNGEN_SCHWACH: int = 5      # Wiederholungen für schwache Signale

# --- Speicher-Cache ---
CACHE_MAX_MB: int = 500              # Absolutes Maximum bevor Notfall

# --- Pause ---
PAUSE_MIN_SEKUNDEN: float = 1.0
PAUSE_MAX_SEKUNDEN: float = 10.0

# --- Abtastrate ---
ABTASTRATE_MIN: float = 0.2          # Schnellstes Intervall
ABTASTRATE_MAX: float = 5.0          # Langsamstes Intervall

# --- Rechenintensität ---
RECHEN_STUFE: float = 0.2            # Stufengröße für erhöhen/senken

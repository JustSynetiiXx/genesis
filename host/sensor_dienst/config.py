"""Konfiguration für den Sensor-Dienst."""
from __future__ import annotations

from pathlib import Path

# --- Pfade ---
SHARED_VERZEICHNIS: Path = Path("/home/max/genesis/shared/")
SENSOR_DATEI: str = "sensoren.bin"
SIGNAL_DATEI: str = "signal.txt"
STATUS_DATEI: str = "genesis_status.bin"
LOG_VERZEICHNIS: Path = Path("/home/max/genesis/logs/")

# --- Abtastraten (Hz) ---
SCHNELL_HZ: float = 5.0   # RAM-Auslastung, Prozess-Speicher
MITTEL_HZ: float = 2.0    # CPU-Auslastung
LANGSAM_HZ: float = 1.0   # CPU-Temperatur, Lüfter-RPM

# --- Sensor-IDs ---
# CPU-Temperatur (0x0001 - 0x000F)
SENSOR_CPU_TEMP_TCTL: int = 0x0001
SENSOR_CPU_TEMP_TCCD1: int = 0x0002

# CPU-Auslastung (0x0100 - 0x011F)
SENSOR_CPU_LAST_GESAMT: int = 0x0100
SENSOR_CPU_LAST_KERN_START: int = 0x0101  # 0x0101 = Kern 0, 0x0102 = Kern 1, ...

# RAM (0x0200 - 0x020F)
SENSOR_RAM_GESAMT: int = 0x0200
SENSOR_RAM_BENUTZT: int = 0x0201
SENSOR_RAM_FREI: int = 0x0202

# Lüfter (0x0300 - 0x030F)
SENSOR_LUEFTER_1: int = 0x0300
SENSOR_LUEFTER_2: int = 0x0301

# --- Sensor-Namen (für menschliche Ausgabe) ---
SENSOR_NAMEN: dict[int, str] = {
    SENSOR_CPU_TEMP_TCTL: "CPU-Temp Tctl",
    SENSOR_CPU_TEMP_TCCD1: "CPU-Temp Tccd1",
    SENSOR_CPU_LAST_GESAMT: "CPU-Last Gesamt",
    SENSOR_RAM_GESAMT: "RAM Gesamt (MB)",
    SENSOR_RAM_BENUTZT: "RAM Benutzt (MB)",
    SENSOR_RAM_FREI: "RAM Frei (MB)",
    SENSOR_LUEFTER_1: "Lüfter 1 (RPM)",
    SENSOR_LUEFTER_2: "Lüfter 2 (RPM)",
}

# Kern-Namen dynamisch hinzufügen (bis 16 Kerne)
for _i in range(16):
    SENSOR_NAMEN[SENSOR_CPU_LAST_KERN_START + _i] = f"CPU-Last Kern {_i}"

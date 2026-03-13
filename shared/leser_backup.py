"""Leser für die binäre Sensordatei (sensoren.bin).

Format:
    Header: float64 zeitstempel, uint16 anzahl_sensoren
    Pro Sensor: uint16 sensor_id, float32 wert

Sensor-IDs:
    0x0001: CPU-Temp Tctl
    0x0002: CPU-Temp Tccd1
    0x0100: CPU-Last Gesamt
    0x0101-0x0110: CPU-Last pro Kern
    0x0200: RAM Gesamt MB
    0x0201: RAM Benutzt MB
    0x0202: RAM Frei MB
    0x0300: Lüfter-RPM
"""

from __future__ import annotations

import struct
import time
from pathlib import Path
from typing import Any


# Sensor-ID Konstanten
SENSOR_CPU_TEMP_TCTL: int = 0x0001
SENSOR_CPU_TEMP_TCCD1: int = 0x0002
SENSOR_CPU_LAST_GESAMT: int = 0x0100
SENSOR_CPU_LAST_KERN_START: int = 0x0101
SENSOR_CPU_LAST_KERN_ENDE: int = 0x0110
SENSOR_RAM_GESAMT: int = 0x0200
SENSOR_RAM_BENUTZT: int = 0x0201
SENSOR_RAM_FREI: int = 0x0202
SENSOR_LUEFTER_RPM: int = 0x0300

# Header: float64 (8 Bytes) + uint16 (2 Bytes) = 10 Bytes
HEADER_FORMAT: str = "<dH"
HEADER_GROESSE: int = struct.calcsize(HEADER_FORMAT)

# Pro Sensor: uint16 (2 Bytes) + float32 (4 Bytes) = 6 Bytes
SENSOR_FORMAT: str = "<Hf"
SENSOR_GROESSE: int = struct.calcsize(SENSOR_FORMAT)

# Menschlich lesbare Namen für Sensor-IDs
SENSOR_NAMEN: dict[int, str] = {
    SENSOR_CPU_TEMP_TCTL: "cpu_temp_tctl",
    SENSOR_CPU_TEMP_TCCD1: "cpu_temp_tccd1",
    SENSOR_CPU_LAST_GESAMT: "cpu_last_gesamt",
    SENSOR_RAM_GESAMT: "ram_gesamt_mb",
    SENSOR_RAM_BENUTZT: "ram_benutzt_mb",
    SENSOR_RAM_FREI: "ram_frei_mb",
    SENSOR_LUEFTER_RPM: "luefter_rpm",
}

# CPU-Kerne dynamisch benennen
for _kern_nr in range(16):
    SENSOR_NAMEN[SENSOR_CPU_LAST_KERN_START + _kern_nr] = f"cpu_last_kern_{_kern_nr}"


def lese_sensoren(pfad: Path) -> dict[str, Any] | None:
    """Liest die binäre Sensordatei und gibt ein Dictionary zurück.

    Args:
        pfad: Pfad zur sensoren.bin Datei.

    Returns:
        Dictionary mit 'zeitstempel' (float) und Sensor-Namen als Keys,
        oder None wenn die Datei nicht gelesen werden kann.
    """
    try:
        daten: bytes = pfad.read_bytes()
    except (FileNotFoundError, PermissionError, OSError):
        return None

    if len(daten) < HEADER_GROESSE:
        return None

    zeitstempel: float
    anzahl: int
    zeitstempel, anzahl = struct.unpack(HEADER_FORMAT, daten[:HEADER_GROESSE])

    erwartete_groesse: int = HEADER_GROESSE + anzahl * SENSOR_GROESSE
    if len(daten) < erwartete_groesse:
        return None

    ergebnis: dict[str, Any] = {
        "zeitstempel": zeitstempel,
        "alter_sekunden": time.time() - zeitstempel,
    }

    offset: int = HEADER_GROESSE
    for _ in range(anzahl):
        sensor_id: int
        wert: float
        sensor_id, wert = struct.unpack(
            SENSOR_FORMAT, daten[offset : offset + SENSOR_GROESSE]
        )
        offset += SENSOR_GROESSE

        name: str = SENSOR_NAMEN.get(sensor_id, f"unbekannt_0x{sensor_id:04x}")
        ergebnis[name] = wert

    return ergebnis


class SensorLeser:
    """Klassen-basierter Leser fuer die binaere Sensordatei.

    Wrapper um lese_sensoren() fuer objektorientierte Nutzung.
    Wird vom EKG-System und von den Tests verwendet.
    """

    def __init__(self, datei_pfad: Path | None = None) -> None:
        """Initialisiert den SensorLeser.

        Args:
            datei_pfad: Pfad zur sensoren.bin Datei.
        """
        self._datei_pfad: Path = datei_pfad if datei_pfad is not None else Path("/home/max/genesis/shared/sensoren.bin")

    @property
    def datei_pfad(self) -> Path:
        """Gibt den Pfad zur Sensordatei zurueck."""
        return self._datei_pfad

    def lese(self) -> dict[str, Any] | None:
        """Liest Sensordaten aus der Binaerdatei.

        Returns:
            Dictionary mit Sensor-Namen und Werten oder None bei Fehler.
        """
        return lese_sensoren(self._datei_pfad)


def schreibe_sensoren(pfad: Path, sensoren: dict[str, float]) -> None:
    """Schreibt Sensordaten in die binäre Datei (für Tests).

    Args:
        pfad: Pfad zur sensoren.bin Datei.
        sensoren: Dictionary mit Sensor-Namen und Werten.
    """
    # Umgekehrte Zuordnung: Name → ID
    name_zu_id: dict[str, int] = {v: k for k, v in SENSOR_NAMEN.items()}

    eintraege: list[tuple[int, float]] = []
    for name, wert in sensoren.items():
        if name in name_zu_id:
            eintraege.append((name_zu_id[name], wert))

    header: bytes = struct.pack(HEADER_FORMAT, time.time(), len(eintraege))
    body: bytes = b"".join(
        struct.pack(SENSOR_FORMAT, sid, wert) for sid, wert in eintraege
    )

    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(header + body)

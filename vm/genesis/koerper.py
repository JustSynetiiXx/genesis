"""Koerper — Sensorik-Verarbeitung für Genesis.

Liest Host-Sensordaten aus shared/sensoren.bin und VM-eigene Sensoren
via psutil. Kategorisiert alle Werte in grobe Zustandskategorien.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import psutil

from shared.leser import lese_sensoren
from vm.config import CPU_PROZENT_MAX


# --- Zustandskategorien ---

def _kategorie_cpu_temp(temp: float) -> str:
    """Kategorisiert CPU-Temperatur."""
    if temp < 45.0:
        return "kühl"
    elif temp < 60.0:
        return "normal"
    elif temp < 75.0:
        return "warm"
    elif temp < 85.0:
        return "heiß"
    else:
        return "kritisch"


def _kategorie_ram(frei_mb: float) -> str:
    """Kategorisiert VM-RAM (frei in MB)."""
    if frei_mb > 500.0:
        return "frei"
    elif frei_mb > 200.0:
        return "normal"
    elif frei_mb > 50.0:
        return "eng"
    else:
        return "voll"


def _kategorie_cpu_last(prozent: float) -> str:
    """Kategorisiert Host-CPU-Auslastung (0-100%)."""
    if prozent < 30.0:
        return "niedrig"
    elif prozent < 60.0:
        return "normal"
    elif prozent < 90.0:
        return "hoch"
    else:
        return "überlastet"


def _kategorie_eigen_cpu(prozent: float) -> str:
    """Kategorisiert eigene CPU-Auslastung relativ zum Maximum.

    psutil.Process.cpu_percent() gibt bei N Kernen Werte bis N*100% zurück.
    Schwellen sind relativ zu CPU_PROZENT_MAX:
    - niedrig:    < 30% des Maximums
    - normal:     30-50% des Maximums
    - hoch:       50-75% des Maximums
    - überlastet: > 75% des Maximums
    """
    anteil: float = prozent / CPU_PROZENT_MAX
    if anteil < 0.30:
        return "niedrig"
    elif anteil < 0.50:
        return "normal"
    elif anteil < 0.75:
        return "hoch"
    else:
        return "überlastet"


def _kategorie_luefter(rpm: float) -> str:
    """Kategorisiert Lüfter-RPM."""
    if rpm < 1200.0:
        return "leise"
    elif rpm < 2000.0:
        return "normal"
    elif rpm < 3000.0:
        return "laut"
    else:
        return "maximum"


class Koerper:
    """Liest und kategorisiert alle Sensordaten.

    Host-Sensoren werden aus der binären Sensordatei gelesen.
    VM-eigene Sensoren werden direkt via psutil abgefragt.
    """

    def __init__(self, sensor_pfad: Path) -> None:
        """Initialisiert den Körper.

        Args:
            sensor_pfad: Pfad zur sensoren.bin Datei im Shared Directory.
        """
        self._sensor_pfad: Path = sensor_pfad
        self._prozess: psutil.Process = psutil.Process()
        # Erster Aufruf von cpu_percent ist immer 0.0 — Baseline setzen
        self._prozess.cpu_percent()

    def fuehle(self) -> dict[str, Any]:
        """Liest alle Sensordaten und kategorisiert sie.

        Returns:
            Dictionary mit 'kategorien', 'rohwerte' und 'zeitstempel'.
        """
        rohwerte: dict[str, float] = {}

        # --- Host-Sensoren aus Shared Directory ---
        host_daten: dict[str, Any] | None = lese_sensoren(self._sensor_pfad)
        if host_daten is not None:
            rohwerte["cpu_temp_tctl"] = host_daten.get("cpu_temp_tctl", 50.0)
            rohwerte["cpu_temp_tccd1"] = host_daten.get("cpu_temp_tccd1", 50.0)
            rohwerte["host_cpu_last"] = host_daten.get("cpu_last_gesamt", 0.0)
            rohwerte["host_ram_frei_mb"] = host_daten.get("ram_frei_mb", 16000.0)
            rohwerte["luefter_rpm"] = host_daten.get("luefter_rpm", 1000.0)
        else:
            # Fallback-Werte wenn Sensordatei nicht lesbar
            rohwerte["cpu_temp_tctl"] = 50.0
            rohwerte["cpu_temp_tccd1"] = 50.0
            rohwerte["host_cpu_last"] = 0.0
            rohwerte["host_ram_frei_mb"] = 16000.0
            rohwerte["luefter_rpm"] = 1000.0

        # --- VM-eigene Sensoren via psutil ---
        vm_ram: Any = psutil.virtual_memory()
        rohwerte["vm_ram_frei_mb"] = vm_ram.available / (1024 * 1024)
        rohwerte["vm_ram_benutzt_mb"] = vm_ram.used / (1024 * 1024)

        mem_info: Any = self._prozess.memory_info()
        rohwerte["eigen_ram_mb"] = mem_info.rss / (1024 * 1024)
        rohwerte["eigen_cpu_prozent"] = self._prozess.cpu_percent()

        # --- Kategorisierung ---
        kategorien: dict[str, str] = {
            "cpu_temp": _kategorie_cpu_temp(rohwerte["cpu_temp_tctl"]),
            "vm_ram": _kategorie_ram(rohwerte["vm_ram_frei_mb"]),
            "cpu_last_eigen": _kategorie_eigen_cpu(rohwerte["eigen_cpu_prozent"]),
            "luefter": _kategorie_luefter(rohwerte["luefter_rpm"]),
            "host_cpu_last": _kategorie_cpu_last(rohwerte["host_cpu_last"]),
            "host_ram": _kategorie_ram(rohwerte["host_ram_frei_mb"]),
        }

        # Umgebungssensoren (werden von leben.py gesetzt wenn Gebärmutter aktiv)
        if "umgebung_rhythmus" in rohwerte:
            kategorien["umgebung_rhythmus"] = _kategorie_rhythmus(
                rohwerte["umgebung_rhythmus"]
            )
        if "reiz_aktiv" in rohwerte:
            kategorien["reiz_aktiv"] = rohwerte.get("reiz_typ", "keiner")  # type: ignore[assignment]

        return {
            "kategorien": kategorien,
            "rohwerte": rohwerte,
            "zeitstempel": time.time(),
        }


def _kategorie_rhythmus(wert: float) -> str:
    """Kategorisiert den Umgebungs-Rhythmus.

    Args:
        wert: Rhythmus-Wert (0.0-1.0).

    Returns:
        'ruhig', 'aktiv' oder 'peak'.
    """
    if wert < 0.3:
        return "ruhig"
    elif wert < 0.7:
        return "aktiv"
    else:
        return "peak"

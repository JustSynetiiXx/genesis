"""Sammelt echte Host-Sensordaten über psutil und hwmon."""
from __future__ import annotations

import logging
import subprocess

import psutil

from host.sensor_dienst.config import (
    SENSOR_CPU_LAST_GESAMT,
    SENSOR_CPU_LAST_KERN_START,
    SENSOR_CPU_TEMP_TCCD1,
    SENSOR_CPU_TEMP_TCTL,
    SENSOR_LUEFTER_1,
    SENSOR_LUEFTER_2,
    SENSOR_RAM_BENUTZT,
    SENSOR_RAM_FREI,
    SENSOR_RAM_GESAMT,
)

log = logging.getLogger(__name__)


class SensorSammler:
    """Sammelt alle Host-Sensordaten und gibt sie als dict[sensor_id, wert] zurück."""

    def sammle_temperatur(self) -> dict[int, float]:
        """Liest CPU-Temperatur über psutil (k10temp: Tctl, Tccd1)."""
        daten: dict[int, float] = {}
        try:
            temps = psutil.sensors_temperatures()
            if "k10temp" in temps:
                for eintrag in temps["k10temp"]:
                    if eintrag.label == "Tctl":
                        daten[SENSOR_CPU_TEMP_TCTL] = eintrag.current
                    elif eintrag.label == "Tccd1":
                        daten[SENSOR_CPU_TEMP_TCCD1] = eintrag.current
        except (AttributeError, OSError) as e:
            log.debug("psutil Temperatur fehlgeschlagen: %s — versuche sensors CLI", e)

        if not daten:
            daten = self._temperatur_fallback()

        if not daten:
            log.warning("Keine CPU-Temperatursensoren gefunden.")
        return daten

    def _temperatur_fallback(self) -> dict[int, float]:
        """Fallback: Parst Ausgabe von 'sensors' CLI-Tool."""
        daten: dict[int, float] = {}
        try:
            ergebnis = subprocess.run(
                ["sensors", "-u"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if ergebnis.returncode != 0:
                return daten

            aktueller_chip: str | None = None
            for zeile in ergebnis.stdout.splitlines():
                if zeile.startswith("k10temp"):
                    aktueller_chip = "k10temp"
                elif zeile and not zeile[0].isspace():
                    aktueller_chip = None
                elif aktueller_chip == "k10temp" and "temp1_input" in zeile:
                    wert = float(zeile.split(":")[1].strip())
                    daten[SENSOR_CPU_TEMP_TCTL] = wert
                elif aktueller_chip == "k10temp" and "temp3_input" in zeile:
                    wert = float(zeile.split(":")[1].strip())
                    daten[SENSOR_CPU_TEMP_TCCD1] = wert
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError) as e:
            log.debug("sensors CLI Fallback fehlgeschlagen: %s", e)
        return daten

    def sammle_cpu_last(self) -> dict[int, float]:
        """Liest CPU-Auslastung (gesamt + pro Kern)."""
        daten: dict[int, float] = {}
        daten[SENSOR_CPU_LAST_GESAMT] = psutil.cpu_percent(interval=None)
        pro_kern = psutil.cpu_percent(interval=None, percpu=True)
        for i, last in enumerate(pro_kern):
            daten[SENSOR_CPU_LAST_KERN_START + i] = last
        return daten

    def sammle_ram(self) -> dict[int, float]:
        """Liest RAM-Auslastung in MB."""
        ram = psutil.virtual_memory()
        return {
            SENSOR_RAM_GESAMT: ram.total / (1024 * 1024),
            SENSOR_RAM_BENUTZT: ram.used / (1024 * 1024),
            SENSOR_RAM_FREI: ram.available / (1024 * 1024),
        }

    def sammle_luefter(self) -> dict[int, float]:
        """Liest Lüfter-RPM über psutil."""
        daten: dict[int, float] = {}
        try:
            fans = psutil.sensors_fans()
            luefter_index = 0
            for _chip, eintraege in fans.items():
                for eintrag in eintraege:
                    sensor_id = SENSOR_LUEFTER_1 + luefter_index
                    if sensor_id <= SENSOR_LUEFTER_2:
                        daten[sensor_id] = float(eintrag.current)
                        luefter_index += 1
        except (AttributeError, OSError) as e:
            log.debug("Lüfter-Sensoren nicht verfügbar: %s", e)
        return daten

    def sammle_alles(self) -> dict[int, float]:
        """Sammelt alle verfügbaren Sensordaten."""
        daten: dict[int, float] = {}
        daten.update(self.sammle_temperatur())
        daten.update(self.sammle_cpu_last())
        daten.update(self.sammle_ram())
        daten.update(self.sammle_luefter())
        return daten

    def sammle_schnell(self) -> dict[int, float]:
        """Schnelle Sensoren: RAM."""
        return self.sammle_ram()

    def sammle_mittel(self) -> dict[int, float]:
        """Mittlere Sensoren: CPU-Last."""
        return self.sammle_cpu_last()

    def sammle_langsam(self) -> dict[int, float]:
        """Langsame Sensoren: Temperatur, Lüfter."""
        daten: dict[int, float] = {}
        daten.update(self.sammle_temperatur())
        daten.update(self.sammle_luefter())
        return daten

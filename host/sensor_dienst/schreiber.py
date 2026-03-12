"""Schreibt Sensordaten als binäre Datei (atomar)."""
from __future__ import annotations

import os
import struct
import tempfile
import time
from pathlib import Path

from host.sensor_dienst.config import SENSOR_DATEI, SHARED_VERZEICHNIS


class SensorSchreiber:
    """Schreibt Sensor-Dict als kompakte binäre Datei.

    Format:
        Header: float64 (Zeitstempel) + uint16 (Anzahl Sensoren)
        Pro Sensor: uint16 (Sensor-ID) + float32 (Wert)
    """

    def __init__(
        self,
        verzeichnis: Path = SHARED_VERZEICHNIS,
        dateiname: str = SENSOR_DATEI,
    ) -> None:
        self.pfad: Path = verzeichnis / dateiname
        self.verzeichnis: Path = verzeichnis
        self.verzeichnis.mkdir(parents=True, exist_ok=True)

    def schreibe(self, sensor_daten: dict[int, float]) -> None:
        """Schreibt Sensordaten atomar in die Binärdatei."""
        zeitstempel = time.time()
        anzahl = len(sensor_daten)

        # Header: float64 + uint16
        puffer = struct.pack("<dH", zeitstempel, anzahl)

        # Pro Sensor: uint16 + float32
        for sensor_id, wert in sensor_daten.items():
            puffer += struct.pack("<Hf", sensor_id, wert)

        self._atomar_schreiben(puffer)

    def _atomar_schreiben(self, daten: bytes) -> None:
        """Schreibt Daten atomar (temp-Datei -> fsync -> rename)."""
        fd = -1
        tmp_pfad = ""
        try:
            fd, tmp_pfad = tempfile.mkstemp(dir=str(self.verzeichnis))
            os.write(fd, daten)
            os.fsync(fd)
            os.close(fd)
            fd = -1
            os.replace(tmp_pfad, str(self.pfad))
        except Exception:
            if fd >= 0:
                os.close(fd)
            if tmp_pfad and os.path.exists(tmp_pfad):
                os.unlink(tmp_pfad)
            raise

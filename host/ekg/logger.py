"""EKG-Logger: Protokolliert Sensordaten in CSV-Dateien.

Schreibt alle Sensordaten mit Zeitstempel in eine CSV-Datei unter logs/.
Läuft in einem Hintergrund-Thread.

Verwendung:
    logger = EkgLogger(sensor_datei=Path("shared/sensoren.bin"))
    logger.starte()
    # ... Dashboard läuft ...
    logger.stoppe()
"""

from __future__ import annotations

import csv
import importlib.util
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

# Shared-Leser importieren
_PROJEKT_WURZEL: Path = Path(__file__).resolve().parent.parent.parent
_LESER_PFAD: Path = _PROJEKT_WURZEL / "shared" / "leser.py"


def _lade_leser() -> Any:
    """Lädt den Sensor-Leser aus dem shared-Verzeichnis.

    Returns:
        Das leser-Modul.
    """
    spec = importlib.util.spec_from_file_location("shared.leser", _LESER_PFAD)
    if spec is None or spec.loader is None:
        raise ImportError(f"Kann Sensor-Leser nicht laden: {_LESER_PFAD}")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


_leser = _lade_leser()

# Standard-Pfade
STANDARD_SENSOR_DATEI: Path = _PROJEKT_WURZEL / "shared" / "sensoren.bin"
STANDARD_LOG_VERZEICHNIS: Path = _PROJEKT_WURZEL / "logs"

# CSV-Spalten
CSV_SPALTEN: list[str] = [
    "zeitstempel",
    "cpu_temp_tctl",
    "cpu_temp_tccd1",
    "cpu_last_gesamt",
    "ram_frei_mb",
    "ram_benutzt_mb",
    "luefter_rpm",
]


class EkgLogger:
    """Protokolliert Sensordaten periodisch in eine CSV-Datei.

    Attributes:
        sensor_datei: Pfad zur binären Sensordatei.
        log_verzeichnis: Verzeichnis für Log-Dateien.
        intervall: Sekunden zwischen Log-Einträgen.
    """

    def __init__(
        self,
        sensor_datei: Path = STANDARD_SENSOR_DATEI,
        log_verzeichnis: Path = STANDARD_LOG_VERZEICHNIS,
        intervall: float = 1.0,
    ) -> None:
        """Initialisiert den Logger.

        Args:
            sensor_datei: Pfad zur sensoren.bin Datei.
            log_verzeichnis: Verzeichnis für CSV-Logs.
            intervall: Sekunden zwischen Log-Einträgen (Standard: 1.0).
        """
        self.sensor_datei: Path = sensor_datei
        self.log_verzeichnis: Path = log_verzeichnis
        self.intervall: float = intervall

        self._laeuft: bool = False
        self._thread: threading.Thread | None = None
        self._datei: TextIO | None = None
        self._schreiber: csv.writer | None = None
        self._letzter_zeitstempel: float = 0.0
        self._log_pfad: Path | None = None

    def _erstelle_log_datei(self) -> Path:
        """Erstellt eine neue Log-Datei mit Zeitstempel im Namen.

        Returns:
            Pfad zur erstellten Log-Datei.
        """
        self.log_verzeichnis.mkdir(parents=True, exist_ok=True)
        zeitstempel: str = datetime.now().strftime("%Y%m%d_%H%M%S")
        pfad: Path = self.log_verzeichnis / f"ekg_{zeitstempel}.csv"
        return pfad

    def _oeffne_log(self) -> None:
        """Öffnet die Log-Datei und schreibt den Header."""
        self._log_pfad = self._erstelle_log_datei()
        self._datei = open(self._log_pfad, "w", newline="", encoding="utf-8")
        self._schreiber = csv.writer(self._datei)
        self._schreiber.writerow(CSV_SPALTEN)
        self._datei.flush()

    def _schliesse_log(self) -> None:
        """Schließt die Log-Datei."""
        if self._datei is not None:
            self._datei.flush()
            self._datei.close()
            self._datei = None
            self._schreiber = None

    def logge(self, sensor_daten: dict[str, Any]) -> None:
        """Schreibt einen Eintrag in die CSV-Datei.

        Args:
            sensor_daten: Dictionary mit Sensordaten vom Leser.
        """
        if self._schreiber is None or self._datei is None:
            return

        zeitstempel: float = sensor_daten.get("zeitstempel", time.time())

        zeile: list[Any] = [
            f"{zeitstempel:.3f}",
            sensor_daten.get("cpu_temp_tctl", ""),
            sensor_daten.get("cpu_temp_tccd1", ""),
            sensor_daten.get("cpu_last_gesamt", ""),
            sensor_daten.get("ram_frei_mb", ""),
            sensor_daten.get("ram_benutzt_mb", ""),
            sensor_daten.get("luefter_rpm", ""),
        ]

        self._schreiber.writerow(zeile)
        self._datei.flush()

    def _loop(self) -> None:
        """Hauptschleife des Logger-Threads."""
        self._oeffne_log()

        try:
            while self._laeuft:
                sensor_daten: dict[str, Any] | None = _leser.lese_sensoren(
                    self.sensor_datei
                )

                if sensor_daten is not None:
                    zeitstempel: float = sensor_daten.get("zeitstempel", 0.0)
                    # Nur neue Daten loggen
                    if zeitstempel > self._letzter_zeitstempel:
                        self._letzter_zeitstempel = zeitstempel
                        self.logge(sensor_daten)

                time.sleep(self.intervall)
        finally:
            self._schliesse_log()

    def starte(self) -> None:
        """Startet den Logger in einem Hintergrund-Thread."""
        if self._laeuft:
            return

        self._laeuft = True
        self._thread = threading.Thread(
            target=self._loop,
            name="EkgLogger",
            daemon=True,
        )
        self._thread.start()

    def stoppe(self) -> None:
        """Stoppt den Logger und wartet auf den Thread."""
        self._laeuft = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    @property
    def log_pfad(self) -> Path | None:
        """Pfad zur aktuellen Log-Datei, oder None wenn nicht aktiv."""
        return self._log_pfad

    @property
    def ist_aktiv(self) -> bool:
        """Ob der Logger gerade läuft."""
        return self._laeuft

"""Tests für das EKG-System (Logger, Eltern-Interface)."""
from __future__ import annotations

import csv
import time
from pathlib import Path

import pytest

from host.ekg.logger import EkgLogger
from host.signale.schlaf import sende_signal, lese_signal


# --- Logger-Tests ---


class TestLoggerSchreibtCsv:
    """Tests für CSV-Logging."""

    def test_logger_schreibt_csv(self, tmp_path: Path) -> None:
        """EkgLogger schreibt korrekte CSV mit Mock-Sensordaten."""
        log_verzeichnis = tmp_path / "logs"

        logger = EkgLogger(
            sensor_datei=tmp_path / "sensoren.bin",
            log_verzeichnis=log_verzeichnis,
            intervall=1.0,
        )

        # Manuell Log-Datei öffnen (ohne Thread)
        logger._oeffne_log()

        mock_daten: dict = {
            "zeitstempel": 1700000000.0,
            "cpu_temp_tctl": 55.3,
            "cpu_temp_tccd1": 52.1,
            "cpu_last_gesamt": 23.5,
            "ram_frei_mb": 15000.0,
            "ram_benutzt_mb": 16000.0,
            "luefter_rpm": 800.0,
        }
        logger.logge(mock_daten)

        mock_daten_2: dict = {
            "zeitstempel": 1700000001.0,
            "cpu_temp_tctl": 56.0,
            "cpu_last_gesamt": 45.0,
        }
        logger.logge(mock_daten_2)

        logger._schliesse_log()

        assert logger.log_pfad is not None
        assert logger.log_pfad.exists()

        with logger.log_pfad.open("r", encoding="utf-8") as f:
            reader = csv.reader(f)
            zeilen = list(reader)

        # Header + 2 Datenzeilen
        assert len(zeilen) == 3
        assert zeilen[0][0] == "zeitstempel"
        assert "1700000000" in zeilen[1][0]
        assert "1700000001" in zeilen[2][0]


# --- Signal-Tests ---


class TestElternSignalSchlaf:
    """Tests für SLEEP-Signal."""

    def test_eltern_signal_schlaf(self, tmp_path: Path) -> None:
        """SLEEP-Signal wird korrekt geschrieben."""
        sende_signal("SLEEP", shared_pfad=tmp_path)

        signal_pfad = tmp_path / "signal.txt"
        assert signal_pfad.exists()
        inhalt = signal_pfad.read_text()
        assert inhalt.startswith("SLEEP")


class TestElternSignalGut:
    """Tests für GOOD-Signal."""

    def test_eltern_signal_gut(self, tmp_path: Path) -> None:
        """GOOD-Signal wird korrekt geschrieben."""
        sende_signal("GOOD", shared_pfad=tmp_path)

        signal_pfad = tmp_path / "signal.txt"
        assert signal_pfad.exists()
        inhalt = signal_pfad.read_text()
        assert inhalt.startswith("GOOD")


class TestElternSignalStatus:
    """Tests für Signal-Status lesen."""

    def test_eltern_signal_status(self, tmp_path: Path) -> None:
        """Signal-Datei kann korrekt zurückgelesen werden."""
        # Kein Signal → None
        ergebnis = lese_signal(shared_pfad=tmp_path)
        assert ergebnis is None

        # Signal schreiben und lesen
        sende_signal("BAD", shared_pfad=tmp_path)

        ergebnis = lese_signal(shared_pfad=tmp_path)
        assert ergebnis is not None
        assert ergebnis[0] == "BAD"
        assert ergebnis[1] > 0.0

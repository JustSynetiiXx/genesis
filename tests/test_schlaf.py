"""Tests für das Schlaf-Signal-System."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from host.signale.schlaf import sende_schlaf_signal, lese_signal
from host.sensor_dienst.config import SIGNAL_DATEI


class TestSchlafSignalGeschrieben:
    """Tests für das Schreiben des Schlaf-Signals."""

    def test_schlaf_signal_geschrieben(self, tmp_path: Path) -> None:
        """Schlaf-Signal wird in die Datei geschrieben."""
        sende_schlaf_signal(shared_pfad=tmp_path)

        datei = tmp_path / SIGNAL_DATEI
        assert datei.exists()
        inhalt = datei.read_text()
        assert inhalt.startswith("SLEEP")


class TestSchlafSignalZeitstempel:
    """Tests für den Zeitstempel im Schlaf-Signal."""

    def test_schlaf_signal_zeitstempel(self, tmp_path: Path) -> None:
        """Signal enthält einen gültigen Unix-Zeitstempel."""
        vorher = time.time()
        sende_schlaf_signal(shared_pfad=tmp_path)
        nachher = time.time()

        datei = tmp_path / SIGNAL_DATEI
        inhalt = datei.read_text().strip()
        teile = inhalt.split()

        assert len(teile) == 2
        assert teile[0] == "SLEEP"

        zeitstempel = float(teile[1])
        assert vorher <= zeitstempel <= nachher


class TestSchlafSignalLesbar:
    """Tests für die Lesbarkeit des Schlaf-Signals."""

    def test_schlaf_signal_lesbar(self, tmp_path: Path) -> None:
        """Signal kann über lese_signal zurück geparst werden."""
        sende_schlaf_signal(shared_pfad=tmp_path)

        ergebnis = lese_signal(shared_pfad=tmp_path)
        assert ergebnis is not None

        signal_typ, zeitstempel = ergebnis
        assert signal_typ == "SLEEP"
        assert zeitstempel > 0.0
        assert zeitstempel <= time.time()

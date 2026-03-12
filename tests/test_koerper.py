"""Tests für vm/genesis/koerper.py — Sensorik-Verarbeitung."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vm.genesis.koerper import (
    Koerper,
    _kategorie_cpu_last,
    _kategorie_cpu_temp,
    _kategorie_luefter,
    _kategorie_ram,
)


class TestKategorieCpuTemp:
    """Kategorisierung der CPU-Temperatur."""

    def test_kuehl(self) -> None:
        assert _kategorie_cpu_temp(30.0) == "kühl"
        assert _kategorie_cpu_temp(44.9) == "kühl"

    def test_normal(self) -> None:
        assert _kategorie_cpu_temp(45.0) == "normal"
        assert _kategorie_cpu_temp(59.9) == "normal"

    def test_warm(self) -> None:
        assert _kategorie_cpu_temp(60.0) == "warm"
        assert _kategorie_cpu_temp(74.9) == "warm"

    def test_heiss(self) -> None:
        assert _kategorie_cpu_temp(75.0) == "heiß"
        assert _kategorie_cpu_temp(84.9) == "heiß"

    def test_kritisch(self) -> None:
        assert _kategorie_cpu_temp(85.0) == "kritisch"
        assert _kategorie_cpu_temp(100.0) == "kritisch"


class TestKategorieRam:
    """Kategorisierung des freien VM-RAM."""

    def test_frei(self) -> None:
        assert _kategorie_ram(1000.0) == "frei"
        assert _kategorie_ram(501.0) == "frei"

    def test_normal(self) -> None:
        assert _kategorie_ram(500.0) == "normal"
        assert _kategorie_ram(201.0) == "normal"

    def test_eng(self) -> None:
        assert _kategorie_ram(200.0) == "eng"
        assert _kategorie_ram(51.0) == "eng"

    def test_voll(self) -> None:
        assert _kategorie_ram(50.0) == "voll"
        assert _kategorie_ram(10.0) == "voll"


class TestKategorieCpuLast:
    """Kategorisierung der CPU-Auslastung."""

    def test_niedrig(self) -> None:
        assert _kategorie_cpu_last(0.0) == "niedrig"
        assert _kategorie_cpu_last(29.9) == "niedrig"

    def test_normal(self) -> None:
        assert _kategorie_cpu_last(30.0) == "normal"

    def test_hoch(self) -> None:
        assert _kategorie_cpu_last(60.0) == "hoch"

    def test_ueberlastet(self) -> None:
        assert _kategorie_cpu_last(90.0) == "überlastet"
        assert _kategorie_cpu_last(100.0) == "überlastet"


class TestKategorieLuefter:
    """Kategorisierung der Lüfter-RPM."""

    def test_leise(self) -> None:
        assert _kategorie_luefter(800.0) == "leise"

    def test_normal(self) -> None:
        assert _kategorie_luefter(1500.0) == "normal"

    def test_laut(self) -> None:
        assert _kategorie_luefter(2500.0) == "laut"

    def test_maximum(self) -> None:
        assert _kategorie_luefter(4000.0) == "maximum"


class TestKoerperFuehle:
    """Integration: Koerper.fuehle() liest und kategorisiert."""

    @patch("vm.genesis.koerper.psutil")
    @patch("vm.genesis.koerper.lese_sensoren")
    def test_fuehle_gibt_korrektes_format(
        self, mock_lese: MagicMock, mock_psutil: MagicMock, tmp_path: Path
    ) -> None:
        # Host-Sensoren simulieren
        mock_lese.return_value = {
            "zeitstempel": 1000.0,
            "cpu_temp_tctl": 65.0,
            "cpu_temp_tccd1": 55.0,
            "cpu_last_gesamt": 25.0,
            "ram_frei_mb": 20000.0,
            "luefter_rpm": 1100.0,
        }

        # VM-Sensoren simulieren
        vm_ram = MagicMock()
        vm_ram.available = 400 * 1024 * 1024  # 400 MB
        vm_ram.used = 1600 * 1024 * 1024
        mock_psutil.virtual_memory.return_value = vm_ram

        proc = MagicMock()
        mem_info = MagicMock()
        mem_info.rss = 50 * 1024 * 1024  # 50 MB
        proc.memory_info.return_value = mem_info
        proc.cpu_percent.return_value = 15.0
        mock_psutil.Process.return_value = proc

        sensor_pfad = tmp_path / "sensoren.bin"
        koerper = Koerper(sensor_pfad)

        ergebnis = koerper.fuehle()

        # Struktur prüfen
        assert "kategorien" in ergebnis
        assert "rohwerte" in ergebnis
        assert "zeitstempel" in ergebnis

        # Kategorien prüfen
        kat = ergebnis["kategorien"]
        assert kat["cpu_temp"] == "warm"       # 65°C
        assert kat["vm_ram"] == "normal"        # 400 MB frei
        assert kat["cpu_last_eigen"] == "niedrig"  # 15%
        assert kat["luefter"] == "leise"        # 1100 RPM
        assert kat["host_cpu_last"] == "niedrig"   # 25%
        assert kat["host_ram"] == "frei"        # 20000 MB

        # Rohwerte prüfen
        roh = ergebnis["rohwerte"]
        assert roh["cpu_temp_tctl"] == 65.0
        assert roh["luefter_rpm"] == 1100.0
        assert abs(roh["vm_ram_frei_mb"] - 400.0) < 1.0

    @patch("vm.genesis.koerper.psutil")
    @patch("vm.genesis.koerper.lese_sensoren")
    def test_fuehle_ohne_host_sensoren(
        self, mock_lese: MagicMock, mock_psutil: MagicMock, tmp_path: Path
    ) -> None:
        """Fallback wenn Sensordatei nicht lesbar."""
        mock_lese.return_value = None

        vm_ram = MagicMock()
        vm_ram.available = 300 * 1024 * 1024
        vm_ram.used = 1700 * 1024 * 1024
        mock_psutil.virtual_memory.return_value = vm_ram

        proc = MagicMock()
        mem_info = MagicMock()
        mem_info.rss = 40 * 1024 * 1024
        proc.memory_info.return_value = mem_info
        proc.cpu_percent.return_value = 5.0
        mock_psutil.Process.return_value = proc

        koerper = Koerper(tmp_path / "nichtda.bin")
        ergebnis = koerper.fuehle()

        # Fallback-Werte sollten sichere Kategorien ergeben
        assert ergebnis["rohwerte"]["cpu_temp_tctl"] == 50.0
        assert ergebnis["kategorien"]["cpu_temp"] == "normal"

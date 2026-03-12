"""Tests für den Sensor-Dienst (Sammler, Schreiber, Leser)."""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from host.sensor_dienst.sammler import SensorSammler
from host.sensor_dienst.schreiber import SensorSchreiber
from host.sensor_dienst.config import (
    SENSOR_CPU_TEMP_TCTL,
    SENSOR_CPU_LAST_GESAMT,
    SENSOR_RAM_GESAMT,
    SENSOR_RAM_BENUTZT,
    SENSOR_RAM_FREI,
    SENSOR_LUEFTER_1,
)
from shared.leser import lese_sensoren


# --- Sammler-Tests ---


class TestSammlerCpuTemperatur:
    """Tests für CPU-Temperatur-Messung."""

    def test_sammler_cpu_temperatur(self) -> None:
        """SensorSammler kann CPU-Temperatur lesen oder gibt leeres Dict."""
        sammler = SensorSammler()
        daten = sammler.sammle_temperatur()

        assert isinstance(daten, dict)
        if SENSOR_CPU_TEMP_TCTL in daten:
            assert 0.0 <= daten[SENSOR_CPU_TEMP_TCTL] <= 120.0


class TestSammlerCpuLast:
    """Tests für CPU-Auslastung."""

    def test_sammler_cpu_last(self) -> None:
        """CPU-Last ist ein Wert zwischen 0 und 100."""
        sammler = SensorSammler()
        daten = sammler.sammle_cpu_last()

        assert SENSOR_CPU_LAST_GESAMT in daten
        assert 0.0 <= daten[SENSOR_CPU_LAST_GESAMT] <= 100.0


class TestSammlerRam:
    """Tests für RAM-Messung."""

    def test_sammler_ram(self) -> None:
        """RAM-Werte sind sinnvoll: Gesamt > Benutzt, Frei > 0."""
        sammler = SensorSammler()
        daten = sammler.sammle_ram()

        assert SENSOR_RAM_GESAMT in daten
        assert SENSOR_RAM_BENUTZT in daten
        assert SENSOR_RAM_FREI in daten

        assert daten[SENSOR_RAM_GESAMT] > 0.0
        assert daten[SENSOR_RAM_BENUTZT] > 0.0
        assert daten[SENSOR_RAM_FREI] > 0.0
        assert daten[SENSOR_RAM_BENUTZT] < daten[SENSOR_RAM_GESAMT]


# --- Schreiber + Leser Tests ---


class TestSchreiberErstelltDatei:
    """Tests für Datei-Erstellung durch den Schreiber."""

    def test_schreiber_erstellt_datei(self, tmp_path: Path) -> None:
        """SensorSchreiber erstellt die Binärdatei."""
        schreiber = SensorSchreiber(verzeichnis=tmp_path, dateiname="test.bin")

        daten = {
            SENSOR_CPU_TEMP_TCTL: 55.0,
            SENSOR_CPU_LAST_GESAMT: 23.5,
            SENSOR_RAM_GESAMT: 30000.0,
            SENSOR_RAM_BENUTZT: 15000.0,
        }
        schreiber.schreibe(daten)

        datei_pfad = tmp_path / "test.bin"
        assert datei_pfad.exists()
        assert datei_pfad.stat().st_size > 0


class TestBinaerFormatLesbar:
    """Tests für Roundtrip: Schreiben und Lesen."""

    def test_binaer_format_lesbar(self, tmp_path: Path) -> None:
        """Geschriebene Datei kann vom Leser korrekt gelesen werden."""
        datei_pfad = tmp_path / "sensoren.bin"
        schreiber = SensorSchreiber(verzeichnis=tmp_path, dateiname="sensoren.bin")

        original = {
            SENSOR_CPU_TEMP_TCTL: 65.3,
            SENSOR_CPU_LAST_GESAMT: 42.7,
            SENSOR_RAM_GESAMT: 30720.0,
            SENSOR_RAM_BENUTZT: 18432.0,
            SENSOR_RAM_FREI: 12288.0,
            SENSOR_LUEFTER_1: 1200.0,
        }
        schreiber.schreibe(original)

        gelesen = lese_sensoren(datei_pfad)
        assert gelesen is not None

        # Werte prüfen (float32 hat begrenzte Präzision)
        assert gelesen["cpu_temp_tctl"] == pytest.approx(65.3, abs=0.1)
        assert gelesen["cpu_last_gesamt"] == pytest.approx(42.7, abs=0.1)
        assert gelesen["ram_gesamt_mb"] == pytest.approx(30720.0, abs=1.0)
        assert gelesen["ram_benutzt_mb"] == pytest.approx(18432.0, abs=1.0)
        assert gelesen["ram_frei_mb"] == pytest.approx(12288.0, abs=1.0)
        assert gelesen["luefter_rpm"] == pytest.approx(1200.0, abs=1.0)

        assert "zeitstempel" in gelesen
        assert gelesen["zeitstempel"] > 0.0


class TestAtomatesSchreiben:
    """Tests für atomares Schreiben (Datei nie korrupt)."""

    def test_atomares_schreiben(self, tmp_path: Path) -> None:
        """Datei ist nie korrupt, auch bei gleichzeitigem Schreiben und Lesen."""
        datei_pfad = tmp_path / "sensoren.bin"
        schreiber = SensorSchreiber(verzeichnis=tmp_path, dateiname="sensoren.bin")

        fehler: list[str] = []

        def schreibe_dauerhaft() -> None:
            for i in range(100):
                daten = {
                    SENSOR_CPU_TEMP_TCTL: 50.0 + i * 0.1,
                    SENSOR_CPU_LAST_GESAMT: float(i % 100),
                    SENSOR_RAM_GESAMT: 30000.0,
                    SENSOR_RAM_BENUTZT: 15000.0 + i,
                }
                try:
                    schreiber.schreibe(daten)
                except OSError as e:
                    fehler.append(f"Schreibfehler: {e}")

        def lese_dauerhaft() -> None:
            for _ in range(100):
                ergebnis = lese_sensoren(datei_pfad)
                if ergebnis is not None:
                    if "zeitstempel" not in ergebnis:
                        fehler.append("Kein Zeitstempel in gelesenen Daten")

        schreib_thread = threading.Thread(target=schreibe_dauerhaft)
        lese_thread = threading.Thread(target=lese_dauerhaft)

        schreib_thread.start()
        lese_thread.start()

        schreib_thread.join(timeout=10.0)
        lese_thread.join(timeout=10.0)

        assert len(fehler) == 0, f"Fehler aufgetreten: {fehler}"


class TestKonfigPfade:
    """Tests für konfigurierbare Pfade."""

    def test_konfigurierbare_pfade(self, tmp_path: Path) -> None:
        """Schreiber und Leser können mit Custom-Pfaden arbeiten."""
        custom_dir = tmp_path / "custom"
        custom_dir.mkdir()
        datei_pfad = custom_dir / "test.bin"

        schreiber = SensorSchreiber(verzeichnis=custom_dir, dateiname="test.bin")

        daten = {
            SENSOR_CPU_TEMP_TCTL: 45.0,
            SENSOR_RAM_GESAMT: 16000.0,
            SENSOR_RAM_BENUTZT: 8000.0,
        }
        schreiber.schreibe(daten)

        gelesen = lese_sensoren(datei_pfad)
        assert gelesen is not None
        assert gelesen["cpu_temp_tctl"] == pytest.approx(45.0, abs=0.1)

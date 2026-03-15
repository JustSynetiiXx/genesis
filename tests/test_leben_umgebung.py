"""Tests für leben.py — Umgebungs-Integration (extern lesen)."""

import json
import time
from pathlib import Path
from typing import Any

import pytest

from vm.genesis.leben import (
    _lese_umgebung,
    _wende_reiz_auf_rohwerte_an,
    _umgebung_sensoren_hinzufuegen,
    _UMGEBUNG_FALLBACK,
)


@pytest.fixture
def umgebung_datei(tmp_path: Path) -> Path:
    """Erstellt eine umgebung_status.json."""
    pfad = tmp_path / "umgebung_status.json"
    return pfad


class TestLeseUmgebung:
    """Tests für _lese_umgebung()."""

    def test_gibt_fallback_wenn_nicht_vorhanden(self, tmp_path: Path) -> None:
        pfad = tmp_path / "nicht_vorhanden.json"
        result = _lese_umgebung(pfad)
        assert result["rhythmus"] == 0.5
        assert result["phase"] == "embryo"

    def test_liest_json_korrekt(self, umgebung_datei: Path) -> None:
        daten: dict[str, Any] = {
            "rhythmus": 0.75,
            "phase": "fetus_frueh",
            "verfall_modifikator": 0.3,
            "reiz_aktiv": None,
            "feedback_zone": "normal_zone",
            "features": {"zusatz_aktionen": []},
            "zeitstempel": time.time(),
        }
        umgebung_datei.write_text(json.dumps(daten))
        result = _lese_umgebung(umgebung_datei)
        assert result["rhythmus"] == 0.75
        assert result["phase"] == "fetus_frueh"

    def test_gibt_fallback_bei_kaputtem_json(self, umgebung_datei: Path) -> None:
        umgebung_datei.write_text("{kaputt")
        result = _lese_umgebung(umgebung_datei)
        assert result == dict(_UMGEBUNG_FALLBACK)


class TestWendeReizAn:
    """Tests für _wende_reiz_auf_rohwerte_an()."""

    def test_kein_reiz_aendert_nichts(self) -> None:
        rohwerte = {"cpu_temp_tctl": 50.0, "luefter_rpm": 1000.0}
        umg: dict[str, Any] = {"reiz_aktiv": None}
        result = _wende_reiz_auf_rohwerte_an(rohwerte, umg)
        assert result["cpu_temp_tctl"] == 50.0

    def test_vibration_erhoeht_luefter(self) -> None:
        rohwerte = {"luefter_rpm": 1000.0}
        umg: dict[str, Any] = {"reiz_aktiv": "vibration", "reiz_staerke": 15.0}
        result = _wende_reiz_auf_rohwerte_an(rohwerte, umg)
        assert result["luefter_rpm"] == 1015.0

    def test_waerme_erhoeht_temperatur(self) -> None:
        rohwerte = {"cpu_temp_tctl": 50.0, "cpu_temp_tccd1": 48.0}
        umg: dict[str, Any] = {"reiz_aktiv": "waerme", "reiz_staerke": 4.0}
        result = _wende_reiz_auf_rohwerte_an(rohwerte, umg)
        assert result["cpu_temp_tctl"] == 54.0
        assert result["cpu_temp_tccd1"] == 52.0

    def test_druck_reduziert_ram(self) -> None:
        rohwerte = {"host_ram_frei_mb": 16000.0}
        umg: dict[str, Any] = {"reiz_aktiv": "druck", "reiz_staerke": 80.0}
        result = _wende_reiz_auf_rohwerte_an(rohwerte, umg)
        assert result["host_ram_frei_mb"] == 15920.0

    def test_null_staerke_aendert_nichts(self) -> None:
        rohwerte = {"luefter_rpm": 1000.0}
        umg: dict[str, Any] = {"reiz_aktiv": "vibration", "reiz_staerke": 0.0}
        result = _wende_reiz_auf_rohwerte_an(rohwerte, umg)
        assert result["luefter_rpm"] == 1000.0


class TestUmgebungSensoren:
    """Tests für _umgebung_sensoren_hinzufuegen()."""

    def test_fuegt_rhythmus_hinzu(self) -> None:
        rohwerte: dict[str, Any] = {}
        umg: dict[str, Any] = {"rhythmus": 0.8, "reiz_aktiv": None}
        _umgebung_sensoren_hinzufuegen(rohwerte, umg)
        assert rohwerte["umgebung_rhythmus"] == 0.8
        assert rohwerte["reiz_aktiv"] == 0.0
        assert rohwerte["reiz_typ"] == "keiner"

    def test_fuegt_reiz_hinzu(self) -> None:
        rohwerte: dict[str, Any] = {}
        umg: dict[str, Any] = {"rhythmus": 0.5, "reiz_aktiv": "vibration"}
        _umgebung_sensoren_hinzufuegen(rohwerte, umg)
        assert rohwerte["reiz_aktiv"] == 1.0
        assert rohwerte["reiz_typ"] == "vibration"

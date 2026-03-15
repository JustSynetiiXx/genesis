"""Tests für host/umgebung_dienst/dienst.py — Umgebungs-Dienst."""

import json
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest

from host.umgebung_dienst.dienst import (
    UmgebungsDienst,
    VERFALL_BASIS,
    PHASE_SCHWELLEN,
    REIZ_TYPEN,
)


@pytest.fixture
def tmp_verzeichnis(tmp_path: Path) -> Path:
    """Temporäres Verzeichnis für Tests."""
    return tmp_path


@pytest.fixture
def dienst(tmp_verzeichnis: Path) -> UmgebungsDienst:
    """Erstellt einen UmgebungsDienst mit temporären Pfaden."""
    ausgabe = tmp_verzeichnis / "umgebung_status.json"
    wachzeit = tmp_verzeichnis / "wachzeit.txt"
    instanz_pfade = {
        "test-1": tmp_verzeichnis / "status_1.json",
    }
    return UmgebungsDienst(
        ausgabe_pfad=ausgabe,
        instanz_pfade=instanz_pfade,
        wachzeit_pfad=wachzeit,
    )


class TestUmgebungsDienstInit:
    """Tests für die Initialisierung."""

    def test_erstellt_dienst(self, dienst: UmgebungsDienst) -> None:
        assert dienst is not None

    def test_wachzeit_anfangs_null(self, dienst: UmgebungsDienst) -> None:
        assert dienst._kumulative_wachzeit == 0.0


class TestTick:
    """Tests für tick()."""

    def test_tick_gibt_dict_zurueck(self, dienst: UmgebungsDienst) -> None:
        result = dienst.tick()
        assert isinstance(result, dict)

    def test_tick_hat_pflichtfelder(self, dienst: UmgebungsDienst) -> None:
        result = dienst.tick()
        assert "rhythmus" in result
        assert "phase" in result
        assert "verfall_modifikator" in result
        assert "feedback_zone" in result
        assert "features" in result
        assert "zeitstempel" in result

    def test_rhythmus_zwischen_0_und_1(self, dienst: UmgebungsDienst) -> None:
        result = dienst.tick()
        assert 0.0 <= result["rhythmus"] <= 1.0

    def test_phase_ist_embryo_anfangs(self, dienst: UmgebungsDienst) -> None:
        result = dienst.tick()
        assert result["phase"] == "embryo"

    def test_verfall_modifikator_positiv(self, dienst: UmgebungsDienst) -> None:
        result = dienst.tick()
        assert result["verfall_modifikator"] > 0

    def test_wachzeit_erhoht_sich(self, dienst: UmgebungsDienst) -> None:
        dienst.tick()
        assert dienst._kumulative_wachzeit > 0

    def test_features_in_embryo(self, dienst: UmgebungsDienst) -> None:
        result = dienst.tick()
        features = result["features"]
        assert features["rhythmus_aktiv"] is False  # Embryo hat keinen Rhythmus
        assert features["reize_aktiv"] is False
        assert features["feedback_aktiv"] is False


class TestPhaseEntwicklung:
    """Tests für Phasenübergänge."""

    def test_embryo_bei_null_tagen(self, dienst: UmgebungsDienst) -> None:
        phase, _ = dienst._aktuelle_phase()
        assert phase == "embryo"

    def test_fetus_frueh_nach_schwelle(self, dienst: UmgebungsDienst) -> None:
        dienst._kumulative_wachzeit = PHASE_SCHWELLEN["fetus_frueh"] * 86400
        phase, _ = dienst._aktuelle_phase()
        assert phase == "fetus_frueh"

    def test_fetus_spaet_nach_schwelle(self, dienst: UmgebungsDienst) -> None:
        dienst._kumulative_wachzeit = PHASE_SCHWELLEN["fetus_spaet"] * 86400
        phase, _ = dienst._aktuelle_phase()
        assert phase == "fetus_spaet"

    def test_reif_nach_schwelle(self, dienst: UmgebungsDienst) -> None:
        dienst._kumulative_wachzeit = PHASE_SCHWELLEN["reif"] * 86400
        phase, _ = dienst._aktuelle_phase()
        assert phase == "reif"


class TestSchreibeStatus:
    """Tests für schreibe_status()."""

    def test_schreibt_json_datei(self, dienst: UmgebungsDienst,
                                  tmp_verzeichnis: Path) -> None:
        status = dienst.tick()
        dienst.schreibe_status(status)
        ausgabe = tmp_verzeichnis / "umgebung_status.json"
        assert ausgabe.exists()
        daten = json.loads(ausgabe.read_bytes())
        assert "rhythmus" in daten
        assert "phase" in daten

    def test_json_ist_valide(self, dienst: UmgebungsDienst,
                              tmp_verzeichnis: Path) -> None:
        status = dienst.tick()
        dienst.schreibe_status(status)
        ausgabe = tmp_verzeichnis / "umgebung_status.json"
        daten = json.loads(ausgabe.read_bytes())
        assert isinstance(daten["rhythmus"], float)
        assert isinstance(daten["phase"], str)


class TestFeedback:
    """Tests für Feedback-Controller."""

    def test_liest_leere_instanzen(self, dienst: UmgebungsDienst) -> None:
        werte = dienst._lese_instanz_schmerz()
        assert werte == []

    def test_liest_instanz_schmerz(self, dienst: UmgebungsDienst,
                                    tmp_verzeichnis: Path) -> None:
        # Schreibe einen simulierten Genesis-Status
        status_pfad = tmp_verzeichnis / "status_1.json"
        status_pfad.write_text(json.dumps({
            "zeitstempel": time.time(),
            "schmerz": 0.15,
        }))
        werte = dienst._lese_instanz_schmerz()
        assert len(werte) == 1
        assert abs(werte[0] - 0.15) < 0.001

    def test_ignoriert_alte_daten(self, dienst: UmgebungsDienst,
                                   tmp_verzeichnis: Path) -> None:
        status_pfad = tmp_verzeichnis / "status_1.json"
        status_pfad.write_text(json.dumps({
            "zeitstempel": time.time() - 60,  # 60s alt
            "schmerz": 0.5,
        }))
        werte = dienst._lese_instanz_schmerz()
        assert werte == []


class TestWachzeit:
    """Tests für persistente Wachzeit."""

    def test_speichert_wachzeit(self, dienst: UmgebungsDienst,
                                 tmp_verzeichnis: Path) -> None:
        dienst._kumulative_wachzeit = 12345.0
        dienst._speichere_wachzeit()
        wachzeit_pfad = tmp_verzeichnis / "wachzeit.txt"
        assert wachzeit_pfad.exists()
        assert abs(float(wachzeit_pfad.read_text().strip()) - 12345.0) < 1.0

    def test_laedt_wachzeit(self, tmp_verzeichnis: Path) -> None:
        wachzeit_pfad = tmp_verzeichnis / "wachzeit.txt"
        wachzeit_pfad.write_text("5000.0\n")
        dienst = UmgebungsDienst(
            ausgabe_pfad=tmp_verzeichnis / "status.json",
            instanz_pfade={},
            wachzeit_pfad=wachzeit_pfad,
        )
        assert abs(dienst._kumulative_wachzeit - 5000.0) < 1.0


class TestNaehrung:
    """Tests für Nährstoff-Schübe."""

    def test_schub_nicht_sofort(self, dienst: UmgebungsDienst) -> None:
        result = dienst.tick()
        assert result["schub_aktiv"] is False

    def test_schub_nach_vielen_ticks(self, dienst: UmgebungsDienst) -> None:
        schub_gefunden = False
        for _ in range(200):
            result = dienst.tick()
            if result["schub_aktiv"]:
                schub_gefunden = True
                assert result["schub_menge"] > 0
                break
        assert schub_gefunden, "Kein Schub innerhalb von 200 Ticks"

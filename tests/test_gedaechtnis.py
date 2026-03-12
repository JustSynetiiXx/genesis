"""Tests für vm/genesis/gedaechtnis.py — SQLite Gedächtnis."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from vm.genesis.gedaechtnis import (
    Erfahrung,
    Heartbeat,
    KurzzeitGedaechtnis,
    LangzeitGedaechtnis,
)


@pytest.fixture
def kurzzeit(tmp_path: Path) -> KurzzeitGedaechtnis:
    return KurzzeitGedaechtnis(tmp_path / "kurzzeit.db")


@pytest.fixture
def langzeit(tmp_path: Path) -> LangzeitGedaechtnis:
    return LangzeitGedaechtnis(tmp_path / "langzeit.db")


@pytest.fixture
def heartbeat(tmp_path: Path) -> Heartbeat:
    return Heartbeat(tmp_path / "heartbeat.db")


def _mache_erfahrung(
    zustand: dict[str, str] | None = None,
    aktion: str = "speicher_verkleinern",
    delta: float = -0.2,
) -> Erfahrung:
    """Hilfsfunktion zum Erstellen einer Test-Erfahrung."""
    z = zustand or {"cpu_temp": "warm", "vm_ram": "eng"}
    return Erfahrung(
        zustand_vorher=z,
        aktion=aktion,
        zustand_nachher={"cpu_temp": "warm", "vm_ram": "normal"},
        schmerz_vorher=0.5,
        schmerz_nachher=0.5 + delta,
        schmerz_delta=delta,
        zeitstempel=time.time(),
    )


class TestKurzzeitGedaechtnis:
    """Kurzzeitgedächtnis: Speichern, Suchen, Leeren."""

    def test_speichern_und_zaehlen(self, kurzzeit: KurzzeitGedaechtnis) -> None:
        kurzzeit.speichere(_mache_erfahrung())
        assert kurzzeit.anzahl() == 1

    def test_mehrere_speichern(self, kurzzeit: KurzzeitGedaechtnis) -> None:
        for _ in range(5):
            kurzzeit.speichere(_mache_erfahrung())
        assert kurzzeit.anzahl() == 5

    def test_suche_findet_richtigen_zustand(self, kurzzeit: KurzzeitGedaechtnis) -> None:
        zustand_a = {"cpu_temp": "warm", "vm_ram": "eng"}
        zustand_b = {"cpu_temp": "kühl", "vm_ram": "frei"}
        kurzzeit.speichere(_mache_erfahrung(zustand=zustand_a))
        kurzzeit.speichere(_mache_erfahrung(zustand=zustand_b))

        ergebnisse = kurzzeit.suche(zustand_a)
        assert len(ergebnisse) == 1
        assert ergebnisse[0].zustand_vorher == zustand_a

    def test_suche_mit_aktion(self, kurzzeit: KurzzeitGedaechtnis) -> None:
        zustand = {"cpu_temp": "warm", "vm_ram": "eng"}
        kurzzeit.speichere(_mache_erfahrung(zustand=zustand, aktion="speicher_verkleinern"))
        kurzzeit.speichere(_mache_erfahrung(zustand=zustand, aktion="nichts_tun"))

        ergebnisse = kurzzeit.suche(zustand, aktion="speicher_verkleinern")
        assert len(ergebnisse) == 1

    def test_leere(self, kurzzeit: KurzzeitGedaechtnis) -> None:
        kurzzeit.speichere(_mache_erfahrung())
        kurzzeit.speichere(_mache_erfahrung())
        kurzzeit.leere()
        assert kurzzeit.anzahl() == 0

    def test_alle_erfahrungen(self, kurzzeit: KurzzeitGedaechtnis) -> None:
        for _ in range(3):
            kurzzeit.speichere(_mache_erfahrung())
        alle = kurzzeit.alle_erfahrungen()
        assert len(alle) == 3


class TestLangzeitGedaechtnis:
    """Langzeitgedächtnis: Aktualisieren, Suchen, Tode."""

    def test_aktualisiere_und_suche(self, langzeit: LangzeitGedaechtnis) -> None:
        zustand = {"cpu_temp": "warm", "vm_ram": "eng"}
        langzeit.aktualisiere(zustand, "speicher_verkleinern", -0.3, time.time())

        ergebnisse = langzeit.suche(zustand)
        assert len(ergebnisse) == 1
        assert ergebnisse[0].aktion == "speicher_verkleinern"
        assert ergebnisse[0].durchschnitt_delta == -0.3
        assert ergebnisse[0].anzahl == 1

    def test_laufender_durchschnitt(self, langzeit: LangzeitGedaechtnis) -> None:
        zustand = {"cpu_temp": "warm", "vm_ram": "eng"}
        langzeit.aktualisiere(zustand, "speicher_verkleinern", -0.4, time.time())
        langzeit.aktualisiere(zustand, "speicher_verkleinern", -0.2, time.time())

        ergebnisse = langzeit.suche(zustand)
        assert len(ergebnisse) == 1
        assert abs(ergebnisse[0].durchschnitt_delta - (-0.3)) < 0.01
        assert ergebnisse[0].anzahl == 2

    def test_verschiedene_aktionen(self, langzeit: LangzeitGedaechtnis) -> None:
        zustand = {"cpu_temp": "warm", "vm_ram": "eng"}
        langzeit.aktualisiere(zustand, "speicher_verkleinern", -0.5, time.time())
        langzeit.aktualisiere(zustand, "nichts_tun", 0.1, time.time())

        ergebnisse = langzeit.suche(zustand)
        assert len(ergebnisse) == 2
        # Sortiert nach delta ASC → negativstes zuerst
        assert ergebnisse[0].aktion == "speicher_verkleinern"

    def test_speichere_tod(self, langzeit: LangzeitGedaechtnis) -> None:
        langzeit.speichere_tod(
            zeitstempel_tod=1000.0,
            zeitstempel_aufwachen=1100.0,
            letzter_zustand={"vm_ram": "voll"},
            letzter_schmerz=0.9,
            war_schlaf=False,
        )
        assert langzeit.anzahl_tode() == 1

    def test_speichere_schlaf_kein_tod(self, langzeit: LangzeitGedaechtnis) -> None:
        langzeit.speichere_tod(
            zeitstempel_tod=1000.0,
            zeitstempel_aufwachen=0.0,
            letzter_zustand={"vm_ram": "normal"},
            letzter_schmerz=0.1,
            war_schlaf=True,
        )
        assert langzeit.anzahl_tode() == 0  # Schlaf zählt nicht als Tod

    def test_letzter_tod(self, langzeit: LangzeitGedaechtnis) -> None:
        langzeit.speichere_tod(1000.0, 1100.0, {"vm_ram": "voll"}, 0.9, False)
        langzeit.speichere_tod(2000.0, 2100.0, {"cpu_temp": "kritisch"}, 0.95, False)

        letzter = langzeit.letzter_tod()
        assert letzter is not None
        assert letzter["zeitstempel"] == 2000.0


class TestHeartbeat:
    """Heartbeat: Zustandsspeicherung und Schlaf-Marker."""

    def test_erster_lese_leer(self, heartbeat: Heartbeat) -> None:
        assert heartbeat.lese() is None

    def test_aktualisiere_und_lese(self, heartbeat: Heartbeat) -> None:
        zustand = {"cpu_temp": "normal"}
        heartbeat.aktualisiere(zustand, 0.2)

        hb = heartbeat.lese()
        assert hb is not None
        assert hb["zustand"] == zustand
        assert hb["schmerz"] == 0.2
        assert hb["schlaf_marker"] is False

    def test_schlaf_marker_setzen(self, heartbeat: Heartbeat) -> None:
        heartbeat.aktualisiere({"cpu_temp": "normal"}, 0.1, schlaf_marker=True)

        hb = heartbeat.lese()
        assert hb is not None
        assert hb["schlaf_marker"] is True

    def test_schlaf_marker_zuruecksetzen(self, heartbeat: Heartbeat) -> None:
        heartbeat.aktualisiere({"cpu_temp": "normal"}, 0.1, schlaf_marker=True)
        heartbeat.setze_schlaf_marker(False)

        hb = heartbeat.lese()
        assert hb is not None
        assert hb["schlaf_marker"] is False

    def test_ueberschreibt_vorherigen(self, heartbeat: Heartbeat) -> None:
        heartbeat.aktualisiere({"cpu_temp": "kühl"}, 0.0)
        heartbeat.aktualisiere({"cpu_temp": "heiß"}, 0.8)

        hb = heartbeat.lese()
        assert hb is not None
        assert hb["zustand"] == {"cpu_temp": "heiß"}
        assert hb["schmerz"] == 0.8

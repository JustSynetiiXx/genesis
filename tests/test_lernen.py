"""Tests für vm/genesis/lernen.py — Lernmechanismus."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from vm.genesis.gedaechtnis import Erfahrung, KurzzeitGedaechtnis, LangzeitGedaechtnis
from vm.genesis.lernen import (
    exploration_wahrscheinlichkeit,
    lerne,
    lerne_aus_reflex,
    lernsignal_staerke,
    waehle_aktion,
)


@pytest.fixture
def kurzzeit(tmp_path: Path) -> KurzzeitGedaechtnis:
    return KurzzeitGedaechtnis(tmp_path / "kurzzeit.db")


@pytest.fixture
def langzeit(tmp_path: Path) -> LangzeitGedaechtnis:
    return LangzeitGedaechtnis(tmp_path / "langzeit.db")


class TestExplorationWahrscheinlichkeit:
    """Schmerzgesteuerte Exploration."""

    def test_unbekannter_zustand_immer_exploration(self) -> None:
        assert exploration_wahrscheinlichkeit(0.5, None) == 1.0

    def test_niedriger_schmerz_gute_erfahrung_wenig_exploration(self) -> None:
        p = exploration_wahrscheinlichkeit(0.1, -0.3)
        assert p < 0.1  # Fast nie explorieren

    def test_hoher_schmerz_keine_gute_erfahrung_viel_exploration(self) -> None:
        p = exploration_wahrscheinlichkeit(0.8, 0.1)
        assert p > 0.7  # Fast immer explorieren

    def test_hoher_schmerz_mit_guter_erfahrung_moderate_exploration(self) -> None:
        p = exploration_wahrscheinlichkeit(0.6, -0.2)
        assert 0.1 < p < 0.7


class TestLernsignalStaerke:
    """Lerngeschwindigkeit proportional zur Signalstärke."""

    def test_stark(self) -> None:
        assert lernsignal_staerke(-0.5) == "stark"
        assert lernsignal_staerke(0.4) == "stark"

    def test_mittel(self) -> None:
        assert lernsignal_staerke(-0.05) == "mittel"
        assert lernsignal_staerke(0.08) == "mittel"

    def test_schwach(self) -> None:
        assert lernsignal_staerke(-0.01) == "schwach"
        assert lernsignal_staerke(0.0) == "schwach"


class TestWaehleAktion:
    """Aktionswahl: Exploitation vs. Exploration."""

    def test_unbekannter_zustand_gibt_gueltige_aktion(
        self, kurzzeit: KurzzeitGedaechtnis, langzeit: LangzeitGedaechtnis
    ) -> None:
        zustand = {"cpu_temp": "warm", "vm_ram": "eng"}
        aktion, ist_exploration = waehle_aktion(zustand, 0.5, kurzzeit, langzeit)
        assert isinstance(aktion, str)
        assert ist_exploration is True  # Unbekannt → immer Exploration

    def test_bekannter_zustand_exploitation(
        self, kurzzeit: KurzzeitGedaechtnis, langzeit: LangzeitGedaechtnis
    ) -> None:
        """Bei niedrigem Schmerz und guter Erfahrung: Exploitation."""
        zustand = {"cpu_temp": "warm", "vm_ram": "eng"}
        # Gute Erfahrung ins Langzeitgedächtnis
        langzeit.aktualisiere(zustand, "speicher_verkleinern", -0.5, time.time())

        # Bei sehr niedrigem Schmerz sollte meistens Exploitation kommen
        exploitation_count = 0
        for _ in range(50):
            _, ist_exploration = waehle_aktion(zustand, 0.05, kurzzeit, langzeit)
            if not ist_exploration:
                exploitation_count += 1

        # Mindestens 80% Exploitation bei niedrigem Schmerz
        assert exploitation_count >= 40

    def test_exploitation_waehlt_beste_aktion(
        self, kurzzeit: KurzzeitGedaechtnis, langzeit: LangzeitGedaechtnis
    ) -> None:
        zustand = {"cpu_temp": "warm", "vm_ram": "eng"}
        langzeit.aktualisiere(zustand, "speicher_verkleinern", -0.5, time.time())
        langzeit.aktualisiere(zustand, "nichts_tun", 0.1, time.time())

        # Sammle Exploitation-Aktionen
        aktionen = []
        for _ in range(100):
            aktion, ist_exploration = waehle_aktion(zustand, 0.05, kurzzeit, langzeit)
            if not ist_exploration:
                aktionen.append(aktion)

        # Die meisten Exploitation-Aktionen sollten die beste sein
        if aktionen:
            assert aktionen.count("speicher_verkleinern") > len(aktionen) * 0.5


class TestLerne:
    """Erfahrungsverarbeitung."""

    def test_speichert_in_kurzzeit(
        self, kurzzeit: KurzzeitGedaechtnis, langzeit: LangzeitGedaechtnis
    ) -> None:
        erfahrung = Erfahrung(
            zustand_vorher={"cpu_temp": "warm"},
            aktion="speicher_verkleinern",
            zustand_nachher={"cpu_temp": "warm"},
            schmerz_vorher=0.5,
            schmerz_nachher=0.4,
            schmerz_delta=-0.1,
            zeitstempel=time.time(),
        )
        lerne(erfahrung, kurzzeit, langzeit)
        assert kurzzeit.anzahl() == 1

    def test_starkes_signal_sofort_in_langzeit(
        self, kurzzeit: KurzzeitGedaechtnis, langzeit: LangzeitGedaechtnis
    ) -> None:
        erfahrung = Erfahrung(
            zustand_vorher={"cpu_temp": "warm"},
            aktion="speicher_verkleinern",
            zustand_nachher={"cpu_temp": "normal"},
            schmerz_vorher=0.8,
            schmerz_nachher=0.3,
            schmerz_delta=-0.5,  # Stark!
            zeitstempel=time.time(),
        )
        lerne(erfahrung, kurzzeit, langzeit)
        assert langzeit.anzahl_gelernt() == 1

    def test_schwaches_signal_nicht_in_langzeit(
        self, kurzzeit: KurzzeitGedaechtnis, langzeit: LangzeitGedaechtnis
    ) -> None:
        erfahrung = Erfahrung(
            zustand_vorher={"cpu_temp": "warm"},
            aktion="nichts_tun",
            zustand_nachher={"cpu_temp": "warm"},
            schmerz_vorher=0.3,
            schmerz_nachher=0.28,
            schmerz_delta=-0.02,  # Schwach
            zeitstempel=time.time(),
        )
        lerne(erfahrung, kurzzeit, langzeit)
        assert langzeit.anzahl_gelernt() == 0


class TestLerneAusReflex:
    """Reflex-Lernen: Letzte bewusste Aktion als negative Erfahrung."""

    def test_reflex_erzeugt_negative_erfahrung_in_kurzzeit(
        self, kurzzeit: KurzzeitGedaechtnis, langzeit: LangzeitGedaechtnis
    ) -> None:
        """Wenn ein Reflex feuert, wird die letzte bewusste Aktion
        als negative Erfahrung im Kurzzeitgedächtnis gespeichert."""
        zustand_entscheidung = {"cpu_temp": "warm", "vm_ram": "normal"}
        zustand_reflex = {"cpu_temp": "heiss", "vm_ram": "eng"}

        lerne_aus_reflex(
            zustand_bei_entscheidung=zustand_entscheidung,
            letzte_aktion="rechenintensitaet_hoch",
            zustand_bei_reflex=zustand_reflex,
            schmerz_bei_reflex=0.75,
            kurzzeit=kurzzeit,
            langzeit=langzeit,
        )

        assert kurzzeit.anzahl() == 1
        erfahrungen = kurzzeit.suche(zustand_entscheidung)
        assert len(erfahrungen) == 1
        assert erfahrungen[0].aktion == "rechenintensitaet_hoch"
        assert erfahrungen[0].schmerz_delta == pytest.approx(0.75)

    def test_reflex_speichert_in_langzeit(
        self, kurzzeit: KurzzeitGedaechtnis, langzeit: LangzeitGedaechtnis
    ) -> None:
        """Reflex-Erfahrung wird immer im Langzeitgedächtnis gespeichert
        (starkes Signal per Definition)."""
        zustand_entscheidung = {"cpu_temp": "warm", "vm_ram": "normal"}
        zustand_reflex = {"cpu_temp": "heiss", "vm_ram": "eng"}

        lerne_aus_reflex(
            zustand_bei_entscheidung=zustand_entscheidung,
            letzte_aktion="rechenintensitaet_hoch",
            zustand_bei_reflex=zustand_reflex,
            schmerz_bei_reflex=0.75,
            kurzzeit=kurzzeit,
            langzeit=langzeit,
        )

        # Letzte Aktion negativ bewertet
        gelernt = langzeit.suche(zustand_entscheidung)
        assert len(gelernt) == 1
        assert gelernt[0].aktion == "rechenintensitaet_hoch"
        assert gelernt[0].durchschnitt_delta > 0  # Positiv = schlecht

    def test_reflex_markiert_zustand_als_gefaehrlich(
        self, kurzzeit: KurzzeitGedaechtnis, langzeit: LangzeitGedaechtnis
    ) -> None:
        """Der Zustand beim Reflex wird als gefährlich markiert:
        'nichts tun' bekommt einen hohen positiven Delta."""
        zustand_entscheidung = {"cpu_temp": "warm", "vm_ram": "normal"}
        zustand_reflex = {"cpu_temp": "heiss", "vm_ram": "eng"}

        lerne_aus_reflex(
            zustand_bei_entscheidung=zustand_entscheidung,
            letzte_aktion="rechenintensitaet_hoch",
            zustand_bei_reflex=zustand_reflex,
            schmerz_bei_reflex=0.75,
            kurzzeit=kurzzeit,
            langzeit=langzeit,
        )

        # Reflex-Zustand: "nichts" als schlecht gelernt
        gelernt_reflex = langzeit.suche(zustand_reflex)
        assert len(gelernt_reflex) == 1
        assert gelernt_reflex[0].aktion == "nichts"
        assert gelernt_reflex[0].durchschnitt_delta == pytest.approx(0.75)

    def test_reflex_ohne_vorherige_aktion_kein_crash(
        self, kurzzeit: KurzzeitGedaechtnis, langzeit: LangzeitGedaechtnis
    ) -> None:
        """Sicherstellen dass die Funktion mit beliebigen Zuständen funktioniert."""
        lerne_aus_reflex(
            zustand_bei_entscheidung={},
            letzte_aktion="nichts",
            zustand_bei_reflex={"vm_ram": "kritisch"},
            schmerz_bei_reflex=0.9,
            kurzzeit=kurzzeit,
            langzeit=langzeit,
        )
        assert kurzzeit.anzahl() == 1
        # 2 Langzeit-Einträge: leerer Zustand + Reflex-Zustand
        assert langzeit.anzahl_gelernt() == 2

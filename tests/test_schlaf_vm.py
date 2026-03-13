"""Tests für vm/genesis/schlaf.py — Schlaf-Wach-Zyklus."""

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
from vm.genesis.schlaf import aufwachen, einschlafen, schlaf_signal_vorhanden


@pytest.fixture
def kurzzeit(tmp_path: Path) -> KurzzeitGedaechtnis:
    return KurzzeitGedaechtnis(tmp_path / "kurzzeit.db")


@pytest.fixture
def langzeit(tmp_path: Path) -> LangzeitGedaechtnis:
    return LangzeitGedaechtnis(tmp_path / "langzeit.db")


@pytest.fixture
def heartbeat(tmp_path: Path) -> Heartbeat:
    return Heartbeat(tmp_path / "heartbeat.db")


class TestSchlafSignal:
    """SLEEP-Signal erkennen."""

    def test_kein_signal(self, tmp_path: Path) -> None:
        assert schlaf_signal_vorhanden(tmp_path / "signal.txt") is False

    def test_sleep_signal(self, tmp_path: Path) -> None:
        signal_datei = tmp_path / "signal.txt"
        signal_datei.write_text("SLEEP 1234567890\n")
        assert schlaf_signal_vorhanden(signal_datei) is True

    def test_anderes_signal(self, tmp_path: Path) -> None:
        signal_datei = tmp_path / "signal.txt"
        signal_datei.write_text("GOOD\n")
        assert schlaf_signal_vorhanden(signal_datei) is False


class TestEinschlafen:
    """Sauberes Einschlafen mit Konsolidierung."""

    def test_konsolidierung_starke_erfahrung(
        self,
        kurzzeit: KurzzeitGedaechtnis,
        langzeit: LangzeitGedaechtnis,
        heartbeat: Heartbeat,
        tmp_path: Path,
    ) -> None:
        # Starke Erfahrung ins Kurzzeitgedächtnis
        kurzzeit.speichere(Erfahrung(
            zustand_vorher={"cpu_temp": "warm"},
            aktion="speicher_verkleinern",
            zustand_nachher={"cpu_temp": "normal"},
            schmerz_vorher=0.8,
            schmerz_nachher=0.3,
            schmerz_delta=-0.5,
            zeitstempel=time.time(),
        ))

        signal_pfad = tmp_path / "signal.txt"
        konsolidiert = einschlafen(
            kurzzeit, langzeit, heartbeat,
            {"cpu_temp": "normal"}, 0.1, signal_pfad,
        )

        assert konsolidiert >= 1
        assert kurzzeit.anzahl() == 0  # Kurzzeit geleert
        assert langzeit.anzahl_gelernt() >= 1  # In Langzeit übertragen

    def test_schlaf_marker_gesetzt(
        self,
        kurzzeit: KurzzeitGedaechtnis,
        langzeit: LangzeitGedaechtnis,
        heartbeat: Heartbeat,
        tmp_path: Path,
    ) -> None:
        einschlafen(
            kurzzeit, langzeit, heartbeat,
            {"cpu_temp": "normal"}, 0.1, tmp_path / "signal.txt",
        )
        hb = heartbeat.lese()
        assert hb is not None
        assert hb["schlaf_marker"] is True

    def test_ready_signal_geschrieben(
        self,
        kurzzeit: KurzzeitGedaechtnis,
        langzeit: LangzeitGedaechtnis,
        heartbeat: Heartbeat,
        tmp_path: Path,
    ) -> None:
        signal_pfad = tmp_path / "signal.txt"
        einschlafen(
            kurzzeit, langzeit, heartbeat,
            {"cpu_temp": "normal"}, 0.1, signal_pfad,
        )
        assert signal_pfad.read_text().strip() == "READY"

    def test_schwache_erfahrung_nicht_konsolidiert(
        self,
        kurzzeit: KurzzeitGedaechtnis,
        langzeit: LangzeitGedaechtnis,
        heartbeat: Heartbeat,
        tmp_path: Path,
    ) -> None:
        # Schwache Einzel-Erfahrung
        kurzzeit.speichere(Erfahrung(
            zustand_vorher={"cpu_temp": "normal"},
            aktion="nichts_tun",
            zustand_nachher={"cpu_temp": "normal"},
            schmerz_vorher=0.2,
            schmerz_nachher=0.19,
            schmerz_delta=-0.01,
            zeitstempel=time.time(),
        ))

        einschlafen(
            kurzzeit, langzeit, heartbeat,
            {"cpu_temp": "normal"}, 0.1, tmp_path / "signal.txt",
        )

        assert langzeit.anzahl_gelernt() == 0  # Nicht konsolidiert


class TestAufwachen:
    """Aufwachen: Schlaf vs. Tod erkennen."""

    def test_erststart(
        self, langzeit: LangzeitGedaechtnis, heartbeat: Heartbeat
    ) -> None:
        status = aufwachen(langzeit, heartbeat)
        assert status["typ"] == "erststart"

    def test_nach_schlaf(
        self, langzeit: LangzeitGedaechtnis, heartbeat: Heartbeat
    ) -> None:
        # Simuliere: Heartbeat mit Schlaf-Marker
        heartbeat.aktualisiere({"cpu_temp": "normal"}, 0.1, schlaf_marker=True)

        status = aufwachen(langzeit, heartbeat)
        assert status["typ"] == "schlaf"

        # Schlaf-Marker sollte zurückgesetzt sein
        hb = heartbeat.lese()
        assert hb is not None
        assert hb["schlaf_marker"] is False

    def test_nach_tod(
        self, langzeit: LangzeitGedaechtnis, heartbeat: Heartbeat
    ) -> None:
        # Simuliere: Heartbeat OHNE Schlaf-Marker (= Absturz)
        heartbeat.aktualisiere({"vm_ram": "voll"}, 0.9, schlaf_marker=False)

        status = aufwachen(langzeit, heartbeat)
        assert status["typ"] == "tod"
        assert status["letzter_schmerz"] == 0.9

        # Tod-Erfahrung sollte im Langzeitgedächtnis sein
        assert langzeit.anzahl_tode() == 1

    def test_tod_erzeugt_lernsignal(
        self, langzeit: LangzeitGedaechtnis, heartbeat: Heartbeat
    ) -> None:
        heartbeat.aktualisiere({"vm_ram": "voll"}, 0.9, schlaf_marker=False)
        aufwachen(langzeit, heartbeat)

        # Zustand "vm_ram: voll" sollte als schlecht gelernt sein
        ergebnisse = langzeit.suche({"vm_ram": "voll"})
        assert len(ergebnisse) >= 1
        assert ergebnisse[0].durchschnitt_delta > 0  # Positiv = schlecht


class TestKompletterSchlafZyklus:
    """Kompletter Schlaf-Aufwach-Zyklus — der Bug-Reproduktionstest.

    Bug war: einschlafen() setzt schlaf_marker=True, aber der finally-Block
    in leben.py überschrieb ihn mit schlaf_marker=False. Beim Aufwachen
    wurde sauberer Schlaf als Tod erkannt.
    """

    def test_einschlafen_aufwachen_kein_tod(
        self,
        kurzzeit: KurzzeitGedaechtnis,
        langzeit: LangzeitGedaechtnis,
        heartbeat: Heartbeat,
        tmp_path: Path,
    ) -> None:
        """Kompletter Zyklus: Einschlafen → Aufwachen → Typ ist 'schlaf', nicht 'tod'."""
        zustand = {"cpu_temp": "normal", "vm_ram": "normal"}
        schmerz = 0.15

        # 1. Einschlafen (wie in leben.py)
        einschlafen(
            kurzzeit, langzeit, heartbeat,
            zustand, schmerz, tmp_path / "signal.txt",
        )

        # 2. Marker prüfen — muss True sein
        hb = heartbeat.lese()
        assert hb is not None
        assert hb["schlaf_marker"] is True, "Schlaf-Marker muss nach einschlafen() True sein"

        # 3. Aufwachen — muss als Schlaf erkannt werden
        status = aufwachen(langzeit, heartbeat)
        assert status["typ"] == "schlaf", (
            f"Erwartet 'schlaf', bekommen '{status['typ']}'. "
            f"Schlaf-Marker wurde zwischen einschlafen() und aufwachen() überschrieben!"
        )

        # 4. Kein Tod im Langzeitgedächtnis
        assert langzeit.anzahl_tode() == 0, "Sauberer Schlaf darf keinen Tod erzeugen"

    def test_einschlafen_finally_ueberschreibt_nicht(
        self,
        kurzzeit: KurzzeitGedaechtnis,
        langzeit: LangzeitGedaechtnis,
        heartbeat: Heartbeat,
        tmp_path: Path,
    ) -> None:
        """Simuliert den leben.py-finally-Block: Schlaf-Marker darf nicht
        überschrieben werden wenn modus == 'einschlafen'."""
        zustand = {"cpu_temp": "normal", "vm_ram": "normal"}
        schmerz = 0.15
        modus = "einschlafen"

        # Einschlafen setzt Marker
        einschlafen(
            kurzzeit, langzeit, heartbeat,
            zustand, schmerz, tmp_path / "signal.txt",
        )

        # Simuliere den korrigierten finally-Block aus leben.py
        if modus != "einschlafen":
            heartbeat.aktualisiere(zustand, schmerz, schlaf_marker=False)

        # Marker muss immer noch True sein
        hb = heartbeat.lese()
        assert hb is not None
        assert hb["schlaf_marker"] is True

        # Aufwachen erkennt Schlaf korrekt
        status = aufwachen(langzeit, heartbeat)
        assert status["typ"] == "schlaf"

    def test_absturz_nach_normalem_loop_ist_tod(
        self,
        langzeit: LangzeitGedaechtnis,
        heartbeat: Heartbeat,
    ) -> None:
        """Wenn der Prozess im normalen Modus stirbt (kein Einschlafen),
        soll es als Tod erkannt werden."""
        zustand = {"cpu_temp": "warm", "vm_ram": "eng"}
        schmerz = 0.45
        modus = "normal"

        # Simuliere den finally-Block bei Absturz
        if modus != "einschlafen":
            heartbeat.aktualisiere(zustand, schmerz, schlaf_marker=False)

        # Aufwachen erkennt Tod korrekt
        status = aufwachen(langzeit, heartbeat)
        assert status["typ"] == "tod"
        assert langzeit.anzahl_tode() == 1

    def test_mehrere_schlaf_zyklen(
        self,
        kurzzeit: KurzzeitGedaechtnis,
        langzeit: LangzeitGedaechtnis,
        heartbeat: Heartbeat,
        tmp_path: Path,
    ) -> None:
        """Mehrere Schlaf-Aufwach-Zyklen hintereinander — keiner darf als Tod erkannt werden."""
        zustand = {"cpu_temp": "normal", "vm_ram": "normal"}

        for i in range(3):
            einschlafen(
                kurzzeit, langzeit, heartbeat,
                zustand, 0.1, tmp_path / "signal.txt",
            )

            status = aufwachen(langzeit, heartbeat)
            assert status["typ"] == "schlaf", f"Zyklus {i+1}: Schlaf als Tod erkannt!"

        assert langzeit.anzahl_tode() == 0

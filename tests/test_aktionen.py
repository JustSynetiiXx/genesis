"""Tests für vm/genesis/aktionen.py — Aktionen und natürlicher Verfall."""

from __future__ import annotations

from vm.genesis.aktionen import (
    ALLE_AKTION_NAMEN,
    Abtastrate,
    AktionsManager,
    Pause,
    RechenIntensitaet,
    SpeicherCache,
)


class TestRechenIntensitaet:
    """Rechenintensität steuert CPU-Verbrauch."""

    def test_start_bei_null(self) -> None:
        ri = RechenIntensitaet()
        assert ri.level == 0.0

    def test_erhoehe(self) -> None:
        ri = RechenIntensitaet()
        ri.erhoehe()
        assert abs(ri.level - 0.2) < 0.01

    def test_reduziere(self) -> None:
        ri = RechenIntensitaet()
        ri.setze_level(0.6)
        ri.reduziere()
        assert abs(ri.level - 0.4) < 0.01

    def test_minimum(self) -> None:
        ri = RechenIntensitaet()
        ri.setze_level(0.8)
        ri.minimum()
        assert ri.level == 0.0

    def test_level_nicht_ueber_eins(self) -> None:
        ri = RechenIntensitaet()
        ri.setze_level(1.5)
        assert ri.level == 1.0

    def test_level_nicht_unter_null(self) -> None:
        ri = RechenIntensitaet()
        ri.reduziere()
        assert ri.level == 0.0


class TestSpeicherCache:
    """Cache belegt echten RAM und wächst natürlich."""

    def test_start_leer(self) -> None:
        cache = SpeicherCache()
        assert cache.groesse_mb() == 0.0

    def test_vergroessere(self) -> None:
        cache = SpeicherCache()
        cache.vergroessere()
        assert abs(cache.groesse_mb() - 10.0) < 0.1

    def test_verkleinere(self) -> None:
        cache = SpeicherCache()
        cache.vergroessere()
        cache.vergroessere()
        cache.verkleinere()
        assert abs(cache.groesse_mb() - 10.0) < 0.1

    def test_verkleinere_leer_kein_fehler(self) -> None:
        cache = SpeicherCache()
        cache.verkleinere()  # Sollte nicht crashen
        assert cache.groesse_mb() == 0.0

    def test_notfall_freigeben(self) -> None:
        cache = SpeicherCache()
        cache.vergroessere()
        cache.vergroessere()
        cache.vergroessere()
        cache.notfall_freigeben()
        assert cache.groesse_mb() == 0.0

    def test_natuerlicher_verfall(self) -> None:
        cache = SpeicherCache()
        cache.natuerlicher_verfall()
        assert cache.groesse_mb() >= 1.0  # ~1 MB gewachsen

    def test_natuerlicher_verfall_kumulativ(self) -> None:
        cache = SpeicherCache()
        for _ in range(5):
            cache.natuerlicher_verfall()
        assert cache.groesse_mb() >= 5.0


class TestAbtastrate:
    """Abtastrate steuert wie oft das System fühlt."""

    def test_start_bei_eins(self) -> None:
        ar = Abtastrate()
        assert ar.intervall == 1.0

    def test_schneller(self) -> None:
        ar = Abtastrate()
        ar.schneller()
        assert ar.intervall == 0.5

    def test_langsamer(self) -> None:
        ar = Abtastrate()
        ar.langsamer()
        assert ar.intervall == 2.0

    def test_minimum_intervall(self) -> None:
        ar = Abtastrate()
        for _ in range(10):
            ar.schneller()
        assert ar.intervall >= 0.2

    def test_maximum_intervall(self) -> None:
        ar = Abtastrate()
        for _ in range(10):
            ar.langsamer()
        assert ar.intervall <= 5.0


class TestAktionsManager:
    """AktionsManager führt alle Aktionen korrekt aus."""

    def test_alle_aktionen_ausfuehrbar(self) -> None:
        """Jede definierte Aktion lässt sich ohne Fehler ausführen."""
        manager = AktionsManager()
        for aktion in ALLE_AKTION_NAMEN:
            if aktion == "pausieren":
                continue  # Pausieren würde Tests verlangsamen
            manager.ausfuehren(aktion)

    def test_reflex_aktionen_ausfuehrbar(self) -> None:
        manager = AktionsManager()
        manager.ausfuehren("rechenintensitaet_minimum")
        manager.ausfuehren("speicher_freigeben_notfall")

    def test_nichts_tun(self) -> None:
        manager = AktionsManager()
        manager.ausfuehren("nichts_tun")  # Sollte nicht crashen

    def test_natuerlicher_verfall_ueber_manager(self) -> None:
        manager = AktionsManager()
        manager.natuerlicher_verfall()
        assert manager.cache.groesse_mb() >= 1.0

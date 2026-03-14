"""Tests für vm/genesis/schmerz.py — Schmerz und Wohlbefinden."""

from __future__ import annotations

import pytest

from vm.genesis.schmerz import (
    SCHMERZ_CONFIG,
    _schmerz_beitrag,
    berechne_schmerz,
    berechne_wohlbefinden,
    warnstufe,
)


class TestSchmerzBeitrag:
    """Einzelner Sensor-Beitrag zum Gesamtschmerz."""

    def test_unter_komfort_kein_schmerz(self) -> None:
        assert _schmerz_beitrag(50.0, 60.0, 90.0, False) == 0.0

    def test_bei_komfort_kein_schmerz(self) -> None:
        assert _schmerz_beitrag(60.0, 60.0, 90.0, False) == 0.0

    def test_bei_maximum_voller_schmerz(self) -> None:
        assert _schmerz_beitrag(90.0, 60.0, 90.0, False) == 1.0

    def test_ueber_maximum_voller_schmerz(self) -> None:
        assert _schmerz_beitrag(100.0, 60.0, 90.0, False) == 1.0

    def test_mitte_halber_schmerz(self) -> None:
        assert abs(_schmerz_beitrag(75.0, 60.0, 90.0, False) - 0.5) < 0.01

    def test_invertiert_viel_frei_kein_schmerz(self) -> None:
        # vm_ram_frei: komfort=500, maximum=10, invertiert
        assert _schmerz_beitrag(600.0, 500.0, 10.0, True) == 0.0

    def test_invertiert_wenig_frei_voller_schmerz(self) -> None:
        assert _schmerz_beitrag(10.0, 500.0, 10.0, True) == 1.0

    def test_invertiert_mitte(self) -> None:
        # 255 MB frei, Komfort=500, Maximum=10, Range=490
        # Beitrag = (500 - 255) / (500 - 10) = 245/490 = 0.5
        assert abs(_schmerz_beitrag(255.0, 500.0, 10.0, True) - 0.5) < 0.01


class TestBerechneSchmerz:
    """Gesamtschmerz aus allen Sensoren."""

    def test_komfort_kein_schmerz(self) -> None:
        rohwerte = {
            "cpu_temp_tctl": 50.0,      # Unter Komfort
            "vm_ram_frei_mb": 4000.0,   # Weit über Komfort (3500)
            "eigen_cpu_prozent": 10.0,  # Niedrig
            "eigen_ram_mb": 50.0,       # Niedrig
            "host_cpu_last": 20.0,      # Niedrig
            "luefter_rpm": 1000.0,      # Niedrig
        }
        schmerz = berechne_schmerz(rohwerte)
        assert schmerz == 0.0

    def test_maximum_voller_schmerz(self) -> None:
        rohwerte = {
            "cpu_temp_tctl": 95.0,
            "vm_ram_frei_mb": 5.0,
            "eigen_cpu_prozent": 200.0,  # CPU_PROZENT_MAX bei 2 Kernen
            "eigen_ram_mb": 1100.0,
            "host_cpu_last": 99.0,
            "luefter_rpm": 5000.0,
        }
        schmerz = berechne_schmerz(rohwerte)
        assert schmerz == 1.0

    def test_schmerz_zwischen_null_und_eins(self) -> None:
        rohwerte = {
            "cpu_temp_tctl": 75.0,
            "vm_ram_frei_mb": 300.0,
            "eigen_cpu_prozent": 50.0,
            "eigen_ram_mb": 200.0,
            "host_cpu_last": 60.0,
            "luefter_rpm": 2000.0,
        }
        schmerz = berechne_schmerz(rohwerte)
        assert 0.0 < schmerz < 1.0

    def test_gewichte_summieren_sich_zu_eins(self) -> None:
        summe = sum(c["gewicht"] for c in SCHMERZ_CONFIG.values())
        assert abs(summe - 1.0) < 0.1  # Darf leicht abweichen


class TestBerechneWohlbefinden:
    """Wohlbefinden basiert auf Veränderung."""

    def test_kein_schmerz_moderates_wohlbefinden(self) -> None:
        wb = berechne_wohlbefinden(0.0, 0.0)
        assert wb == 0.5  # basis=1.0*0.5, erleichterung=0

    def test_schmerz_sinkt_erleichterung(self) -> None:
        wb = berechne_wohlbefinden(0.2, 0.8)
        assert wb > 0.5  # Erleichterung durch Besserung

    def test_schmerz_steigt_kein_wohlbefinden_bonus(self) -> None:
        wb = berechne_wohlbefinden(0.8, 0.2)
        # Hoher Schmerz → basis niedrig, kein Erleichterungs-Bonus
        assert wb < 0.2

    def test_maximaler_schmerz_kein_wohlbefinden(self) -> None:
        wb = berechne_wohlbefinden(1.0, 1.0)
        assert wb == 0.0

    def test_wohlbefinden_maximal_eins(self) -> None:
        wb = berechne_wohlbefinden(0.0, 1.0)
        assert wb <= 1.0


class TestWarnstufe:
    """Warnstufen-Bestimmung."""

    def test_komfort(self) -> None:
        assert warnstufe(0.0) == "komfort"
        assert warnstufe(0.14) == "komfort"

    def test_unbehagen(self) -> None:
        assert warnstufe(0.15) == "unbehagen"
        assert warnstufe(0.34) == "unbehagen"

    def test_stress(self) -> None:
        assert warnstufe(0.35) == "stress"
        assert warnstufe(0.59) == "stress"

    def test_panik(self) -> None:
        assert warnstufe(0.60) == "panik"
        assert warnstufe(0.84) == "panik"

    def test_reflex(self) -> None:
        assert warnstufe(0.85) == "reflex"
        assert warnstufe(1.0) == "reflex"

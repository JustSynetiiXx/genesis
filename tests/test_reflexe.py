"""Tests für vm/genesis/reflexe.py — Notfall-Reaktionen."""

from __future__ import annotations

from vm.genesis.reflexe import REFLEXE, pruefe


class TestReflexBedingungen:
    """Reflexe feuern bei den richtigen Schwellen."""

    def test_hitzeschutz_feuert_ueber_85(self) -> None:
        rohwerte = {"cpu_temp_tctl": 86.0, "vm_ram_frei_mb": 500.0, "eigen_cpu_prozent": 20.0}
        gefeuert = pruefe(rohwerte)
        namen = [r.name for r in gefeuert]
        assert "hitzeschutz" in namen

    def test_hitzeschutz_feuert_nicht_unter_85(self) -> None:
        rohwerte = {"cpu_temp_tctl": 84.0, "vm_ram_frei_mb": 500.0, "eigen_cpu_prozent": 20.0}
        gefeuert = pruefe(rohwerte)
        namen = [r.name for r in gefeuert]
        assert "hitzeschutz" not in namen

    def test_ram_notfall_feuert_unter_50(self) -> None:
        rohwerte = {"cpu_temp_tctl": 50.0, "vm_ram_frei_mb": 40.0, "eigen_cpu_prozent": 20.0}
        gefeuert = pruefe(rohwerte)
        namen = [r.name for r in gefeuert]
        assert "ram_notfall" in namen

    def test_ram_notfall_feuert_nicht_ueber_50(self) -> None:
        rohwerte = {"cpu_temp_tctl": 50.0, "vm_ram_frei_mb": 100.0, "eigen_cpu_prozent": 20.0}
        gefeuert = pruefe(rohwerte)
        namen = [r.name for r in gefeuert]
        assert "ram_notfall" not in namen

    def test_cpu_notfall_feuert_ueber_schwelle(self) -> None:
        # Schwelle: CPU_PROZENT_MAX * 0.9 = 180% bei 2 Kernen
        rohwerte = {"cpu_temp_tctl": 50.0, "vm_ram_frei_mb": 500.0, "eigen_cpu_prozent": 185.0}
        gefeuert = pruefe(rohwerte)
        namen = [r.name for r in gefeuert]
        assert "cpu_notfall" in namen

    def test_cpu_notfall_feuert_nicht_unter_schwelle(self) -> None:
        # Unter der Schwelle (180%) darf der Reflex nicht feuern
        rohwerte = {"cpu_temp_tctl": 50.0, "vm_ram_frei_mb": 500.0, "eigen_cpu_prozent": 170.0}
        gefeuert = pruefe(rohwerte)
        namen = [r.name for r in gefeuert]
        assert "cpu_notfall" not in namen


class TestKeinReflexBeiNormaleWerten:
    """Keine Reflexe bei normalen Werten."""

    def test_alle_normal(self) -> None:
        rohwerte = {"cpu_temp_tctl": 55.0, "vm_ram_frei_mb": 800.0, "eigen_cpu_prozent": 30.0}
        gefeuert = pruefe(rohwerte)
        assert len(gefeuert) == 0


class TestMehrereReflexeGleichzeitig:
    """Mehrere Reflexe können gleichzeitig feuern."""

    def test_hitze_und_ram(self) -> None:
        rohwerte = {"cpu_temp_tctl": 90.0, "vm_ram_frei_mb": 30.0, "eigen_cpu_prozent": 20.0}
        gefeuert = pruefe(rohwerte)
        namen = [r.name for r in gefeuert]
        assert "hitzeschutz" in namen
        assert "ram_notfall" in namen


class TestReflexAktionen:
    """Reflexe haben die richtigen Aktionen zugewiesen."""

    def test_hitzeschutz_aktion(self) -> None:
        hitzeschutz = next(r for r in REFLEXE if r.name == "hitzeschutz")
        assert hitzeschutz.aktion == "rechenintensitaet_minimum"

    def test_ram_notfall_aktion(self) -> None:
        ram_notfall = next(r for r in REFLEXE if r.name == "ram_notfall")
        assert ram_notfall.aktion == "speicher_freigeben_notfall"

    def test_cpu_notfall_aktion(self) -> None:
        cpu_notfall = next(r for r in REFLEXE if r.name == "cpu_notfall")
        assert cpu_notfall.aktion == "rechenintensitaet_minimum"

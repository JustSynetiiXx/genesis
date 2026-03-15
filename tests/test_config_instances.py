"""Tests für vm/config_instances.py — Klon-Infrastruktur."""

import pytest
from pathlib import Path

from vm.config_instances import (
    INSTANCES,
    UMGEBUNG_STATUS_PFAD,
    DEFAULT_INSTANZ,
    get_instanz_config,
    get_instanz_pfade,
)


class TestInstances:
    """Tests für die Instanz-Konfiguration."""

    def test_instances_hat_genesis_1(self) -> None:
        assert "genesis-1" in INSTANCES

    def test_instances_hat_genesis_2(self) -> None:
        assert "genesis-2" in INSTANCES

    def test_instances_hat_genesis_3(self) -> None:
        assert "genesis-3" in INSTANCES

    def test_jede_instanz_hat_pflichtfelder(self) -> None:
        for name, cfg in INSTANCES.items():
            assert "db_pfad" in cfg, f"{name} fehlt db_pfad"
            assert "shared_pfad" in cfg, f"{name} fehlt shared_pfad"
            assert "beschreibung" in cfg, f"{name} fehlt beschreibung"

    def test_pfade_sind_unterschiedlich(self) -> None:
        pfade = [cfg["db_pfad"] for cfg in INSTANCES.values()]
        assert len(pfade) == len(set(pfade)), "DB-Pfade müssen eindeutig sein"
        pfade = [cfg["shared_pfad"] for cfg in INSTANCES.values()]
        assert len(pfade) == len(set(pfade)), "Shared-Pfade müssen eindeutig sein"


class TestGetInstanzConfig:
    """Tests für get_instanz_config()."""

    def test_genesis_1_existiert(self) -> None:
        cfg = get_instanz_config("genesis-1")
        assert "db_pfad" in cfg

    def test_unbekannte_instanz_wirft_fehler(self) -> None:
        with pytest.raises(KeyError):
            get_instanz_config("genesis-99")


class TestGetInstanzPfade:
    """Tests für get_instanz_pfade()."""

    def test_gibt_path_objekte_zurueck(self) -> None:
        db, shared = get_instanz_pfade("genesis-1")
        assert isinstance(db, Path)
        assert isinstance(shared, Path)

    def test_pfade_genesis_2_anders_als_1(self) -> None:
        db1, shared1 = get_instanz_pfade("genesis-1")
        db2, shared2 = get_instanz_pfade("genesis-2")
        assert db1 != db2
        assert shared1 != shared2


class TestKonstanten:
    """Tests für Modul-Konstanten."""

    def test_umgebung_status_pfad_ist_path(self) -> None:
        assert isinstance(UMGEBUNG_STATUS_PFAD, Path)

    def test_default_instanz(self) -> None:
        assert DEFAULT_INSTANZ == "genesis-1"
        assert DEFAULT_INSTANZ in INSTANCES

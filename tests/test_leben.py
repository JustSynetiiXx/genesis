"""Tests für vm/genesis/leben.py — Der Hauptloop."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestLebenMain:
    """System startet, läuft und beendet sich sauber."""

    @patch("vm.genesis.leben.Koerper")
    def test_system_startet_und_laeuft(self, mock_koerper_cls: MagicMock, tmp_path: Path) -> None:
        """System läuft 5 Loops und beendet sich dann."""
        mock_koerper = MagicMock()
        mock_koerper.fuehle.return_value = {
            "kategorien": {
                "cpu_temp": "normal",
                "vm_ram": "frei",
                "cpu_last_eigen": "niedrig",
                "luefter": "leise",
                "host_cpu_last": "niedrig",
                "host_ram": "frei",
            },
            "rohwerte": {
                "cpu_temp_tctl": 50.0,
                "cpu_temp_tccd1": 45.0,
                "vm_ram_frei_mb": 800.0,
                "vm_ram_benutzt_mb": 1200.0,
                "eigen_ram_mb": 40.0,
                "eigen_cpu_prozent": 10.0,
                "host_cpu_last": 15.0,
                "host_ram_frei_mb": 20000.0,
                "luefter_rpm": 1000.0,
            },
            "zeitstempel": 1000.0,
        }
        mock_koerper_cls.return_value = mock_koerper

        shared_dir = tmp_path / "shared"
        db_dir = tmp_path / "db"

        # Import hier damit Patches wirken
        from vm.genesis.leben import main

        # System mit max_loops=5 laufen lassen (Wachphase zählt mit)
        with patch("vm.genesis.leben.time.sleep"):
            main(shared_dir=shared_dir, db_dir=db_dir, max_loops=5)

        # Prüfen dass Koerper mehrmals aufgerufen wurde
        assert mock_koerper.fuehle.call_count >= 5

        # Datenbanken wurden erstellt
        assert (db_dir / "heartbeat.db").exists()
        assert (db_dir / "langzeit.db").exists()
        assert (db_dir / "kurzzeit.db").exists()

    @patch("vm.genesis.leben.Koerper")
    def test_status_datei_wird_geschrieben(self, mock_koerper_cls: MagicMock, tmp_path: Path) -> None:
        """Status-JSON wird ins Shared Directory geschrieben."""
        mock_koerper = MagicMock()
        mock_koerper.fuehle.return_value = {
            "kategorien": {
                "cpu_temp": "normal",
                "vm_ram": "frei",
                "cpu_last_eigen": "niedrig",
                "luefter": "leise",
                "host_cpu_last": "niedrig",
                "host_ram": "frei",
            },
            "rohwerte": {
                "cpu_temp_tctl": 50.0,
                "cpu_temp_tccd1": 45.0,
                "vm_ram_frei_mb": 800.0,
                "vm_ram_benutzt_mb": 1200.0,
                "eigen_ram_mb": 40.0,
                "eigen_cpu_prozent": 10.0,
                "host_cpu_last": 15.0,
                "host_ram_frei_mb": 20000.0,
                "luefter_rpm": 1000.0,
            },
            "zeitstempel": 1000.0,
        }
        mock_koerper_cls.return_value = mock_koerper

        shared_dir = tmp_path / "shared"
        db_dir = tmp_path / "db"

        from vm.genesis.leben import main

        with patch("vm.genesis.leben.time.sleep"):
            main(shared_dir=shared_dir, db_dir=db_dir, max_loops=3)

        status_pfad = shared_dir / "genesis_status.json"
        assert status_pfad.exists()

        import json
        status = json.loads(status_pfad.read_text())
        assert "schmerz" in status
        assert "wohlbefinden" in status
        assert "warnstufe" in status
        assert "modus" in status

    @patch("vm.genesis.leben.Koerper")
    def test_schlaf_signal_beendet_loop(self, mock_koerper_cls: MagicMock, tmp_path: Path) -> None:
        """SLEEP-Signal in signal.txt beendet den Hauptloop."""
        mock_koerper = MagicMock()
        mock_koerper.fuehle.return_value = {
            "kategorien": {
                "cpu_temp": "normal", "vm_ram": "frei",
                "cpu_last_eigen": "niedrig", "luefter": "leise",
                "host_cpu_last": "niedrig", "host_ram": "frei",
            },
            "rohwerte": {
                "cpu_temp_tctl": 50.0, "cpu_temp_tccd1": 45.0,
                "vm_ram_frei_mb": 800.0, "vm_ram_benutzt_mb": 1200.0,
                "eigen_ram_mb": 40.0, "eigen_cpu_prozent": 10.0,
                "host_cpu_last": 15.0, "host_ram_frei_mb": 20000.0,
                "luefter_rpm": 1000.0,
            },
            "zeitstempel": 1000.0,
        }
        mock_koerper_cls.return_value = mock_koerper

        shared_dir = tmp_path / "shared"
        shared_dir.mkdir(parents=True)
        db_dir = tmp_path / "db"

        # SLEEP-Signal schreiben BEVOR der Loop startet
        signal_pfad = shared_dir / "signal.txt"
        signal_pfad.write_text("SLEEP 1234567890\n")

        from vm.genesis.leben import main

        with patch("vm.genesis.leben.time.sleep"):
            # max_loops hoch genug, Loop sollte durch SLEEP beendet werden
            main(shared_dir=shared_dir, db_dir=db_dir, max_loops=100)

        # READY-Signal sollte geschrieben worden sein
        assert signal_pfad.read_text().strip() == "READY"

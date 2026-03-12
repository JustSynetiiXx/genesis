"""EKG-Dashboard: Echtzeit-Monitoring für Genesis.

Zeigt alle 5 Panels in einem Terminal-Dashboard an:
1. Vitalwerte (CPU, RAM, Lüfter)
2. Aktivität (was Genesis tut — Phase 0: Platzhalter)
3. Lernen (Erfahrungsdatenbank — Phase 0: Platzhalter)
4. Verhalten (menschlich lesbare Interpretation — Phase 0: Platzhalter)
5. Geschichte (Sensorverlauf über Zeit)

Verwendung:
    python -m host.ekg.dashboard
    python -m host.ekg.dashboard --sensor-datei /pfad/zu/sensoren.bin
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from host.ekg.panels import aktivitaet, geschichte, lernen, verhalten, vitalwerte
from host.ekg.panels.geschichte import SensorGeschichte

# Shared-Leser importieren (liegt außerhalb des host-Packages)
_PROJEKT_WURZEL: Path = Path(__file__).resolve().parent.parent.parent
_LESER_PFAD: Path = _PROJEKT_WURZEL / "shared" / "leser.py"


def _lade_leser() -> Any:
    """Lädt den Sensor-Leser aus dem shared-Verzeichnis.

    Returns:
        Das leser-Modul.

    Raises:
        ImportError: Wenn der Leser nicht gefunden wird.
    """
    if not _LESER_PFAD.exists():
        raise ImportError(f"Sensor-Leser nicht gefunden: {_LESER_PFAD}")

    spec = importlib.util.spec_from_file_location("shared.leser", _LESER_PFAD)
    if spec is None or spec.loader is None:
        raise ImportError(f"Kann Sensor-Leser nicht laden: {_LESER_PFAD}")

    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


# Leser beim Import laden
_leser = _lade_leser()


# Standard-Pfade
STANDARD_SENSOR_DATEI: Path = _PROJEKT_WURZEL / "shared" / "sensoren.bin"
STANDARD_STATUS_DATEI: Path = _PROJEKT_WURZEL / "shared" / "genesis_status.bin"


class EkgDashboard:
    """Echtzeit-Terminal-Dashboard für Genesis-Monitoring.

    Attributes:
        sensor_datei: Pfad zur binären Sensordatei.
        refresh_rate: Aktualisierungsrate in Hertz.
        konsole: Rich Console-Instanz.
        geschichte: Sensor-Geschichte für Zeitverlauf.
    """

    def __init__(
        self,
        sensor_datei: Path = STANDARD_SENSOR_DATEI,
        refresh_rate: float = 2.0,
    ) -> None:
        """Initialisiert das Dashboard.

        Args:
            sensor_datei: Pfad zur sensoren.bin Datei.
            refresh_rate: Aktualisierungen pro Sekunde (Standard: 2Hz).
        """
        self.sensor_datei: Path = sensor_datei
        self.refresh_rate: float = refresh_rate
        self.konsole: Console = Console()
        self.geschichte: SensorGeschichte = SensorGeschichte(
            max_eintraege=int(refresh_rate * 300)  # 5 Minuten Geschichte
        )
        self._laeuft: bool = False

    def _lese_sensoren(self) -> dict[str, Any] | None:
        """Liest aktuelle Sensordaten.

        Returns:
            Sensor-Dictionary oder None.
        """
        return _leser.lese_sensoren(self.sensor_datei)

    def _erstelle_kopfzeile(self) -> Panel:
        """Erstellt die Kopfzeile des Dashboards.

        Returns:
            Rich Panel mit Titel und Status.
        """
        sensor_daten: dict[str, Any] | None = self._lese_sensoren()

        if sensor_daten is not None:
            alter: float = sensor_daten.get("alter_sekunden", 0.0)
            if alter < 2.0:
                status = Text(" LIVE ", style="bold white on green")
            elif alter < 10.0:
                status = Text(f" VERZÖGERT ({alter:.0f}s) ", style="bold white on yellow")
            else:
                status = Text(f" VERALTET ({alter:.0f}s) ", style="bold white on red")
        else:
            status = Text(" KEINE DATEN ", style="bold white on red")

        titel = Text()
        titel.append("Genesis EKG", style="bold cyan")
        titel.append(" — ")
        titel.append("Phase 0", style="dim")
        titel.append(" — ")
        titel.append_text(status)
        titel.append(" — ")
        titel.append(time.strftime("%H:%M:%S"), style="dim")

        return Panel(titel, style="cyan", height=3)

    def _erstelle_layout(self) -> Layout:
        """Erstellt das Dashboard-Layout.

        Layout:
            ┌────────────────────────────────┐
            │          Kopfzeile             │
            ├──────────────┬─────────────────┤
            │  Vitalwerte  │   Aktivität     │
            │              ├─────────────────┤
            │              │   Lernen        │
            ├──────────────┼─────────────────┤
            │  Geschichte  │   Verhalten     │
            └──────────────┴─────────────────┘

        Returns:
            Rich Layout mit allen Panels.
        """
        layout = Layout()

        layout.split_column(
            Layout(name="kopf", size=3),
            Layout(name="oben", ratio=3),
            Layout(name="unten", ratio=2),
        )

        layout["oben"].split_row(
            Layout(name="vitalwerte", ratio=3),
            Layout(name="rechts_oben", ratio=2),
        )

        layout["rechts_oben"].split_column(
            Layout(name="aktivitaet"),
            Layout(name="lernen"),
        )

        layout["unten"].split_row(
            Layout(name="geschichte", ratio=3),
            Layout(name="verhalten", ratio=2),
        )

        return layout

    def _aktualisiere(self, layout: Layout) -> None:
        """Aktualisiert alle Panels im Layout.

        Args:
            layout: Das Dashboard-Layout.
        """
        sensor_daten: dict[str, Any] | None = self._lese_sensoren()

        # Geschichte aktualisieren
        self.geschichte.aktualisiere(sensor_daten)

        # Panels befüllen
        layout["kopf"].update(self._erstelle_kopfzeile())
        layout["vitalwerte"].update(
            vitalwerte.erstelle_panel(sensor_daten)
        )
        layout["aktivitaet"].update(
            aktivitaet.erstelle_panel(None)  # Phase 0: Genesis nicht aktiv
        )
        layout["lernen"].update(
            lernen.erstelle_panel(None)  # Phase 0: Genesis nicht aktiv
        )
        layout["verhalten"].update(
            verhalten.erstelle_panel(None)  # Phase 0: Genesis nicht aktiv
        )
        layout["geschichte"].update(
            geschichte.erstelle_panel(self.geschichte)
        )

    def starte(self) -> None:
        """Startet das Dashboard mit Live-Aktualisierung.

        Blockiert bis Ctrl+C gedrückt wird.
        """
        self._laeuft = True
        layout: Layout = self._erstelle_layout()
        intervall: float = 1.0 / self.refresh_rate

        self.konsole.print(
            Text("Genesis EKG startet...", style="bold cyan")
        )
        self.konsole.print(
            Text(f"Sensor-Datei: {self.sensor_datei}", style="dim")
        )
        self.konsole.print(
            Text(f"Refresh-Rate: {self.refresh_rate} Hz", style="dim")
        )
        self.konsole.print(
            Text("Drücke Ctrl+C zum Beenden.\n", style="dim")
        )

        try:
            with Live(
                layout,
                console=self.konsole,
                refresh_per_second=self.refresh_rate,
                screen=True,
            ) as live:
                while self._laeuft:
                    self._aktualisiere(layout)
                    time.sleep(intervall)
        except KeyboardInterrupt:
            pass
        finally:
            self._laeuft = False
            self.konsole.print(
                Text("\nGenesis EKG beendet.", style="bold cyan")
            )

    def stoppe(self) -> None:
        """Stoppt das Dashboard."""
        self._laeuft = False


def main() -> None:
    """Hauptfunktion — parst Argumente und startet das Dashboard."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Genesis EKG-Dashboard — Echtzeit-Monitoring"
    )
    parser.add_argument(
        "--sensor-datei",
        type=Path,
        default=STANDARD_SENSOR_DATEI,
        help=f"Pfad zur Sensordatei (Standard: {STANDARD_SENSOR_DATEI})",
    )
    parser.add_argument(
        "--refresh-rate",
        type=float,
        default=2.0,
        help="Aktualisierungen pro Sekunde (Standard: 2.0)",
    )

    args = parser.parse_args()

    dashboard = EkgDashboard(
        sensor_datei=args.sensor_datei,
        refresh_rate=args.refresh_rate,
    )
    dashboard.starte()


if __name__ == "__main__":
    main()

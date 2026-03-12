"""Aktivitäts-Panel: Was tut Genesis gerade?

In Phase 0 zeigt dieses Panel nur einen Platzhalter.
Vorbereitet für: Aktuelle Aktion, Aktionshistorie, Explorationsrate.
"""

from __future__ import annotations

from typing import Any

from rich.panel import Panel
from rich.table import Table
from rich.text import Text


# Aktionsnamen für Phase 1+
AKTIONS_NAMEN: dict[int, str] = {
    1: "Rechenintensität regulieren",
    2: "Speicher freigeben/beanspruchen",
    3: "Selbst pausieren (schlafen)",
    4: "Abtastrate ändern",
    5: "Nichts tun",
}


def erstelle_panel(
    genesis_status: dict[str, Any] | None = None,
) -> Panel:
    """Erstellt das Aktivitäts-Panel.

    Args:
        genesis_status: Status-Dictionary von Genesis (Phase 1+),
            oder None wenn Genesis nicht aktiv ist.

    Returns:
        Rich Panel mit Aktivitätsinformationen.
    """
    if genesis_status is None:
        # Phase 0: Genesis nicht aktiv
        inhalt = Table(show_header=False, box=None, expand=True, padding=(0, 1))
        inhalt.add_column("Info", ratio=1)

        inhalt.add_row(Text("Genesis nicht aktiv", style="dim"))
        inhalt.add_row(Text(""))
        inhalt.add_row(Text("Phase 0: Nur Sensoren und EKG", style="dim italic"))
        inhalt.add_row(Text(""))
        inhalt.add_row(Text("Vorbereitet für:", style="dim"))
        inhalt.add_row(Text("  • Aktuelle Aktion", style="dim"))
        inhalt.add_row(Text("  • Aktionshistorie", style="dim"))
        inhalt.add_row(Text("  • Explorationsrate", style="dim"))

        return Panel(inhalt, title="⚡ Aktivität", border_style="dim")

    # Phase 1+: Genesis aktiv — Daten anzeigen
    tabelle = Table(show_header=False, box=None, expand=True, padding=(0, 1))
    tabelle.add_column("Bezeichnung", style="bold", width=18)
    tabelle.add_column("Wert", ratio=1)

    # Aktuelle Aktion
    aktuelle_aktion: int = genesis_status.get("aktuelle_aktion", 0)
    aktions_name: str = AKTIONS_NAMEN.get(aktuelle_aktion, f"Unbekannt ({aktuelle_aktion})")
    tabelle.add_row("Aktuelle Aktion", Text(aktions_name, style="cyan"))

    # Explorationsrate
    exploration: float = genesis_status.get("explorationsrate", 0.0)
    expl_farbe: str = "green" if exploration < 0.3 else ("yellow" if exploration < 0.7 else "red")
    tabelle.add_row(
        "Explorationsrate",
        Text(f"{exploration:.1%}", style=expl_farbe),
    )

    # Schmerz
    schmerz: float = genesis_status.get("schmerz", 0.0)
    schmerz_farbe: str = "green" if schmerz < 0.3 else ("yellow" if schmerz < 0.6 else "red")
    tabelle.add_row(
        "Schmerz",
        Text(f"{schmerz:.2f}", style=schmerz_farbe),
    )

    # Wohlbefinden
    wohlbefinden: float = genesis_status.get("wohlbefinden", 0.0)
    wohl_farbe: str = "red" if wohlbefinden < 0.3 else ("yellow" if wohlbefinden < 0.6 else "green")
    tabelle.add_row(
        "Wohlbefinden",
        Text(f"{wohlbefinden:.2f}", style=wohl_farbe),
    )

    # Letzte Aktionen
    letzte_aktionen: list[int] = genesis_status.get("letzte_aktionen", [])
    if letzte_aktionen:
        historie: str = " → ".join(
            AKTIONS_NAMEN.get(a, "?") for a in letzte_aktionen[-5:]
        )
        tabelle.add_row("Letzte Aktionen", Text(historie, style="dim"))

    return Panel(tabelle, title="⚡ Aktivität", border_style="cyan")

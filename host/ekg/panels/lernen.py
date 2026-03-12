"""Lern-Panel: Erfahrungsdatenbank und Lernfortschritt.

In Phase 0 zeigt dieses Panel nur einen Platzhalter.
Vorbereitet für: DB-Größe, gelernte Muster, Erfolgsraten.
"""

from __future__ import annotations

from typing import Any

from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def erstelle_panel(
    lern_status: dict[str, Any] | None = None,
) -> Panel:
    """Erstellt das Lern-Panel.

    Args:
        lern_status: Lernstatus-Dictionary von Genesis (Phase 1+),
            oder None wenn Genesis nicht aktiv ist.

    Returns:
        Rich Panel mit Lerninformationen.
    """
    if lern_status is None:
        # Phase 0: Genesis nicht aktiv
        inhalt = Table(show_header=False, box=None, expand=True, padding=(0, 1))
        inhalt.add_column("Info", ratio=1)

        inhalt.add_row(Text("Genesis nicht aktiv", style="dim"))
        inhalt.add_row(Text(""))
        inhalt.add_row(Text("Phase 0: Nur Sensoren und EKG", style="dim italic"))
        inhalt.add_row(Text(""))
        inhalt.add_row(Text("Vorbereitet für:", style="dim"))
        inhalt.add_row(Text("  • Erfahrungsdatenbank-Größe", style="dim"))
        inhalt.add_row(Text("  • Gelernte Muster", style="dim"))
        inhalt.add_row(Text("  • Erfolgsraten pro Aktion", style="dim"))
        inhalt.add_row(Text("  • Lernkurve", style="dim"))

        return Panel(inhalt, title="🧠 Lernen", border_style="dim")

    # Phase 1+: Genesis aktiv — Lernstatus anzeigen
    tabelle = Table(show_header=False, box=None, expand=True, padding=(0, 1))
    tabelle.add_column("Bezeichnung", style="bold", width=22)
    tabelle.add_column("Wert", ratio=1)

    # Erfahrungsdatenbank
    erfahrungen: int = lern_status.get("anzahl_erfahrungen", 0)
    tabelle.add_row(
        "Erfahrungen gesamt",
        Text(f"{erfahrungen:,}", style="cyan"),
    )

    # Gelernte Muster
    muster: int = lern_status.get("gelernte_muster", 0)
    tabelle.add_row(
        "Gelernte Muster",
        Text(f"{muster:,}", style="cyan"),
    )

    # Einzigartige Zustände
    zustaende: int = lern_status.get("einzigartige_zustaende", 0)
    tabelle.add_row(
        "Einzigartige Zustände",
        Text(f"{zustaende:,}", style="cyan"),
    )

    # Erfolgsraten pro Aktion
    erfolgsraten: dict[int, float] = lern_status.get("erfolgsraten", {})
    if erfolgsraten:
        tabelle.add_row(Text(""), Text(""))
        tabelle.add_row(
            Text("Erfolgsraten:", style="bold underline"),
            Text(""),
        )
        from .aktivitaet import AKTIONS_NAMEN

        for aktion_id, rate in sorted(erfolgsraten.items()):
            name: str = AKTIONS_NAMEN.get(aktion_id, f"Aktion {aktion_id}")
            rate_farbe: str = "red" if rate < 0.3 else ("yellow" if rate < 0.6 else "green")
            tabelle.add_row(
                f"  {name}",
                Text(f"{rate:.1%}", style=rate_farbe),
            )

    # Tode
    tode: int = lern_status.get("anzahl_tode", 0)
    if tode > 0:
        tabelle.add_row(
            "Tode erlebt",
            Text(f"{tode}", style="red bold"),
        )

    return Panel(tabelle, title="🧠 Lernen", border_style="magenta")

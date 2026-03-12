"""Verhaltens-Panel: Menschlich lesbare Interpretation.

In Phase 0 zeigt dieses Panel nur einen Platzhalter.
Vorbereitet für: Verhaltensmuster-Erkennung und Interpretation.
"""

from __future__ import annotations

from typing import Any

from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def erstelle_panel(
    genesis_status: dict[str, Any] | None = None,
    lern_status: dict[str, Any] | None = None,
) -> Panel:
    """Erstellt das Verhaltens-Panel.

    Interpretiert das Verhalten von Genesis in menschlich lesbarer Form.
    WICHTIG: Ehrliche Interpretation. Erwartbares Verhalten wird als solches
    gekennzeichnet. Nur wirklich überraschendes Verhalten wird hervorgehoben.

    Args:
        genesis_status: Status-Dictionary von Genesis (Phase 1+).
        lern_status: Lernstatus-Dictionary von Genesis (Phase 1+).

    Returns:
        Rich Panel mit Verhaltensinterpretation.
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
        inhalt.add_row(Text("  • Verhaltensmuster-Erkennung", style="dim"))
        inhalt.add_row(Text("  • Menschlich lesbare Interpretation", style="dim"))
        inhalt.add_row(Text("  • Erwartbar vs. überraschend", style="dim"))
        inhalt.add_row(Text("  • Zeitlicher Verlauf", style="dim"))

        return Panel(inhalt, title="👁 Verhalten", border_style="dim")

    # Phase 1+: Genesis aktiv — Verhalten interpretieren
    tabelle = Table(show_header=False, box=None, expand=True, padding=(0, 1))
    tabelle.add_column("Info", ratio=1)

    # Gesamtzustand
    schmerz: float = genesis_status.get("schmerz", 0.0)
    wohlbefinden: float = genesis_status.get("wohlbefinden", 0.0)

    if schmerz < 0.1 and wohlbefinden > 0.7:
        zustand_text = Text("Zufrieden — Alles im Komfortbereich", style="green")
    elif schmerz < 0.3:
        zustand_text = Text("Ruhig — Geringer Stress", style="green")
    elif schmerz < 0.6:
        zustand_text = Text("Unruhig — Mittlerer Stress", style="yellow")
    elif schmerz < 0.8:
        zustand_text = Text("Gestresst — Hoher Schmerz", style="dark_orange")
    else:
        zustand_text = Text("Notfall — Kritischer Schmerz", style="red bold")

    tabelle.add_row(zustand_text)
    tabelle.add_row(Text(""))

    # Aktuelle Aktivität interpretieren
    aktuelle_aktion: int = genesis_status.get("aktuelle_aktion", 0)
    interpretationen: dict[int, str] = {
        1: "Passt Rechenintensität an",
        2: "Verwaltet Speicher",
        3: "Hat sich schlafen gelegt",
        4: "Ändert wie oft es fühlt",
        5: "Tut nichts — wartet ab",
    }
    interpretation: str = interpretationen.get(aktuelle_aktion, "Unbekannte Aktivität")
    tabelle.add_row(Text(f"Aktuell: {interpretation}", style="cyan"))

    # Explorationsverhalten
    exploration: float = genesis_status.get("explorationsrate", 0.0)
    if exploration > 0.7:
        tabelle.add_row(Text(
            "⚠ Hohe Exploration — probiert verzweifelt Neues",
            style="yellow",
        ))
    elif exploration > 0.3:
        tabelle.add_row(Text(
            "Moderate Exploration — sucht nach besseren Strategien",
            style="dim",
        ))
    else:
        tabelle.add_row(Text(
            "Niedrige Exploration — folgt bekannten Mustern",
            style="dim",
        ))

    # Ehrlichkeitshinweis
    tabelle.add_row(Text(""))
    tabelle.add_row(Text(
        "Hinweis: Alles oben ist erwartbares Verhalten, "
        "direkt auf den Code zurückführbar.",
        style="dim italic",
    ))

    return Panel(tabelle, title="👁 Verhalten", border_style="blue")

"""Lern-Panel: Erfahrungsdatenbank und Lernfortschritt.

Liest genesis_status.json aus dem Shared Directory und zeigt:
- Erfahrungen heute (Kurzzeitgedächtnis), Langzeit, Tode, letzter Tod-Zustand.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.panel import Panel
from rich.table import Table
from rich.text import Text


# Pfad zur Genesis-Status-Datei
_PROJEKT_WURZEL: Path = Path(__file__).resolve().parent.parent.parent.parent
_STATUS_DATEI: Path = _PROJEKT_WURZEL / "shared" / "genesis_status.json"


def _lese_status() -> dict[str, Any] | None:
    """Liest genesis_status.json atomar.

    Returns:
        Status-Dictionary oder None wenn nicht lesbar.
    """
    try:
        rohdaten: bytes = _STATUS_DATEI.read_bytes()
        return json.loads(rohdaten)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def erstelle_panel(
    lern_status: dict[str, Any] | None = None,
) -> Panel:
    """Erstellt das Lern-Panel.

    Args:
        lern_status: Wird ignoriert — liest direkt aus genesis_status.json.

    Returns:
        Rich Panel mit Lerninformationen.
    """
    status: dict[str, Any] | None = _lese_status()

    if status is None:
        inhalt = Table(show_header=False, box=None, expand=True, padding=(0, 1))
        inhalt.add_column("Info", ratio=1)
        inhalt.add_row(Text("Genesis nicht aktiv", style="dim"))
        return Panel(inhalt, title="🧠 Lernen", border_style="dim")

    # Genesis aktiv — Lernstatus anzeigen
    tabelle = Table(show_header=False, box=None, expand=True, padding=(0, 1))
    tabelle.add_column("Bezeichnung", style="bold", width=22)
    tabelle.add_column("Wert", ratio=1)

    # Erfahrungen heute (Kurzzeitgedächtnis)
    erfahrungen_heute: int = status.get("erfahrungen_heute") or 0
    tabelle.add_row(
        "Erfahrungen heute",
        Text(f"{erfahrungen_heute:,}", style="cyan"),
    )

    # Erfahrungen Langzeit
    erfahrungen_langzeit: int = status.get("erfahrungen_langzeit") or 0
    tabelle.add_row(
        "Erfahrungen Langzeit",
        Text(f"{erfahrungen_langzeit:,}", style="cyan"),
    )

    # Tode gesamt
    tode: int = status.get("tode_gesamt") or 0
    if tode > 0:
        tabelle.add_row(
            "Tode gesamt",
            Text(f"{tode}", style="red bold"),
        )
    else:
        tabelle.add_row(
            "Tode gesamt",
            Text("0", style="green"),
        )

    # Letzter Tod-Zustand
    letzter_tod: Any = status.get("letzter_tod_zustand")
    if isinstance(letzter_tod, dict) and letzter_tod:
        tod_text: str = ", ".join(f"{k}={v}" for k, v in letzter_tod.items())
        tabelle.add_row(
            "Letzter Tod",
            Text(tod_text, style="red"),
        )

    return Panel(tabelle, title="🧠 Lernen", border_style="magenta")

"""Verhaltens-Panel: Menschlich lesbare Interpretation.

Liest genesis_status.json aus dem Shared Directory und zeigt:
- Warnstufe mit Farbcodierung, Schmerz, Wohlbefinden, Interpretation.
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

# Warnstufen → Farben
WARNSTUFE_FARBEN: dict[str, str] = {
    "komfort": "green",
    "unbehagen": "yellow",
    "stress": "dark_orange",
    "gefahr": "red",
    "kritisch": "red bold",
}


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


def _interpretiere(status: dict[str, Any]) -> tuple[str, str]:
    """Erzeugt menschlich lesbare Interpretation.

    Args:
        status: Genesis-Status-Dictionary.

    Returns:
        Tuple aus (Interpretation, Style).
    """
    schmerz: float = status.get("schmerz") or 0.0
    exploration: bool = bool(status.get("exploration"))
    aktion: str = status.get("aktion") or ""
    modus: str = status.get("modus") or ""

    # Reihenfolge ist wichtig — spezifischste Regel zuerst
    if schmerz > 0.6 and exploration:
        return "Es schreit", "red bold"
    if aktion == "pausieren":
        return "Es schläft", "blue"
    if exploration and schmerz < 0.15:
        return "Es lernt", "cyan"
    if schmerz < 0.15 and not exploration:
        return "Es ist zufrieden", "green"
    if schmerz > 0.35 and exploration:
        return "Es hat Angst", "dark_orange"
    if not exploration:
        return "Es erinnert sich", "magenta"
    if modus == "wachphase":
        return "Es ist aufgewacht", "yellow"

    return "Es existiert", "dim"


def erstelle_panel(
    genesis_status: dict[str, Any] | None = None,
    lern_status: dict[str, Any] | None = None,
) -> Panel:
    """Erstellt das Verhaltens-Panel.

    Args:
        genesis_status: Wird ignoriert — liest direkt aus genesis_status.json.
        lern_status: Wird ignoriert.

    Returns:
        Rich Panel mit Verhaltensinterpretation.
    """
    status: dict[str, Any] | None = _lese_status()

    if status is None:
        inhalt = Table(show_header=False, box=None, expand=True, padding=(0, 1))
        inhalt.add_column("Info", ratio=1)
        inhalt.add_row(Text("Genesis nicht aktiv", style="dim"))
        return Panel(inhalt, title="👁 Verhalten", border_style="dim")

    # Genesis aktiv — Verhalten interpretieren
    tabelle = Table(show_header=False, box=None, expand=True, padding=(0, 1))
    tabelle.add_column("Bezeichnung", style="bold", width=16)
    tabelle.add_column("Wert", ratio=1)

    # Warnstufe
    warnstufe: str = status.get("warnstufe") or "unbekannt"
    warn_farbe: str = WARNSTUFE_FARBEN.get(warnstufe, "dim")
    tabelle.add_row("Warnstufe", Text(warnstufe.upper(), style=warn_farbe))

    # Schmerz
    schmerz: float = status.get("schmerz") or 0.0
    schmerz_farbe: str = "green" if schmerz < 0.15 else ("yellow" if schmerz < 0.35 else ("dark_orange" if schmerz < 0.6 else "red"))
    tabelle.add_row("Schmerz", Text(f"{schmerz:.4f}", style=schmerz_farbe))

    # Wohlbefinden
    wohlbefinden: float = status.get("wohlbefinden") or 0.0
    wohl_farbe: str = "red" if wohlbefinden < 0.3 else ("yellow" if wohlbefinden < 0.6 else "green")
    tabelle.add_row("Wohlbefinden", Text(f"{wohlbefinden:.4f}", style=wohl_farbe))

    # Menschlich lesbare Interpretation
    interpretation, interp_style = _interpretiere(status)
    tabelle.add_row(Text(""), Text(""))
    tabelle.add_row("Interpretation", Text(interpretation, style=f"{interp_style} bold"))

    return Panel(tabelle, title="👁 Verhalten", border_style="blue")

"""Aktivitäts-Panel: Was tut Genesis gerade?

Liest genesis_status.json aus dem Shared Directory und zeigt:
- Aktuelle Aktion, Exploration, Cache, Rechen-Level, Abtastrate, Wachzeit.
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

# Menschlich lesbare Aktionsnamen
AKTIONS_NAMEN: dict[str, str] = {
    "rechenintensitaet_hoch": "Rechenintensität ↑",
    "rechenintensitaet_runter": "Rechenintensität ↓",
    "speicher_freigeben": "Speicher freigeben",
    "speicher_beanspruchen": "Speicher beanspruchen",
    "pausieren": "Selbst pausieren (schlafen)",
    "abtastrate_hoch": "Abtastrate ↑",
    "abtastrate_runter": "Abtastrate ↓",
    "nichts": "Nichts tun",
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


def erstelle_panel(
    genesis_status: dict[str, Any] | None = None,
) -> Panel:
    """Erstellt das Aktivitäts-Panel.

    Args:
        genesis_status: Wird ignoriert — liest direkt aus genesis_status.json.

    Returns:
        Rich Panel mit Aktivitätsinformationen.
    """
    status: dict[str, Any] | None = _lese_status()

    if status is None:
        inhalt = Table(show_header=False, box=None, expand=True, padding=(0, 1))
        inhalt.add_column("Info", ratio=1)
        inhalt.add_row(Text("Genesis nicht aktiv", style="dim"))
        return Panel(inhalt, title="⚡ Aktivität", border_style="dim")

    # Genesis aktiv — Daten anzeigen
    tabelle = Table(show_header=False, box=None, expand=True, padding=(0, 1))
    tabelle.add_column("Bezeichnung", style="bold", width=18)
    tabelle.add_column("Wert", ratio=1)

    # Aktuelle Aktion
    aktion: str = status.get("aktion") or "unbekannt"
    aktions_name: str = AKTIONS_NAMEN.get(aktion, aktion)
    tabelle.add_row("Aktuelle Aktion", Text(aktions_name, style="cyan bold"))

    # Exploration
    exploration: bool = bool(status.get("exploration"))
    if exploration:
        tabelle.add_row("Modus", Text("Exploration", style="yellow"))
    else:
        tabelle.add_row("Modus", Text("Erfahrung nutzen", style="green"))

    # Cache-Größe
    cache_mb: float = status.get("cache_mb") or 0.0
    cache_farbe: str = "green" if cache_mb < 500 else ("yellow" if cache_mb < 1000 else "red")
    tabelle.add_row("Cache", Text(f"{cache_mb:.0f} MB", style=cache_farbe))

    # Rechen-Level
    rechen_level: float = status.get("rechen_level") or 0.0
    level_farbe: str = "green" if rechen_level < 0.5 else ("yellow" if rechen_level < 0.8 else "red")
    tabelle.add_row("Rechen-Level", Text(f"{rechen_level:.1%}", style=level_farbe))

    # Abtastrate
    abtastrate: float = status.get("abtastrate") or 0.0
    tabelle.add_row("Abtastrate", Text(f"{abtastrate:.1f} Hz", style="cyan"))

    # Wach seit
    wach_seit: float = status.get("wach_seit") or 0.0
    minuten: int = int(wach_seit // 60)
    sekunden: int = int(wach_seit % 60)
    if minuten > 0:
        wach_text: str = f"{minuten}m {sekunden}s"
    else:
        wach_text = f"{sekunden}s"
    tabelle.add_row("Wach seit", Text(wach_text, style="cyan"))

    return Panel(tabelle, title="⚡ Aktivität", border_style="cyan")

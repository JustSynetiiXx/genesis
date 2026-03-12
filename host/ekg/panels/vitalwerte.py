"""Panel 1: Vitalwerte — Echtzeit-Sensordaten mit Farbcodierung."""
from __future__ import annotations

from typing import Any

from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def _temp_farbe(temp: float) -> str:
    """Farbcode für CPU-Temperatur."""
    if temp < 60:
        return "green"
    elif temp < 75:
        return "yellow"
    elif temp < 85:
        return "dark_orange"
    return "red bold"


def _balken(prozent: float, breite: int = 20) -> Text:
    """Erzeugt einen farbigen Fortschrittsbalken."""
    gefuellt = int(prozent / 100 * breite)
    leer = breite - gefuellt

    if prozent < 50:
        farbe = "green"
    elif prozent < 75:
        farbe = "yellow"
    elif prozent < 90:
        farbe = "dark_orange"
    else:
        farbe = "red bold"

    text = Text()
    text.append("█" * gefuellt, style=farbe)
    text.append("░" * leer, style="dim")
    text.append(f" {prozent:5.1f}%")
    return text


def erstelle_panel(daten: dict[str, Any] | None) -> Panel:
    """Erzeugt das Vitalwerte-Panel."""
    if daten is None:
        return Panel(
            "[dim]Keine Sensordaten verfügbar.[/dim]",
            title="❤ Vitalwerte",
            border_style="red",
        )

    tabelle = Table(show_header=False, expand=True, padding=(0, 1))
    tabelle.add_column("Sensor", style="bold", width=20)
    tabelle.add_column("Wert", min_width=30)

    # CPU-Temperatur
    tctl = daten.get("cpu_temp_tctl")
    tccd1 = daten.get("cpu_temp_tccd1")
    if tctl is not None:
        farbe = _temp_farbe(tctl)
        tabelle.add_row("CPU Tctl", Text(f"{tctl:.1f}°C", style=farbe))
    if tccd1 is not None:
        farbe = _temp_farbe(tccd1)
        tabelle.add_row("CPU Tccd1", Text(f"{tccd1:.1f}°C", style=farbe))

    # CPU-Last gesamt
    cpu_gesamt = daten.get("cpu_last_gesamt")
    if cpu_gesamt is not None:
        tabelle.add_row("CPU Gesamt", _balken(cpu_gesamt))

    # CPU-Last pro Kern
    for i in range(16):
        key = f"cpu_last_kern_{i}"
        if key in daten:
            tabelle.add_row(f"  Kern {i}", _balken(daten[key]))

    # RAM
    ram_gesamt = daten.get("ram_gesamt_mb")
    ram_benutzt = daten.get("ram_benutzt_mb")
    ram_frei = daten.get("ram_frei_mb")
    if ram_gesamt and ram_benutzt:
        prozent = (ram_benutzt / ram_gesamt) * 100
        text = Text()
        text.append_text(_balken(prozent))
        text.append(f"  ({ram_benutzt:.0f}/{ram_gesamt:.0f} MB)")
        tabelle.add_row("RAM", text)
    if ram_frei is not None:
        tabelle.add_row("RAM Frei", Text(f"{ram_frei:.0f} MB"))

    # Lüfter
    luefter = daten.get("luefter_rpm")
    if luefter is not None:
        tabelle.add_row("Lüfter (GPU)", Text(f"{luefter:.0f} RPM"))

    # Alter der Daten
    alter = daten.get("alter_sekunden", 0)
    stil = "green" if alter < 2 else "yellow" if alter < 5 else "red"
    tabelle.add_row("Datenalter", Text(f"{alter:.2f}s", style=stil))

    return Panel(tabelle, title="❤ Vitalwerte", border_style="green")

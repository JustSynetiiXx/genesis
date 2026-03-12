"""Geschichte-Panel: Sensorverlauf über Zeit.

Zeigt CPU-Temperatur und RAM-Nutzung als Sparkline-artige ASCII-Charts
über die letzten N Minuten.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any

from rich.panel import Panel
from rich.table import Table
from rich.text import Text


# Sparkline-Zeichen (8 Stufen)
SPARK_ZEICHEN: str = "▁▂▃▄▅▆▇█"


class SensorGeschichte:
    """Speichert Sensorwerte über Zeit für die Darstellung als Zeitstrahl.

    Attributes:
        max_eintraege: Maximale Anzahl gespeicherter Einträge.
        _verlauf: Deque mit (zeitstempel, sensor_daten) Tupeln.
    """

    def __init__(self, max_eintraege: int = 120) -> None:
        """Initialisiert die Geschichte.

        Args:
            max_eintraege: Maximale Anzahl gespeicherter Datenpunkte.
                Bei 2Hz Refresh sind 120 Einträge = 1 Minute.
        """
        self.max_eintraege: int = max_eintraege
        self._verlauf: deque[tuple[float, dict[str, Any]]] = deque(
            maxlen=max_eintraege
        )
        self._letzter_zeitstempel: float = 0.0

    def aktualisiere(self, sensor_daten: dict[str, Any] | None) -> None:
        """Fügt neue Sensordaten zur Geschichte hinzu.

        Vermeidet Duplikate basierend auf dem Zeitstempel der Sensordaten.

        Args:
            sensor_daten: Aktuelle Sensordaten vom Leser, oder None.
        """
        if sensor_daten is None:
            return

        zeitstempel: float = sensor_daten.get("zeitstempel", 0.0)
        if zeitstempel <= self._letzter_zeitstempel:
            return  # Duplikat vermeiden

        self._letzter_zeitstempel = zeitstempel
        self._verlauf.append((zeitstempel, sensor_daten))

    @property
    def anzahl(self) -> int:
        """Anzahl der gespeicherten Einträge."""
        return len(self._verlauf)

    @property
    def dauer_sekunden(self) -> float:
        """Zeitspanne der gespeicherten Daten in Sekunden."""
        if len(self._verlauf) < 2:
            return 0.0
        return self._verlauf[-1][0] - self._verlauf[0][0]

    def werte_fuer(self, schluessel: str) -> list[float]:
        """Gibt alle gespeicherten Werte für einen Sensor zurück.

        Args:
            schluessel: Sensor-Schlüssel (z.B. 'cpu_temp_tctl').

        Returns:
            Liste von Werten in chronologischer Reihenfolge.
        """
        ergebnis: list[float] = []
        for _, daten in self._verlauf:
            wert: float | None = daten.get(schluessel)
            if wert is not None:
                ergebnis.append(wert)
        return ergebnis


def _sparkline(
    werte: list[float],
    minimum: float | None = None,
    maximum: float | None = None,
    breite: int = 50,
) -> str:
    """Erzeugt eine Sparkline aus Werten.

    Args:
        werte: Liste von float-Werten.
        minimum: Unterer Grenzwert (Standard: min der Werte).
        maximum: Oberer Grenzwert (Standard: max der Werte).
        breite: Maximale Breite in Zeichen.

    Returns:
        Sparkline-String.
    """
    if not werte:
        return "─" * breite

    # Auf gewünschte Breite reduzieren durch Sampling
    if len(werte) > breite:
        schritt: float = len(werte) / breite
        werte = [werte[int(i * schritt)] for i in range(breite)]

    min_w: float = minimum if minimum is not None else min(werte)
    max_w: float = maximum if maximum is not None else max(werte)
    spanne: float = max_w - min_w

    if spanne == 0:
        # Alle Werte gleich — Mitte anzeigen
        return SPARK_ZEICHEN[4] * len(werte)

    ergebnis: list[str] = []
    for w in werte:
        normalisiert: float = (w - min_w) / spanne
        index: int = min(int(normalisiert * (len(SPARK_ZEICHEN) - 1)), len(SPARK_ZEICHEN) - 1)
        ergebnis.append(SPARK_ZEICHEN[index])

    return "".join(ergebnis)


def erstelle_panel(
    geschichte: SensorGeschichte | None = None,
) -> Panel:
    """Erstellt das Geschichte-Panel.

    Args:
        geschichte: SensorGeschichte-Instanz mit historischen Daten.

    Returns:
        Rich Panel mit Sensorverlauf.
    """
    if geschichte is None or geschichte.anzahl < 2:
        inhalt = Table(show_header=False, box=None, expand=True, padding=(0, 1))
        inhalt.add_column("Info", ratio=1)
        inhalt.add_row(Text("Sammle Daten...", style="dim"))
        inhalt.add_row(Text(
            f"Einträge: {geschichte.anzahl if geschichte else 0}",
            style="dim",
        ))
        return Panel(inhalt, title="📈 Geschichte", border_style="dim")

    tabelle = Table(show_header=False, box=None, expand=True, padding=(0, 1))
    tabelle.add_column("Sensor", style="bold", width=14)
    tabelle.add_column("Verlauf", ratio=1)
    tabelle.add_column("Aktuell", width=10, justify="right")

    dauer: float = geschichte.dauer_sekunden
    dauer_text: str = (
        f"{dauer:.0f}s" if dauer < 60 else f"{dauer / 60:.1f}min"
    )

    # CPU-Temperatur Tctl
    temp_werte: list[float] = geschichte.werte_fuer("cpu_temp_tctl")
    if temp_werte:
        spark: str = _sparkline(temp_werte, minimum=30.0, maximum=100.0)
        aktuell: float = temp_werte[-1]
        farbe: str = "green" if aktuell < 60 else ("yellow" if aktuell < 75 else "red")
        tabelle.add_row(
            "CPU Temp",
            Text(spark, style=farbe),
            Text(f"{aktuell:.1f}°C", style=farbe),
        )

    # CPU-Last Gesamt
    last_werte: list[float] = geschichte.werte_fuer("cpu_last_gesamt")
    if last_werte:
        spark = _sparkline(last_werte, minimum=0.0, maximum=100.0)
        aktuell = last_werte[-1]
        farbe = "green" if aktuell < 50 else ("yellow" if aktuell < 75 else "red")
        tabelle.add_row(
            "CPU Last",
            Text(spark, style=farbe),
            Text(f"{aktuell:.1f}%", style=farbe),
        )

    # RAM Benutzt
    ram_werte: list[float] = geschichte.werte_fuer("ram_benutzt_mb")
    ram_gesamt_werte: list[float] = geschichte.werte_fuer("ram_gesamt_mb")
    if ram_werte:
        ram_max: float = ram_gesamt_werte[-1] if ram_gesamt_werte else max(ram_werte) * 1.1
        spark = _sparkline(ram_werte, minimum=0.0, maximum=ram_max)
        aktuell = ram_werte[-1]
        anteil: float = aktuell / ram_max if ram_max > 0 else 0
        farbe = "green" if anteil < 0.5 else ("yellow" if anteil < 0.75 else "red")
        tabelle.add_row(
            "RAM",
            Text(spark, style=farbe),
            Text(f"{aktuell:.0f} MB", style=farbe),
        )

    # Lüfter
    luefter_werte: list[float] = geschichte.werte_fuer("luefter_rpm")
    if luefter_werte:
        spark = _sparkline(luefter_werte, minimum=0.0, maximum=3000.0)
        aktuell = luefter_werte[-1]
        farbe = "cyan" if aktuell < 1500 else ("yellow" if aktuell < 2500 else "red")
        tabelle.add_row(
            "Lüfter",
            Text(spark, style=farbe),
            Text(f"{aktuell:.0f} RPM", style=farbe),
        )

    # Zeitanzeige
    tabelle.add_row(
        Text(""),
        Text(f"← {dauer_text} →", style="dim", justify="center"),
        Text("jetzt", style="dim"),
    )

    return Panel(tabelle, title="📈 Geschichte", border_style="yellow")

"""Reize — Zufällige, nicht-bedrohliche Sensor-Events.

Die Umgebung erzeugt gelegentlich Reize die Genesis spürt:
- Vibration: CPU-Last steigt kurz
- Wärme: Temperatur steigt kurz
- Druck: RAM sinkt kurz

Reize sind NICHT gefährlich — sie überschreiten nie Reflex-Schwellen.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any


@dataclass
class Reiz:
    """Ein aktiver Reiz in der Umgebung."""
    typ: str           # "vibration", "waerme", "druck"
    staerke: float     # Stärke des Reizes
    dauer: int         # Verbleibende Ticks
    gesamt_dauer: int  # Ursprüngliche Dauer


# Reiz-Definitionen: typ → (min_staerke, max_staerke, einheit)
REIZ_TYPEN: dict[str, dict[str, Any]] = {
    "vibration": {
        "min_staerke": 10.0,
        "max_staerke": 20.0,
        "sensor": "eigen_cpu_prozent",
        "beschreibung": "CPU-Last steigt kurz (Mutter bewegt sich)",
    },
    "waerme": {
        "min_staerke": 3.0,
        "max_staerke": 5.0,
        "sensor": "cpu_temp_tctl",
        "beschreibung": "Temperatur steigt kurz (Körperwärme-Schwankung)",
    },
    "druck": {
        "min_staerke": 50.0,
        "max_staerke": 100.0,
        "sensor": "vm_ram_frei_mb",
        "beschreibung": "RAM sinkt kurz (Druck auf Bauch)",
    },
}


class ReizGenerator:
    """Erzeugt zufällige Reize in der Umgebung.

    Reize kommen alle 30-120 Ticks und dauern 3-10 Ticks.
    """

    def __init__(self, erlaubte_typen: list[str] | None = None) -> None:
        """Initialisiert den Reiz-Generator.

        Args:
            erlaubte_typen: Welche Reiz-Typen erlaubt sind (None = alle).
        """
        self._erlaubte_typen: list[str] = erlaubte_typen or list(REIZ_TYPEN.keys())
        self._naechster_reiz: int = random.randint(30, 120)
        self._tick_zaehler: int = 0
        self._aktiver_reiz: Reiz | None = None
        self._min_intervall: int = 30
        self._max_intervall: int = 120

    def setze_intervall(self, min_ticks: int, max_ticks: int) -> None:
        """Setzt das Intervall für neue Reize.

        Args:
            min_ticks: Minimale Ticks zwischen Reizen.
            max_ticks: Maximale Ticks zwischen Reizen.
        """
        self._min_intervall = max(5, min_ticks)
        self._max_intervall = max(self._min_intervall + 1, max_ticks)

    def setze_erlaubte_typen(self, typen: list[str]) -> None:
        """Setzt die erlaubten Reiz-Typen.

        Args:
            typen: Liste von erlaubten Reiz-Typ-Namen.
        """
        self._erlaubte_typen = [t for t in typen if t in REIZ_TYPEN]

    def pruefe_reiz(self) -> Reiz | None:
        """Prüft ob ein neuer Reiz gestartet wird oder ein aktiver weiterläuft.

        Returns:
            Aktiver Reiz oder None.
        """
        # Aktiver Reiz läuft weiter
        if self._aktiver_reiz is not None:
            self._aktiver_reiz.dauer -= 1
            if self._aktiver_reiz.dauer <= 0:
                self._aktiver_reiz = None
            return self._aktiver_reiz

        # Kein aktiver Reiz — prüfe ob neuer startet
        if not self._erlaubte_typen:
            return None

        self._tick_zaehler += 1
        if self._tick_zaehler >= self._naechster_reiz:
            self._tick_zaehler = 0
            self._naechster_reiz = random.randint(
                self._min_intervall, self._max_intervall
            )
            # Neuen Reiz erstellen
            typ: str = random.choice(self._erlaubte_typen)
            info: dict[str, Any] = REIZ_TYPEN[typ]
            staerke: float = random.uniform(info["min_staerke"], info["max_staerke"])
            dauer: int = random.randint(3, 10)
            self._aktiver_reiz = Reiz(
                typ=typ,
                staerke=staerke,
                dauer=dauer,
                gesamt_dauer=dauer,
            )
            return self._aktiver_reiz

        return None

    @property
    def aktiver_reiz(self) -> Reiz | None:
        """Aktuell aktiver Reiz (falls vorhanden)."""
        return self._aktiver_reiz


def wende_reiz_an(rohwerte: dict[str, float], reiz: Reiz | None) -> dict[str, float]:
    """Wendet einen aktiven Reiz auf die Rohwerte an.

    Modifiziert die Rohwerte temporär. Die Originale bleiben unverändert.

    Args:
        rohwerte: Aktuelle Sensor-Rohwerte.
        reiz: Aktiver Reiz oder None.

    Returns:
        Modifizierte Rohwerte (Kopie).
    """
    if reiz is None:
        return rohwerte

    modifiziert: dict[str, float] = dict(rohwerte)

    if reiz.typ == "vibration":
        modifiziert["eigen_cpu_prozent"] = modifiziert.get("eigen_cpu_prozent", 0.0) + reiz.staerke
    elif reiz.typ == "waerme":
        modifiziert["cpu_temp_tctl"] = modifiziert.get("cpu_temp_tctl", 50.0) + reiz.staerke
    elif reiz.typ == "druck":
        modifiziert["vm_ram_frei_mb"] = max(
            50.0,
            modifiziert.get("vm_ram_frei_mb", 3000.0) - reiz.staerke,
        )

    return modifiziert

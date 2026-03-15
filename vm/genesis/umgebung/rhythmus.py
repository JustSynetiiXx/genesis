"""Rhythmus — 24-Stunden-Zyklus den Genesis spüren aber nicht kontrollieren kann.

Sinuskurve über 24h basierend auf der realen Uhrzeit.
0.0 = tiefste Nacht (03:00 Uhr), 1.0 = Mittagspeak (15:00 Uhr).
"""

from __future__ import annotations

import math
from datetime import datetime


def rhythmus_wert(jetzt: datetime | None = None) -> float:
    """Berechnet den aktuellen Rhythmus-Wert (0.0-1.0).

    Sinuskurve mit Minimum um 03:00 und Maximum um 15:00.

    Args:
        jetzt: Zeitpunkt (Standard: aktuelle Zeit).

    Returns:
        Float zwischen 0.0 und 1.0.
    """
    if jetzt is None:
        jetzt = datetime.now()

    # Stunden als Float (0.0 - 24.0)
    stunde: float = jetzt.hour + jetzt.minute / 60.0 + jetzt.second / 3600.0

    # Sinus: Minimum bei 03:00, Maximum bei 15:00
    # sin hat Minimum bei -π/2 und Maximum bei π/2
    # Wir verschieben: (stunde - 3) / 24 * 2π → Sinus
    # Bei stunde=3: sin(-π/2) = -1 → 0.0
    # Bei stunde=15: sin(π/2) = 1 → 1.0
    winkel: float = (stunde - 3.0) / 24.0 * 2.0 * math.pi
    roh: float = math.sin(winkel)

    # Von [-1, 1] auf [0, 1] skalieren
    return (roh + 1.0) / 2.0


def kategorie_rhythmus(wert: float) -> str:
    """Kategorisiert den Rhythmus-Wert.

    Args:
        wert: Rhythmus-Wert (0.0-1.0).

    Returns:
        'ruhig', 'aktiv' oder 'peak'.
    """
    if wert < 0.3:
        return "ruhig"
    elif wert < 0.7:
        return "aktiv"
    else:
        return "peak"

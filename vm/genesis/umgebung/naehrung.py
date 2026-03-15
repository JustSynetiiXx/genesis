"""Nährstoff-Versorgung — Variabler Cache-Verfall und Nährstoff-Schübe.

Der Cache-Verfall ist nicht mehr konstant sondern abhängig vom Rhythmus.
Zusätzlich gibt es zufällige Nährstoff-Schübe (wie über die Nabelschnur).
"""

from __future__ import annotations

import random

from vm.config import VERFALL_MB_PRO_TICK


# Nährstoff-Schub: alle 50-150 Ticks, 10-30 MB
_SCHUB_MIN_INTERVALL: int = 50
_SCHUB_MAX_INTERVALL: int = 150
_SCHUB_MIN_MB: float = 10.0
_SCHUB_MAX_MB: float = 30.0


class NaehrstoffVersorgung:
    """Verwaltet die variable Nährstoff-Versorgung.

    Der Verfall hängt vom Rhythmus ab:
    - Peak (hoher Rhythmus): Verfall * 0.5 (mehr Nährstoffe)
    - Ruhig (niedriger Rhythmus): Verfall * 1.5 (weniger Nährstoffe)

    Zusätzlich gibt es zufällige Nährstoff-Schübe.
    """

    def __init__(self) -> None:
        self._naechster_schub: int = random.randint(
            _SCHUB_MIN_INTERVALL, _SCHUB_MAX_INTERVALL
        )
        self._tick_zaehler: int = 0
        self._letzter_schub_menge: float = 0.0

    def aktueller_verfall(self, rhythmus_wert: float,
                          feedback_modifikator: float = 1.0) -> float:
        """Berechnet den aktuellen Cache-Verfall pro Tick.

        Args:
            rhythmus_wert: Aktueller Rhythmus (0.0-1.0).
            feedback_modifikator: Multiplikator vom Feedback-Controller (Standard 1.0).

        Returns:
            Verfall in MB pro Tick.
        """
        # Rhythmus-Modifikator: 0.5 bei Peak (1.0), 1.5 bei Nacht (0.0)
        # Linear: modifikator = 1.5 - rhythmus_wert * 1.0
        rhythmus_mod: float = 1.5 - rhythmus_wert * 1.0
        return VERFALL_MB_PRO_TICK * rhythmus_mod * feedback_modifikator

    def naehrstoff_schub(self, feedback_modifikator: float = 1.0) -> tuple[bool, float]:
        """Prüft ob ein Nährstoff-Schub fällig ist.

        Args:
            feedback_modifikator: Multiplikator für Schub-Intervall.
                < 1.0 = häufiger, > 1.0 = seltener.

        Returns:
            Tuple (schub_aktiv, menge_mb). Menge ist 0 wenn kein Schub.
        """
        self._tick_zaehler += 1
        self._letzter_schub_menge = 0.0

        # Feedback beeinflusst das Intervall
        effektives_intervall: int = max(
            10, int(self._naechster_schub * feedback_modifikator)
        )

        if self._tick_zaehler >= effektives_intervall:
            menge: float = random.uniform(_SCHUB_MIN_MB, _SCHUB_MAX_MB)
            self._letzter_schub_menge = menge
            self._tick_zaehler = 0
            self._naechster_schub = random.randint(
                _SCHUB_MIN_INTERVALL, _SCHUB_MAX_INTERVALL
            )
            return True, menge

        return False, 0.0

    @property
    def ticks_bis_schub(self) -> int:
        """Geschätzte Ticks bis zum nächsten Nährstoff-Schub."""
        return max(0, self._naechster_schub - self._tick_zaehler)

    @property
    def letzter_schub_menge(self) -> float:
        """Menge des letzten Nährstoff-Schubs in MB."""
        return self._letzter_schub_menge

    def beschleunige_schub(self) -> None:
        """Beschleunigt den nächsten Schub (für signal_senden Aktion)."""
        # Halbiert die verbleibende Wartezeit
        verbleibend: int = self._naechster_schub - self._tick_zaehler
        if verbleibend > 5:
            self._tick_zaehler += verbleibend // 2

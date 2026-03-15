"""Entwicklungsphasen — Die Umgebung wird über Tage komplexer.

Phasen basieren auf kumulativer Wachzeit (nicht Echtzeit-Tagen):
- embryo (Tag 1-3): Nur Basis, keine Reize
- fetus_frueh (Tag 4-7): Rhythmus, variable Nährstoffe, erste Reize
- fetus_spaet (Tag 8-14): Alle Reize, Feedback, neue Aktionen
- reif (ab Tag 15): Volle Komplexität
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


# Sekunden pro "Tag" in Betriebszeit
# 1 Tag = 86400 Sekunden, aber Genesis hat Pausen etc.
# Wir zählen nur aktive Wachzeit.
SEKUNDEN_PRO_TAG: int = 86400

# Schwellen in kumulativen Wachtagen
PHASE_SCHWELLEN: dict[str, int] = {
    "embryo": 0,        # Tag 1-3
    "fetus_frueh": 3,   # Tag 4-7
    "fetus_spaet": 7,   # Tag 8-14
    "reif": 14,         # Ab Tag 15
}


class EntwicklungsManager:
    """Verwaltet die Entwicklungsphasen von Genesis.

    Speichert kumulative Wachzeit persistent.
    """

    def __init__(self, zustand_pfad: Path | None = None) -> None:
        """Initialisiert den Entwicklungs-Manager.

        Args:
            zustand_pfad: Pfad zur Datei für persistente Wachzeit.
        """
        self._zustand_pfad: Path | None = zustand_pfad
        self._kumulative_wachzeit: float = 0.0
        self._lade_wachzeit()

    def _lade_wachzeit(self) -> None:
        """Lädt die kumulative Wachzeit aus der Zustandsdatei."""
        if self._zustand_pfad is None:
            return
        try:
            self._kumulative_wachzeit = float(
                self._zustand_pfad.read_text(encoding="utf-8").strip()
            )
        except (FileNotFoundError, ValueError, OSError):
            self._kumulative_wachzeit = 0.0

    def _speichere_wachzeit(self) -> None:
        """Speichert die kumulative Wachzeit."""
        if self._zustand_pfad is None:
            return
        try:
            self._zustand_pfad.parent.mkdir(parents=True, exist_ok=True)
            self._zustand_pfad.write_text(
                f"{self._kumulative_wachzeit:.1f}\n", encoding="utf-8"
            )
        except OSError:
            pass

    def tick(self, sekunden: float) -> None:
        """Fügt Wachzeit hinzu (einmal pro Loop aufrufen).

        Args:
            sekunden: Vergangene Sekunden seit letztem Tick.
        """
        self._kumulative_wachzeit += sekunden
        # Nur alle 60 Sekunden speichern um I/O zu reduzieren
        if int(self._kumulative_wachzeit) % 60 == 0:
            self._speichere_wachzeit()

    @property
    def wachtage(self) -> float:
        """Kumulative Wachzeit in Tagen."""
        return self._kumulative_wachzeit / SEKUNDEN_PRO_TAG

    @property
    def wachzeit_sekunden(self) -> float:
        """Kumulative Wachzeit in Sekunden."""
        return self._kumulative_wachzeit

    def aktuelle_phase(self) -> str:
        """Gibt die aktuelle Entwicklungsphase zurück.

        Returns:
            Eine von: 'embryo', 'fetus_frueh', 'fetus_spaet', 'reif'.
        """
        tage: float = self.wachtage
        if tage >= PHASE_SCHWELLEN["reif"]:
            return "reif"
        elif tage >= PHASE_SCHWELLEN["fetus_spaet"]:
            return "fetus_spaet"
        elif tage >= PHASE_SCHWELLEN["fetus_frueh"]:
            return "fetus_frueh"
        else:
            return "embryo"

    def phase_config(self) -> dict[str, Any]:
        """Gibt die aktive Feature-Konfiguration für die aktuelle Phase zurück.

        Returns:
            Dict mit allen aktiven Features und deren Einstellungen.
        """
        phase: str = self.aktuelle_phase()

        config: dict[str, Any] = {
            "phase": phase,
            "wachtage": round(self.wachtage, 2),
            "wachzeit_sekunden": round(self._kumulative_wachzeit, 1),
            # Feature-Flags
            "rhythmus_aktiv": phase != "embryo",
            "variable_naehrung": phase != "embryo",
            "reize_aktiv": phase in ("fetus_frueh", "fetus_spaet", "reif"),
            "feedback_aktiv": phase in ("fetus_spaet", "reif"),
            "externe_aktionen": phase in ("fetus_spaet", "reif"),
            # Erlaubte Reiz-Typen
            "erlaubte_reize": self._erlaubte_reize(phase),
            # Verfügbare Aktionen
            "zusatz_aktionen": self._zusatz_aktionen(phase),
        }
        return config

    def _erlaubte_reize(self, phase: str) -> list[str]:
        """Gibt erlaubte Reiz-Typen für eine Phase zurück."""
        if phase == "embryo":
            return []
        elif phase == "fetus_frueh":
            return ["vibration"]
        else:
            return ["vibration", "waerme", "druck"]

    def _zusatz_aktionen(self, phase: str) -> list[str]:
        """Gibt zusätzliche Aktionen für eine Phase zurück."""
        if phase in ("fetus_spaet", "reif"):
            return ["signal_senden", "umgebung_erkunden", "rhythmus_anpassen"]
        else:
            return []

    def speichere(self) -> None:
        """Erzwingt das Speichern der Wachzeit."""
        self._speichere_wachzeit()

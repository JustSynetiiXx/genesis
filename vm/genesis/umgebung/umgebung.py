"""Umgebung — Der Feedback-Controller und zentrale Umgebungs-Steuerung.

Die Umgebung beobachtet Genesis und reagiert:
- Komfort-Zone (Schmerz < 0.05): Mehr Herausforderung
- Stress-Zone (Schmerz > 0.25): Mehr Fürsorge
- Normal-Zone (0.05-0.25): Keine Anpassung
"""

from __future__ import annotations

import logging
import time
from collections import deque
from pathlib import Path
from typing import Any

from vm.genesis.umgebung.entwicklung import EntwicklungsManager
from vm.genesis.umgebung.naehrung import NaehrstoffVersorgung
from vm.genesis.umgebung.reize import Reiz, ReizGenerator, wende_reiz_an
from vm.genesis.umgebung.rhythmus import kategorie_rhythmus, rhythmus_wert

logger = logging.getLogger("genesis")

# Feedback-Schwellen
_KOMFORT_SCHWELLE: float = 0.05
_STRESS_SCHWELLE: float = 0.25
_HISTORIE_LAENGE: int = 100


class GebaerMutter:
    """Die lebende Umgebung für Genesis.

    Koordiniert alle Umgebungs-Subsysteme und reagiert auf Genesis' Zustand.
    """

    def __init__(self, db_verzeichnis: Path | None = None) -> None:
        """Initialisiert die Gebärmutter.

        Args:
            db_verzeichnis: Pfad zum Persistenz-Verzeichnis.
        """
        wachzeit_pfad: Path | None = None
        if db_verzeichnis is not None:
            wachzeit_pfad = db_verzeichnis / "wachzeit.txt"

        self.entwicklung: EntwicklungsManager = EntwicklungsManager(wachzeit_pfad)
        self.naehrung: NaehrstoffVersorgung = NaehrstoffVersorgung()
        self.reize: ReizGenerator = ReizGenerator(erlaubte_typen=[])

        # Feedback-State
        self._schmerz_historie: deque[float] = deque(maxlen=_HISTORIE_LAENGE)
        self._aktuelle_zone: str = "normal_zone"
        self._letzter_rhythmus: float = 0.5
        self._letzte_rhythmus_kategorie: str = "aktiv"
        self._letzter_reiz: Reiz | None = None
        self._letzter_schub: bool = False
        self._letzter_schub_menge: float = 0.0
        self._letzter_verfall: float = 0.2
        self._genauigkeit_ticks: int = 0  # Für umgebung_erkunden

        # Feedback-Modifikatoren
        self._verfall_mod: float = 1.0
        self._schub_mod: float = 1.0

    def tick(self, loop_intervall: float) -> dict[str, Any]:
        """Wird einmal pro Loop aufgerufen. Aktualisiert alle Umgebungs-Systeme.

        Args:
            loop_intervall: Sekunden seit letztem Tick.

        Returns:
            Dict mit allen Umgebungsdaten für diesen Tick.
        """
        # Entwicklung tracken
        self.entwicklung.tick(loop_intervall)
        phase_cfg: dict[str, Any] = self.entwicklung.phase_config()

        # Rhythmus
        if phase_cfg["rhythmus_aktiv"]:
            self._letzter_rhythmus = rhythmus_wert()
            self._letzte_rhythmus_kategorie = kategorie_rhythmus(self._letzter_rhythmus)
        else:
            self._letzter_rhythmus = 0.5  # Konstant in embryo-Phase
            self._letzte_rhythmus_kategorie = "aktiv"

        # Reize konfigurieren und prüfen
        if phase_cfg["reize_aktiv"]:
            self.reize.setze_erlaubte_typen(phase_cfg["erlaubte_reize"])
            self._letzter_reiz = self.reize.pruefe_reiz()
        else:
            self._letzter_reiz = None

        # Nährstoff-Verfall berechnen
        if phase_cfg["variable_naehrung"]:
            self._letzter_verfall = self.naehrung.aktueller_verfall(
                self._letzter_rhythmus, self._verfall_mod
            )
        else:
            from vm.config import VERFALL_MB_PRO_TICK
            self._letzter_verfall = VERFALL_MB_PRO_TICK

        # Nährstoff-Schub prüfen
        self._letzter_schub, self._letzter_schub_menge = self.naehrung.naehrstoff_schub(
            self._schub_mod
        )

        # Genauigkeit abbauen
        if self._genauigkeit_ticks > 0:
            self._genauigkeit_ticks -= 1

        return {
            "phase": phase_cfg["phase"],
            "phase_config": phase_cfg,
            "rhythmus": self._letzter_rhythmus,
            "rhythmus_kategorie": self._letzte_rhythmus_kategorie,
            "reiz": self._letzter_reiz,
            "verfall_mb": self._letzter_verfall,
            "schub_aktiv": self._letzter_schub,
            "schub_menge": self._letzter_schub_menge,
            "zone": self._aktuelle_zone,
            "ticks_bis_schub": self.naehrung.ticks_bis_schub,
            "genauigkeit_aktiv": self._genauigkeit_ticks > 0,
            "wachtage": phase_cfg["wachtage"],
        }

    def feedback(self, schmerz: float) -> None:
        """Füttert den Feedback-Controller mit dem aktuellen Schmerz.

        Args:
            schmerz: Aktueller Schmerzwert (0.0-1.0).
        """
        self._schmerz_historie.append(schmerz)

        if len(self._schmerz_historie) < _HISTORIE_LAENGE:
            return

        # Nur bewerten wenn Feedback aktiv (Phase fetus_spaet+)
        phase_cfg = self.entwicklung.phase_config()
        if not phase_cfg["feedback_aktiv"]:
            self._aktuelle_zone = "normal_zone"
            self._verfall_mod = 1.0
            self._schub_mod = 1.0
            return

        durchschnitt: float = sum(self._schmerz_historie) / len(self._schmerz_historie)
        alte_zone: str = self._aktuelle_zone

        if durchschnitt < _KOMFORT_SCHWELLE:
            self._aktuelle_zone = "komfort_zone"
            # Mehr Herausforderung
            self._verfall_mod = 1.2
            self._schub_mod = 1.5  # Seltener Schübe
            self.reize.setze_intervall(20, 80)  # Häufigere Reize
        elif durchschnitt > _STRESS_SCHWELLE:
            self._aktuelle_zone = "stress_zone"
            # Mehr Fürsorge
            self._verfall_mod = 0.8
            self._schub_mod = 0.5  # Häufigere Schübe
            self.reize.setze_intervall(60, 200)  # Seltenere Reize
        else:
            self._aktuelle_zone = "normal_zone"
            self._verfall_mod = 1.0
            self._schub_mod = 1.0
            self.reize.setze_intervall(30, 120)

        if alte_zone != self._aktuelle_zone:
            logger.info(
                "Umgebung passt sich an: %s → %s (Ø Schmerz: %.3f)",
                alte_zone, self._aktuelle_zone, durchschnitt,
            )

    def wende_reiz_auf_rohwerte_an(self, rohwerte: dict[str, float]) -> dict[str, float]:
        """Wendet den aktuellen Reiz auf Rohwerte an.

        Args:
            rohwerte: Sensor-Rohwerte.

        Returns:
            Modifizierte Rohwerte.
        """
        return wende_reiz_an(rohwerte, self._letzter_reiz)

    def verfuegbare_zusatz_aktionen(self) -> list[str]:
        """Gibt die in der aktuellen Phase verfügbaren Zusatz-Aktionen zurück."""
        return self.entwicklung.phase_config()["zusatz_aktionen"]

    def ausfuehren_signal_senden(self) -> None:
        """Genesis sendet ein Signal — nächster Nährstoff-Schub kommt schneller."""
        self.naehrung.beschleunige_schub()

    def ausfuehren_umgebung_erkunden(self) -> None:
        """Genesis tastet die Umgebung ab — genauere Sensorwerte für 5 Ticks."""
        self._genauigkeit_ticks = 5

    def ausfuehren_rhythmus_anpassen(self) -> bool:
        """Genesis versucht sich an den Rhythmus anzupassen.

        Returns:
            True wenn erfolgreich (nahe am Peak), False sonst.
        """
        # Erfolgreich wenn Rhythmus > 0.6 (nahe am Peak)
        if self._letzter_rhythmus > 0.6:
            return True
        return False

    def status_fuer_dashboard(self) -> dict[str, Any]:
        """Gibt alle Umgebungsdaten für das Dashboard zurück."""
        phase_cfg = self.entwicklung.phase_config()
        return {
            "phase": phase_cfg["phase"],
            "wachtage": phase_cfg["wachtage"],
            "wachzeit_sekunden": phase_cfg["wachzeit_sekunden"],
            "rhythmus": round(self._letzter_rhythmus, 3),
            "rhythmus_kategorie": self._letzte_rhythmus_kategorie,
            "verfall_mb": round(self._letzter_verfall, 4),
            "reiz_aktiv": self._letzter_reiz is not None,
            "reiz_typ": self._letzter_reiz.typ if self._letzter_reiz else None,
            "reiz_staerke": round(self._letzter_reiz.staerke, 1) if self._letzter_reiz else None,
            "reiz_dauer": self._letzter_reiz.dauer if self._letzter_reiz else None,
            "zone": self._aktuelle_zone,
            "ticks_bis_schub": self.naehrung.ticks_bis_schub,
            "letzter_schub": self._letzter_schub,
            "schub_menge": round(self._letzter_schub_menge, 1),
            "features": {
                "rhythmus": phase_cfg["rhythmus_aktiv"],
                "naehrung": phase_cfg["variable_naehrung"],
                "reize": phase_cfg["reize_aktiv"],
                "feedback": phase_cfg["feedback_aktiv"],
                "externe_aktionen": phase_cfg["externe_aktionen"],
            },
            "verfall_mod": round(self._verfall_mod, 2),
            "schub_mod": round(self._schub_mod, 2),
        }

    def speichere(self) -> None:
        """Speichert persistente Daten."""
        self.entwicklung.speichere()

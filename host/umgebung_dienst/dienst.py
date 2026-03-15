"""Umgebungs-Dienst — Eigenständiger Prozess für die Gebärmutter.

Berechnet pro Tick (jede Sekunde):
- Rhythmus (24h-Sinuskurve)
- Aktive Reize
- Verfall-Modifikator
- Feedback-Zone (basierend auf Schmerz aller Genesis-Instanzen)
- Entwicklungsphase
- Nährstoff-Schübe

Schreibt alles in shared/umgebung_status.json.

Starten:
    python3 -m host.umgebung_dienst.dienst
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import random
import signal
import sys
import tempfile
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [UMGEBUNG] %(message)s",
)
logger = logging.getLogger("umgebung")

# --- Konstanten ---
TICK_INTERVALL: float = 1.0  # Sekunden
VERFALL_BASIS: float = 0.2   # MB pro Tick
SCHUB_MIN_INTERVALL: int = 50
SCHUB_MAX_INTERVALL: int = 150
SCHUB_MIN_MB: float = 10.0
SCHUB_MAX_MB: float = 30.0
FEEDBACK_HISTORIE: int = 100
KOMFORT_SCHWELLE: float = 0.05
STRESS_SCHWELLE: float = 0.25

# Entwicklungsphasen (kumulative Betriebssekunden)
SEKUNDEN_PRO_TAG: int = 86400
PHASE_SCHWELLEN: dict[str, int] = {
    "embryo": 0,
    "fetus_frueh": 3,
    "fetus_spaet": 7,
    "reif": 14,
}

# Reiz-Definitionen
REIZ_TYPEN: dict[str, dict[str, float]] = {
    "vibration": {"min_staerke": 10.0, "max_staerke": 20.0},
    "waerme": {"min_staerke": 3.0, "max_staerke": 5.0},
    "druck": {"min_staerke": 50.0, "max_staerke": 100.0},
}


class UmgebungsDienst:
    """Eigenständiger Umgebungs-Prozess.

    Berechnet alle Umgebungsdaten und schreibt sie als JSON.
    Liest Schmerz-Werte aller Genesis-Instanzen für Feedback.
    """

    def __init__(self, ausgabe_pfad: Path,
                 instanz_pfade: dict[str, Path],
                 wachzeit_pfad: Path | None = None) -> None:
        """Initialisiert den Dienst.

        Args:
            ausgabe_pfad: Pfad zur umgebung_status.json.
            instanz_pfade: Dict von Instanzname → genesis_status.json Pfad.
            wachzeit_pfad: Pfad zur persistenten Wachzeit-Datei.
        """
        self._ausgabe_pfad: Path = ausgabe_pfad
        self._instanz_pfade: dict[str, Path] = instanz_pfade
        self._wachzeit_pfad: Path | None = wachzeit_pfad
        self._laeuft: bool = True

        # Rhythmus — keine eigene Berechnung nötig, nur Sinus
        # Entwicklung
        self._kumulative_wachzeit: float = self._lade_wachzeit()
        self._start_zeit: float = time.time()

        # Reize
        self._reiz_tick_zaehler: int = 0
        self._naechster_reiz: int = random.randint(30, 120)
        self._aktiver_reiz_typ: str | None = None
        self._aktiver_reiz_staerke: float = 0.0
        self._aktiver_reiz_verbleibend: int = 0
        self._reiz_min_intervall: int = 30
        self._reiz_max_intervall: int = 120

        # Nährstoffe
        self._naehr_tick_zaehler: int = 0
        self._naechster_schub: int = random.randint(
            SCHUB_MIN_INTERVALL, SCHUB_MAX_INTERVALL
        )
        self._letzter_schub_aktiv: bool = False
        self._letzter_schub_menge: float = 0.0

        # Feedback
        self._schmerz_historie: deque[float] = deque(maxlen=FEEDBACK_HISTORIE)
        self._feedback_zone: str = "normal_zone"
        self._verfall_mod: float = 1.0
        self._schub_mod: float = 1.0

    def _lade_wachzeit(self) -> float:
        """Lädt persistente Wachzeit."""
        if self._wachzeit_pfad is None:
            return 0.0
        try:
            return float(self._wachzeit_pfad.read_text(encoding="utf-8").strip())
        except (FileNotFoundError, ValueError, OSError):
            return 0.0

    def _speichere_wachzeit(self) -> None:
        """Speichert Wachzeit persistent."""
        if self._wachzeit_pfad is None:
            return
        try:
            self._wachzeit_pfad.parent.mkdir(parents=True, exist_ok=True)
            self._wachzeit_pfad.write_text(
                f"{self._kumulative_wachzeit:.1f}\n", encoding="utf-8"
            )
        except OSError:
            pass

    # --- Rhythmus ---
    def _rhythmus(self) -> tuple[float, str]:
        """Berechnet den aktuellen Rhythmus-Wert."""
        jetzt = datetime.now()
        stunde: float = jetzt.hour + jetzt.minute / 60.0 + jetzt.second / 3600.0
        winkel: float = (stunde - 3.0) / 24.0 * 2.0 * math.pi
        wert: float = (math.sin(winkel) + 1.0) / 2.0
        if wert < 0.3:
            kat = "ruhig"
        elif wert < 0.7:
            kat = "aktiv"
        else:
            kat = "peak"
        return wert, kat

    # --- Entwicklung ---
    def _aktuelle_phase(self) -> tuple[str, float]:
        """Gibt Phase und Wachtage zurück."""
        tage: float = self._kumulative_wachzeit / SEKUNDEN_PRO_TAG
        if tage >= PHASE_SCHWELLEN["reif"]:
            return "reif", tage
        elif tage >= PHASE_SCHWELLEN["fetus_spaet"]:
            return "fetus_spaet", tage
        elif tage >= PHASE_SCHWELLEN["fetus_frueh"]:
            return "fetus_frueh", tage
        else:
            return "embryo", tage

    def _phase_config(self, phase: str) -> dict[str, Any]:
        """Feature-Flags für Phase."""
        return {
            "rhythmus_aktiv": phase != "embryo",
            "variable_naehrung": phase != "embryo",
            "reize_aktiv": phase in ("fetus_frueh", "fetus_spaet", "reif"),
            "feedback_aktiv": phase in ("fetus_spaet", "reif"),
            "externe_aktionen": phase in ("fetus_spaet", "reif"),
            "erlaubte_reize": (
                [] if phase == "embryo"
                else ["vibration"] if phase == "fetus_frueh"
                else ["vibration", "waerme", "druck"]
            ),
            "zusatz_aktionen": (
                ["signal_senden", "umgebung_erkunden", "rhythmus_anpassen"]
                if phase in ("fetus_spaet", "reif") else []
            ),
        }

    # --- Reize ---
    def _tick_reiz(self, erlaubte_typen: list[str]) -> None:
        """Aktualisiert Reiz-Status."""
        # Aktiver Reiz abbauen
        if self._aktiver_reiz_verbleibend > 0:
            self._aktiver_reiz_verbleibend -= 1
            if self._aktiver_reiz_verbleibend <= 0:
                self._aktiver_reiz_typ = None
                self._aktiver_reiz_staerke = 0.0
            return

        if not erlaubte_typen:
            self._aktiver_reiz_typ = None
            return

        self._reiz_tick_zaehler += 1
        if self._reiz_tick_zaehler >= self._naechster_reiz:
            self._reiz_tick_zaehler = 0
            self._naechster_reiz = random.randint(
                self._reiz_min_intervall, self._reiz_max_intervall
            )
            typ: str = random.choice(erlaubte_typen)
            info = REIZ_TYPEN[typ]
            self._aktiver_reiz_typ = typ
            self._aktiver_reiz_staerke = random.uniform(
                info["min_staerke"], info["max_staerke"]
            )
            self._aktiver_reiz_verbleibend = random.randint(3, 10)

    # --- Nährstoffe ---
    def _tick_naehrung(self) -> None:
        """Prüft ob ein Nährstoff-Schub fällig ist."""
        self._naehr_tick_zaehler += 1
        self._letzter_schub_aktiv = False
        self._letzter_schub_menge = 0.0

        effektives_intervall: int = max(
            10, int(self._naechster_schub * self._schub_mod)
        )
        if self._naehr_tick_zaehler >= effektives_intervall:
            self._letzter_schub_menge = random.uniform(SCHUB_MIN_MB, SCHUB_MAX_MB)
            self._letzter_schub_aktiv = True
            self._naehr_tick_zaehler = 0
            self._naechster_schub = random.randint(
                SCHUB_MIN_INTERVALL, SCHUB_MAX_INTERVALL
            )

    # --- Feedback ---
    def _lese_instanz_schmerz(self) -> list[float]:
        """Liest Schmerz-Werte aller Genesis-Instanzen."""
        werte: list[float] = []
        for name, pfad in self._instanz_pfade.items():
            try:
                daten = json.loads(pfad.read_bytes())
                alter: float = time.time() - daten.get("zeitstempel", 0)
                if alter < 30:  # Nur aktive Instanzen
                    werte.append(daten.get("schmerz", 0.0))
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                continue
        return werte

    def _tick_feedback(self, feedback_aktiv: bool) -> None:
        """Aktualisiert Feedback basierend auf Instanz-Schmerzen."""
        schmerz_werte: list[float] = self._lese_instanz_schmerz()
        if schmerz_werte:
            durchschnitt: float = sum(schmerz_werte) / len(schmerz_werte)
            self._schmerz_historie.append(durchschnitt)

        if not feedback_aktiv or len(self._schmerz_historie) < FEEDBACK_HISTORIE:
            self._feedback_zone = "normal_zone"
            self._verfall_mod = 1.0
            self._schub_mod = 1.0
            return

        avg: float = sum(self._schmerz_historie) / len(self._schmerz_historie)
        alte_zone: str = self._feedback_zone

        if avg < KOMFORT_SCHWELLE:
            self._feedback_zone = "komfort_zone"
            self._verfall_mod = 1.2
            self._schub_mod = 1.5
            self._reiz_min_intervall = 20
            self._reiz_max_intervall = 80
        elif avg > STRESS_SCHWELLE:
            self._feedback_zone = "stress_zone"
            self._verfall_mod = 0.8
            self._schub_mod = 0.5
            self._reiz_min_intervall = 60
            self._reiz_max_intervall = 200
        else:
            self._feedback_zone = "normal_zone"
            self._verfall_mod = 1.0
            self._schub_mod = 1.0
            self._reiz_min_intervall = 30
            self._reiz_max_intervall = 120

        if alte_zone != self._feedback_zone:
            logger.info(
                "Feedback: %s → %s (Ø Schmerz: %.3f)",
                alte_zone, self._feedback_zone, avg,
            )

    # --- Verfall ---
    def _verfall_modifikator(self, rhythmus: float,
                              variable_naehrung: bool) -> float:
        """Berechnet den aktuellen Verfall-Modifikator."""
        if not variable_naehrung:
            return VERFALL_BASIS
        rhythmus_mod: float = 1.5 - rhythmus * 1.0
        return VERFALL_BASIS * rhythmus_mod * self._verfall_mod

    # --- Haupt-Tick ---
    def tick(self) -> dict[str, Any]:
        """Ein Tick der Umgebung."""
        self._kumulative_wachzeit += TICK_INTERVALL

        phase, wachtage = self._aktuelle_phase()
        cfg = self._phase_config(phase)

        # Rhythmus
        if cfg["rhythmus_aktiv"]:
            rhythmus, rhythmus_kat = self._rhythmus()
        else:
            rhythmus, rhythmus_kat = 0.5, "aktiv"

        # Reize
        if cfg["reize_aktiv"]:
            self._tick_reiz(cfg["erlaubte_reize"])
        else:
            self._aktiver_reiz_typ = None
            self._aktiver_reiz_staerke = 0.0
            self._aktiver_reiz_verbleibend = 0

        # Nährstoffe
        self._tick_naehrung()

        # Feedback
        self._tick_feedback(cfg["feedback_aktiv"])

        # Verfall
        verfall: float = self._verfall_modifikator(rhythmus, cfg["variable_naehrung"])

        ticks_bis_schub: int = max(
            0, int(self._naechster_schub * self._schub_mod) - self._naehr_tick_zaehler
        )

        return {
            "rhythmus": round(rhythmus, 4),
            "rhythmus_kategorie": rhythmus_kat,
            "verfall_modifikator": round(verfall, 4),
            "reiz_aktiv": self._aktiver_reiz_typ,
            "reiz_staerke": round(self._aktiver_reiz_staerke, 1) if self._aktiver_reiz_typ else 0.0,
            "reiz_verbleibend": self._aktiver_reiz_verbleibend,
            "feedback_zone": self._feedback_zone,
            "phase": phase,
            "phase_tag": round(wachtage, 2),
            "naechster_schub_in": ticks_bis_schub,
            "schub_aktiv": self._letzter_schub_aktiv,
            "schub_menge": round(self._letzter_schub_menge, 1),
            "features": cfg,
            "verfall_mod": round(self._verfall_mod, 2),
            "schub_mod": round(self._schub_mod, 2),
            "zeitstempel": time.time(),
        }

    def schreibe_status(self, status: dict[str, Any]) -> None:
        """Schreibt Status atomar als JSON."""
        try:
            verzeichnis: Path = self._ausgabe_pfad.parent
            verzeichnis.mkdir(parents=True, exist_ok=True)
            tmp_fd, tmp_pfad_str = tempfile.mkstemp(
                dir=str(verzeichnis), suffix=".tmp"
            )
            tmp_pfad: Path = Path(tmp_pfad_str)
            try:
                with open(tmp_fd, "w") as f:
                    json.dump(status, f, ensure_ascii=False)
                tmp_pfad.rename(self._ausgabe_pfad)
            except Exception:
                tmp_pfad.unlink(missing_ok=True)
                raise
        except OSError as e:
            logger.warning("Status schreiben fehlgeschlagen: %s", e)

    def stopp_handler(self, signum: int, frame: Any) -> None:
        """Sauberes Beenden."""
        self._laeuft = False

    def run(self) -> None:
        """Hauptschleife des Dienstes."""
        signal.signal(signal.SIGINT, self.stopp_handler)
        signal.signal(signal.SIGTERM, self.stopp_handler)

        logger.info("Umgebungs-Dienst gestartet")
        logger.info("Ausgabe: %s", self._ausgabe_pfad)
        logger.info("Instanzen: %s", list(self._instanz_pfade.keys()))

        tick_nr: int = 0
        while self._laeuft:
            status = self.tick()
            self.schreibe_status(status)

            # Wachzeit alle 60s speichern
            if tick_nr % 60 == 0:
                self._speichere_wachzeit()

            tick_nr += 1
            if tick_nr % 300 == 0:
                phase, tage = self._aktuelle_phase()
                logger.info(
                    "Tick %d | Phase: %s (%.1f Tage) | Zone: %s | Rhythmus: %.2f",
                    tick_nr, phase, tage,
                    self._feedback_zone, status["rhythmus"],
                )

            time.sleep(TICK_INTERVALL)

        self._speichere_wachzeit()
        logger.info("Umgebungs-Dienst beendet.")


def main() -> None:
    """Startet den Umgebungs-Dienst."""
    parser = argparse.ArgumentParser(
        description="Genesis Umgebungs-Dienst (Gebärmutter)"
    )
    parser.add_argument(
        "--ausgabe", type=str,
        default="/opt/genesis/shared/umgebung_status.json",
        help="Pfad zur Ausgabedatei",
    )
    parser.add_argument(
        "--wachzeit", type=str,
        default="/var/lib/genesis/umgebung_wachzeit.txt",
        help="Pfad zur persistenten Wachzeit-Datei",
    )
    args = parser.parse_args()

    # Instanz-Pfade aus config_instances laden
    try:
        from vm.config_instances import INSTANCES
        instanz_pfade: dict[str, Path] = {}
        for name, cfg in INSTANCES.items():
            status_pfad = Path(cfg["shared_pfad"]) / "genesis_status.json"
            instanz_pfade[name] = status_pfad
    except ImportError:
        # Fallback: nur genesis-1
        instanz_pfade = {
            "genesis-1": Path("/opt/genesis/shared/genesis_status.json"),
        }

    dienst = UmgebungsDienst(
        ausgabe_pfad=Path(args.ausgabe),
        instanz_pfade=instanz_pfade,
        wachzeit_pfad=Path(args.wachzeit),
    )
    dienst.run()


if __name__ == "__main__":
    main()

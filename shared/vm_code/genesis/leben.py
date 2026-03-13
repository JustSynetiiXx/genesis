"""Leben — Der Hauptloop des Neugeborenen.

Start → Aufwachen → Wachphase (nur Fühlen) → Hauptloop → Schlaf-Signal → Ende.

Der Loop: Fühlen → Schmerz → Reflexe → Entscheiden → Handeln → Lernen → Wiederholen.
"""

from __future__ import annotations

import json
import logging
import signal
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from vm.config import (
    DB_VERZEICHNIS,
    HEARTBEAT_INTERVALL,
    LOOP_INTERVALL,
    SHARED_DIR,
    SIGNAL_DATEI,
    STATUS_DATEI,
    WACHPHASE_SEKUNDEN,
)
from vm.genesis.aktionen import AktionsManager
from vm.genesis.gedaechtnis import Heartbeat, KurzzeitGedaechtnis, LangzeitGedaechtnis
from vm.genesis.koerper import Koerper
from vm.genesis.lernen import Erfahrung, lerne, waehle_aktion
from vm.genesis.reflexe import pruefe as pruefe_reflexe
from vm.genesis.schmerz import berechne_schmerz, berechne_wohlbefinden, warnstufe
from vm.genesis import schlaf as schlaf_modul

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("genesis")


def _schreibe_status(status_pfad: Path, zustand: dict[str, Any],
                     schmerz: float, wohlbefinden: float,
                     stufe: str, aktion: str | None,
                     reflex_aktiv: bool, exploration: bool,
                     aktions_manager: AktionsManager,
                     erfahrungen_heute: int, erfahrungen_langzeit: int,
                     tode_gesamt: int, letzter_tod: dict[str, Any] | None,
                     wach_seit: int, modus: str) -> None:
    """Schreibt den Genesis-Status als JSON für das EKG.

    Atomares Schreiben: temp-Datei → rename.
    """
    status: dict[str, Any] = {
        "zeitstempel": time.time(),
        "zustand": zustand.get("kategorien", {}),
        "rohwerte": zustand.get("rohwerte", {}),
        "schmerz": round(schmerz, 4),
        "wohlbefinden": round(wohlbefinden, 4),
        "warnstufe": stufe,
        "aktion": aktion,
        "reflex_aktiv": reflex_aktiv,
        "exploration": exploration,
        "cache_mb": round(aktions_manager.cache.groesse_mb(), 2),
        "rechen_level": round(aktions_manager.rechen.level, 2),
        "abtastrate": aktions_manager.abtastrate.intervall,
        "erfahrungen_heute": erfahrungen_heute,
        "erfahrungen_langzeit": erfahrungen_langzeit,
        "tode_gesamt": tode_gesamt,
        "letzter_tod_zustand": (
            letzter_tod["zustand"] if letzter_tod else None
        ),
        "wach_seit": wach_seit,
        "modus": modus,
    }

    try:
        verzeichnis: Path = status_pfad.parent
        verzeichnis.mkdir(parents=True, exist_ok=True)
        # Atomares Schreiben
        tmp_fd, tmp_pfad_str = tempfile.mkstemp(
            dir=str(verzeichnis), suffix=".tmp"
        )
        tmp_pfad: Path = Path(tmp_pfad_str)
        try:
            with open(tmp_fd, "w") as f:
                json.dump(status, f, ensure_ascii=False)
            tmp_pfad.rename(status_pfad)
        except Exception:
            tmp_pfad.unlink(missing_ok=True)
            raise
    except OSError as e:
        logger.warning("Status schreiben fehlgeschlagen: %s", e)


def main(shared_dir: Path | None = None, db_dir: Path | None = None,
         max_loops: int | None = None) -> None:
    """Der Lebenszyklus des Neugeborenen.

    Args:
        shared_dir: Pfad zum Shared Directory (Standard: aus config).
        db_dir: Pfad zum Datenbank-Verzeichnis (Standard: aus config).
        max_loops: Maximale Anzahl Loops (None = unendlich, für Tests).
    """
    shared: Path = shared_dir or SHARED_DIR
    db: Path = db_dir or DB_VERZEICHNIS

    # Verzeichnisse erstellen
    db.mkdir(parents=True, exist_ok=True)
    shared.mkdir(parents=True, exist_ok=True)

    sensor_pfad: Path = shared / "sensoren.bin"
    signal_pfad: Path = shared / SIGNAL_DATEI
    status_pfad: Path = shared / STATUS_DATEI

    # --- Komponenten initialisieren ---
    koerper: Koerper = Koerper(sensor_pfad)
    aktionen: AktionsManager = AktionsManager()
    heartbeat_db: Heartbeat = Heartbeat(db / "heartbeat.db")
    langzeit_db: LangzeitGedaechtnis = LangzeitGedaechtnis(db / "langzeit.db")
    kurzzeit_db: KurzzeitGedaechtnis = KurzzeitGedaechtnis(db / "kurzzeit.db")

    # Letzter bekannter Zustand (für SIGTERM-Handler)
    letzter_zustand: dict[str, str] = {}
    letzter_schmerz: float = 0.0

    # --- SIGTERM Handler ---
    def notfall_handler(signum: int, frame: Any) -> None:
        """Letzter Atemzug. Heartbeat ohne Schlaf-Marker speichern."""
        logger.warning("SIGTERM empfangen — Notfall-Heartbeat wird geschrieben")
        try:
            heartbeat_db.aktualisiere(letzter_zustand, letzter_schmerz, schlaf_marker=False)
        except Exception:
            pass  # Letzte Chance, Fehler ignorieren
        aktionen.stoppe()
        sys.exit(1)

    signal.signal(signal.SIGTERM, notfall_handler)

    # --- 1. Aufwachen ---
    logger.info("Genesis erwacht...")
    aufwach_status: dict[str, Any] = schlaf_modul.aufwachen(langzeit_db, heartbeat_db)
    logger.info("Aufwach-Typ: %s", aufwach_status["typ"])
    if aufwach_status["typ"] == "tod":
        logger.warning(
            "Tod erkannt! Zeitlücke: %.1f Sekunden, letzter Schmerz: %.2f",
            aufwach_status["zeitluecke"],
            aufwach_status["letzter_schmerz"],
        )
    elif aufwach_status["typ"] == "erststart":
        logger.info("Erststart — kein vorheriger Zustand vorhanden.")

    # Worker-Thread starten
    aktionen.starte()

    vorheriger_schmerz: float = 0.0
    wach_seit: int = 0
    letzter_heartbeat: float = time.time()
    modus: str = "wachphase"

    try:
        # --- 2. Wachphase: Nur Fühlen, keine Aktionen ---
        logger.info("Wachphase: %d Sekunden nur Fühlen...", WACHPHASE_SEKUNDEN)
        for i in range(WACHPHASE_SEKUNDEN):
            if max_loops is not None and wach_seit >= max_loops:
                break

            zustand: dict[str, Any] = koerper.fuehle()
            schmerz_wert: float = berechne_schmerz(zustand["rohwerte"])
            stufe: str = warnstufe(schmerz_wert)
            wohlbefinden_wert: float = berechne_wohlbefinden(schmerz_wert, vorheriger_schmerz)

            # Reflexe feuern auch in der Wachphase
            gefeuerte_reflexe = pruefe_reflexe(zustand["rohwerte"])
            if gefeuerte_reflexe:
                for reflex in gefeuerte_reflexe:
                    aktionen.ausfuehren(reflex.aktion)
                    logger.info("Reflex (Wachphase): %s", reflex.name)

            # Heartbeat aktualisieren
            letzter_zustand = zustand.get("kategorien", {})
            letzter_schmerz = schmerz_wert
            jetzt: float = time.time()
            if jetzt - letzter_heartbeat >= HEARTBEAT_INTERVALL:
                heartbeat_db.aktualisiere(letzter_zustand, letzter_schmerz)
                letzter_heartbeat = jetzt

            # Status für EKG
            _schreibe_status(
                status_pfad, zustand, schmerz_wert, wohlbefinden_wert,
                stufe, None, bool(gefeuerte_reflexe), False,
                aktionen, kurzzeit_db.anzahl(), langzeit_db.anzahl_gelernt(),
                langzeit_db.anzahl_tode(), langzeit_db.letzter_tod(),
                wach_seit, modus,
            )

            vorheriger_schmerz = schmerz_wert
            wach_seit += 1
            time.sleep(LOOP_INTERVALL)

        # --- 3. Hauptloop ---
        modus = "normal"
        logger.info("Hauptloop gestartet.")
        loop_zaehler: int = 0

        while max_loops is None or wach_seit < max_loops:
            # Schlaf-Signal prüfen (am Anfang, damit sofort reagiert wird)
            if schlaf_modul.schlaf_signal_vorhanden(signal_pfad):
                logger.info("Schlaf-Signal erkannt — Einschlafen...")
                modus = "einschlafen"
                konsolidiert: int = schlaf_modul.einschlafen(
                    kurzzeit_db, langzeit_db, heartbeat_db,
                    letzter_zustand, letzter_schmerz, signal_pfad,
                )
                logger.info("Konsolidiert: %d Erfahrungen. Gute Nacht.", konsolidiert)
                break

            # Fühlen
            zustand = koerper.fuehle()
            schmerz_wert = berechne_schmerz(zustand["rohwerte"])
            wohlbefinden_wert = berechne_wohlbefinden(schmerz_wert, vorheriger_schmerz)
            stufe = warnstufe(schmerz_wert)

            # Reflexe prüfen (haben Vorrang)
            gefeuerte_reflexe = pruefe_reflexe(zustand["rohwerte"])
            reflex_aktiv: bool = bool(gefeuerte_reflexe)
            aktion_name: str | None = None
            exploration: bool = False

            if reflex_aktiv:
                for reflex in gefeuerte_reflexe:
                    aktionen.ausfuehren(reflex.aktion)
                    logger.debug("Reflex: %s → %s", reflex.name, reflex.aktion)
            else:
                # Entscheiden (Lernmechanismus)
                aktion_name, exploration = waehle_aktion(
                    zustand["kategorien"], schmerz_wert,
                    kurzzeit_db, langzeit_db,
                )

                # Handeln
                aktionen.ausfuehren(aktion_name)

            # Natürlicher Verfall (immer, auch bei Reflex)
            aktionen.natuerlicher_verfall()

            # Warten (basierend auf Abtastrate)
            time.sleep(aktionen.abtastrate.intervall)

            # Neuen Zustand messen (NACH der Aktion + Warten)
            neuer_zustand: dict[str, Any] = koerper.fuehle()
            neuer_schmerz: float = berechne_schmerz(neuer_zustand["rohwerte"])

            # Lernen (nur wenn kein Reflex)
            if not reflex_aktiv and aktion_name is not None:
                erfahrung: Erfahrung = Erfahrung(
                    zustand_vorher=zustand["kategorien"],
                    aktion=aktion_name,
                    zustand_nachher=neuer_zustand["kategorien"],
                    schmerz_vorher=schmerz_wert,
                    schmerz_nachher=neuer_schmerz,
                    schmerz_delta=neuer_schmerz - schmerz_wert,
                    zeitstempel=time.time(),
                )
                lerne(erfahrung, kurzzeit_db, langzeit_db)

            # Zustand für nächste Iteration und SIGTERM-Handler
            letzter_zustand = zustand.get("kategorien", {})
            letzter_schmerz = schmerz_wert

            # Heartbeat aktualisieren
            jetzt = time.time()
            if jetzt - letzter_heartbeat >= HEARTBEAT_INTERVALL:
                heartbeat_db.aktualisiere(letzter_zustand, letzter_schmerz)
                letzter_heartbeat = jetzt

            # Status für EKG
            _schreibe_status(
                status_pfad, zustand, schmerz_wert, wohlbefinden_wert,
                stufe, aktion_name, reflex_aktiv, exploration,
                aktionen, kurzzeit_db.anzahl(), langzeit_db.anzahl_gelernt(),
                langzeit_db.anzahl_tode(), langzeit_db.letzter_tod(),
                wach_seit, modus,
            )

            vorheriger_schmerz = schmerz_wert
            wach_seit += 1
            loop_zaehler += 1

            if loop_zaehler % 60 == 0:
                logger.info(
                    "Loop %d | Schmerz: %.2f | Aktion: %s | Cache: %.1f MB",
                    loop_zaehler, schmerz_wert,
                    aktion_name or "reflex",
                    aktionen.cache.groesse_mb(),
                )

    except KeyboardInterrupt:
        logger.info("Manueller Abbruch (Ctrl+C)")
    finally:
        # Aufräumen
        logger.info("Aufräumen...")
        heartbeat_db.aktualisiere(letzter_zustand, letzter_schmerz, schlaf_marker=False)
        aktionen.stoppe()
        heartbeat_db.schliesse()
        langzeit_db.schliesse()
        kurzzeit_db.schliesse()
        logger.info("Genesis beendet. Wach seit %d Iterationen.", wach_seit)


if __name__ == "__main__":
    main()

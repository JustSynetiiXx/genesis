"""Leben — Der Hauptloop des Neugeborenen.

Start → Aufwachen → Wachphase (nur Fühlen) → Hauptloop → Schlaf-Signal → Ende.

Der Loop: Fühlen → Schmerz → Reflexe → Entscheiden → Handeln → Lernen → Wiederholen.

Umgebungsdaten werden extern aus umgebung_status.json gelesen (geschrieben vom
Umgebungs-Dienst). Unterstützt mehrere Instanzen via --instance Parameter.
"""

from __future__ import annotations

import argparse
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

LOG_DATEI_NAME: str = "genesis_log.txt"
LOG_MAX_ZEILEN: int = 500
from vm.genesis.aktionen import ALLE_AKTION_NAMEN, AktionsManager
from vm.genesis.gedaechtnis import Heartbeat, KurzzeitGedaechtnis, LangzeitGedaechtnis
from vm.genesis.koerper import Koerper
from vm.genesis.lernen import Erfahrung, lerne, lerne_aus_reflex, waehle_aktion
from vm.genesis.reflexe import pruefe as pruefe_reflexe
from vm.genesis.schmerz import berechne_schmerz, berechne_schmerz_details, berechne_wohlbefinden, warnstufe
from vm.genesis import schlaf as schlaf_modul

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("genesis")


# --- Umgebungs-Status lesen (extern vom Umgebungs-Dienst) ---

_UMGEBUNG_FALLBACK: dict[str, Any] = {
    "rhythmus": 0.5,
    "rhythmus_kategorie": "aktiv",
    "verfall_modifikator": 0.2,
    "reiz_aktiv": None,
    "reiz_staerke": 0.0,
    "reiz_verbleibend": 0,
    "feedback_zone": "normal_zone",
    "phase": "embryo",
    "phase_tag": 0.0,
    "naechster_schub_in": 50,
    "schub_aktiv": False,
    "schub_menge": 0.0,
    "features": {
        "rhythmus_aktiv": False,
        "variable_naehrung": False,
        "reize_aktiv": False,
        "feedback_aktiv": False,
        "externe_aktionen": False,
        "erlaubte_reize": [],
        "zusatz_aktionen": [],
    },
    "verfall_mod": 1.0,
    "schub_mod": 1.0,
    "zeitstempel": 0,
}


def _lese_umgebung(pfad: Path) -> dict[str, Any]:
    """Liest den aktuellen Umgebungs-Status aus der JSON-Datei.

    Args:
        pfad: Pfad zur umgebung_status.json.

    Returns:
        Umgebungs-Daten oder Fallback-Werte wenn nicht lesbar.
    """
    try:
        daten = json.loads(pfad.read_bytes())
        alter: float = time.time() - daten.get("zeitstempel", 0)
        if alter > 30:
            logger.warning("Umgebungs-Daten veraltet (%.0fs)", alter)
        return daten
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return dict(_UMGEBUNG_FALLBACK)


def _wende_reiz_auf_rohwerte_an(rohwerte: dict[str, float],
                                 umg: dict[str, Any]) -> dict[str, float]:
    """Wendet den Umgebungs-Reiz auf die Sensor-Rohwerte an.

    Args:
        rohwerte: Sensor-Rohwerte.
        umg: Umgebungs-Daten aus umgebung_status.json.

    Returns:
        Modifizierte Rohwerte.
    """
    reiz_typ = umg.get("reiz_aktiv")
    if reiz_typ is None:
        return rohwerte

    staerke: float = umg.get("reiz_staerke", 0.0)
    if staerke <= 0:
        return rohwerte

    ergebnis = dict(rohwerte)
    if reiz_typ == "vibration":
        ergebnis["luefter_rpm"] = ergebnis.get("luefter_rpm", 1000.0) + staerke
    elif reiz_typ == "waerme":
        ergebnis["cpu_temp_tctl"] = ergebnis.get("cpu_temp_tctl", 50.0) + staerke
        ergebnis["cpu_temp_tccd1"] = ergebnis.get("cpu_temp_tccd1", 50.0) + staerke
    elif reiz_typ == "druck":
        frei: float = ergebnis.get("host_ram_frei_mb", 16000.0)
        ergebnis["host_ram_frei_mb"] = max(0.0, frei - staerke)

    return ergebnis


def _umgebung_sensoren_hinzufuegen(rohwerte: dict[str, float],
                                     umg: dict[str, Any]) -> None:
    """Fügt Umgebungs-Sensoren zu den Rohwerten hinzu (in-place).

    Args:
        rohwerte: Sensor-Rohwerte (wird modifiziert).
        umg: Umgebungs-Daten.
    """
    rohwerte["umgebung_rhythmus"] = umg.get("rhythmus", 0.5)
    if umg.get("reiz_aktiv") is not None:
        rohwerte["reiz_aktiv"] = 1.0
        rohwerte["reiz_typ"] = umg["reiz_aktiv"]
    else:
        rohwerte["reiz_aktiv"] = 0.0
        rohwerte["reiz_typ"] = "keiner"


class _DateiLogHandler(logging.Handler):
    """Schreibt INFO-Logs in eine Datei, begrenzt auf LOG_MAX_ZEILEN."""

    def __init__(self, pfad: Path) -> None:
        super().__init__(level=logging.INFO)
        self._pfad: Path = pfad
        self._pfad.parent.mkdir(parents=True, exist_ok=True)
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            zeile: str = self.format(record) + "\n"
            # Append
            with open(self._pfad, "a", encoding="utf-8") as f:
                f.write(zeile)
            # Kürzen wenn zu lang
            self._kuerze()
        except Exception:
            self.handleError(record)

    def _kuerze(self) -> None:
        """Hält die Datei auf maximal LOG_MAX_ZEILEN."""
        try:
            zeilen: list[str] = self._pfad.read_text(encoding="utf-8").splitlines()
            if len(zeilen) > LOG_MAX_ZEILEN:
                self._pfad.write_text(
                    "\n".join(zeilen[-LOG_MAX_ZEILEN:]) + "\n",
                    encoding="utf-8",
                )
        except OSError:
            pass


def _schreibe_status(status_pfad: Path, zustand: dict[str, Any],
                     schmerz: float, wohlbefinden: float,
                     stufe: str, aktion: str | None,
                     reflex_aktiv: bool, exploration: bool,
                     aktions_manager: AktionsManager,
                     erfahrungen_heute: int, erfahrungen_langzeit: int,
                     tode_gesamt: int, letzter_tod: dict[str, Any] | None,
                     wach_seit: int, modus: str,
                     schmerz_details: dict[str, Any] | None = None,
                     umgebung_daten: dict[str, Any] | None = None) -> None:
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
        "schmerz_details": schmerz_details,
        "umgebung": umgebung_daten,
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
         max_loops: int | None = None,
         umgebung_pfad: Path | None = None) -> None:
    """Der Lebenszyklus des Neugeborenen.

    Args:
        shared_dir: Pfad zum Shared Directory (Standard: aus config).
        db_dir: Pfad zum Datenbank-Verzeichnis (Standard: aus config).
        max_loops: Maximale Anzahl Loops (None = unendlich, für Tests).
        umgebung_pfad: Pfad zur umgebung_status.json (Standard: aus config_instances).
    """
    shared: Path = shared_dir or SHARED_DIR
    db: Path = db_dir or DB_VERZEICHNIS

    # Umgebungs-Status-Pfad bestimmen
    if umgebung_pfad is None:
        try:
            from vm.config_instances import UMGEBUNG_STATUS_PFAD
            umgebung_pfad = UMGEBUNG_STATUS_PFAD
        except ImportError:
            umgebung_pfad = shared / "umgebung_status.json"

    # Verzeichnisse erstellen
    db.mkdir(parents=True, exist_ok=True)
    shared.mkdir(parents=True, exist_ok=True)

    sensor_pfad: Path = shared / "sensoren.bin"
    signal_pfad: Path = shared / SIGNAL_DATEI
    status_pfad: Path = shared / STATUS_DATEI
    log_pfad: Path = shared / LOG_DATEI_NAME

    # Log-Handler für Datei registrieren
    datei_handler: _DateiLogHandler = _DateiLogHandler(log_pfad)
    logger.addHandler(datei_handler)

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

    # Letzte bewusste Aktion tracken (für Reflex-Lernen)
    letzte_bewusste_aktion: str | None = None
    zustand_bei_letzter_entscheidung: dict[str, str] = {}

    try:
        # --- 2. Wachphase: Nur Fühlen, keine Aktionen ---
        logger.info("Wachphase: %d Sekunden nur Fühlen...", WACHPHASE_SEKUNDEN)

        # Umgebungs-Info beim Start loggen
        umg_start: dict[str, Any] = _lese_umgebung(umgebung_pfad)
        logger.info("Entwicklungsphase: %s (%.1f Wachtage)",
                     umg_start.get("phase", "unbekannt"),
                     umg_start.get("phase_tag", 0.0))

        for i in range(WACHPHASE_SEKUNDEN):
            if max_loops is not None and wach_seit >= max_loops:
                break

            # Umgebung lesen (extern vom Umgebungs-Dienst)
            umg_daten: dict[str, Any] = _lese_umgebung(umgebung_pfad)

            zustand: dict[str, Any] = koerper.fuehle()

            # Reize auf Rohwerte anwenden
            zustand["rohwerte"] = _wende_reiz_auf_rohwerte_an(
                zustand["rohwerte"], umg_daten
            )
            # Umgebungssensoren hinzufügen
            _umgebung_sensoren_hinzufuegen(zustand["rohwerte"], umg_daten)

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
            details = berechne_schmerz_details(zustand["rohwerte"])
            _schreibe_status(
                status_pfad, zustand, schmerz_wert, wohlbefinden_wert,
                stufe, None, bool(gefeuerte_reflexe), False,
                aktionen, kurzzeit_db.anzahl(), langzeit_db.anzahl_gelernt(),
                langzeit_db.anzahl_tode(), langzeit_db.letzter_tod(),
                wach_seit, modus,
                schmerz_details=details,
                umgebung_daten=umg_daten,
            )

            vorheriger_schmerz = schmerz_wert
            wach_seit += 1
            time.sleep(LOOP_INTERVALL)

        # --- 3. Hauptloop ---
        modus = "normal"
        logger.info("Hauptloop gestartet.")
        loop_zaehler: int = 0

        # Aktionsliste dynamisch basierend auf Phase
        import vm.genesis.aktionen as aktionen_modul

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

            # Umgebung lesen (extern vom Umgebungs-Dienst)
            umg_daten = _lese_umgebung(umgebung_pfad)

            # Fühlen
            zustand = koerper.fuehle()

            # Reize auf Rohwerte anwenden
            zustand["rohwerte"] = _wende_reiz_auf_rohwerte_an(
                zustand["rohwerte"], umg_daten
            )
            # Umgebungssensoren hinzufügen
            _umgebung_sensoren_hinzufuegen(zustand["rohwerte"], umg_daten)

            # Nährstoff-Schub: Cache reduzieren
            if umg_daten.get("schub_aktiv") and umg_daten.get("schub_menge", 0) > 0:
                reduziert: float = aktionen.cache.reduziere_um(umg_daten["schub_menge"])
                if reduziert > 0:
                    logger.debug("Nährstoff-Schub: %.1f MB Cache reduziert", reduziert)

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

                # Aus Reflex lernen: Die letzte bewusste Aktion war nicht gut genug
                if letzte_bewusste_aktion is not None:
                    lerne_aus_reflex(
                        zustand_bei_letzter_entscheidung,
                        letzte_bewusste_aktion,
                        zustand["kategorien"],
                        schmerz_wert,
                        kurzzeit_db,
                        langzeit_db,
                    )
                    logger.debug(
                        "Reflex-Lernen: %s in Zustand %s war schlecht (Schmerz: %.2f)",
                        letzte_bewusste_aktion,
                        zustand_bei_letzter_entscheidung,
                        schmerz_wert,
                    )
            else:
                # Verfügbare Aktionen basierend auf Entwicklungsphase
                features = umg_daten.get("features", {})
                zusatz: list[str] = features.get("zusatz_aktionen", [])
                verfuegbar: list[str] = list(aktionen_modul.ALLE_AKTION_NAMEN)
                verfuegbar.extend(zusatz)

                # Entscheiden (Lernmechanismus)
                aktion_name, exploration = waehle_aktion(
                    zustand["kategorien"], schmerz_wert,
                    kurzzeit_db, langzeit_db,
                    verfuegbare_aktionen=verfuegbar,
                )

                # Handeln
                aktionen.ausfuehren(aktion_name)

                # Externe Aktionen loggen (Umgebung reagiert nicht direkt,
                # aber Genesis lernt trotzdem aus dem Ergebnis)
                if aktion_name in ("signal_senden", "umgebung_erkunden",
                                   "rhythmus_anpassen"):
                    logger.debug("Externe Aktion: %s", aktion_name)

                # Bewusste Aktion merken (für Reflex-Lernen)
                letzte_bewusste_aktion = aktion_name
                zustand_bei_letzter_entscheidung = zustand["kategorien"]

            # Natürlicher Verfall (variabel durch Umgebungs-Dienst)
            verfall: float = umg_daten.get("verfall_modifikator", 0.2)
            aktionen.natuerlicher_verfall(verfall)

            # Rhythmus-Anpassung Bonus: Verfall kurz senken bei Erfolg
            rhythmus: float = umg_daten.get("rhythmus", 0.5)
            if aktion_name == "rhythmus_anpassen" and rhythmus > 0.6:
                aktionen.cache.reduziere_um(verfall * 3)

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
            details = berechne_schmerz_details(zustand["rohwerte"])
            _schreibe_status(
                status_pfad, zustand, schmerz_wert, wohlbefinden_wert,
                stufe, aktion_name, reflex_aktiv, exploration,
                aktionen, kurzzeit_db.anzahl(), langzeit_db.anzahl_gelernt(),
                langzeit_db.anzahl_tode(), langzeit_db.letzter_tod(),
                wach_seit, modus,
                schmerz_details=details,
                umgebung_daten=umg_daten,
            )

            vorheriger_schmerz = schmerz_wert
            wach_seit += 1
            loop_zaehler += 1

            if loop_zaehler % 60 == 0:
                phase_info: str = umg_daten.get("phase", "unbekannt")
                logger.info(
                    "Loop %d | Schmerz: %.2f | Aktion: %s | Cache: %.1f MB | Phase: %s",
                    loop_zaehler, schmerz_wert,
                    aktion_name or "reflex",
                    aktionen.cache.groesse_mb(),
                    phase_info,
                )

    except KeyboardInterrupt:
        logger.info("Manueller Abbruch (Ctrl+C)")
    finally:
        # Aufräumen
        logger.info("Aufräumen...")
        # Schlaf-Marker NUR überschreiben wenn wir NICHT sauber eingeschlafen sind
        # (einschlafen() hat den Marker bereits korrekt auf True gesetzt)
        if modus != "einschlafen":
            heartbeat_db.aktualisiere(letzter_zustand, letzter_schmerz, schlaf_marker=False)
        aktionen.stoppe()
        heartbeat_db.schliesse()
        langzeit_db.schliesse()
        kurzzeit_db.schliesse()
        logger.info("Genesis beendet. Wach seit %d Iterationen.", wach_seit)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genesis — Digitales Leben")
    parser.add_argument(
        "--instance", type=str, default="genesis-1",
        help="Name der Instanz (z.B. genesis-1, genesis-2)",
    )
    args = parser.parse_args()

    # Pfade aus config_instances laden
    try:
        from vm.config_instances import get_instanz_pfade, UMGEBUNG_STATUS_PFAD
        db_pfad, shared_pfad = get_instanz_pfade(args.instance)
        logger.info("Instanz: %s (DB: %s, Shared: %s)", args.instance, db_pfad, shared_pfad)
        main(shared_dir=shared_pfad, db_dir=db_pfad, umgebung_pfad=UMGEBUNG_STATUS_PFAD)
    except ImportError:
        # Fallback ohne config_instances
        main()
    except KeyError as e:
        logger.error("Instanz-Fehler: %s", e)
        sys.exit(1)

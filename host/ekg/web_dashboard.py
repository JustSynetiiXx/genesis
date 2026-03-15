"""Web-Dashboard für Genesis — Mobile-optimiert, Multi-Page, Multi-Instance.

Zeigt Genesis-Status im Browser an. Liest nur, beeinflusst Genesis nicht.
Unterstützt mehrere Genesis-Instanzen via ?instance= Query-Parameter.

Starten:
    python3 -m host.ekg.web_dashboard
    → http://localhost:8080

Keine externen Dependencies — nur Python stdlib.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, date
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, parse_qs

# Pfade
_PROJEKT_WURZEL: Path = Path(__file__).resolve().parent.parent.parent
_STATUS_DATEI: Path = _PROJEKT_WURZEL / "shared" / "genesis_status.json"
_SENSOR_DATEI: Path = _PROJEKT_WURZEL / "shared" / "sensoren.bin"
_LESER_PFAD: Path = _PROJEKT_WURZEL / "shared" / "leser.py"
_LOG_DATEI: Path = _PROJEKT_WURZEL / "shared" / "genesis_log.txt"
_LOG_DATEI_PROD: Path = Path("/opt/genesis/shared/genesis_log.txt")
_LOG_VERZEICHNIS: Path = Path("/opt/genesis/shared")
_SIGNAL_DATEI: Path = _PROJEKT_WURZEL / "shared" / "signal.txt"
_TEST_MARKER_DATEI: Path = Path("/opt/genesis/shared/test_marker.txt")
_TEST_MARKER_LOKAL: Path = _PROJEKT_WURZEL / "shared" / "test_marker.txt"
_SCRIPTS_DIR: Path = _PROJEKT_WURZEL / "scripts"
_UMGEBUNG_STATUS_DATEI: Path = Path("/opt/genesis/shared/umgebung_status.json")

# DB-Pfade (Read-Only Zugriff!)
_LANGZEIT_DB: Path = Path("/var/lib/genesis/langzeit.db")
_KURZZEIT_DB: Path = Path("/var/lib/genesis/kurzzeit.db")


# --- Multi-Instance Support ---

def _lade_instanzen() -> dict[str, dict[str, Any]]:
    """Lädt Instanz-Konfigurationen."""
    try:
        from vm.config_instances import INSTANCES
        return INSTANCES
    except ImportError:
        return {
            "genesis-1": {
                "db_pfad": "/var/lib/genesis/",
                "shared_pfad": "/opt/genesis/shared/",
                "beschreibung": "Standard-Instanz",
            }
        }


def _instanz_pfade(instanz: str) -> tuple[Path, Path, Path, Path, Path]:
    """Gibt (status_datei, log_datei, langzeit_db, kurzzeit_db, signal_datei) für eine Instanz zurück."""
    instanzen = _lade_instanzen()
    if instanz not in instanzen:
        instanz = "genesis-1"
    cfg = instanzen[instanz]
    shared = Path(cfg["shared_pfad"])
    db = Path(cfg["db_pfad"])
    return (
        shared / "genesis_status.json",
        shared / "genesis_log.txt",
        db / "langzeit.db",
        db / "kurzzeit.db",
        shared / "signal.txt",
    )


def _api_instances() -> dict[str, Any]:
    """Gibt alle Instanzen mit ihrem aktuellen Status zurück."""
    instanzen = _lade_instanzen()
    ergebnis: list[dict[str, Any]] = []
    for name, cfg in instanzen.items():
        shared = Path(cfg["shared_pfad"])
        status_pfad = shared / "genesis_status.json"
        # Status lesen
        status_text = "tot"
        schmerz = 0.0
        phase = "?"
        wach_seit = 0
        try:
            daten = json.loads(status_pfad.read_bytes())
            alter = time.time() - daten.get("zeitstempel", 0)
            schmerz = daten.get("schmerz", 0.0)
            umg = daten.get("umgebung") or {}
            phase = umg.get("phase", "?")
            wach_seit = daten.get("wach_seit", 0)
            if alter < 5:
                status_text = "lebt"
            elif alter < 30:
                status_text = "schlaeft"
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        ergebnis.append({
            "name": name,
            "beschreibung": cfg.get("beschreibung", ""),
            "status": status_text,
            "schmerz": round(schmerz, 4),
            "phase": phase,
            "wach_seit": wach_seit,
        })
    return {"instanzen": ergebnis}

# Sensor-Leser importieren
_leser_modul: Any = None


def _lade_leser() -> Any:
    """Lädt den Sensor-Leser aus dem shared-Verzeichnis."""
    global _leser_modul
    if _leser_modul is not None:
        return _leser_modul
    spec = importlib.util.spec_from_file_location("shared.leser", _LESER_PFAD)
    if spec is None or spec.loader is None:
        return None
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    _leser_modul = modul
    return modul


def _lese_genesis_status(instanz: str | None = None) -> dict[str, Any] | None:
    """Liest genesis_status.json atomar."""
    pfad = _STATUS_DATEI
    if instanz:
        pfad = _instanz_pfade(instanz)[0]
    try:
        return json.loads(pfad.read_bytes())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _lese_sensoren() -> dict[str, Any] | None:
    """Liest sensoren.bin über den Leser."""
    leser = _lade_leser()
    if leser is None:
        return None
    return leser.lese_sensoren(_SENSOR_DATEI)


def _lese_logs(n: int = 50, instanz: str | None = None) -> list[str]:
    """Liest die letzten n Log-Zeilen aus genesis_log.txt."""
    pfad = _LOG_DATEI
    if instanz:
        pfad = _instanz_pfade(instanz)[1]
    try:
        zeilen: list[str] = pfad.read_text(encoding="utf-8").splitlines()
        # Neueste zuerst
        return list(reversed(zeilen[-n:]))
    except (FileNotFoundError, OSError):
        return []


def _schreibe_signal(signal_text: str, instanz: str | None = None) -> None:
    """Schreibt ein Signal in signal.txt."""
    pfad = _SIGNAL_DATEI
    if instanz:
        pfad = _instanz_pfade(instanz)[4]
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(signal_text + "\n", encoding="utf-8")


def _genesis_lebt(instanz: str | None = None) -> str:
    """Prüft ob Genesis lebt. Gibt 'lebt', 'schlaeft' oder 'tot' zurück."""
    # Schlaf-Signal prüfen
    signal_pfad = _SIGNAL_DATEI
    if instanz:
        signal_pfad = _instanz_pfade(instanz)[4]
    try:
        signal_inhalt: str = signal_pfad.read_text(encoding="utf-8").strip()
        if signal_inhalt.startswith("SLEEP"):
            return "schlaeft"
    except (FileNotFoundError, OSError):
        pass

    # Status-Zeitstempel prüfen
    status: dict[str, Any] | None = _lese_genesis_status(instanz)
    if status is None:
        return "tot"
    alter: float = time.time() - status.get("zeitstempel", 0)
    if alter < 5:
        return "lebt"
    if alter < 30:
        return "schlaeft"
    return "tot"


def _api_daten(instanz: str | None = None) -> dict[str, Any]:
    """Kombiniert Genesis-Status und Sensordaten für die API."""
    status = _lese_genesis_status(instanz)
    sensoren = _lese_sensoren()
    return {
        "genesis": status,
        "sensoren": sensoren,
        "genesis_status": _genesis_lebt(instanz),
        "instanz": instanz or "genesis-1",
    }


# --- SQLite Read-Only Helpers ---

def _db_readonly(pfad: Path) -> sqlite3.Connection | None:
    """Öffnet eine SQLite-DB read-only. Gibt None zurück wenn nicht vorhanden."""
    if not pfad.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.OperationalError:
        return None


def _api_langzeit(instanz: str | None = None) -> dict[str, Any]:
    """Liest ALLE Einträge aus langzeit.db Tabelle 'gelernt'."""
    db_pfad = _LANGZEIT_DB
    if instanz:
        db_pfad = _instanz_pfade(instanz)[2]
    conn = _db_readonly(db_pfad)
    if conn is None:
        return {"eintraege": [], "gesamt": 0}
    try:
        cursor = conn.execute(
            "SELECT zustand, aktion, durchschnitt_delta, anzahl, letzte_erfahrung "
            "FROM gelernt ORDER BY anzahl DESC"
        )
        eintraege: list[dict[str, Any]] = []
        for row in cursor.fetchall():
            eintraege.append({
                "zustand": json.loads(row["zustand"]),
                "aktion": row["aktion"],
                "durchschnitt_delta": row["durchschnitt_delta"],
                "anzahl": row["anzahl"],
                "letzte_erfahrung": row["letzte_erfahrung"],
            })
        return {"eintraege": eintraege, "gesamt": len(eintraege)}
    except sqlite3.OperationalError:
        return {"eintraege": [], "gesamt": 0}
    finally:
        conn.close()


def _api_tode(instanz: str | None = None) -> dict[str, Any]:
    """Liest ALLE Einträge aus langzeit.db Tabelle 'tode'."""
    db_pfad = _LANGZEIT_DB
    if instanz:
        db_pfad = _instanz_pfade(instanz)[2]
    conn = _db_readonly(db_pfad)
    if conn is None:
        return {"tode": [], "gesamt_tode": 0, "gesamt_schlaf": 0}
    try:
        cursor = conn.execute(
            "SELECT zeitstempel_tod, zeitstempel_aufwachen, letzter_zustand, "
            "letzter_schmerz, war_schlaf FROM tode ORDER BY zeitstempel_tod DESC"
        )
        tode: list[dict[str, Any]] = []
        gesamt_tode: int = 0
        gesamt_schlaf: int = 0
        for row in cursor.fetchall():
            war_schlaf: bool = bool(row["war_schlaf"])
            tode.append({
                "zeitstempel_tod": row["zeitstempel_tod"],
                "zeitstempel_aufwachen": row["zeitstempel_aufwachen"],
                "letzter_zustand": json.loads(row["letzter_zustand"]),
                "letzter_schmerz": row["letzter_schmerz"],
                "war_schlaf": war_schlaf,
            })
            if war_schlaf:
                gesamt_schlaf += 1
            else:
                gesamt_tode += 1
        return {"tode": tode, "gesamt_tode": gesamt_tode, "gesamt_schlaf": gesamt_schlaf}
    except sqlite3.OperationalError:
        return {"tode": [], "gesamt_tode": 0, "gesamt_schlaf": 0}
    finally:
        conn.close()


def _api_kurzzeit_stats(instanz: str | None = None) -> dict[str, Any]:
    """Berechnet Aktions-Statistiken aus kurzzeit.db."""
    db_pfad = _KURZZEIT_DB
    if instanz:
        db_pfad = _instanz_pfade(instanz)[3]
    conn = _db_readonly(db_pfad)
    if conn is None:
        return {"aktionen": {}, "gesamt": 0}
    try:
        cursor = conn.execute(
            "SELECT aktion, COUNT(*) as anzahl, AVG(schmerz_delta) as avg_delta "
            "FROM erfahrungen GROUP BY aktion ORDER BY anzahl DESC"
        )
        aktionen: dict[str, dict[str, Any]] = {}
        gesamt: int = 0
        for row in cursor.fetchall():
            aktionen[row["aktion"]] = {
                "anzahl": row["anzahl"],
                "avg_delta": round(row["avg_delta"], 5),
            }
            gesamt += row["anzahl"]
        return {"aktionen": aktionen, "gesamt": gesamt}
    except sqlite3.OperationalError:
        return {"aktionen": {}, "gesamt": 0}
    finally:
        conn.close()


def _api_phasen(instanz: str | None = None) -> dict[str, Any]:
    """Berechnet den Phasen-Status basierend auf verfügbaren Daten."""
    langzeit = _api_langzeit(instanz)
    tode = _api_tode(instanz)
    kurzzeit = _api_kurzzeit_stats(instanz)
    status = _lese_genesis_status(instanz)

    # Phase 2: Beobachtung
    phase2: dict[str, Any] = {
        "tode_gesamt": tode["gesamt_tode"],
        "schlaf_gesamt": tode["gesamt_schlaf"],
        "langzeit_eintraege": langzeit["gesamt"],
        "kurzzeit_erfahrungen": kurzzeit["gesamt"],
        "status": "aktiv",
    }

    # Phase 3: Klon-Test — braucht Baseline-Daten
    hat_baseline: bool = langzeit["gesamt"] >= 10 and tode["gesamt_tode"] >= 1
    phase3: dict[str, Any] = {
        "baseline_vorhanden": hat_baseline,
        "status": "bereit" if hat_baseline else "nicht_bereit",
    }

    # Phase 4: Erweiterter Laufstall — Kriterien prüfen
    # Muster die nicht nur Reflexe sind: Langzeit-Einträge mit negativem Delta
    muster_ohne_reflex: int = sum(
        1 for e in langzeit["eintraege"]
        if e["durchschnitt_delta"] < -0.01 and e["anzahl"] >= 3
    )
    # Aus Tod gelernt: Gibt es Tode UND hat sich Verhalten danach geändert?
    aus_tod_gelernt: bool = tode["gesamt_tode"] >= 2  # Vereinfachte Heuristik
    phase4: dict[str, Any] = {
        "muster_ohne_reflex": muster_ohne_reflex,
        "aus_tod_gelernt": aus_tod_gelernt,
        "stresstest_ueberlebt": False,  # Manuell zu bewerten
        "status": "nicht_erreicht",
    }
    if muster_ohne_reflex >= 3 and aus_tod_gelernt:
        phase4["status"] = "teilweise"

    # Phase 5: Laptop
    phase5: dict[str, Any] = {
        "status": "nicht_erreicht",
        "voraussetzungen": "Phase 4 abgeschlossen",
    }

    return {
        "phase2": phase2,
        "phase3": phase3,
        "phase4": phase4,
        "phase5": phase5,
    }


def _lade_config() -> dict[str, Any]:
    """Lädt Config-Werte aus vm.config."""
    try:
        from vm import config as cfg
        return {
            "loop_intervall": cfg.LOOP_INTERVALL,
            "wachphase_sekunden": cfg.WACHPHASE_SEKUNDEN,
            "verfall_mb_pro_tick": cfg.VERFALL_MB_PRO_TICK,
            "lernschwelle_stark": cfg.LERNSCHWELLE_STARK,
            "lernschwelle_mittel": cfg.LERNSCHWELLE_MITTEL,
            "wiederholungen_mittel": cfg.WIEDERHOLUNGEN_MITTEL,
            "wiederholungen_schwach": cfg.WIEDERHOLUNGEN_SCHWACH,
            "cache_max_mb": cfg.CACHE_MAX_MB,
            "abtastrate_min": cfg.ABTASTRATE_MIN,
            "abtastrate_max": cfg.ABTASTRATE_MAX,
            "rechen_stufe": cfg.RECHEN_STUFE,
            "pause_min_sekunden": cfg.PAUSE_MIN_SEKUNDEN,
            "pause_max_sekunden": cfg.PAUSE_MAX_SEKUNDEN,
        }
    except ImportError:
        return {"fehler": "vm.config nicht verfügbar"}


def _api_umgebung(instanz: str | None = None) -> dict[str, Any]:
    """Liest Umgebungsdaten aus dem Genesis-Status oder umgebung_status.json."""
    # Zuerst aus Genesis-Status lesen (hat instanz-spezifische Daten)
    status = _lese_genesis_status(instanz)
    if status is not None:
        umg = status.get("umgebung")
        if umg is not None:
            return umg
    # Fallback: Direkt aus umgebung_status.json lesen
    try:
        return json.loads(_UMGEBUNG_STATUS_DATEI.read_bytes())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"fehler": "Keine Umgebungsdaten verfügbar"}


def _api_export(instanz: str | None = None) -> dict[str, Any]:
    """Komplett-Dump aller Daten als JSON für externe Analyse."""
    tode = _api_tode(instanz)
    return {
        "export_zeitstempel": datetime.now().isoformat(),
        "genesis_version": "Phase 2 — Beobachtung",
        "instanz": instanz or "genesis-1",
        "aktueller_status": _api_daten(instanz),
        "langzeit_gedaechtnis": _api_langzeit(instanz),
        "tod_historie": {
            "ereignisse": tode["tode"],
            "gesamt_tode": tode["gesamt_tode"],
            "gesamt_schlaf": tode["gesamt_schlaf"],
        },
        "kurzzeit_statistik": _api_kurzzeit_stats(instanz),
        "phasen_status": _api_phasen(instanz),
        "config": _lade_config(),
        "logs": _lese_logs(200, instanz),
    }


def _api_logs_archiv() -> dict[str, Any]:
    """Listet alle archivierten Log-Dateien auf."""
    archive: list[dict[str, Any]] = []
    try:
        for datei in sorted(_LOG_VERZEICHNIS.glob("genesis_log_????-??-??.txt"), reverse=True):
            datum = datei.stem.replace("genesis_log_", "")
            groesse_kb = datei.stat().st_size / 1024
            archive.append({
                "datum": datum,
                "datei": datei.name,
                "groesse_kb": round(groesse_kb, 1),
            })
    except OSError:
        pass
    return {"archive": archive}


# --- Log-Rotation ---

_letztes_rotations_datum: str = ""


def _rotiere_logs() -> None:
    """Rotiert genesis_log.txt zu genesis_log_YYYY-MM-DD.txt bei Mitternacht."""
    global _letztes_rotations_datum
    heute = date.today().isoformat()
    if _letztes_rotations_datum == heute:
        return
    _letztes_rotations_datum = heute
    # Prüfe ob es eine Log-Datei gibt die rotiert werden muss
    log_pfad = _LOG_DATEI_PROD
    if not log_pfad.exists() or log_pfad.stat().st_size == 0:
        return
    # Datum der letzten Änderung der Log-Datei
    from datetime import date as date_cls
    letztes_datum = date_cls.fromtimestamp(log_pfad.stat().st_mtime)
    if letztes_datum >= date.today():
        return  # Log ist von heute, noch nicht rotieren
    archiv_name = f"genesis_log_{letztes_datum.isoformat()}.txt"
    archiv_pfad = _LOG_VERZEICHNIS / archiv_name
    if archiv_pfad.exists():
        return  # Archiv für diesen Tag existiert bereits
    try:
        log_pfad.rename(archiv_pfad)
        log_pfad.write_text("", encoding="utf-8")
    except OSError:
        pass


def _log_rotation_thread() -> None:
    """Hintergrund-Thread der jede Minute auf Log-Rotation prüft."""
    while True:
        try:
            _rotiere_logs()
        except Exception:
            pass
        time.sleep(60)


# --- Stresstest-Management ---

_aktiver_test_prozess: subprocess.Popen[bytes] | None = None
_aktiver_test_typ: str = ""
_aktiver_test_start: float = 0.0
_aktiver_test_dauer: int = 0


def _test_marker_pfad() -> Path:
    """Gibt den Pfad zur test_marker.txt zurück (Prod oder lokal)."""
    if _TEST_MARKER_DATEI.parent.exists():
        return _TEST_MARKER_DATEI
    return _TEST_MARKER_LOKAL


def _api_test_status() -> dict[str, Any]:
    """Gibt zurück ob gerade ein Test läuft."""
    global _aktiver_test_prozess, _aktiver_test_typ, _aktiver_test_start, _aktiver_test_dauer
    if _aktiver_test_prozess is not None:
        if _aktiver_test_prozess.poll() is not None:
            # Prozess ist beendet
            _aktiver_test_prozess = None
            _aktiver_test_typ = ""
            _aktiver_test_start = 0.0
            _aktiver_test_dauer = 0
            return {"aktiv": False}
        vergangen: float = time.time() - _aktiver_test_start
        verbleibend: float = max(0, _aktiver_test_dauer - vergangen)
        return {
            "aktiv": True,
            "typ": _aktiver_test_typ,
            "start": datetime.fromtimestamp(_aktiver_test_start).isoformat(),
            "verbleibend_sekunden": int(verbleibend),
        }
    return {"aktiv": False}


def _api_test_start(test_typ: str, dauer: int = 600, mb: int = 1000) -> dict[str, Any]:
    """Startet einen Stresstest im Hintergrund.

    Args:
        test_typ: 'cpu', 'ram' oder 'kombi'.
        dauer: Dauer in Sekunden.
        mb: MB RAM (nur für ram/kombi).

    Returns:
        Status-Dict.
    """
    global _aktiver_test_prozess, _aktiver_test_typ, _aktiver_test_start, _aktiver_test_dauer

    # Prüfe ob schon ein Test läuft
    status = _api_test_status()
    if status["aktiv"]:
        return {"ok": False, "fehler": f"Test '{status['typ']}' läuft bereits"}

    # Skript-Pfad bestimmen
    skript_map: dict[str, str] = {
        "cpu": "stress_cpu.py",
        "ram": "stress_ram.py",
        "kombi": "stress_kombi.py",
    }
    if test_typ not in skript_map:
        return {"ok": False, "fehler": f"Unbekannter Testtyp: {test_typ}"}

    skript: Path = _SCRIPTS_DIR / skript_map[test_typ]
    if not skript.exists():
        return {"ok": False, "fehler": f"Skript nicht gefunden: {skript}"}

    # Kommando zusammenbauen
    cmd: list[str] = [sys.executable, str(skript), "--dauer", str(dauer)]
    if test_typ in ("ram", "kombi"):
        cmd.extend(["--mb", str(mb)])

    # TEST_START Marker schreiben
    marker: Path = _test_marker_pfad()
    marker.parent.mkdir(parents=True, exist_ok=True)
    zeitstempel: str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(marker, "a", encoding="utf-8") as f:
        f.write(f"TEST_START:{test_typ}:{zeitstempel}:{dauer}\n")

    # Prozess starten
    _aktiver_test_prozess = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    _aktiver_test_typ = test_typ
    _aktiver_test_start = time.time()
    _aktiver_test_dauer = dauer

    # Hintergrund-Thread für TEST_ENDE Marker
    def _warte_auf_ende() -> None:
        global _aktiver_test_prozess
        if _aktiver_test_prozess is not None:
            _aktiver_test_prozess.wait()
        ende_zeit: str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(marker, "a", encoding="utf-8") as f:
            f.write(f"TEST_ENDE:{test_typ}:{ende_zeit}\n")

    threading.Thread(target=_warte_auf_ende, daemon=True).start()

    return {"ok": True, "typ": test_typ, "dauer": dauer}


def _api_test_logs() -> dict[str, Any]:
    """Liest test_marker.txt, findet den letzten Test, gibt Logs im Zeitraum zurück."""
    marker: Path = _test_marker_pfad()
    if not marker.exists():
        return {"fehler": "Keine Tests durchgeführt"}

    zeilen: list[str] = marker.read_text(encoding="utf-8").strip().splitlines()

    # Letzten TEST_START und TEST_ENDE finden
    letzter_start: str | None = None
    letztes_ende: str | None = None
    test_typ: str = ""
    dauer_sek: int = 0

    for zeile in reversed(zeilen):
        if zeile.startswith("TEST_ENDE:") and letztes_ende is None:
            teile = zeile.split(":")
            letztes_ende = ":".join(teile[2:])
        if zeile.startswith("TEST_START:") and letzter_start is None:
            teile = zeile.split(":")
            test_typ = teile[1]
            letzter_start = ":".join(teile[2:-1])
            dauer_sek = int(teile[-1]) if teile[-1].isdigit() else 600
            break

    if letzter_start is None:
        return {"fehler": "Kein Test gefunden"}

    # Logs im Zeitraum filtern
    alle_logs: list[str] = _lese_logs(500)
    # Logs sind neueste zuerst — wir geben sie so zurück
    return {
        "test_typ": test_typ,
        "start": letzter_start,
        "ende": letztes_ende,
        "dauer_sekunden": dauer_sek,
        "logs": alle_logs,
    }



HTML_SEITE: str = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>Genesis EKG</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
--bg:#0a0a0a;--card:rgba(255,255,255,0.04);--card-border:rgba(255,255,255,0.08);
--green:#0f0;--yellow:#fc0;--orange:#f80;--red:#f44;--cyan:#0cc;
--dim:#666;--text:#e0e0e0;--text2:#999;
--tab-h:56px;--safe-b:env(safe-area-inset-bottom,0px);
--mono:'SF Mono','Fira Code','Courier New',monospace;
--sans:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
--r:12px;
}
body{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:15px;
  min-height:100vh;padding-bottom:calc(var(--tab-h) + var(--safe-b) + 8px);
  -webkit-font-smoothing:antialiased}
.page{display:none;padding:10px}
.page.active{display:block}

/* Tab Bar */
.tab-bar{position:fixed;bottom:0;left:0;right:0;
  height:calc(var(--tab-h) + var(--safe-b));padding-bottom:var(--safe-b);
  background:rgba(10,10,10,0.92);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
  border-top:1px solid rgba(255,255,255,0.08);display:flex;z-index:100;
  overflow-x:auto;-webkit-overflow-scrolling:touch}
.tab{flex:0 0 auto;min-width:60px;padding:0 8px;
  display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;
  color:var(--dim);font-size:9px;font-family:var(--sans);font-weight:500;
  cursor:pointer;-webkit-tap-highlight-color:transparent;user-select:none;
  text-decoration:none;min-height:44px}
.tab.active{color:var(--green)}
.tab .icon{font-size:20px;line-height:1}

/* Cards */
.card{background:var(--card);border:1px solid var(--card-border);
  border-radius:var(--r);padding:12px;margin-bottom:8px}
.card-title{font-size:11px;text-transform:uppercase;letter-spacing:1px;
  color:var(--dim);margin-bottom:8px;font-weight:600}
.big{font-family:var(--mono);font-size:28px;font-weight:700;text-align:center}
.row{display:flex;justify-content:space-between;align-items:center;padding:4px 0;font-size:13px}
.label{color:var(--text2)}
.val{font-family:var(--mono);font-weight:600}
.dual{display:grid;grid-template-columns:1fr 1fr;gap:8px}

/* Status Badge */
.badge{display:inline-block;font-size:10px;padding:2px 10px;border-radius:10px;
  font-weight:700;text-transform:uppercase;letter-spacing:0.5px}
.badge-lebt{background:rgba(0,255,0,0.12);color:var(--green)}
.badge-schlaeft{background:rgba(255,204,0,0.12);color:var(--yellow)}
.badge-tot{background:rgba(255,68,68,0.12);color:var(--red)}

/* Colors */
.c-green{color:var(--green)}.c-yellow{color:var(--yellow)}.c-orange{color:var(--orange)}
.c-red{color:var(--red)}.c-cyan{color:var(--cyan)}.c-dim{color:var(--dim)}.c-text{color:var(--text)}

/* Instance Switcher */
.inst-bar{display:flex;gap:6px;padding:8px 10px;overflow-x:auto;-webkit-overflow-scrolling:touch}
.inst-btn{font-family:var(--sans);font-size:12px;font-weight:600;
  padding:6px 14px;border:1px solid var(--card-border);border-radius:20px;
  background:var(--card);color:var(--text);cursor:pointer;white-space:nowrap;
  -webkit-tap-highlight-color:transparent;text-decoration:none}
.inst-btn.active{border-color:var(--green);color:var(--green);background:rgba(0,255,0,0.06)}

/* Buttons */
.btn{font-family:var(--sans);font-size:14px;font-weight:600;
  padding:12px 18px;border:1px solid rgba(255,255,255,0.1);border-radius:10px;
  cursor:pointer;background:rgba(255,255,255,0.04);color:var(--text);
  min-width:44px;min-height:44px;touch-action:manipulation;
  -webkit-tap-highlight-color:transparent;text-decoration:none}
.btn:active{opacity:0.7;transform:scale(0.96)}
.btn-sleep{border-color:rgba(255,204,0,0.3);color:var(--yellow)}
.btn-wake{border-color:rgba(0,255,0,0.3);color:var(--green)}
.btn-restart{border-color:rgba(0,204,204,0.3);color:var(--cyan)}
.btn-good{border-color:rgba(0,255,0,0.3);color:var(--green)}
.btn-bad{border-color:rgba(255,68,68,0.3);color:var(--red)}
.btn-stress{border-color:rgba(255,136,0,0.3);color:var(--orange)}

/* Bars */
.bar-bg{background:rgba(255,255,255,0.06);border-radius:4px;height:12px;overflow:hidden;flex:1}
.bar-fill{height:100%;border-radius:4px;transition:width 0.5s ease}

/* Logs */
.log-line{font-family:var(--mono);font-size:11px;padding:3px 0;border-bottom:1px solid rgba(255,255,255,0.03);
  color:var(--text2);word-break:break-all}

/* Phase Cards */
.phase-card{background:var(--card);border:1px solid var(--card-border);
  border-radius:var(--r);padding:14px;margin-bottom:10px}
.phase-card.active-phase{border-color:rgba(0,255,0,0.2);box-shadow:0 0 15px rgba(0,255,0,0.05)}
.phase-card h3{font-size:15px;font-weight:700;margin-bottom:10px;color:#fff}
.criterion{padding:3px 0;font-size:13px;color:var(--text)}

/* Debug Banner */
#dbg{position:fixed;top:0;left:0;right:0;z-index:9999;background:rgba(255,0,0,0.9);
  color:#fff;padding:10px;font-size:12px;font-family:monospace;max-height:40vh;
  overflow:auto;white-space:pre-wrap;display:none}

/* Responsive */
@media(max-width:400px){.big{font-size:22px}.tab{min-width:50px;font-size:8px}.tab .icon{font-size:17px}}
</style>
</head>
<body>
<div id="dbg"></div>

<!-- Instance Bar -->
<div class="inst-bar" id="inst-bar"></div>

<!-- Pages -->
<div class="page active" id="page-dashboard"><div id="dashboard-content"><div class="card"><div class="big c-dim">Verbinde...</div></div></div></div>
<div class="page" id="page-uebersicht"><div id="uebersicht-content"></div></div>
<div class="page" id="page-koerper"><div id="koerper-content"></div></div>
<div class="page" id="page-gedaechtnis"><div id="gedaechtnis-content"></div></div>
<div class="page" id="page-verhalten"><div id="verhalten-content"></div></div>
<div class="page" id="page-umgebung"><div id="umgebung-content"></div></div>
<div class="page" id="page-phasen"><div id="phasen-content"></div></div>
<div class="page" id="page-logs"><div id="logs-content"></div></div>
<div class="page" id="page-steuerung"><div id="steuerung-content"></div></div>

<!-- Tab Bar -->
<nav class="tab-bar">
  <a class="tab active" href="javascript:void(0)" onclick="sw('dashboard')"><span class="icon">&#x1F4CA;</span>Home</a>
  <a class="tab" href="javascript:void(0)" onclick="sw('uebersicht')"><span class="icon">&#x1F441;</span>Alle</a>
  <a class="tab" href="javascript:void(0)" onclick="sw('koerper')"><span class="icon">&#x1FAC0;</span>Body</a>
  <a class="tab" href="javascript:void(0)" onclick="sw('gedaechtnis')"><span class="icon">&#x1F9E0;</span>Memory</a>
  <a class="tab" href="javascript:void(0)" onclick="sw('verhalten')"><span class="icon">&#x1F3AF;</span>Stats</a>
  <a class="tab" href="javascript:void(0)" onclick="sw('umgebung')"><span class="icon">&#x1FAC4;</span>Womb</a>
  <a class="tab" href="javascript:void(0)" onclick="sw('phasen')"><span class="icon">&#x1F4CB;</span>Phasen</a>
  <a class="tab" href="javascript:void(0)" onclick="sw('logs')"><span class="icon">&#x1F4DC;</span>Logs</a>
  <a class="tab" href="javascript:void(0)" onclick="sw('steuerung')"><span class="icon">&#x2699;</span>Ctrl</a>
</nav>

<script>
/* === Debug === */
var dbgEl=document.getElementById('dbg');
function dbg(m){dbgEl.style.display='block';dbgEl.textContent+=m+'\n';}
window.onerror=function(m,u,l){dbg('ERR: '+m+' L'+l);};
window.onunhandledrejection=function(e){dbg('PROMISE: '+(e.reason||e));};
dbgEl.onclick=function(){dbgEl.style.display='none';};

/* === Globals === */
var CI='genesis-1';
var CT='dashboard';
var LS=null;

function iq(u){return u+(u.indexOf('?')>=0?'&':'?')+'instance='+encodeURIComponent(CI);}

/* === Instance Bar === */
function initInst(){
  fetch('/api/instances').then(function(r){return r.json();}).then(function(d){
    var el=document.getElementById('inst-bar');
    if(!d.instanzen||d.instanzen.length<=1){el.style.display='none';return;}
    var h='';
    for(var i=0;i<d.instanzen.length;i++){
      var n=d.instanzen[i];
      h+='<a class="inst-btn'+(n.name===CI?' active':'')+'" href="javascript:void(0)" onclick="pickInst(\''+n.name+'\')">'+n.name+'</a>';
    }
    el.innerHTML=h;
  }).catch(function(e){});
}
function pickInst(n){CI=n;initInst();update();}

/* === Tab Switching === */
function sw(name){
  var pages=document.querySelectorAll('.page');
  var tabs=document.querySelectorAll('.tab');
  for(var i=0;i<pages.length;i++) pages[i].className='page';
  for(var i=0;i<tabs.length;i++) tabs[i].className='tab';
  var p=document.getElementById('page-'+name);
  if(p) p.className='page active';
  /* find matching tab */
  for(var i=0;i<tabs.length;i++){
    if(tabs[i].getAttribute('onclick').indexOf("'"+name+"'")>=0) tabs[i].className='tab active';
  }
  CT=name;
  loadTab(name);
}

function loadTab(name){
  if(name==='dashboard'&&LS) renderDash(LS);
  else if(name==='uebersicht') loadUebersicht();
  else if(name==='koerper'&&LS) renderKoerper(LS);
  else if(name==='gedaechtnis') loadGedaechtnis();
  else if(name==='verhalten') loadVerhalten();
  else if(name==='umgebung') loadUmgebung();
  else if(name==='phasen') loadPhasen();
  else if(name==='logs') loadLogs();
  else if(name==='steuerung') renderSteuerung();
}

/* === Helpers === */
function pct(v,mn,mx){return Math.max(0,Math.min(100,((v-mn)/(mx-mn))*100));}
function fc(v){return v<0.2?'var(--green)':v<0.5?'var(--yellow)':v<0.8?'var(--orange)':'var(--red)';}
function fcInv(v){return v>0.8?'var(--green)':v>0.5?'var(--yellow)':v>0.2?'var(--orange)':'var(--red)';}
function setBadge(s){
  document.title='Genesis ['+(s==='lebt'?'LEBT':s==='schlaeft'?'ZZZ':'TOT')+']';
}

/* === Dashboard === */
function renderDash(d){
  var el=document.getElementById('dashboard-content');
  var g=d.genesis;
  var st=d.genesis_status||'tot';
  setBadge(st);
  if(!g){el.innerHTML='<div class="card"><div class="big c-dim">Keine Daten</div><div style="text-align:center;color:var(--text2);font-size:13px;margin-top:8px">API antwortet, aber genesis_status.json fehlt</div></div>';return;}

  var h='';
  /* Status Badge */
  h+='<div style="text-align:center;margin:8px 0">';
  h+='<span class="badge badge-'+st+'">'+(st==='lebt'?'LEBT':st==='schlaeft'?'SCHLAEFT':'TOT')+'</span>';
  h+=' <span style="color:var(--text2);font-size:12px;margin-left:6px">'+CI+'</span></div>';

  /* Schmerz & Wohlbefinden */
  var schmerz=g.schmerz||0, wohl=g.wohlbefinden||0;
  h+='<div class="dual">';
  h+='<div class="card"><div class="card-title">Schmerz</div>';
  h+='<div class="big" style="color:'+fc(schmerz)+'">'+schmerz.toFixed(4)+'</div></div>';
  h+='<div class="card"><div class="card-title">Wohlbefinden</div>';
  h+='<div class="big" style="color:'+fcInv(wohl)+'">'+wohl.toFixed(4)+'</div></div>';
  h+='</div>';

  /* Aktion */
  var aN={'rechenintensitaet':'Rechenintensitaet','speicher_freigeben':'Speicher freigeben',
    'pause':'Pause','abtastrate':'Abtastrate','nichts':'Nichts'};
  var aktion=g.letzte_aktion||'nichts';
  h+='<div class="card"><div class="card-title">Letzte Aktion</div>';
  h+='<div class="big c-cyan" style="font-size:18px">'+(aN[aktion]||aktion)+'</div></div>';

  /* VM Ressourcen */
  h+='<div class="dual">';
  var ram=g.ram_belegt_mb||0, ramMax=g.ram_gesamt_mb||2048;
  var ramPct=pct(ram,0,ramMax);
  h+='<div class="card"><div class="card-title">RAM</div>';
  h+='<div class="big" style="font-size:18px;color:'+fc(ramPct/100)+'">'+ram.toFixed(0)+' / '+ramMax+' MB</div>';
  h+='<div class="bar-bg"><div class="bar-fill" style="width:'+ramPct+'%;background:'+fc(ramPct/100)+'"></div></div></div>';

  var cpu=g.cpu_prozent||0;
  h+='<div class="card"><div class="card-title">CPU</div>';
  h+='<div class="big" style="font-size:18px;color:'+fc(cpu/100)+'">'+cpu.toFixed(1)+'%</div>';
  h+='<div class="bar-bg"><div class="bar-fill" style="width:'+cpu+'%;background:'+fc(cpu/100)+'"></div></div></div>';
  h+='</div>';

  /* Cache + Verfall */
  h+='<div class="dual">';
  var cache=g.cache_mb||0, cacheMax=g.cache_max_mb||50;
  h+='<div class="card"><div class="card-title">Cache</div>';
  h+='<div class="big" style="font-size:18px;color:'+fc(cache/cacheMax)+'">'+cache.toFixed(1)+' MB</div></div>';
  var verfall=g.verfall_mb||g.verfall_modifikator||0;
  h+='<div class="card"><div class="card-title">Verfall</div>';
  h+='<div class="big c-yellow" style="font-size:18px">'+verfall.toFixed(3)+' MB/t</div></div>';
  h+='</div>';

  /* Tick + Erfahrungen */
  h+='<div class="dual">';
  h+='<div class="card"><div class="card-title">Tick</div>';
  h+='<div class="big c-text" style="font-size:18px">'+(g.tick||0)+'</div></div>';
  h+='<div class="card"><div class="card-title">Erfahrungen</div>';
  h+='<div class="big c-cyan" style="font-size:18px">'+(g.erfahrungen_gesamt||0)+'</div></div>';
  h+='</div>';

  /* Exploration */
  var expl=typeof g.exploration==='number'?g.exploration:(g.exploration?1:0);
  h+='<div class="card"><div class="card-title">Exploration</div>';
  h+='<div class="row"><span class="label">Zufallsrate</span><span class="val '+(expl>0.5?'c-yellow':'c-green')+'">'+expl.toFixed(3)+'</span></div>';
  h+='<div class="bar-bg"><div class="bar-fill" style="width:'+(expl*100)+'%;background:'+(expl>0.5?'var(--yellow)':'var(--green)')+'"></div></div></div>';

  el.innerHTML=h;
}

/* === Uebersicht (all instances) === */
function loadUebersicht(){
  fetch('/api/instances').then(function(r){return r.json();}).then(function(d){
    var el=document.getElementById('uebersicht-content');
    if(!d.instanzen||d.instanzen.length===0){el.innerHTML='<div class="card"><div class="big c-dim">Keine Instanzen</div></div>';return;}
    var h='<div class="card"><div class="card-title">Alle Instanzen</div>';
    for(var i=0;i<d.instanzen.length;i++){
      var n=d.instanzen[i];
      h+='<div class="row" style="padding:8px 0;border-bottom:1px solid var(--card-border)">';
      h+='<span>'+n.name+' <span class="badge badge-'+n.status+'" style="font-size:9px">'+n.status+'</span></span>';
      h+='<span class="val" style="color:'+fc(n.schmerz)+'">S:'+n.schmerz.toFixed(3)+'</span>';
      h+='</div>';
    }
    h+='</div>';
    el.innerHTML=h;
  }).catch(function(){});
}

/* === Koerper === */
function renderKoerper(d){
  var el=document.getElementById('koerper-content');
  var g=d.genesis,s=d.sensoren;
  var h='';
  /* Zustandsvektor */
  if(g&&g.zustand){
    h+='<div class="card"><div class="card-title">Zustandsvektor</div>';
    var z=g.zustand;
    if(typeof z==='object'){
      var keys=Object.keys(z);
      for(var i=0;i<keys.length;i++){
        h+='<div class="row"><span class="label">'+keys[i]+'</span><span class="val c-text">'+z[keys[i]]+'</span></div>';
      }
    } else {
      h+='<div class="val c-text" style="font-size:12px;word-break:break-all">'+JSON.stringify(z)+'</div>';
    }
    h+='</div>';
  }
  /* Host Sensoren */
  if(s){
    h+='<div class="card"><div class="card-title">Host Sensoren</div>';
    var sk=[['CPU Temp','cpu_temp','C'],['CPU Last','cpu_last','%'],['RAM','ram_prozent','%'],['Fan','fan_rpm','RPM']];
    for(var i=0;i<sk.length;i++){
      var v=s[sk[i][1]];
      if(v!==undefined&&v!==null){
        h+='<div class="row"><span class="label">'+sk[i][0]+'</span><span class="val c-text">'+v+' '+sk[i][2]+'</span></div>';
      }
    }
    h+='</div>';
  }
  /* Schmerzkomponenten */
  if(g&&g.schmerz_komponenten){
    h+='<div class="card"><div class="card-title">Schmerz-Komponenten</div>';
    var sk=g.schmerz_komponenten;
    if(typeof sk==='object'){
      var keys=Object.keys(sk);
      for(var i=0;i<keys.length;i++){
        var v=sk[keys[i]];
        var w=(typeof v==='number')?v.toFixed(4):v;
        h+='<div class="row"><span class="label">'+keys[i]+'</span>';
        h+='<span class="val" style="color:'+fc(typeof v==='number'?v:0)+'">'+w+'</span></div>';
      }
    }
    h+='</div>';
  }
  if(!h) h='<div class="card"><div class="big c-dim">Keine Koerperdaten</div></div>';
  el.innerHTML=h;
}

/* === Gedaechtnis === */
function loadGedaechtnis(){
  var el=document.getElementById('gedaechtnis-content');
  el.innerHTML='<div class="card"><div class="big c-dim">Lade...</div></div>';
  Promise.all([
    fetch(iq('/api/langzeit')).then(function(r){return r.json();}),
    fetch(iq('/api/tode')).then(function(r){return r.json();}),
    fetch(iq('/api/kurzzeit/stats')).then(function(r){return r.json();})
  ]).then(function(res){
    var lz=res[0],td=res[1],kz=res[2];
    var h='';
    /* Stats */
    h+='<div class="dual">';
    h+='<div class="card"><div class="card-title">Langzeit</div><div class="big c-cyan">'+(lz.gesamt||0)+'</div></div>';
    h+='<div class="card"><div class="card-title">Kurzzeit</div><div class="big c-cyan">'+(kz.gesamt||0)+'</div></div>';
    h+='</div>';

    /* Tode */
    h+='<div class="card"><div class="card-title">Tode &amp; Schlaf</div>';
    h+='<div class="row"><span class="label">Echte Tode</span><span class="val c-red">'+(td.gesamt_tode||0)+'</span></div>';
    h+='<div class="row"><span class="label">Schlaf</span><span class="val c-yellow">'+(td.gesamt_schlaf||0)+'</span></div>';
    if(td.tode&&td.tode.length>0){
      for(var i=0;i<Math.min(td.tode.length,10);i++){
        var t=td.tode[i];
        var typ=t.war_schlaf?'Schlaf':'Tod';
        var col=t.war_schlaf?'c-yellow':'c-red';
        h+='<div class="row" style="font-size:12px"><span class="label '+col+'">'+typ+'</span>';
        h+='<span class="val c-dim">S:'+(t.letzter_schmerz||0).toFixed(3)+'</span></div>';
      }
    }
    h+='</div>';

    /* Langzeit Eintraege */
    if(lz.eintraege&&lz.eintraege.length>0){
      h+='<div class="card"><div class="card-title">Gelernte Muster (Top 20)</div>';
      for(var i=0;i<Math.min(lz.eintraege.length,20);i++){
        var e=lz.eintraege[i];
        var dc=e.durchschnitt_delta<0?'c-green':'c-red';
        h+='<div class="row" style="font-size:12px;border-bottom:1px solid var(--card-border);padding:6px 0">';
        h+='<span class="label" style="flex:1">'+e.aktion+' (x'+e.anzahl+')</span>';
        h+='<span class="val '+dc+'">'+e.durchschnitt_delta.toFixed(4)+'</span></div>';
      }
      h+='</div>';
    }

    /* Kurzzeit Aktionen */
    if(kz.aktionen){
      var keys=Object.keys(kz.aktionen);
      if(keys.length>0){
        h+='<div class="card"><div class="card-title">Aktions-Statistik</div>';
        for(var i=0;i<keys.length;i++){
          var a=kz.aktionen[keys[i]];
          var dc=a.avg_delta<0?'c-green':'c-red';
          h+='<div class="row" style="font-size:13px"><span class="label">'+keys[i]+' (x'+a.anzahl+')</span>';
          h+='<span class="val '+dc+'">'+a.avg_delta.toFixed(5)+'</span></div>';
        }
        h+='</div>';
      }
    }
    el.innerHTML=h;
  }).catch(function(e){el.innerHTML='<div class="card"><div class="big c-red">Fehler: '+e+'</div></div>';});
}

/* === Verhalten (Stats) === */
function loadVerhalten(){
  var el=document.getElementById('verhalten-content');
  if(!LS||!LS.genesis){el.innerHTML='<div class="card"><div class="big c-dim">Keine Daten</div></div>';return;}
  var g=LS.genesis;
  var h='';
  /* Aktions-Historie wenn verfuegbar */
  h+='<div class="card"><div class="card-title">Aktuelles Verhalten</div>';
  h+='<div class="row"><span class="label">Aktion</span><span class="val c-cyan">'+(g.letzte_aktion||'?')+'</span></div>';
  h+='<div class="row"><span class="label">Schmerz</span><span class="val" style="color:'+fc(g.schmerz||0)+'">'+(g.schmerz||0).toFixed(4)+'</span></div>';
  h+='<div class="row"><span class="label">Wohlbefinden</span><span class="val" style="color:'+fcInv(g.wohlbefinden||0)+'">'+(g.wohlbefinden||0).toFixed(4)+'</span></div>';
  h+='<div class="row"><span class="label">Exploration</span><span class="val c-yellow">'+(typeof g.exploration==='number'?g.exploration:(g.exploration?1:0)).toFixed(3)+'</span></div>';
  h+='<div class="row"><span class="label">Tick</span><span class="val c-text">'+(g.tick||0)+'</span></div>';
  h+='<div class="row"><span class="label">Erfahrungen</span><span class="val c-text">'+(g.erfahrungen_gesamt||0)+'</span></div>';
  h+='</div>';
  /* Reiz */
  if(g.reiz_aktiv){
    h+='<div class="card"><div class="card-title">Aktiver Reiz</div>';
    h+='<div class="row"><span class="label">Typ</span><span class="val c-orange">'+(g.reiz_typ||g.reiz_aktiv)+'</span></div>';
    h+='<div class="row"><span class="label">Staerke</span><span class="val c-orange">'+(g.reiz_staerke||0).toFixed(1)+'</span></div>';
    h+='</div>';
  }
  el.innerHTML=h;
}

/* === Umgebung (Womb) === */
function loadUmgebung(){
  var el=document.getElementById('umgebung-content');
  el.innerHTML='<div class="card"><div class="big c-dim">Lade...</div></div>';
  fetch(iq('/api/umgebung')).then(function(r){return r.json();}).then(function(u){
    var h='';
    if(u.fehler){h='<div class="card"><div class="big c-dim">'+u.fehler+'</div></div>';el.innerHTML=h;return;}

    /* Rhythmus */
    h+='<div class="card"><div class="card-title">Rhythmus</div>';
    var rW=u.rhythmus_wert||0;
    h+='<div class="big c-cyan" style="font-size:20px">'+(rW*100).toFixed(0)+'%</div>';
    h+='<div style="text-align:center;color:var(--text2);font-size:12px;margin-top:4px">'+(u.rhythmus_kategorie||'?')+'</div>';
    h+='</div>';

    /* Verfall + Naehrstoffe */
    h+='<div class="dual">';
    h+='<div class="card"><div class="card-title">Verfall</div>';
    var vMB=u.verfall_mb||u.verfall_modifikator||0.2;
    h+='<div class="big" style="font-size:18px;color:'+(vMB<0.15?'var(--green)':vMB<0.25?'var(--yellow)':'var(--orange)')+'">'+vMB.toFixed(3)+' MB/t</div></div>';
    h+='<div class="card"><div class="card-title">Naehrstoff</div>';
    h+='<div class="big c-cyan" style="font-size:18px">'+(u.ticks_bis_schub||u.naechster_schub_in||'?')+'</div>';
    h+='<div style="text-align:center;font-size:11px;color:var(--text2)">Ticks bis Schub</div></div>';
    h+='</div>';

    /* Zone */
    var zoneL={'komfort_zone':'Komfort','normal_zone':'Normal','stress_zone':'Stress'};
    var zoneC={'komfort_zone':'var(--green)','normal_zone':'var(--cyan)','stress_zone':'var(--orange)'};
    var zone=u.zone||u.feedback_zone||'normal_zone';
    h+='<div class="card"><div class="card-title">Feedback-Zone</div>';
    h+='<div class="big" style="font-size:20px;color:'+(zoneC[zone]||'var(--dim)')+'">'+(zoneL[zone]||zone)+'</div></div>';

    /* Features */
    var feat=u.features||{};
    h+='<div class="card"><div class="card-title">Features</div>';
    var fl=[['Rhythmus',feat.rhythmus||feat.rhythmus_aktiv],['Naehrung',feat.naehrung||feat.variable_naehrung],
            ['Reize',feat.reize||feat.reize_aktiv],['Feedback',feat.feedback||feat.feedback_aktiv],
            ['Ext. Aktionen',feat.externe_aktionen]];
    for(var i=0;i<fl.length;i++){
      h+='<div class="row"><span class="label">'+fl[i][0]+'</span>';
      h+='<span class="val '+(fl[i][1]?'c-green':'c-dim')+'">'+(fl[i][1]?'aktiv':'-')+'</span></div>';
    }
    h+='</div>';

    el.innerHTML=h;
  }).catch(function(e){el.innerHTML='<div class="card"><div class="big c-red">Fehler: '+e+'</div></div>';});
}

/* === Phasen === */
function loadPhasen(){
  var el=document.getElementById('phasen-content');
  el.innerHTML='<div class="card"><div class="big c-dim">Lade...</div></div>';
  fetch(iq('/api/phasen')).then(function(r){return r.json();}).then(function(p){
    var h='';
    var ck=function(ok){return ok?'[OK] ':'[--] ';};
    var psC=function(s){return s==='aktiv'?'badge-lebt':s==='bereit'?'badge-schlaeft':'badge-tot';};

    /* Phase 1 */
    h+='<div class="phase-card"><h3>Phase 1 - Basis Code <span class="badge badge-lebt">done</span></h3>';
    h+='<div class="criterion">[OK] Sensorik, Schmerz, Reflexe</div>';
    h+='<div class="criterion">[OK] 132 Tests bestanden</div></div>';

    /* Phase 2 */
    var p2=p.phase2;
    h+='<div class="phase-card active-phase"><h3>Phase 2 - Beobachtung <span class="badge '+psC(p2.status)+'">'+p2.status+'</span></h3>';
    h+='<div class="criterion">'+ck(p2.kurzzeit_erfahrungen>0)+'Erfahrungen: '+p2.kurzzeit_erfahrungen+'</div>';
    h+='<div class="criterion">'+ck(p2.tode_gesamt>0)+'Tode: '+p2.tode_gesamt+'</div>';
    h+='<div class="criterion">'+ck(p2.langzeit_eintraege>=10)+'Langzeit-Muster: '+p2.langzeit_eintraege+' (Ziel: 10+)</div></div>';

    /* Phase 3 */
    var p3=p.phase3;
    h+='<div class="phase-card"><h3>Phase 3 - Klon-Test <span class="badge '+psC(p3.status)+'">'+p3.status+'</span></h3>';
    h+='<div class="criterion">'+ck(p3.baseline_vorhanden)+'Baseline vorhanden</div></div>';

    /* Phase 4 */
    var p4=p.phase4;
    h+='<div class="phase-card"><h3>Phase 4 - Erweiterter Laufstall <span class="badge '+psC(p4.status)+'">'+p4.status+'</span></h3>';
    h+='<div class="criterion">'+ck(p4.muster_ohne_reflex>=3)+'Muster: '+p4.muster_ohne_reflex+' (Ziel: 3+)</div>';
    h+='<div class="criterion">'+ck(p4.aus_tod_gelernt)+'Aus Tod gelernt</div>';
    h+='<div class="criterion">'+ck(p4.stresstest_ueberlebt)+'Stresstest ueberlebt</div></div>';

    /* Phase 5 */
    h+='<div class="phase-card"><h3>Phase 5 - Laptop <span class="badge badge-tot">'+p.phase5.status+'</span></h3>';
    h+='<div class="criterion">[--] Phase 4 abgeschlossen</div></div>';

    el.innerHTML=h;
  }).catch(function(){});
}

/* === Logs === */
function loadLogs(){
  var el=document.getElementById('logs-content');
  el.innerHTML='<div class="card"><div class="big c-dim">Lade...</div></div>';
  fetch(iq('/api/logs')).then(function(r){return r.json();}).then(function(d){
    var h='<div class="card"><div class="card-title">Logs (neueste zuerst)</div>';
    if(!d.logs||d.logs.length===0){h+='<div class="c-dim">Keine Logs</div>';}
    else{
      for(var i=0;i<d.logs.length;i++){
        h+='<div class="log-line">'+d.logs[i].replace(/</g,'&lt;')+'</div>';
      }
    }
    h+='</div>';
    el.innerHTML=h;
  }).catch(function(){});
}

/* === Steuerung === */
function renderSteuerung(){
  var el=document.getElementById('steuerung-content');
  var h='';
  h+='<div class="card"><div class="card-title">Signale</div>';
  h+='<div style="display:flex;flex-wrap:wrap;gap:8px">';
  h+='<button class="btn btn-good" onclick="sig(\'good\')">Gut</button>';
  h+='<button class="btn btn-bad" onclick="sig(\'bad\')">Schlecht</button>';
  h+='<button class="btn btn-sleep" onclick="sig(\'sleep\')">Schlafen</button>';
  h+='<button class="btn btn-wake" onclick="sig(\'wake\')">Aufwecken</button>';
  h+='<button class="btn btn-restart" onclick="sig(\'restart\')">Neustart</button>';
  h+='</div></div>';

  h+='<div class="card"><div class="card-title">Stresstests</div>';
  h+='<div style="display:flex;flex-wrap:wrap;gap:8px">';
  h+='<button class="btn btn-stress" onclick="startTest(\'cpu\')">CPU Stress</button>';
  h+='<button class="btn btn-stress" onclick="startTest(\'ram\')">RAM Stress</button>';
  h+='<button class="btn btn-stress" onclick="startTest(\'kombi\')">Kombi Stress</button>';
  h+='</div>';
  h+='<div id="test-status" style="margin-top:8px;font-size:12px;color:var(--text2)"></div>';
  h+='</div>';

  h+='<div class="card"><div class="card-title">Export</div>';
  h+='<div style="display:flex;flex-wrap:wrap;gap:8px">';
  h+='<button class="btn" onclick="exportJSON()">JSON Export</button>';
  h+='<button class="btn" onclick="exportLogs()">Log Export</button>';
  h+='</div></div>';

  el.innerHTML=h;
  updateTestStatus();
}

/* === Signals === */
function sig(typ){
  var url='';
  if(typ==='sleep')url='/api/signal/sleep';
  else if(typ==='wake')url='/api/control/wake';
  else if(typ==='restart')url='/api/control/restart';
  else if(typ==='good')url='/api/signal/good';
  else if(typ==='bad')url='/api/signal/bad';
  fetch(url,{method:'POST'});
}

function startTest(typ){
  if(!confirm('Stresstest "'+typ+'" starten?'))return;
  fetch('/api/test/'+typ,{method:'POST'}).then(function(r){return r.json();}).then(function(d){
    if(!d.ok)alert('Fehler: '+d.fehler);
    else updateTestStatus();
  });
}

function updateTestStatus(){
  var el=document.getElementById('test-status');
  if(!el)return;
  fetch('/api/test/status').then(function(r){return r.json();}).then(function(d){
    if(d.aktiv){
      var m=Math.floor(d.verbleibend_sekunden/60),s=d.verbleibend_sekunden%60;
      el.innerHTML='<span class="c-orange">Test laeuft: '+d.typ+' ('+m+':'+String(s).padStart(2,'0')+' verbleibend)</span>';
    } else {
      el.innerHTML='Kein Test aktiv';
    }
  }).catch(function(){});
}

function exportJSON(){
  fetch('/api/export').then(function(r){return r.json();}).then(function(d){
    var blob=new Blob([JSON.stringify(d,null,2)],{type:'application/json'});
    var url=URL.createObjectURL(blob);
    var a=document.createElement('a');
    a.href=url;a.download='genesis_export.json';a.click();
    URL.revokeObjectURL(url);
  });
}
function exportLogs(){
  fetch('/api/logs/export').then(function(r){return r.blob();}).then(function(blob){
    var url=URL.createObjectURL(blob);
    var a=document.createElement('a');
    a.href=url;a.download='genesis_log.txt';a.click();
    URL.revokeObjectURL(url);
  });
}

/* === Main Update Loop === */
function update(){
  fetch(iq('/api/status')).then(function(r){return r.json();}).then(function(d){
    LS=d;
    setBadge(d.genesis_status||'tot');
    if(CT==='dashboard') renderDash(d);
    else if(CT==='koerper') renderKoerper(d);
    else if(CT==='verhalten') loadVerhalten();
    if(CT==='steuerung') updateTestStatus();
  }).catch(function(err){
    setBadge('tot');
    if(CT==='dashboard'){
      document.getElementById('dashboard-content').innerHTML=
        '<div class="card"><div class="big c-red">Verbindung verloren</div><div style="text-align:center;color:var(--text2);font-size:12px;margin-top:8px">'+err+'</div></div>';
    }
  });
}

/* === Init === */
initInst();
update();
setInterval(update,2000);
</script>
</body>
</html>"""


class GenesisHandler(BaseHTTPRequestHandler):
    """HTTP-Handler für das Genesis Web-Dashboard."""

    def _parse_instanz(self) -> str | None:
        """Extrahiert ?instance= aus der URL."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        instanz_list = params.get("instance", [])
        return instanz_list[0] if instanz_list else None

    def _api_pfad(self) -> str:
        """Gibt den Pfad ohne Query-Parameter zurück."""
        return urlparse(self.path).path

    def do_GET(self) -> None:
        """Behandelt GET-Anfragen."""
        pfad = self._api_pfad()
        inst = self._parse_instanz()

        if pfad == "/api/instances":
            self._sende_json(_api_instances())
        elif pfad == "/api/status":
            self._sende_json(_api_daten(inst))
        elif pfad == "/api/logs":
            self._sende_json({"logs": _lese_logs(50, inst)})
        elif pfad == "/api/logs/export":
            self._sende_log_export()
        elif pfad == "/api/langzeit":
            self._sende_json(_api_langzeit(inst))
        elif pfad == "/api/tode":
            self._sende_json(_api_tode(inst))
        elif pfad == "/api/kurzzeit/stats":
            self._sende_json(_api_kurzzeit_stats(inst))
        elif pfad == "/api/phasen":
            self._sende_json(_api_phasen(inst))
        elif pfad == "/api/umgebung":
            self._sende_json(_api_umgebung(inst))
        elif pfad == "/api/export":
            self._sende_json(_api_export(inst))
        elif pfad == "/api/logs/archiv":
            self._sende_json(_api_logs_archiv())
        elif pfad.startswith("/api/logs/archiv/"):
            self._sende_archiv_log()
        elif pfad == "/api/test/status":
            self._sende_json(_api_test_status())
        elif pfad == "/api/logs/test":
            self._sende_json(_api_test_logs())
        else:
            self._sende_html()

    def do_POST(self) -> None:
        """Behandelt POST-Anfragen für Steuerung."""
        pfad = self._api_pfad()
        inst = self._parse_instanz()
        antwort: dict[str, Any] = {"ok": False, "fehler": "Unbekannter Endpunkt"}

        if pfad == "/api/signal/sleep":
            _schreibe_signal(f"SLEEP {time.time():.0f}", inst)
            antwort = {"ok": True, "aktion": "sleep"}

        elif pfad == "/api/signal/good":
            _schreibe_signal("GOOD", inst)
            antwort = {"ok": True, "aktion": "good"}

        elif pfad == "/api/signal/bad":
            _schreibe_signal("BAD", inst)
            antwort = {"ok": True, "aktion": "bad"}

        elif pfad == "/api/control/wake":
            instanz_name = inst or "genesis-1"
            if _genesis_lebt(inst) == "lebt":
                antwort = {"ok": False, "fehler": "Genesis läuft bereits"}
            else:
                signal_pfad = _SIGNAL_DATEI
                if inst:
                    signal_pfad = _instanz_pfade(inst)[4]
                try:
                    signal_pfad.unlink(missing_ok=True)
                except OSError:
                    pass
                subprocess.Popen(
                    [sys.executable, "-m", "vm.genesis.leben",
                     "--instance", instanz_name],
                    env={**__import__("os").environ, "PYTHONPATH": "/opt/genesis"},
                    cwd="/opt/genesis",
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                antwort = {"ok": True, "aktion": "wake", "instanz": instanz_name}

        elif pfad == "/api/control/restart":
            _schreibe_signal(f"SLEEP {time.time():.0f}", inst)
            antwort = {"ok": True, "aktion": "restart"}

        elif pfad in ("/api/test/cpu", "/api/test/ram", "/api/test/kombi"):
            test_typ: str = pfad.split("/")[-1]
            antwort = _api_test_start(test_typ)

        self._sende_json(antwort)

    def _sende_html(self) -> None:
        """Sendet die Dashboard-HTML-Seite."""
        inhalt: bytes = HTML_SEITE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(inhalt)))
        self.end_headers()
        self.wfile.write(inhalt)

    def _sende_json(self, daten: dict[str, Any]) -> None:
        """Sendet JSON-Daten."""
        inhalt: bytes = json.dumps(daten, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(inhalt)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(inhalt)

    def _sende_log_export(self) -> None:
        """Sendet die komplette Log-Datei als Download."""
        log_pfad: Path = Path("/opt/genesis/shared/genesis_log.txt")
        zeitstempel: str = datetime.now().strftime("%Y%m%d_%H%M%S")
        dateiname: str = f"genesis_log_{zeitstempel}.txt"

        try:
            if log_pfad.exists():
                inhalt: bytes = log_pfad.read_bytes()
            else:
                inhalt = "Keine Logs vorhanden\n".encode("utf-8")
        except OSError:
            inhalt = "Keine Logs vorhanden\n".encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{dateiname}"')
        self.send_header("Content-Length", str(len(inhalt)))
        self.end_headers()
        self.wfile.write(inhalt)

    def _sende_archiv_log(self) -> None:
        """Sendet eine archivierte Log-Datei als Download."""
        # Datum aus Pfad extrahieren: /api/logs/archiv/YYYY-MM-DD
        datum: str = self.path.split("/")[-1]
        # Validierung: nur YYYY-MM-DD Format erlauben
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", datum):
            self._sende_json({"fehler": "Ungültiges Datum"})
            return
        datei_pfad: Path = _LOG_VERZEICHNIS / f"genesis_log_{datum}.txt"
        if not datei_pfad.exists():
            self._sende_json({"fehler": "Archiv nicht gefunden"})
            return
        try:
            inhalt: bytes = datei_pfad.read_bytes()
        except OSError:
            inhalt = b""
        dateiname: str = f"genesis_log_{datum}.txt"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{dateiname}"')
        self.send_header("Content-Length", str(len(inhalt)))
        self.end_headers()
        self.wfile.write(inhalt)

    def log_message(self, format: str, *args: Any) -> None:
        """Unterdrückt Standard-Logging für saubere Ausgabe."""
        pass


def main(port: int = 8080) -> None:
    """Startet das Web-Dashboard.

    Args:
        port: HTTP-Port (Standard: 8080).
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Genesis Web-Dashboard — Mobile EKG"
    )
    parser.add_argument(
        "--port", type=int, default=8080,
        help="HTTP-Port (Standard: 8080)",
    )
    args = parser.parse_args()

    # Log-Rotation Hintergrund-Thread starten
    rotation_thread = threading.Thread(target=_log_rotation_thread, daemon=True)
    rotation_thread.start()

    server = HTTPServer(("0.0.0.0", args.port), GenesisHandler)
    print(f"Genesis Web-Dashboard gestartet: http://localhost:{args.port}")
    print("Log-Rotation aktiv (täglich 00:00).")
    print("Ctrl+C zum Beenden.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("\nDashboard beendet.")


if __name__ == "__main__":
    main()

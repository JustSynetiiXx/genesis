"""Web-Dashboard für Genesis — Mobile-optimiert, Multi-Page.

Zeigt Genesis-Status im Browser an. Liest nur, beeinflusst Genesis nicht.

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

# DB-Pfade (Read-Only Zugriff!)
_LANGZEIT_DB: Path = Path("/var/lib/genesis/langzeit.db")
_KURZZEIT_DB: Path = Path("/var/lib/genesis/kurzzeit.db")

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


def _lese_genesis_status() -> dict[str, Any] | None:
    """Liest genesis_status.json atomar."""
    try:
        return json.loads(_STATUS_DATEI.read_bytes())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _lese_sensoren() -> dict[str, Any] | None:
    """Liest sensoren.bin über den Leser."""
    leser = _lade_leser()
    if leser is None:
        return None
    return leser.lese_sensoren(_SENSOR_DATEI)


def _lese_logs(n: int = 50) -> list[str]:
    """Liest die letzten n Log-Zeilen aus genesis_log.txt."""
    try:
        zeilen: list[str] = _LOG_DATEI.read_text(encoding="utf-8").splitlines()
        # Neueste zuerst
        return list(reversed(zeilen[-n:]))
    except (FileNotFoundError, OSError):
        return []


def _schreibe_signal(signal_text: str) -> None:
    """Schreibt ein Signal in signal.txt."""
    _SIGNAL_DATEI.parent.mkdir(parents=True, exist_ok=True)
    _SIGNAL_DATEI.write_text(signal_text + "\n", encoding="utf-8")


def _genesis_lebt() -> str:
    """Prüft ob Genesis lebt. Gibt 'lebt', 'schlaeft' oder 'tot' zurück."""
    # Schlaf-Signal prüfen
    try:
        signal_inhalt: str = _SIGNAL_DATEI.read_text(encoding="utf-8").strip()
        if signal_inhalt.startswith("SLEEP"):
            return "schlaeft"
    except (FileNotFoundError, OSError):
        pass

    # Status-Zeitstempel prüfen
    status: dict[str, Any] | None = _lese_genesis_status()
    if status is None:
        return "tot"
    alter: float = time.time() - status.get("zeitstempel", 0)
    if alter < 5:
        return "lebt"
    if alter < 30:
        return "schlaeft"
    return "tot"


def _api_daten() -> dict[str, Any]:
    """Kombiniert Genesis-Status und Sensordaten für die API."""
    status = _lese_genesis_status()
    sensoren = _lese_sensoren()
    return {
        "genesis": status,
        "sensoren": sensoren,
        "genesis_status": _genesis_lebt(),
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


def _api_langzeit() -> dict[str, Any]:
    """Liest ALLE Einträge aus langzeit.db Tabelle 'gelernt'."""
    conn = _db_readonly(_LANGZEIT_DB)
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


def _api_tode() -> dict[str, Any]:
    """Liest ALLE Einträge aus langzeit.db Tabelle 'tode'."""
    conn = _db_readonly(_LANGZEIT_DB)
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


def _api_kurzzeit_stats() -> dict[str, Any]:
    """Berechnet Aktions-Statistiken aus kurzzeit.db."""
    conn = _db_readonly(_KURZZEIT_DB)
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


def _api_phasen() -> dict[str, Any]:
    """Berechnet den Phasen-Status basierend auf verfügbaren Daten."""
    langzeit = _api_langzeit()
    tode = _api_tode()
    kurzzeit = _api_kurzzeit_stats()
    status = _lese_genesis_status()

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


def _api_export() -> dict[str, Any]:
    """Komplett-Dump aller Daten als JSON für externe Analyse."""
    tode = _api_tode()
    return {
        "export_zeitstempel": datetime.now().isoformat(),
        "genesis_version": "Phase 2 — Beobachtung",
        "aktueller_status": _api_daten(),
        "langzeit_gedaechtnis": _api_langzeit(),
        "tod_historie": {
            "ereignisse": tode["tode"],
            "gesamt_tode": tode["gesamt_tode"],
            "gesamt_schlaf": tode["gesamt_schlaf"],
        },
        "kurzzeit_statistik": _api_kurzzeit_stats(),
        "phasen_status": _api_phasen(),
        "config": _lade_config(),
        "logs": _lese_logs(200),
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


HTML_SEITE: str = """\
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>Genesis EKG</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
:root {
    --bg: #0a0a0a;
    --card: rgba(255,255,255,0.03);
    --card-border: rgba(255,255,255,0.06);
    --card-hover: rgba(255,255,255,0.05);
    --border: #222;
    --green: #00ff00;
    --yellow: #ffcc00;
    --orange: #ff8800;
    --red: #ff4444;
    --cyan: #00cccc;
    --dim: #666;
    --dimmer: #444;
    --text: #e0e0e0;
    --text-secondary: #999;
    --tab-h: 58px;
    --safe-b: env(safe-area-inset-bottom, 0px);
    --mono: 'SF Mono', 'Fira Code', 'Courier New', monospace;
    --sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    --radius: 12px;
}
body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--sans);
    font-size: 15px;
    min-height: 100vh;
    padding-bottom: calc(var(--tab-h) + var(--safe-b) + 8px);
    -webkit-font-smoothing: antialiased;
}
.page { display: none; padding: 10px; }
.page.active { display: block; }

/* Tab-Bar */
.tab-bar {
    position: fixed;
    bottom: 0; left: 0; right: 0;
    height: calc(var(--tab-h) + var(--safe-b));
    padding-bottom: var(--safe-b);
    background: rgba(10,10,10,0.85);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border-top: 1px solid rgba(255,255,255,0.08);
    display: flex;
    z-index: 100;
}
.tab {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    color: var(--dim);
    font-size: 9px;
    font-family: var(--sans);
    font-weight: 500;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
    user-select: none;
    min-height: 44px;
    transition: color 0.2s;
    text-decoration: none;
    letter-spacing: 0.3px;
}
.tab .icon { font-size: 22px; line-height: 1; }
.tab.active { color: var(--green); }
.tab:active { opacity: 0.6; }

/* Header */
.page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 2px 12px;
}
.page-title {
    font-size: 20px;
    font-weight: 700;
    color: #fff;
    letter-spacing: -0.3px;
}
.status-badge {
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 600;
    padding: 4px 12px;
    border-radius: 20px;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}
.status-lebt { background: rgba(0,255,0,0.12); color: var(--green); }
.status-schlaeft { background: rgba(255,204,0,0.12); color: var(--yellow); }
.status-tot { background: rgba(255,68,68,0.12); color: var(--red); }

/* Cards */
.card {
    background: var(--card);
    border: 1px solid var(--card-border);
    border-radius: var(--radius);
    padding: 12px;
    margin-bottom: 10px;
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
}
.card-title {
    font-size: 11px;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 1.2px;
    font-weight: 600;
    margin-bottom: 8px;
    padding-bottom: 6px;
    border-bottom: 1px solid rgba(255,255,255,0.04);
}
.big-number {
    font-family: var(--mono);
    font-size: 36px;
    font-weight: 700;
    text-align: center;
    letter-spacing: -1px;
}
.interpretation {
    font-size: 18px;
    text-align: center;
    padding: 8px 0;
    font-weight: 600;
    letter-spacing: -0.2px;
}
.bar-container {
    background: rgba(255,255,255,0.06);
    border-radius: 6px;
    height: 10px;
    margin: 6px 0 8px 0;
    overflow: hidden;
}
.bar-fill {
    height: 100%;
    border-radius: 6px;
    transition: width 0.5s ease;
}
.row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 4px 0;
    font-size: 14px;
}
.row .label { color: var(--text-secondary); }
.row .value { font-family: var(--mono); font-weight: 600; font-size: 13px; }
.dual {
    display: flex;
    gap: 10px;
}
.dual > .card { flex: 1; margin-bottom: 0; }

/* Warnstufe */
#warnstufe {
    text-align: center;
    padding: 16px 8px;
    font-size: 24px;
    font-weight: 700;
    border-radius: var(--radius);
    margin-bottom: 10px;
    text-transform: uppercase;
    letter-spacing: 3px;
}
.warn-komfort {
    background: linear-gradient(135deg, #0a3d0a, #1a5c1a);
    color: var(--green);
    box-shadow: 0 0 20px rgba(0,255,0,0.08);
}
.warn-unbehagen {
    background: linear-gradient(135deg, #3d3d00, #5c5c00);
    color: var(--yellow);
    box-shadow: 0 0 20px rgba(255,204,0,0.08);
}
.warn-stress {
    background: linear-gradient(135deg, #3d2200, #5c3a00);
    color: var(--orange);
    box-shadow: 0 0 20px rgba(255,136,0,0.08);
}
.warn-panik {
    background: linear-gradient(135deg, #3d0000, #5c0000);
    color: var(--red);
    box-shadow: 0 0 20px rgba(255,68,68,0.1);
}
.warn-reflex {
    background: linear-gradient(135deg, #3d0000, #5c0000);
    color: var(--red);
    animation: blink 0.5s infinite;
    box-shadow: 0 0 25px rgba(255,68,68,0.15);
}
.warn-offline { background: var(--border); color: var(--dim); }
@keyframes blink { 50% { opacity: 0.5; } }

/* Farben */
.c-green { color: var(--green); }
.c-yellow { color: var(--yellow); }
.c-orange { color: var(--orange); }
.c-red { color: var(--red); }
.c-cyan { color: var(--cyan); }
.c-dim { color: var(--dim); }
.c-text { color: var(--text); }

/* Körper-Details */
.sensor-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 7px 0;
    border-bottom: 1px solid rgba(255,255,255,0.03);
}
.sensor-row:last-child { border-bottom: none; }
.sensor-name { flex: 0 0 80px; font-size: 12px; color: var(--text-secondary); }
.sensor-wert {
    flex: 0 0 70px; font-family: var(--mono);
    font-size: 13px; font-weight: 600; text-align: right;
}
.sensor-kat { flex: 0 0 55px; font-size: 10px; text-align: center; color: var(--dim); text-transform: uppercase; }
.sensor-bar-wrap {
    flex: 1; background: rgba(255,255,255,0.06); border-radius: 4px;
    height: 12px; overflow: hidden; min-width: 30px;
}
.sensor-bar-fill { height: 100%; border-radius: 4px; transition: width 0.5s ease; }
.sensor-beitrag {
    flex: 0 0 50px; font-family: var(--mono);
    font-size: 12px; font-weight: 600; text-align: right;
}

/* Buttons */
.controls {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 10px;
}
.controls button {
    font-family: var(--sans);
    font-size: 14px;
    font-weight: 600;
    padding: 12px 18px;
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 10px;
    cursor: pointer;
    background: rgba(255,255,255,0.04);
    color: var(--text);
    min-width: 44px;
    min-height: 44px;
    touch-action: manipulation;
    transition: all 0.2s;
    backdrop-filter: blur(5px);
}
.controls button:active { transform: scale(0.95); opacity: 0.8; }
.btn-sleep { border-color: rgba(255,204,0,0.3); color: var(--yellow); }
.btn-sleep:hover { background: rgba(255,204,0,0.08); }
.btn-sleep.active { background: rgba(255,204,0,0.15); }
.btn-sleep.done { background: rgba(255,255,255,0.02); color: var(--dim); border-color: rgba(255,255,255,0.05); }
.btn-wake { border-color: rgba(0,255,0,0.3); color: var(--green); }
.btn-wake:hover { background: rgba(0,255,0,0.08); }
.btn-wake.active { background: rgba(0,255,0,0.15); }
.btn-restart { border-color: rgba(255,136,0,0.3); color: var(--orange); }
.btn-restart:hover { background: rgba(255,136,0,0.08); }
.btn-restart.active { background: rgba(255,136,0,0.15); }
.btn-good { border-color: rgba(0,255,0,0.3); color: var(--green); }
.btn-good:hover { background: rgba(0,255,0,0.08); }
.btn-bad { border-color: rgba(255,68,68,0.3); color: var(--red); }
.btn-bad:hover { background: rgba(255,68,68,0.08); }
.btn-flash-green { background: rgba(0,255,0,0.2) !important; }
.btn-flash-red { background: rgba(255,68,68,0.2) !important; }
.btn-export { border-color: rgba(0,204,204,0.3); color: var(--cyan); }
.btn-export:hover { background: rgba(0,204,204,0.08); }

/* Logs */
.log-panel {
    background: rgba(0,0,0,0.4);
    border: 1px solid var(--card-border);
    border-radius: var(--radius);
    padding: 12px;
    margin-bottom: 8px;
    max-height: 60vh;
    overflow-y: auto;
    font-family: var(--mono);
    font-size: 11px;
    line-height: 1.5;
    color: rgba(0,204,0,0.8);
}
.log-line { white-space: pre-wrap; word-break: break-all; padding: 1px 0; }
.log-line:first-child { color: var(--green); font-weight: 600; }
.log-hint {
    font-size: 12px;
    color: var(--dim);
    text-align: center;
    padding: 10px;
    border: 1px dashed rgba(255,255,255,0.08);
    border-radius: var(--radius);
    margin-bottom: 10px;
}

/* Gedächtnis-Tabelle */
.mem-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
}
.mem-table th {
    text-align: left;
    color: var(--text-secondary);
    padding: 8px 4px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    font-weight: 600;
}
.mem-table td {
    padding: 6px 4px;
    border-bottom: 1px solid rgba(255,255,255,0.02);
    vertical-align: top;
    font-family: var(--mono);
    font-size: 12px;
}
.mem-table .zustand-cell {
    font-family: var(--sans);
    font-size: 11px;
    color: var(--dim);
}

/* Balkendiagramm */
.bar-chart-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 7px 0;
    border-bottom: 1px solid rgba(255,255,255,0.03);
}
.bar-chart-row:last-child { border-bottom: none; }
.bar-chart-label { flex: 0 0 90px; font-size: 12px; color: var(--text-secondary); }
.bar-chart-bar {
    flex: 1;
    background: rgba(255,255,255,0.04);
    border-radius: 6px;
    height: 24px;
    overflow: hidden;
}
.bar-chart-fill {
    height: 100%;
    border-radius: 6px;
    display: flex;
    align-items: center;
    padding-left: 8px;
    font-family: var(--mono);
    font-size: 11px;
    color: rgba(0,0,0,0.7);
    font-weight: 700;
    transition: width 0.5s ease;
}
.bar-chart-val {
    flex: 0 0 65px; text-align: right;
    font-family: var(--mono); font-size: 12px; font-weight: 600;
}

/* Phasen-Karten */
.phase-card {
    background: var(--card);
    border: 1px solid var(--card-border);
    border-radius: var(--radius);
    padding: 14px;
    margin-bottom: 10px;
    backdrop-filter: blur(10px);
}
.phase-card.active-phase {
    border-color: rgba(0,255,0,0.2);
    box-shadow: 0 0 15px rgba(0,255,0,0.05);
}
.phase-card h3 {
    font-size: 15px;
    font-weight: 700;
    margin-bottom: 10px;
    color: #fff;
}
.phase-card .criterion {
    padding: 3px 0;
    font-size: 13px;
    color: var(--text);
}
.phase-status {
    display: inline-block;
    font-size: 10px;
    padding: 2px 10px;
    border-radius: 10px;
    margin-left: 8px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.ps-aktiv { background: rgba(0,255,0,0.12); color: var(--green); }
.ps-bereit { background: rgba(255,204,0,0.12); color: var(--yellow); }
.ps-nicht { background: rgba(255,255,255,0.04); color: var(--dim); }

/* Tod-Liste */
.tod-item {
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.04);
    border-radius: 10px;
    padding: 10px;
    margin-bottom: 8px;
}
.tod-item.schlaf { border-left: 3px solid var(--yellow); }
.tod-item.tod { border-left: 3px solid var(--red); }

/* Exploration Pill */
.exploration-pill {
    display: inline-block;
    font-family: var(--mono);
    font-size: 12px;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: 8px;
    margin-left: 4px;
}
.ep-explore { background: rgba(255,204,0,0.1); color: var(--yellow); }
.ep-exploit { background: rgba(0,255,0,0.1); color: var(--green); }

/* Stresstest */
.btn-stress { border-color: rgba(255,136,0,0.3); color: var(--orange); }
.btn-stress:hover { background: rgba(255,136,0,0.08); }
.btn-stress:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-stress:disabled:active { transform: none; }
.test-banner {
    background: linear-gradient(135deg, rgba(255,136,0,0.15), rgba(255,68,68,0.1));
    border: 1px solid rgba(255,136,0,0.3);
    border-radius: var(--radius);
    padding: 10px 14px;
    margin-bottom: 10px;
    font-size: 14px;
    font-weight: 600;
    color: var(--orange);
    display: flex;
    align-items: center;
    gap: 8px;
    animation: pulse-border 2s infinite;
}
@keyframes pulse-border { 50% { border-color: rgba(255,136,0,0.6); } }
.test-log-highlight {
    border-left: 3px solid var(--yellow);
    padding-left: 8px;
}
</style>
</head>
<body>

<!-- Tab: Dashboard -->
<div class="page active" id="page-dashboard">
    <div class="page-header">
        <span class="page-title">Genesis EKG</span>
        <span class="status-badge" id="status-badge">...</span>
    </div>
    <div id="dashboard-content"><div class="c-dim" style="text-align:center;padding:40px">Verbinde...</div></div>
</div>

<!-- Tab: Körper -->
<div class="page" id="page-koerper">
    <div class="page-header">
        <span class="page-title">Körper</span>
        <span class="status-badge" id="status-badge-k">...</span>
    </div>
    <div id="koerper-content"></div>
</div>

<!-- Tab: Gedächtnis -->
<div class="page" id="page-gedaechtnis">
    <div class="page-header"><span class="page-title">Gedächtnis</span></div>
    <div id="gedaechtnis-content"><div class="c-dim">Lade...</div></div>
</div>

<!-- Tab: Verhalten -->
<div class="page" id="page-verhalten">
    <div class="page-header"><span class="page-title">Verhalten</span></div>
    <div id="verhalten-content"><div class="c-dim">Lade...</div></div>
</div>

<!-- Tab: Phasen -->
<div class="page" id="page-phasen">
    <div class="page-header"><span class="page-title">Phasen</span></div>
    <div id="phasen-content"><div class="c-dim">Lade...</div></div>
</div>

<!-- Tab: Logs -->
<div class="page" id="page-logs">
    <div class="page-header"><span class="page-title">Logs</span></div>
    <div id="test-banner-logs" style="display:none"></div>
    <div class="log-hint">Logs werden täglich um 00:00 rotiert</div>
    <div class="log-panel" id="log-panel">
        <div id="log-content"></div>
    </div>
</div>

<!-- Tab: Steuerung -->
<div class="page" id="page-steuerung">
    <div class="page-header">
        <span class="page-title">Steuerung</span>
        <span class="status-badge" id="status-badge-s">...</span>
    </div>
    <div class="card">
        <div class="card-title">Schlaf / Neustart</div>
        <div class="controls">
            <button class="btn-sleep" id="btn-sleep" onclick="sendSignal('sleep')">Gute Nacht</button>
            <button class="btn-wake" id="btn-wake" onclick="sendSignal('wake')">Aufwecken</button>
            <button class="btn-restart" id="btn-restart" onclick="sendSignal('restart')">Neustart</button>
        </div>
    </div>
    <div class="card">
        <div class="card-title">Eltern-Signale</div>
        <div class="controls">
            <button class="btn-good" id="btn-good" onclick="sendSignal('good')">Gut</button>
            <button class="btn-bad" id="btn-bad" onclick="sendSignal('bad')">Schlecht</button>
        </div>
    </div>
    <div class="card">
        <div class="card-title">Stresstests</div>
        <div id="test-status-ctrl"></div>
        <div class="controls">
            <button class="btn-stress" id="btn-test-cpu" onclick="starteTest('cpu')">CPU-Test</button>
            <button class="btn-stress" id="btn-test-ram" onclick="starteTest('ram')">RAM-Test</button>
            <button class="btn-stress" id="btn-test-kombi" onclick="starteTest('kombi')">Kombi-Test</button>
            <button class="btn-export" onclick="exportTestLogs()">Test-Logs (JSON)</button>
        </div>
    </div>
    <div class="card">
        <div class="card-title">Export</div>
        <div class="controls">
            <button class="btn-export" onclick="exportJSON()">Komplett-Export (JSON)</button>
            <button class="btn-export" onclick="exportLogs()">Logs exportieren</button>
        </div>
    </div>
    <div class="card">
        <div class="card-title">Log-Archiv</div>
        <div id="archiv-liste"><div class="c-dim" style="padding:8px;font-size:13px">Lade...</div></div>
    </div>
</div>

<!-- Tab-Bar -->
<nav class="tab-bar">
    <a class="tab active" onclick="switchTab('dashboard')"><span class="icon">📊</span>Home</a>
    <a class="tab" onclick="switchTab('koerper')"><span class="icon">🫀</span>Körper</a>
    <a class="tab" onclick="switchTab('gedaechtnis')"><span class="icon">🧠</span>Memory</a>
    <a class="tab" onclick="switchTab('verhalten')"><span class="icon">🎯</span>Stats</a>
    <a class="tab" onclick="switchTab('phasen')"><span class="icon">📋</span>Phasen</a>
    <a class="tab" onclick="switchTab('logs')"><span class="icon">📜</span>Logs</a>
    <a class="tab" onclick="switchTab('steuerung')"><span class="icon">⚙️</span>Control</a>
</nav>

<script>
/* --- Navigation --- */
var currentTab = 'dashboard';
function switchTab(name) {
    document.querySelectorAll('.page').forEach(function(p){p.classList.remove('active');});
    document.querySelectorAll('.tab').forEach(function(t){t.classList.remove('active');});
    document.getElementById('page-'+name).classList.add('active');
    var tabs = document.querySelectorAll('.tab');
    var names = ['dashboard','koerper','gedaechtnis','verhalten','phasen','logs','steuerung'];
    for (var i=0;i<names.length;i++) if (names[i]===name) tabs[i].classList.add('active');
    currentTab = name;
    if (name==='gedaechtnis') ladeGedaechtnis();
    if (name==='verhalten') ladeVerhalten();
    if (name==='phasen') ladePhasen();
    if (name==='logs') ladeLogPanel();
    if (name==='steuerung') ladeArchiv();
}

/* --- Helpers --- */
var AKTIONEN = {
    'rechenintensitaet_hoch':'Rechen ↑','rechenintensitaet_runter':'Rechen ↓',
    'rechenintensitaet_minimum':'Rechen MIN','speicher_freigeben':'RAM freigeben',
    'speicher_freigeben_notfall':'RAM Notfall!','speicher_verkleinern':'RAM ↓',
    'speicher_beanspruchen':'RAM beanspruchen','speicher_vergroessern':'RAM ↑',
    'pausieren':'Pausieren','abtastrate_hoch':'Abtastrate ↑','abtastrate_runter':'Abtastrate ↓',
    'nichts_tun':'Nichts tun','nichts':'Nichts tun'
};
function aktName(a){return AKTIONEN[a]||a;}
function fmtTime(ts){
    if(!ts)return '—';
    var d=new Date(ts*1000);
    return d.toLocaleDateString('de-DE',{day:'2-digit',month:'2-digit'})+' '
        +d.toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
}
function fc(w,s){return w<s[0]?'c-green':w<s[1]?'c-yellow':w<s[2]?'c-orange':'c-red';}
function fi(w,s){return w>s[0]?'c-green':w>s[1]?'c-yellow':w>s[2]?'c-orange':'c-red';}
function bar(wert,farbe){
    var p=Math.max(0,Math.min(100,wert*100));
    return '<div class="bar-container"><div class="bar-fill" style="width:'+p+'%;background:'+farbe+'"></div></div>';
}
function wachZeit(sek){
    sek=sek||0;var h=Math.floor(sek/3600),m=Math.floor((sek%3600)/60),s=Math.floor(sek%60);
    if(h>0)return h+'h '+m+'m';if(m>0)return m+'m '+s+'s';return s+'s';
}
function interpretiere(g){
    var s=g.schmerz||0,e=!!g.exploration,a=g.aktion||'',m=g.modus||'';
    if(s>0.6&&e)return['Es schreit','c-red'];
    if(a==='pausieren')return['Es schläft','c-cyan'];
    if(e&&s<0.15)return['Es lernt','c-cyan'];
    if(s<0.15&&!e)return['Es ist zufrieden','c-green'];
    if(s>0.35&&e)return['Es hat Angst','c-orange'];
    if(!e)return['Es erinnert sich','c-green'];
    if(m==='wachphase')return['Es ist aufgewacht','c-yellow'];
    return['Es existiert','c-dim'];
}
/* Zustand kompakt: Nur abweichende Sensoren zeigen */
var NORMAL_WERTE = {
    'cpu_temp':'normal','vm_ram':'frei','cpu_last_eigen':'niedrig',
    'luefter':'leise','host_cpu_last':'niedrig','host_ram':'frei'
};
var ZUSTAND_LABELS = {
    'cpu_temp':'CPU','vm_ram':'VM-RAM','cpu_last_eigen':'CPU-Last',
    'luefter':'Lüfter','host_cpu_last':'Host-CPU','host_ram':'Host-RAM'
};
function zustandKompakt(z){
    var teile=[];
    for(var k in z){
        var norm = NORMAL_WERTE[k];
        // Mehrere Werte als "normal" behandeln
        if(z[k]===norm || z[k]==='niedrig' || z[k]==='leise' || z[k]==='frei' || z[k]==='kühl' || z[k]==='normal') continue;
        teile.push((ZUSTAND_LABELS[k]||k)+': '+z[k]);
    }
    if(teile.length===0) return '<span class="c-dim">Normalzustand</span>';
    return teile.join(', ');
}

/* --- Status-Badge --- */
function setBadge(gStatus){
    var labels={'lebt':'lebt','schlaeft':'schläft','tot':'tot'};
    var badges=document.querySelectorAll('[id^="status-badge"]');
    for(var i=0;i<badges.length;i++){
        badges[i].textContent=labels[gStatus]||'?';
        badges[i].className='status-badge status-'+gStatus;
    }
}

/* --- Dashboard Tab --- */
function renderDashboard(daten){
    var g=daten.genesis,el=document.getElementById('dashboard-content');
    if(!g){el.innerHTML='<div id="warnstufe" class="warn-offline">Offline</div>';return;}
    var schmerz=g.schmerz||0,wohl=g.wohlbefinden||0,stufe=g.warnstufe||'unbekannt';
    var wC='warn-'+stufe;if(stufe==='gefahr')wC='warn-panik';
    var interp=interpretiere(g);
    var aktion=g.aktion?aktName(g.aktion):'—';
    if(g.reflex_aktiv)aktion='⚡ REFLEX';
    var cache=g.cache_mb||0,rechen=g.rechen_level||0;
    var sF=schmerz<0.15?'var(--green)':schmerz<0.35?'var(--yellow)':schmerz<0.6?'var(--orange)':'var(--red)';
    var wF=wohl<0.3?'var(--red)':wohl<0.6?'var(--yellow)':'var(--green)';
    var h='';
    h+='<div id="warnstufe" class="'+wC+'">'+stufe+'</div>';
    h+='<div class="dual">';
    h+='<div class="card"><div class="card-title">Schmerz</div>';
    h+='<div class="big-number" style="color:'+sF+'">'+schmerz.toFixed(3)+'</div>';
    h+=bar(schmerz,sF)+'</div>';
    h+='<div class="card"><div class="card-title">Wohlbefinden</div>';
    h+='<div class="big-number" style="color:'+wF+'">'+wohl.toFixed(3)+'</div>';
    h+=bar(wohl,wF)+'</div></div>';
    // Interpretation — dezenter
    h+='<div class="card"><div class="interpretation '+interp[1]+'">'+interp[0]+'</div></div>';
    // Aktivität (inkl. Rechen + Abtastrate)
    h+='<div class="card"><div class="card-title">Aktivität</div>';
    h+='<div class="row"><span class="label">Aktion</span><span class="value c-cyan">'+aktion+'</span></div>';
    h+='<div class="row"><span class="label">Modus</span><span class="value">'
        +'<span class="exploration-pill '+(g.exploration?'ep-explore':'ep-exploit')+'">'
        +(g.exploration?'Exploration':'Exploitation')+'</span></span></div>';
    h+='<div class="row"><span class="label">Cache</span><span class="value '+(cache<500?'c-green':cache<1000?'c-yellow':'c-red')+'">'+cache.toFixed(0)+' MB</span></div>';
    h+='<div class="row"><span class="label">Rechen</span><span class="value '+(rechen<0.5?'c-green':rechen<0.8?'c-yellow':'c-red')+'">'+(rechen*100).toFixed(0)+'%</span></div>';
    h+='<div class="row"><span class="label">Abtastrate</span><span class="value c-cyan">'+(g.abtastrate||0).toFixed(1)+' Hz</span></div>';
    h+='<div class="row"><span class="label">Wach seit</span><span class="value c-text">'+wachZeit(g.wach_seit)+'</span></div>';
    h+='</div>';
    // Lernen (kompakt)
    h+='<div class="card"><div class="card-title">Lernen</div>';
    h+='<div class="row"><span class="label">Erfahrungen heute</span><span class="value c-cyan">'+(g.erfahrungen_heute||0)+'</span></div>';
    h+='<div class="row"><span class="label">Langzeit</span><span class="value c-cyan">'+(g.erfahrungen_langzeit||0)+'</span></div>';
    h+='<div class="row"><span class="label">Tode</span><span class="value '+((g.tode_gesamt||0)>0?'c-red':'c-green')+'">'+(g.tode_gesamt||0)+'</span></div>';
    h+='</div>';
    el.innerHTML=h;
}

/* --- Körper Tab --- */
function renderKoerper(daten){
    var g=daten.genesis,el=document.getElementById('koerper-content');
    if(!g){el.innerHTML='<div class="c-dim">Keine Daten</div>';return;}
    var roh=g.rohwerte||{},h='';
    h+='<div class="card"><div class="card-title">Vitalwerte</div>';
    var vw=[
        {l:'CPU Temp',v:roh.cpu_temp_tctl||0,u:'°C',c:fc(roh.cpu_temp_tctl||0,[60,75,85])},
        {l:'VM RAM frei',v:roh.vm_ram_frei_mb||0,u:' MB',c:fi(roh.vm_ram_frei_mb||0,[500,200,50])},
        {l:'Host CPU',v:roh.host_cpu_last||0,u:'%',c:fc(roh.host_cpu_last||0,[50,75,90])},
        {l:'Eigen RAM',v:roh.eigen_ram_mb||0,u:' MB',c:fc(roh.eigen_ram_mb||0,[100,300,800])},
        {l:'Eigen CPU',v:roh.eigen_cpu_prozent||0,u:'%',c:fc(roh.eigen_cpu_prozent||0,[30,60,90])},
        {l:'Lüfter',v:roh.luefter_rpm||0,u:' RPM',c:fc(roh.luefter_rpm||0,[2000,3500,4500])},
    ];
    for(var i=0;i<vw.length;i++){
        h+='<div class="row"><span class="label">'+vw[i].l+'</span>';
        h+='<span class="value '+vw[i].c+'">'+vw[i].v.toFixed(vw[i].u==='%'||vw[i].u==='°C'?1:0)+vw[i].u+'</span></div>';
    }
    h+='<div class="row"><span class="label">Rechen-Level</span><span class="value '
        +((g.rechen_level||0)<0.5?'c-green':(g.rechen_level||0)<0.8?'c-yellow':'c-red')+'">'
        +((g.rechen_level||0)*100).toFixed(0)+'%</span></div>';
    h+='<div class="row"><span class="label">Abtastrate</span><span class="value c-cyan">'+(g.abtastrate||0).toFixed(1)+' Hz</span></div>';
    h+='<div class="row"><span class="label">Cache</span><span class="value '
        +((g.cache_mb||0)<500?'c-green':(g.cache_mb||0)<1000?'c-yellow':'c-red')+'">'
        +(g.cache_mb||0).toFixed(0)+' MB</span></div>';
    h+='</div>';
    // Schmerz-Beiträge
    var sd=g.schmerz_details;
    if(sd){
        h+='<div class="card"><div class="card-title">Schmerz-Beiträge</div>';
        var sArr=[],sL={cpu_temp_tctl:'CPU Temp',vm_ram_frei_mb:'VM RAM',eigen_ram_mb:'Eigen RAM',eigen_cpu_prozent:'Eigen CPU',host_cpu_last:'Host CPU',luefter_rpm:'Lüfter'};
        var sE={cpu_temp_tctl:'°C',vm_ram_frei_mb:' MB',eigen_ram_mb:' MB',eigen_cpu_prozent:'%',host_cpu_last:'%',luefter_rpm:' RPM'};
        for(var k in sd) sArr.push({name:k,label:sL[k]||k,einheit:sE[k]||'',d:sd[k]});
        sArr.sort(function(a,b){return(b.d.beitrag||0)-(a.d.beitrag||0);});
        for(var j=0;j<sArr.length;j++){
            var s=sArr[j],b=s.d.beitrag||0;
            var bF=b<=0?'var(--green)':b<=0.1?'var(--yellow)':b<=0.3?'var(--orange)':'var(--red)';
            var bP=Math.min(100,b*333);
            var bC=b<=0?'c-green':b<=0.1?'c-yellow':b<=0.3?'c-orange':'c-red';
            h+='<div class="sensor-row">';
            h+='<span class="sensor-name">'+s.label+'</span>';
            h+='<span class="sensor-wert" style="color:'+bF+'">'+(s.d.rohwert||0).toFixed(1)+s.einheit+'</span>';
            h+='<span class="sensor-kat">'+( s.d.kategorie||'?')+'</span>';
            h+='<div class="sensor-bar-wrap"><div class="sensor-bar-fill" style="width:'+bP+'%;background:'+bF+'"></div></div>';
            h+='<span class="sensor-beitrag '+bC+'">'+b.toFixed(3)+'</span>';
            h+='</div>';
        }
        h+='</div>';
    }
    el.innerHTML=h;
}

/* --- Gedächtnis Tab --- */
function ladeGedaechtnis(){
    Promise.all([
        fetch('/api/langzeit').then(function(r){return r.json();}),
        fetch('/api/tode').then(function(r){return r.json();}),
        fetch('/api/kurzzeit/stats').then(function(r){return r.json();})
    ]).then(function(res){
        var lang=res[0],tode=res[1],kurz=res[2];
        var el=document.getElementById('gedaechtnis-content'),h='';
        // Kurzzeit
        h+='<div class="card"><div class="card-title">Kurzzeit (heute)</div>';
        h+='<div class="row"><span class="label">Erfahrungen</span><span class="value c-cyan">'+kurz.gesamt+'</span></div>';
        h+='</div>';
        // Langzeit
        h+='<div class="card"><div class="card-title">Langzeit — '+lang.gesamt+' Muster</div>';
        if(lang.eintraege.length>0){
            h+='<div style="overflow-x:auto"><table class="mem-table"><thead><tr>';
            h+='<th>Aktion</th><th>Zustand</th><th>Δ</th><th>#</th>';
            h+='</tr></thead><tbody>';
            for(var i=0;i<lang.eintraege.length;i++){
                var e=lang.eintraege[i],delta=e.durchschnitt_delta;
                var dC=delta<-0.01?'c-green':delta>0.01?'c-red':'c-dim';
                h+='<tr><td class="c-cyan">'+aktName(e.aktion)+'</td>';
                h+='<td class="zustand-cell">'+zustandKompakt(e.zustand)+'</td>';
                h+='<td class="'+dC+'">'+delta.toFixed(4)+'</td>';
                h+='<td class="c-text">'+e.anzahl+'</td></tr>';
            }
            h+='</tbody></table></div>';
        } else {
            h+='<div class="c-dim" style="padding:12px;text-align:center">Noch keine gelernten Muster</div>';
        }
        h+='</div>';
        // Tode
        h+='<div class="card"><div class="card-title">Tod-Historie — '+tode.gesamt_tode+' Tode, '+tode.gesamt_schlaf+' Schlaf</div>';
        if(tode.tode.length>0){
            for(var j=0;j<tode.tode.length;j++){
                var t=tode.tode[j];
                var cls=t.war_schlaf?'schlaf':'tod',typ=t.war_schlaf?'😴 Schlaf':'💀 Tod';
                h+='<div class="tod-item '+cls+'">';
                h+='<div class="row"><span class="label">'+typ+'</span><span class="value c-text">'+fmtTime(t.zeitstempel_tod)+'</span></div>';
                h+='<div class="row"><span class="label">Aufgewacht</span><span class="value c-dim">'+fmtTime(t.zeitstempel_aufwachen)+'</span></div>';
                h+='<div class="row"><span class="label">Schmerz</span><span class="value '+(t.letzter_schmerz>0.3?'c-red':'c-green')+'">'+t.letzter_schmerz.toFixed(3)+'</span></div>';
                h+='</div>';
            }
        } else {
            h+='<div class="c-dim" style="padding:12px;text-align:center">Keine Ereignisse</div>';
        }
        h+='</div>';
        el.innerHTML=h;
    }).catch(function(){});
}

/* --- Verhalten Tab --- */
function ladeVerhalten(){
    fetch('/api/kurzzeit/stats').then(function(r){return r.json();}).then(function(kurz){
        var el=document.getElementById('verhalten-content'),h='';
        var gData=_lastStatus;
        if(gData&&gData.genesis){
            var g=gData.genesis;
            h+='<div class="card"><div class="card-title">Aktuelle Strategie</div>';
            h+='<div class="row"><span class="label">Modus</span><span class="value">'
                +'<span class="exploration-pill '+(g.exploration?'ep-explore':'ep-exploit')+'">'
                +(g.exploration?'Exploration':'Exploitation')+'</span></span></div>';
            h+='<div class="row"><span class="label">Aktuelle Aktion</span><span class="value c-cyan">'+aktName(g.aktion||'')+'</span></div>';
            h+='</div>';
        }
        // Balkendiagramm
        h+='<div class="card"><div class="card-title">Aktions-Verteilung — '+kurz.gesamt+' Erfahrungen</div>';
        var maxAnz=0,aktArr=[];
        for(var a in kurz.aktionen){
            aktArr.push({name:a,anz:kurz.aktionen[a].anzahl,avg:kurz.aktionen[a].avg_delta});
            if(kurz.aktionen[a].anzahl>maxAnz) maxAnz=kurz.aktionen[a].anzahl;
        }
        aktArr.sort(function(a,b){return b.anz-a.anz;});
        if(aktArr.length>0){
            for(var i=0;i<aktArr.length;i++){
                var ak=aktArr[i];
                var pct=maxAnz>0?(ak.anz/maxAnz*100):0;
                var barC=ak.avg<-0.02?'var(--green)':ak.avg>0.02?'var(--red)':'var(--cyan)';
                h+='<div class="bar-chart-row">';
                h+='<span class="bar-chart-label">'+aktName(ak.name)+'</span>';
                h+='<div class="bar-chart-bar"><div class="bar-chart-fill" style="width:'+pct+'%;background:'+barC+'">'+ak.anz+'</div></div>';
                h+='<span class="bar-chart-val" style="color:'+barC+'">'+ak.avg.toFixed(4)+'</span>';
                h+='</div>';
            }
        } else {
            h+='<div class="c-dim" style="padding:12px;text-align:center">Keine Daten</div>';
        }
        h+='</div>';
        // Legende
        h+='<div class="card"><div class="card-title">Legende (Ø Schmerz-Delta)</div>';
        h+='<div class="row"><span class="label"><span class="c-green">■</span> Grün</span><span class="value c-dim">Senkt Schmerz (Δ &lt; -0.02)</span></div>';
        h+='<div class="row"><span class="label"><span class="c-cyan">■</span> Cyan</span><span class="value c-dim">Neutral (±0.02)</span></div>';
        h+='<div class="row"><span class="label"><span class="c-red">■</span> Rot</span><span class="value c-dim">Erhöht Schmerz (Δ &gt; +0.02)</span></div>';
        h+='</div>';
        el.innerHTML=h;
    }).catch(function(){});
}

/* --- Phasen Tab --- */
function ladePhasen(){
    fetch('/api/phasen').then(function(r){return r.json();}).then(function(p){
        var el=document.getElementById('phasen-content'),h='';
        var ck=function(ok){return ok?'✅':'🔴';};
        var psC=function(s){return s==='aktiv'?'ps-aktiv':s==='bereit'?'ps-bereit':'ps-nicht';};
        // Phase 1
        h+='<div class="phase-card"><h3>Phase 1 — Basis Code <span class="phase-status ps-aktiv">abgeschlossen</span></h3>';
        h+='<div class="criterion">✅ Sensorik, Schmerz, Reflexe</div>';
        h+='<div class="criterion">✅ Schlaf-Wach-Zyklus</div>';
        h+='<div class="criterion">✅ 5 Aktionen + Verfall</div>';
        h+='<div class="criterion">✅ Lernmechanismus + Gedächtnis</div>';
        h+='<div class="criterion">✅ 132 Tests bestanden</div></div>';
        // Phase 2
        var p2=p.phase2;
        h+='<div class="phase-card active-phase"><h3>Phase 2 — Beobachtung <span class="phase-status '+psC(p2.status)+'">'+p2.status+'</span></h3>';
        h+='<div class="criterion">'+ck(p2.kurzzeit_erfahrungen>0)+' System läuft ('+p2.kurzzeit_erfahrungen+' Erfahrungen)</div>';
        h+='<div class="criterion">'+ck(p2.tode_gesamt>0)+' Tode erlebt: '+p2.tode_gesamt+'</div>';
        h+='<div class="criterion">'+ck(p2.langzeit_eintraege>=10)+' Langzeit-Muster: '+p2.langzeit_eintraege+' (Ziel: ≥10)</div>';
        h+='<div class="criterion">🔴 Gezielte Stresstests</div>';
        h+='<div class="criterion">🔴 Dokumentation abgeschlossen</div></div>';
        // Phase 3
        var p3=p.phase3;
        h+='<div class="phase-card"><h3>Phase 3 — Klon-Test <span class="phase-status '+psC(p3.status)+'">'+p3.status+'</span></h3>';
        h+='<div class="criterion">'+ck(p3.baseline_vorhanden)+' Baseline-Daten vorhanden</div>';
        h+='<div class="criterion">🔴 Klone erstellt</div>';
        h+='<div class="criterion">🔴 Vergleich durchgeführt</div></div>';
        // Phase 4
        var p4=p.phase4;
        h+='<div class="phase-card"><h3>Phase 4 — Erweiterter Laufstall <span class="phase-status '+psC(p4.status)+'">'+p4.status+'</span></h3>';
        h+='<div class="criterion">'+ck(p4.muster_ohne_reflex>=3)+' ≥3 sinnvolle Muster (aktuell: '+p4.muster_ohne_reflex+')</div>';
        h+='<div class="criterion">'+ck(p4.aus_tod_gelernt)+' Aus Tod gelernt</div>';
        h+='<div class="criterion">'+ck(p4.stresstest_ueberlebt)+' Stresstest überlebt</div></div>';
        // Phase 5
        h+='<div class="phase-card"><h3>Phase 5 — Laptop <span class="phase-status ps-nicht">'+p.phase5.status+'</span></h3>';
        h+='<div class="criterion">🔴 Phase 4 abgeschlossen</div>';
        h+='<div class="criterion">🔴 Unvorhergesehenes Verhalten</div>';
        h+='<div class="criterion">🔴 48h stabil</div>';
        h+='<div class="criterion">🔴 Klone unterschiedlich</div></div>';
        el.innerHTML=h;
    }).catch(function(){});
}

/* --- Log Tab --- */
function ladeLogPanel(){
    fetch('/api/logs').then(function(r){return r.json();}).then(function(d){
        var el=document.getElementById('log-content');
        if(!d.logs||d.logs.length===0){el.innerHTML='<div class="log-line c-dim">Keine Logs vorhanden</div>';return;}
        var h='';
        for(var i=0;i<d.logs.length;i++){
            h+='<div class="log-line">'+d.logs[i].replace(/</g,'&lt;')+'</div>';
        }
        el.innerHTML=h;
    }).catch(function(){});
}

/* --- Signals & Controls --- */
var _restartPhase=0;
function sendSignal(typ){
    var url='';
    if(typ==='sleep')url='/api/signal/sleep';
    else if(typ==='wake')url='/api/control/wake';
    else if(typ==='restart')url='/api/control/restart';
    else if(typ==='good')url='/api/signal/good';
    else if(typ==='bad')url='/api/signal/bad';
    if(typ==='good'){
        var bg=document.getElementById('btn-good');
        bg.classList.add('btn-flash-green');
        setTimeout(function(){bg.classList.remove('btn-flash-green');},500);
    }else if(typ==='bad'){
        var bb=document.getElementById('btn-bad');
        bb.classList.add('btn-flash-red');
        setTimeout(function(){bb.classList.remove('btn-flash-red');},500);
    }else if(typ==='sleep'){
        document.getElementById('btn-sleep').classList.add('active');
        setTimeout(function(){
            document.getElementById('btn-sleep').classList.remove('active');
            document.getElementById('btn-sleep').classList.add('done');
        },10000);
    }else if(typ==='wake'){
        document.getElementById('btn-wake').classList.add('active');
        setTimeout(function(){document.getElementById('btn-wake').classList.remove('active');},5000);
    }else if(typ==='restart'){
        _restartPhase=1;
        var rb=document.getElementById('btn-restart');
        rb.classList.add('active');rb.textContent='Einschlafen...';
        setTimeout(function(){
            rb.textContent='Aufwecken...';_restartPhase=2;
            fetch('/api/control/wake',{method:'POST'}).then(function(){
                setTimeout(function(){rb.classList.remove('active');rb.textContent='Neustart';_restartPhase=0;},3000);
            });
        },10000);
    }
    fetch(url,{method:'POST'});
}
function exportJSON(){
    fetch('/api/export').then(function(r){return r.json();}).then(function(d){
        var now=new Date();
        var ts=now.getFullYear()+String(now.getMonth()+1).padStart(2,'0')+String(now.getDate()).padStart(2,'0')
            +'_'+String(now.getHours()).padStart(2,'0')+String(now.getMinutes()).padStart(2,'0')
            +String(now.getSeconds()).padStart(2,'0');
        var blob=new Blob([JSON.stringify(d,null,2)],{type:'application/json'});
        var url=URL.createObjectURL(blob);
        var a=document.createElement('a');
        a.href=url;a.download='genesis_export_'+ts+'.json';a.click();
        URL.revokeObjectURL(url);
    });
}
function exportLogs(){
    var now=new Date();
    var ts=now.getFullYear()+String(now.getMonth()+1).padStart(2,'0')+String(now.getDate()).padStart(2,'0')
        +'_'+String(now.getHours()).padStart(2,'0')+String(now.getMinutes()).padStart(2,'0')
        +String(now.getSeconds()).padStart(2,'0');
    fetch('/api/logs/export').then(function(r){return r.blob();}).then(function(blob){
        var url=URL.createObjectURL(blob);
        var a=document.createElement('a');
        a.href=url;a.download='genesis_log_'+ts+'.txt';a.click();
        URL.revokeObjectURL(url);
    });
}

/* --- Stresstests --- */
function starteTest(typ){
    if(!confirm('Stresstest "'+typ+'" starten?')) return;
    fetch('/api/test/'+typ,{method:'POST'}).then(function(r){return r.json();}).then(function(d){
        if(!d.ok) alert('Fehler: '+d.fehler);
    });
}
function exportTestLogs(){
    fetch('/api/logs/test').then(function(r){return r.json();}).then(function(d){
        var blob=new Blob([JSON.stringify(d,null,2)],{type:'application/json'});
        var url=URL.createObjectURL(blob);
        var a=document.createElement('a');
        a.href=url;a.download='genesis_test_logs.json';a.click();
        URL.revokeObjectURL(url);
    });
}
function fmtVerbleibend(sek){
    var m=Math.floor(sek/60),s=sek%60;
    return m+':'+String(s).padStart(2,'0');
}
function aktualisiereTestStatus(){
    fetch('/api/test/status').then(function(r){return r.json();}).then(function(d){
        var btns=document.querySelectorAll('.btn-stress');
        var statusEl=document.getElementById('test-status-ctrl');
        var bannerEl=document.getElementById('test-banner-logs');
        if(d.aktiv){
            for(var i=0;i<btns.length;i++){btns[i].disabled=true;}
            var txt='Test läuft: '+d.typ.toUpperCase()+' (noch '+fmtVerbleibend(d.verbleibend_sekunden)+')';
            if(statusEl)statusEl.innerHTML='<div class="test-banner">⚡ '+txt+'</div>';
            if(bannerEl){bannerEl.style.display='block';bannerEl.innerHTML='<div class="test-banner">⚡ TEST AKTIV: '+d.typ.toUpperCase()+'-Stress (noch '+fmtVerbleibend(d.verbleibend_sekunden)+')</div>';}
        } else {
            for(var j=0;j<btns.length;j++){btns[j].disabled=false;}
            if(statusEl)statusEl.innerHTML='';
            if(bannerEl){bannerEl.style.display='none';bannerEl.innerHTML='';}
        }
    }).catch(function(){});
}

/* --- Archiv --- */
function ladeArchiv(){
    fetch('/api/logs/archiv').then(function(r){return r.json();}).then(function(d){
        var el=document.getElementById('archiv-liste');
        if(!d.archive||d.archive.length===0){
            el.innerHTML='<div class="c-dim" style="padding:8px;font-size:13px">Keine archivierten Logs</div>';
            return;
        }
        var h='';
        for(var i=0;i<d.archive.length;i++){
            var a=d.archive[i];
            h+='<div class="row" style="padding:6px 0">';
            h+='<span class="label" style="font-size:13px">'+a.datum+'</span>';
            h+='<span class="value" style="display:flex;gap:8px;align-items:center">';
            h+='<span class="c-dim" style="font-size:12px">'+a.groesse_kb.toFixed(1)+' KB</span>';
            h+='<a href="/api/logs/archiv/'+a.datum+'" style="color:var(--cyan);font-size:12px;text-decoration:none" download="genesis_log_'+a.datum+'.txt">Download</a>';
            h+='</span></div>';
        }
        el.innerHTML=h;
    }).catch(function(){});
}

/* --- Haupt-Loop --- */
var _lastStatus=null;
function aktualisiere(){
    fetch('/api/status').then(function(r){return r.json();}).then(function(d){
        _lastStatus=d;
        setBadge(d.genesis_status||'tot');
        if(currentTab==='dashboard')renderDashboard(d);
        else if(currentTab==='koerper')renderKoerper(d);
        if(d.genesis_status==='lebt'){
            document.getElementById('btn-sleep').classList.remove('done');
            document.getElementById('btn-sleep').textContent='Gute Nacht';
        }
    }).catch(function(){
        setBadge('tot');
        if(currentTab==='dashboard'){
            document.getElementById('dashboard-content').innerHTML=
                '<div class="c-dim" style="text-align:center;padding:40px">Verbindung verloren...</div>';
        }
    });
    if(currentTab==='logs')ladeLogPanel();
    if(currentTab==='gedaechtnis')ladeGedaechtnis();
    if(currentTab==='verhalten')ladeVerhalten();
    if(currentTab==='phasen')ladePhasen();
    aktualisiereTestStatus();
}
aktualisiere();
setInterval(aktualisiere,2000);
</script>
</body>
</html>
"""


class GenesisHandler(BaseHTTPRequestHandler):
    """HTTP-Handler für das Genesis Web-Dashboard."""

    def do_GET(self) -> None:
        """Behandelt GET-Anfragen."""
        if self.path == "/api/status":
            self._sende_json(_api_daten())
        elif self.path == "/api/logs":
            self._sende_json({"logs": _lese_logs(50)})
        elif self.path == "/api/logs/export":
            self._sende_log_export()
        elif self.path == "/api/langzeit":
            self._sende_json(_api_langzeit())
        elif self.path == "/api/tode":
            self._sende_json(_api_tode())
        elif self.path == "/api/kurzzeit/stats":
            self._sende_json(_api_kurzzeit_stats())
        elif self.path == "/api/phasen":
            self._sende_json(_api_phasen())
        elif self.path == "/api/export":
            self._sende_json(_api_export())
        elif self.path == "/api/logs/archiv":
            self._sende_json(_api_logs_archiv())
        elif self.path.startswith("/api/logs/archiv/"):
            self._sende_archiv_log()
        elif self.path == "/api/test/status":
            self._sende_json(_api_test_status())
        elif self.path == "/api/logs/test":
            self._sende_json(_api_test_logs())
        else:
            self._sende_html()

    def do_POST(self) -> None:
        """Behandelt POST-Anfragen für Steuerung."""
        antwort: dict[str, Any] = {"ok": False, "fehler": "Unbekannter Endpunkt"}

        if self.path == "/api/signal/sleep":
            _schreibe_signal(f"SLEEP {time.time():.0f}")
            antwort = {"ok": True, "aktion": "sleep"}

        elif self.path == "/api/signal/good":
            _schreibe_signal("GOOD")
            antwort = {"ok": True, "aktion": "good"}

        elif self.path == "/api/signal/bad":
            _schreibe_signal("BAD")
            antwort = {"ok": True, "aktion": "bad"}

        elif self.path == "/api/control/wake":
            if _genesis_lebt() == "lebt":
                antwort = {"ok": False, "fehler": "Genesis läuft bereits"}
            else:
                try:
                    _SIGNAL_DATEI.unlink(missing_ok=True)
                except OSError:
                    pass
                subprocess.Popen(
                    [sys.executable, "-m", "vm.genesis.leben"],
                    env={**__import__("os").environ, "PYTHONPATH": "/opt/genesis"},
                    cwd="/opt/genesis",
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                antwort = {"ok": True, "aktion": "wake"}

        elif self.path == "/api/control/restart":
            _schreibe_signal(f"SLEEP {time.time():.0f}")
            antwort = {"ok": True, "aktion": "restart"}

        elif self.path in ("/api/test/cpu", "/api/test/ram", "/api/test/kombi"):
            test_typ: str = self.path.split("/")[-1]
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

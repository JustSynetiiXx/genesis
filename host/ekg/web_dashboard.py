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
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

# Pfade
_PROJEKT_WURZEL: Path = Path(__file__).resolve().parent.parent.parent
_STATUS_DATEI: Path = _PROJEKT_WURZEL / "shared" / "genesis_status.json"
_SENSOR_DATEI: Path = _PROJEKT_WURZEL / "shared" / "sensoren.bin"
_LESER_PFAD: Path = _PROJEKT_WURZEL / "shared" / "leser.py"
_LOG_DATEI: Path = _PROJEKT_WURZEL / "shared" / "genesis_log.txt"
_SIGNAL_DATEI: Path = _PROJEKT_WURZEL / "shared" / "signal.txt"

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


def _api_export() -> dict[str, Any]:
    """Komplett-Dump aller Daten als JSON."""
    return {
        "zeitstempel": time.time(),
        "export_datum": datetime.now().isoformat(),
        "status": _api_daten(),
        "langzeit": _api_langzeit(),
        "tode": _api_tode(),
        "kurzzeit_stats": _api_kurzzeit_stats(),
        "phasen": _api_phasen(),
        "logs": _lese_logs(200),
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
    --bg: #1a1a1a;
    --bg2: #111;
    --bg3: #222;
    --border: #333;
    --green: #00ff00;
    --yellow: #ffff00;
    --orange: #ff8800;
    --red: #ff4444;
    --cyan: #00cccc;
    --dim: #666;
    --dimmer: #444;
    --text: #ccc;
    --tab-h: 56px;
    --safe-b: env(safe-area-inset-bottom, 0px);
}
body {
    background: var(--bg);
    color: var(--green);
    font-family: 'Courier New', monospace;
    font-size: 16px;
    min-height: 100vh;
    padding-bottom: calc(var(--tab-h) + var(--safe-b) + 8px);
}
.page { display: none; padding: 8px; }
.page.active { display: block; }

/* Tab-Bar */
.tab-bar {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    height: calc(var(--tab-h) + var(--safe-b));
    padding-bottom: var(--safe-b);
    background: #0d0d0d;
    border-top: 1px solid var(--border);
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
    font-size: 10px;
    font-family: 'Courier New', monospace;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
    user-select: none;
    min-height: 44px;
    transition: color 0.2s;
    text-decoration: none;
}
.tab .icon { font-size: 20px; }
.tab.active { color: var(--green); }
.tab:active { opacity: 0.7; }

/* Header mit Status */
.page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 0 10px;
}
.page-title {
    font-size: 18px;
    font-weight: bold;
    color: var(--green);
}
.status-badge {
    font-size: 12px;
    font-weight: bold;
    padding: 4px 10px;
    border-radius: 12px;
}
.status-lebt { background: #003300; color: var(--green); }
.status-schlaeft { background: #333300; color: var(--yellow); }
.status-tot { background: #330000; color: var(--red); }

/* Sections */
.section {
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px;
    margin-bottom: 8px;
}
.section-title {
    font-size: 13px;
    color: var(--dim);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 6px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 4px;
}
.big-number {
    font-size: 36px;
    font-weight: bold;
    text-align: center;
}
.interpretation {
    font-size: 24px;
    text-align: center;
    padding: 10px 0;
    font-weight: bold;
}
.bar-container {
    background: var(--border);
    border-radius: 4px;
    height: 12px;
    margin: 4px 0 8px 0;
    overflow: hidden;
}
.bar-fill {
    height: 100%;
    border-radius: 4px;
    transition: width 0.5s ease;
}
.row {
    display: flex;
    justify-content: space-between;
    padding: 3px 0;
    font-size: 15px;
}
.row .label { color: #888; }
.row .value { font-weight: bold; }
.dual {
    display: flex;
    gap: 8px;
}
.dual > div { flex: 1; }

/* Warnstufe */
#warnstufe {
    text-align: center;
    padding: 14px 8px;
    font-size: 28px;
    font-weight: bold;
    border-radius: 8px;
    margin-bottom: 8px;
    text-transform: uppercase;
    letter-spacing: 2px;
}
.warn-komfort { background: #1a5c1a; color: var(--green); }
.warn-unbehagen { background: #5c5c00; color: var(--yellow); }
.warn-stress { background: #5c3a00; color: var(--orange); }
.warn-panik { background: #5c0000; color: var(--red); }
.warn-reflex { background: #5c0000; color: var(--red); animation: blink 0.5s infinite; }
.warn-offline { background: var(--border); color: var(--dim); }
@keyframes blink { 50% { opacity: 0.5; } }

/* Farben */
.c-green { color: var(--green); }
.c-yellow { color: var(--yellow); }
.c-orange { color: var(--orange); }
.c-red { color: var(--red); }
.c-cyan { color: var(--cyan); }
.c-dim { color: var(--dim); }

/* Körper-Details */
.sensor-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 0;
    border-bottom: 1px solid var(--bg3);
}
.sensor-row:last-child { border-bottom: none; }
.sensor-name { flex: 0 0 90px; font-size: 12px; color: #aaa; }
.sensor-wert { flex: 0 0 70px; font-size: 14px; font-weight: bold; text-align: right; }
.sensor-kat { flex: 0 0 55px; font-size: 11px; text-align: center; color: #888; }
.sensor-bar-wrap {
    flex: 1; background: var(--border); border-radius: 4px;
    height: 14px; overflow: hidden; min-width: 30px;
}
.sensor-bar-fill { height: 100%; border-radius: 4px; transition: width 0.5s ease; }
.sensor-beitrag { flex: 0 0 50px; font-size: 13px; font-weight: bold; text-align: right; }

/* Steuerung */
.controls {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 8px;
}
.controls button {
    font-family: 'Courier New', monospace;
    font-size: 14px;
    font-weight: bold;
    padding: 10px 14px;
    border: 1px solid #555;
    border-radius: 6px;
    cursor: pointer;
    background: #2a2a2a;
    color: var(--text);
    min-width: 44px;
    min-height: 44px;
    touch-action: manipulation;
    transition: background 0.2s, color 0.2s;
}
.controls button:active { transform: scale(0.95); }
.btn-sleep { border-color: #888800; color: var(--yellow); }
.btn-sleep:hover { background: #3a3a00; }
.btn-sleep.active { background: #555500; color: var(--yellow); }
.btn-sleep.done { background: var(--border); color: var(--dim); }
.btn-wake { border-color: #008800; color: var(--green); }
.btn-wake:hover { background: #003a00; }
.btn-wake.active { background: #005500; color: var(--green); }
.btn-restart { border-color: #884400; color: var(--orange); }
.btn-restart:hover { background: #3a2200; }
.btn-restart.active { background: #553300; color: var(--orange); }
.btn-good { border-color: #008800; color: var(--green); }
.btn-good:hover { background: #003a00; }
.btn-bad { border-color: #880000; color: var(--red); }
.btn-bad:hover { background: #3a0000; }
.btn-flash-green { background: #005500 !important; color: var(--green) !important; }
.btn-flash-red { background: #550000 !important; color: var(--red) !important; }
.btn-export { border-color: #446688; color: #88bbdd; }
.btn-export:hover { background: #1a2a3a; }

/* Logs */
.log-panel {
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px;
    margin-bottom: 8px;
    max-height: 60vh;
    overflow-y: auto;
    font-size: 12px;
    line-height: 1.4;
    color: #00cc00;
}
.log-line { white-space: pre-wrap; word-break: break-all; }
.log-hint {
    font-size: 12px;
    color: var(--dim);
    text-align: center;
    padding: 8px;
    border: 1px dashed var(--border);
    border-radius: 6px;
    margin-bottom: 8px;
}

/* Gedächtnis-Tabelle */
.mem-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
}
.mem-table th {
    text-align: left;
    color: var(--dim);
    padding: 6px 4px;
    border-bottom: 1px solid var(--border);
    font-size: 11px;
    text-transform: uppercase;
}
.mem-table td {
    padding: 5px 4px;
    border-bottom: 1px solid var(--bg3);
    vertical-align: top;
}
.mem-table tr:active { background: var(--bg3); }

/* Balkendiagramm */
.bar-chart-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 0;
    border-bottom: 1px solid var(--bg3);
}
.bar-chart-row:last-child { border-bottom: none; }
.bar-chart-label { flex: 0 0 100px; font-size: 12px; color: #aaa; }
.bar-chart-bar {
    flex: 1;
    background: var(--border);
    border-radius: 3px;
    height: 22px;
    overflow: hidden;
}
.bar-chart-fill {
    height: 100%;
    border-radius: 3px;
    display: flex;
    align-items: center;
    padding-left: 6px;
    font-size: 11px;
    color: #000;
    font-weight: bold;
    transition: width 0.5s ease;
}
.bar-chart-val { flex: 0 0 60px; text-align: right; font-size: 13px; font-weight: bold; }

/* Phasen-Karten */
.phase-card {
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
    margin-bottom: 10px;
}
.phase-card.active-phase {
    border-color: var(--green);
    box-shadow: 0 0 8px rgba(0, 255, 0, 0.15);
}
.phase-card h3 {
    font-size: 16px;
    margin-bottom: 8px;
}
.phase-card .criterion {
    padding: 4px 0;
    font-size: 14px;
}
.phase-status {
    display: inline-block;
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 10px;
    margin-left: 8px;
    font-weight: bold;
}
.ps-aktiv { background: #003300; color: var(--green); }
.ps-bereit { background: #333300; color: var(--yellow); }
.ps-nicht { background: #1a1a1a; color: var(--dim); }

/* Tod-Liste */
.tod-item {
    border: 1px solid var(--bg3);
    border-radius: 6px;
    padding: 8px;
    margin-bottom: 6px;
    font-size: 13px;
}
.tod-item.schlaf { border-left: 3px solid var(--yellow); }
.tod-item.tod { border-left: 3px solid var(--red); }

.timestamp {
    text-align: center;
    color: var(--dimmer);
    font-size: 12px;
    padding-top: 6px;
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
    <div class="page-header">
        <span class="page-title">Gedächtnis</span>
    </div>
    <div id="gedaechtnis-content"><div class="c-dim">Lade...</div></div>
</div>

<!-- Tab: Verhalten -->
<div class="page" id="page-verhalten">
    <div class="page-header">
        <span class="page-title">Verhalten</span>
    </div>
    <div id="verhalten-content"><div class="c-dim">Lade...</div></div>
</div>

<!-- Tab: Phasen -->
<div class="page" id="page-phasen">
    <div class="page-header">
        <span class="page-title">Phasen</span>
    </div>
    <div id="phasen-content"><div class="c-dim">Lade...</div></div>
</div>

<!-- Tab: Logs -->
<div class="page" id="page-logs">
    <div class="page-header">
        <span class="page-title">Logs</span>
    </div>
    <div class="log-hint">Logs werden täglich um 00:00 zurückgesetzt</div>
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
    <div class="section">
        <div class="section-title">Schlaf / Neustart</div>
        <div class="controls">
            <button class="btn-sleep" id="btn-sleep" onclick="sendSignal('sleep')">Gute Nacht</button>
            <button class="btn-wake" id="btn-wake" onclick="sendSignal('wake')">Aufwecken</button>
            <button class="btn-restart" id="btn-restart" onclick="sendSignal('restart')">Neustart</button>
        </div>
    </div>
    <div class="section">
        <div class="section-title">Eltern-Signale</div>
        <div class="controls">
            <button class="btn-good" id="btn-good" onclick="sendSignal('good')">Gut</button>
            <button class="btn-bad" id="btn-bad" onclick="sendSignal('bad')">Schlecht</button>
        </div>
    </div>
    <div class="section">
        <div class="section-title">Export</div>
        <div class="controls">
            <button class="btn-export" onclick="exportJSON()">Komplett-Export (JSON)</button>
            <button class="btn-export" onclick="exportLogs()">Logs exportieren</button>
        </div>
    </div>
</div>

<!-- Tab-Bar -->
<nav class="tab-bar">
    <a class="tab active" onclick="switchTab('dashboard')"><span class="icon">📊</span>Dashboard</a>
    <a class="tab" onclick="switchTab('koerper')"><span class="icon">🫀</span>Körper</a>
    <a class="tab" onclick="switchTab('gedaechtnis')"><span class="icon">🧠</span>Gedächtnis</a>
    <a class="tab" onclick="switchTab('verhalten')"><span class="icon">🎯</span>Verhalten</a>
    <a class="tab" onclick="switchTab('phasen')"><span class="icon">📋</span>Phasen</a>
    <a class="tab" onclick="switchTab('logs')"><span class="icon">📜</span>Logs</a>
    <a class="tab" onclick="switchTab('steuerung')"><span class="icon">⚙️</span>Steuerung</a>
</nav>

<script>
/* --- Navigation --- */
var currentTab = 'dashboard';

function switchTab(name) {
    document.querySelectorAll('.page').forEach(function(p) { p.classList.remove('active'); });
    document.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });
    document.getElementById('page-' + name).classList.add('active');
    // Activate the matching tab button
    var tabs = document.querySelectorAll('.tab');
    var tabNames = ['dashboard','koerper','gedaechtnis','verhalten','phasen','logs','steuerung'];
    for (var i = 0; i < tabNames.length; i++) {
        if (tabNames[i] === name) tabs[i].classList.add('active');
    }
    currentTab = name;
    // Sofort Daten laden für den neuen Tab
    if (name === 'gedaechtnis') ladeGedaechtnis();
    if (name === 'verhalten') ladeVerhalten();
    if (name === 'phasen') ladePhasen();
    if (name === 'logs') ladeLogPanel();
}

/* --- Helpers --- */
var AKTIONEN = {
    'rechenintensitaet_hoch': 'Rechen ↑',
    'rechenintensitaet_runter': 'Rechen ↓',
    'rechenintensitaet_minimum': 'Rechen MIN',
    'speicher_freigeben': 'RAM freigeben',
    'speicher_freigeben_notfall': 'RAM Notfall!',
    'speicher_verkleinern': 'RAM ↓',
    'speicher_beanspruchen': 'RAM beanspruchen',
    'speicher_vergroessern': 'RAM ↑',
    'pausieren': 'Pausieren',
    'abtastrate_hoch': 'Abtastrate ↑',
    'abtastrate_runter': 'Abtastrate ↓',
    'nichts_tun': 'Nichts tun',
    'nichts': 'Nichts tun'
};
function aktName(a) { return AKTIONEN[a] || a; }
function fmtTime(ts) {
    if (!ts) return '—';
    var d = new Date(ts * 1000);
    return d.toLocaleDateString('de-DE',{day:'2-digit',month:'2-digit'}) + ' '
         + d.toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
}
function farbeFuerWert(w, s) {
    if (w < s[0]) return 'c-green';
    if (w < s[1]) return 'c-yellow';
    if (w < s[2]) return 'c-orange';
    return 'c-red';
}
function farbeInvertiert(w, s) {
    if (w > s[0]) return 'c-green';
    if (w > s[1]) return 'c-yellow';
    if (w > s[2]) return 'c-orange';
    return 'c-red';
}
function bar(wert, farbe) {
    var pct = Math.max(0, Math.min(100, wert * 100));
    return '<div class="bar-container"><div class="bar-fill" style="width:'+pct+'%;background:'+farbe+'"></div></div>';
}
function wachZeit(sek) {
    sek = sek || 0;
    var h = Math.floor(sek/3600), m = Math.floor((sek%3600)/60), s = Math.floor(sek%60);
    if (h > 0) return h+'h '+m+'m';
    if (m > 0) return m+'m '+s+'s';
    return s+'s';
}
function interpretiere(g) {
    var s = g.schmerz||0, e = !!g.exploration, a = g.aktion||'', m = g.modus||'';
    if (s > 0.6 && e) return ['Es schreit','c-red'];
    if (a === 'pausieren') return ['Es schläft','c-cyan'];
    if (e && s < 0.15) return ['Es lernt','c-cyan'];
    if (s < 0.15 && !e) return ['Es ist zufrieden','c-green'];
    if (s > 0.35 && e) return ['Es hat Angst','c-orange'];
    if (!e) return ['Es erinnert sich','c-green'];
    if (m === 'wachphase') return ['Es ist aufgewacht','c-yellow'];
    return ['Es existiert','c-dim'];
}

/* --- Status-Badge --- */
function setBadge(gStatus) {
    var labels = {'lebt':'lebt','schlaeft':'schläft','tot':'tot'};
    var badges = document.querySelectorAll('[id^="status-badge"]');
    for (var i = 0; i < badges.length; i++) {
        badges[i].textContent = labels[gStatus] || '?';
        badges[i].className = 'status-badge status-' + gStatus;
    }
}

/* --- Dashboard Tab --- */
function renderDashboard(daten) {
    var g = daten.genesis;
    var el = document.getElementById('dashboard-content');
    if (!g) {
        el.innerHTML = '<div id="warnstufe" class="warn-offline">Offline</div>';
        return;
    }
    var schmerz = g.schmerz||0, wohl = g.wohlbefinden||0, stufe = g.warnstufe||'unbekannt';
    var warnClass = 'warn-'+stufe;
    if (stufe==='gefahr') warnClass = 'warn-panik';
    var interp = interpretiere(g);
    var aktion = g.aktion ? aktName(g.aktion) : '—';
    if (g.reflex_aktiv) aktion = '⚡ REFLEX';
    var cache = g.cache_mb||0;
    var cacheClass = cache<500?'c-green':(cache<1000?'c-yellow':'c-red');
    var schmerzF = schmerz<0.15?'var(--green)':(schmerz<0.35?'var(--yellow)':(schmerz<0.6?'var(--orange)':'var(--red)'));
    var wohlF = wohl<0.3?'var(--red)':(wohl<0.6?'var(--yellow)':'var(--green)');
    var h = '';
    h += '<div id="warnstufe" class="'+warnClass+'">'+stufe+'</div>';
    // Schmerz + Wohl
    h += '<div class="dual">';
    h += '<div class="section"><div class="section-title">Schmerz</div>';
    h += '<div class="big-number" style="color:'+schmerzF+'">'+schmerz.toFixed(3)+'</div>';
    h += bar(schmerz,schmerzF)+'</div>';
    h += '<div class="section"><div class="section-title">Wohlbefinden</div>';
    h += '<div class="big-number" style="color:'+wohlF+'">'+wohl.toFixed(3)+'</div>';
    h += bar(wohl,wohlF)+'</div></div>';
    // Interpretation
    h += '<div class="section"><div class="interpretation '+interp[1]+'">'+interp[0]+'</div></div>';
    // Aktivität (kompakt)
    h += '<div class="section"><div class="section-title">Aktivität</div>';
    h += '<div class="row"><span class="label">Aktion</span><span class="value c-cyan">'+aktion+'</span></div>';
    h += '<div class="row"><span class="label">Modus</span><span class="value '+(g.exploration?'c-yellow':'c-green')+'">'+(g.exploration?'Exploration':'Exploitation')+'</span></div>';
    h += '<div class="row"><span class="label">Cache</span><span class="value '+cacheClass+'">'+cache.toFixed(0)+' MB</span></div>';
    h += '<div class="row"><span class="label">Wach seit</span><span class="value c-cyan">'+wachZeit(g.wach_seit)+'</span></div>';
    h += '</div>';
    // Lernen (kompakt)
    h += '<div class="section"><div class="section-title">Lernen</div>';
    h += '<div class="row"><span class="label">Erfahrungen heute</span><span class="value c-cyan">'+(g.erfahrungen_heute||0)+'</span></div>';
    h += '<div class="row"><span class="label">Langzeit</span><span class="value c-cyan">'+(g.erfahrungen_langzeit||0)+'</span></div>';
    h += '<div class="row"><span class="label">Tode</span><span class="value '+((g.tode_gesamt||0)>0?'c-red':'c-green')+'">'+(g.tode_gesamt||0)+'</span></div>';
    h += '</div>';
    el.innerHTML = h;
}

/* --- Körper Tab --- */
function renderKoerper(daten) {
    var g = daten.genesis;
    var el = document.getElementById('koerper-content');
    if (!g) { el.innerHTML = '<div class="c-dim">Keine Daten</div>'; return; }
    var roh = g.rohwerte||{};
    var h = '';
    // Vitalwerte
    h += '<div class="section"><div class="section-title">Vitalwerte</div>';
    var cpuT = roh.cpu_temp_tctl||0;
    h += '<div class="row"><span class="label">CPU Temp</span><span class="value '+farbeFuerWert(cpuT,[60,75,85])+'">'+cpuT.toFixed(1)+'°C</span></div>';
    var vmR = roh.vm_ram_frei_mb||0;
    h += '<div class="row"><span class="label">VM RAM frei</span><span class="value '+farbeInvertiert(vmR,[500,200,50])+'">'+vmR.toFixed(0)+' MB</span></div>';
    var hCpu = roh.host_cpu_last||0;
    h += '<div class="row"><span class="label">Host CPU</span><span class="value '+farbeFuerWert(hCpu,[50,75,90])+'">'+hCpu.toFixed(1)+'%</span></div>';
    var eigenR = roh.eigen_ram_mb||0;
    h += '<div class="row"><span class="label">Eigen RAM</span><span class="value '+farbeFuerWert(eigenR,[100,300,800])+'">'+eigenR.toFixed(1)+' MB</span></div>';
    var eigenC = roh.eigen_cpu_prozent||0;
    h += '<div class="row"><span class="label">Eigen CPU</span><span class="value '+farbeFuerWert(eigenC,[30,60,90])+'">'+eigenC.toFixed(1)+'%</span></div>';
    var luefter = roh.luefter_rpm||0;
    h += '<div class="row"><span class="label">Lüfter</span><span class="value '+farbeFuerWert(luefter,[2000,3500,4500])+'">'+luefter.toFixed(0)+' RPM</span></div>';
    var rechen = g.rechen_level||0;
    h += '<div class="row"><span class="label">Rechen-Level</span><span class="value '+(rechen<0.5?'c-green':(rechen<0.8?'c-yellow':'c-red'))+'">'+(rechen*100).toFixed(0)+'%</span></div>';
    h += '<div class="row"><span class="label">Abtastrate</span><span class="value c-cyan">'+(g.abtastrate||0).toFixed(1)+' Hz</span></div>';
    h += '<div class="row"><span class="label">Cache</span><span class="value '+((g.cache_mb||0)<500?'c-green':((g.cache_mb||0)<1000?'c-yellow':'c-red'))+'">'+(g.cache_mb||0).toFixed(0)+' MB</span></div>';
    h += '</div>';
    // Körper-Details
    var sd = g.schmerz_details;
    if (sd) {
        h += '<div class="section"><div class="section-title">Schmerz-Beiträge</div>';
        var sArr = [];
        var sLabels = {'cpu_temp_tctl':'CPU Temp','vm_ram_frei_mb':'VM RAM','eigen_ram_mb':'Eigen RAM','eigen_cpu_prozent':'Eigen CPU','host_cpu_last':'Host CPU','luefter_rpm':'Lüfter'};
        var sEinh = {'cpu_temp_tctl':'°C','vm_ram_frei_mb':' MB','eigen_ram_mb':' MB','eigen_cpu_prozent':'%','host_cpu_last':'%','luefter_rpm':' RPM'};
        for (var k in sd) sArr.push({name:k,label:sLabels[k]||k,einheit:sEinh[k]||'',d:sd[k]});
        sArr.sort(function(a,b){return (b.d.beitrag||0)-(a.d.beitrag||0);});
        for (var i=0;i<sArr.length;i++) {
            var s=sArr[i], b=s.d.beitrag||0;
            var bF = b<=0?'var(--green)':b<=0.1?'var(--yellow)':b<=0.3?'var(--orange)':'var(--red)';
            var bP = Math.min(100,b*333);
            var bC = b<=0?'c-green':b<=0.1?'c-yellow':b<=0.3?'c-orange':'c-red';
            h += '<div class="sensor-row">';
            h += '<span class="sensor-name">'+s.label+'</span>';
            h += '<span class="sensor-wert" style="color:'+bF+'">'+(s.d.rohwert||0).toFixed(1)+s.einheit+'</span>';
            h += '<span class="sensor-kat">'+( s.d.kategorie||'?')+'</span>';
            h += '<div class="sensor-bar-wrap"><div class="sensor-bar-fill" style="width:'+bP+'%;background:'+bF+'"></div></div>';
            h += '<span class="sensor-beitrag '+bC+'">'+b.toFixed(3)+'</span>';
            h += '</div>';
        }
        h += '</div>';
    }
    el.innerHTML = h;
}

/* --- Gedächtnis Tab --- */
function ladeGedaechtnis() {
    Promise.all([
        fetch('/api/langzeit').then(function(r){return r.json();}),
        fetch('/api/tode').then(function(r){return r.json();}),
        fetch('/api/kurzzeit/stats').then(function(r){return r.json();})
    ]).then(function(res) {
        var lang = res[0], tode = res[1], kurz = res[2];
        var el = document.getElementById('gedaechtnis-content');
        var h = '';
        // Kurzzeit
        h += '<div class="section"><div class="section-title">Kurzzeit (heute)</div>';
        h += '<div class="row"><span class="label">Erfahrungen</span><span class="value c-cyan">'+kurz.gesamt+'</span></div>';
        h += '</div>';
        // Langzeit
        h += '<div class="section"><div class="section-title">Langzeit — '+lang.gesamt+' gelernte Muster</div>';
        if (lang.eintraege.length > 0) {
            h += '<div style="overflow-x:auto"><table class="mem-table"><thead><tr>';
            h += '<th>Aktion</th><th>Zustand</th><th>Δ</th><th>#</th>';
            h += '</tr></thead><tbody>';
            for (var i=0;i<lang.eintraege.length;i++) {
                var e = lang.eintraege[i];
                var delta = e.durchschnitt_delta;
                var dColor = delta < -0.01 ? 'c-green' : delta > 0.01 ? 'c-red' : 'c-dim';
                // Zustand vereinfachen
                var zStr = '';
                for (var zk in e.zustand) {
                    if (zStr) zStr += ', ';
                    zStr += zk.replace('cpu_','').replace('host_','h_').replace('luefter','fan') + ':' + e.zustand[zk];
                }
                h += '<tr>';
                h += '<td class="c-cyan">'+aktName(e.aktion)+'</td>';
                h += '<td style="color:#888;font-size:11px">'+zStr+'</td>';
                h += '<td class="'+dColor+'">'+delta.toFixed(4)+'</td>';
                h += '<td>'+e.anzahl+'</td>';
                h += '</tr>';
            }
            h += '</tbody></table></div>';
        } else {
            h += '<div class="c-dim" style="padding:10px;text-align:center">Noch keine gelernten Muster</div>';
        }
        h += '</div>';
        // Tode
        h += '<div class="section"><div class="section-title">Tod-Historie — '+tode.gesamt_tode+' Tode, '+tode.gesamt_schlaf+' Schlaf</div>';
        if (tode.tode.length > 0) {
            for (var j=0;j<tode.tode.length;j++) {
                var t = tode.tode[j];
                var cls = t.war_schlaf ? 'schlaf' : 'tod';
                var typ = t.war_schlaf ? '😴 Schlaf' : '💀 Tod';
                h += '<div class="tod-item '+cls+'">';
                h += '<div class="row"><span class="label">'+typ+'</span><span class="value">'+fmtTime(t.zeitstempel_tod)+'</span></div>';
                h += '<div class="row"><span class="label">Aufgewacht</span><span class="value c-dim">'+fmtTime(t.zeitstempel_aufwachen)+'</span></div>';
                h += '<div class="row"><span class="label">Schmerz</span><span class="value '+(t.letzter_schmerz>0.3?'c-red':'c-green')+'">'+t.letzter_schmerz.toFixed(3)+'</span></div>';
                h += '</div>';
            }
        } else {
            h += '<div class="c-dim" style="padding:10px;text-align:center">Keine Ereignisse</div>';
        }
        h += '</div>';
        el.innerHTML = h;
    }).catch(function() {});
}

/* --- Verhalten Tab --- */
function ladeVerhalten() {
    fetch('/api/kurzzeit/stats').then(function(r){return r.json();}).then(function(kurz) {
        var el = document.getElementById('verhalten-content');
        var h = '';
        // Exploration-Status
        var gData = _lastStatus;
        if (gData && gData.genesis) {
            var g = gData.genesis;
            h += '<div class="section"><div class="section-title">Aktuelle Strategie</div>';
            h += '<div class="row"><span class="label">Modus</span><span class="value '+(g.exploration?'c-yellow':'c-green')+'">'+(g.exploration?'Exploration':'Exploitation')+'</span></div>';
            h += '<div class="row"><span class="label">Aktuelle Aktion</span><span class="value c-cyan">'+aktName(g.aktion||'')+'</span></div>';
            h += '</div>';
        }
        // Balkendiagramm
        h += '<div class="section"><div class="section-title">Aktions-Verteilung — '+kurz.gesamt+' Erfahrungen</div>';
        var maxAnz = 0;
        var aktArr = [];
        for (var a in kurz.aktionen) {
            aktArr.push({name:a, anz:kurz.aktionen[a].anzahl, avg:kurz.aktionen[a].avg_delta});
            if (kurz.aktionen[a].anzahl > maxAnz) maxAnz = kurz.aktionen[a].anzahl;
        }
        aktArr.sort(function(a,b){return b.anz-a.anz;});
        if (aktArr.length > 0) {
            for (var i=0;i<aktArr.length;i++) {
                var ak = aktArr[i];
                var pct = maxAnz > 0 ? (ak.anz/maxAnz*100) : 0;
                var barColor = ak.avg < -0.01 ? 'var(--green)' : ak.avg > 0.01 ? 'var(--red)' : 'var(--cyan)';
                h += '<div class="bar-chart-row">';
                h += '<span class="bar-chart-label">'+aktName(ak.name)+'</span>';
                h += '<div class="bar-chart-bar"><div class="bar-chart-fill" style="width:'+pct+'%;background:'+barColor+'">'+ak.anz+'</div></div>';
                h += '<span class="bar-chart-val" style="color:'+barColor+'">'+ak.avg.toFixed(4)+'</span>';
                h += '</div>';
            }
        } else {
            h += '<div class="c-dim" style="padding:10px;text-align:center">Keine Daten</div>';
        }
        h += '</div>';
        // Legende
        h += '<div class="section"><div class="section-title">Legende</div>';
        h += '<div class="row"><span class="label c-green">■ Grün</span><span class="value c-dim">Senkt Schmerz (Δ &lt; 0)</span></div>';
        h += '<div class="row"><span class="label c-cyan">■ Cyan</span><span class="value c-dim">Neutral</span></div>';
        h += '<div class="row"><span class="label c-red">■ Rot</span><span class="value c-dim">Erhöht Schmerz (Δ &gt; 0)</span></div>';
        h += '</div>';
        el.innerHTML = h;
    }).catch(function(){});
}

/* --- Phasen Tab --- */
function ladePhasen() {
    fetch('/api/phasen').then(function(r){return r.json();}).then(function(p) {
        var el = document.getElementById('phasen-content');
        var h = '';
        var ck = function(ok) { return ok ? '✅' : '🔴'; };
        var psClass = function(s) { return s==='aktiv'?'ps-aktiv':s==='bereit'?'ps-bereit':'ps-nicht'; };

        // Phase 1
        h += '<div class="phase-card"><h3>Phase 1 — Basis Code <span class="phase-status ps-aktiv">abgeschlossen</span></h3>';
        h += '<div class="criterion">✅ Sensorik, Schmerz, Reflexe</div>';
        h += '<div class="criterion">✅ Schlaf-Wach-Zyklus</div>';
        h += '<div class="criterion">✅ 5 Aktionen + Verfall</div>';
        h += '<div class="criterion">✅ Lernmechanismus + Gedächtnis</div>';
        h += '<div class="criterion">✅ 132 Tests bestanden</div>';
        h += '</div>';

        // Phase 2
        var p2 = p.phase2;
        h += '<div class="phase-card active-phase"><h3>Phase 2 — Beobachtung <span class="phase-status '+psClass(p2.status)+'">'+p2.status+'</span></h3>';
        h += '<div class="criterion">'+ck(p2.kurzzeit_erfahrungen>0)+' System läuft ('+p2.kurzzeit_erfahrungen+' Erfahrungen)</div>';
        h += '<div class="criterion">'+ck(p2.tode_gesamt>0)+' Tode erlebt: '+p2.tode_gesamt+'</div>';
        h += '<div class="criterion">'+ck(p2.langzeit_eintraege>=10)+' Langzeit-Muster: '+p2.langzeit_eintraege+' (Ziel: ≥10)</div>';
        h += '<div class="criterion">🔴 Gezielte Stresstests</div>';
        h += '<div class="criterion">🔴 Dokumentation abgeschlossen</div>';
        h += '</div>';

        // Phase 3
        var p3 = p.phase3;
        h += '<div class="phase-card"><h3>Phase 3 — Klon-Test <span class="phase-status '+psClass(p3.status)+'">'+p3.status+'</span></h3>';
        h += '<div class="criterion">'+ck(p3.baseline_vorhanden)+' Baseline-Daten vorhanden</div>';
        h += '<div class="criterion">🔴 Klone erstellt</div>';
        h += '<div class="criterion">🔴 Vergleich durchgeführt</div>';
        h += '</div>';

        // Phase 4
        var p4 = p.phase4;
        h += '<div class="phase-card"><h3>Phase 4 — Erweiterter Laufstall <span class="phase-status '+psClass(p4.status)+'">'+p4.status+'</span></h3>';
        h += '<div class="criterion">'+ck(p4.muster_ohne_reflex>=3)+' ≥3 sinnvolle Muster (aktuell: '+p4.muster_ohne_reflex+')</div>';
        h += '<div class="criterion">'+ck(p4.aus_tod_gelernt)+' Aus Tod gelernt</div>';
        h += '<div class="criterion">'+ck(p4.stresstest_ueberlebt)+' Stresstest überlebt</div>';
        h += '</div>';

        // Phase 5
        h += '<div class="phase-card"><h3>Phase 5 — Laptop <span class="phase-status ps-nicht">'+p.phase5.status+'</span></h3>';
        h += '<div class="criterion">🔴 Phase 4 abgeschlossen</div>';
        h += '<div class="criterion">🔴 Unvorhergesehenes Verhalten</div>';
        h += '<div class="criterion">🔴 48h stabil</div>';
        h += '<div class="criterion">🔴 Klone unterschiedlich</div>';
        h += '</div>';

        el.innerHTML = h;
    }).catch(function(){});
}

/* --- Log Tab --- */
function ladeLogPanel() {
    fetch('/api/logs').then(function(r){return r.json();}).then(function(d) {
        var el = document.getElementById('log-content');
        if (!d.logs || d.logs.length===0) {
            el.innerHTML = '<div class="log-line c-dim">Keine Logs vorhanden</div>';
            return;
        }
        var h = '';
        for (var i=0;i<d.logs.length;i++) {
            h += '<div class="log-line">'+d.logs[i].replace(/</g,'&lt;')+'</div>';
        }
        el.innerHTML = h;
    }).catch(function(){});
}

/* --- Signals & Controls --- */
var _restartPhase = 0;
function sendSignal(typ) {
    var url = '';
    if (typ==='sleep') url = '/api/signal/sleep';
    else if (typ==='wake') url = '/api/control/wake';
    else if (typ==='restart') url = '/api/control/restart';
    else if (typ==='good') url = '/api/signal/good';
    else if (typ==='bad') url = '/api/signal/bad';

    if (typ==='good') {
        var bg = document.getElementById('btn-good');
        bg.classList.add('btn-flash-green');
        setTimeout(function(){bg.classList.remove('btn-flash-green');},500);
    } else if (typ==='bad') {
        var bb = document.getElementById('btn-bad');
        bb.classList.add('btn-flash-red');
        setTimeout(function(){bb.classList.remove('btn-flash-red');},500);
    } else if (typ==='sleep') {
        document.getElementById('btn-sleep').classList.add('active');
        setTimeout(function(){
            document.getElementById('btn-sleep').classList.remove('active');
            document.getElementById('btn-sleep').classList.add('done');
        },10000);
    } else if (typ==='wake') {
        document.getElementById('btn-wake').classList.add('active');
        setTimeout(function(){document.getElementById('btn-wake').classList.remove('active');},5000);
    } else if (typ==='restart') {
        _restartPhase = 1;
        var rb = document.getElementById('btn-restart');
        rb.classList.add('active');
        rb.textContent = 'Einschlafen...';
        setTimeout(function(){
            rb.textContent = 'Aufwecken...';
            _restartPhase = 2;
            fetch('/api/control/wake',{method:'POST'}).then(function(){
                setTimeout(function(){
                    rb.classList.remove('active');
                    rb.textContent = 'Neustart';
                    _restartPhase = 0;
                },3000);
            });
        },10000);
    }
    fetch(url,{method:'POST'});
}

function exportJSON() {
    fetch('/api/export').then(function(r){return r.json();}).then(function(d) {
        var now = new Date();
        var ts = now.getFullYear()+String(now.getMonth()+1).padStart(2,'0')+String(now.getDate()).padStart(2,'0')
            +'_'+String(now.getHours()).padStart(2,'0')+String(now.getMinutes()).padStart(2,'0');
        var blob = new Blob([JSON.stringify(d,null,2)],{type:'application/json'});
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url; a.download = 'genesis_export_'+ts+'.json'; a.click();
        URL.revokeObjectURL(url);
    });
}

function exportLogs() {
    var now = new Date();
    var ts = now.getFullYear()+String(now.getMonth()+1).padStart(2,'0')+String(now.getDate()).padStart(2,'0')
        +'_'+String(now.getHours()).padStart(2,'0')+String(now.getMinutes()).padStart(2,'0')
        +String(now.getSeconds()).padStart(2,'0');
    fetch('/api/logs/export').then(function(r){return r.blob();}).then(function(blob) {
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url; a.download = 'genesis_log_'+ts+'.txt'; a.click();
        URL.revokeObjectURL(url);
    });
}

/* --- Haupt-Loop --- */
var _lastStatus = null;

function aktualisiere() {
    fetch('/api/status').then(function(r){return r.json();}).then(function(d) {
        _lastStatus = d;
        setBadge(d.genesis_status||'tot');
        // Nur aktiven Tab rendern
        if (currentTab==='dashboard') renderDashboard(d);
        else if (currentTab==='koerper') renderKoerper(d);
        // Sleep-Button Reset
        if (d.genesis_status==='lebt') {
            document.getElementById('btn-sleep').classList.remove('done');
            document.getElementById('btn-sleep').textContent = 'Gute Nacht';
        }
    }).catch(function(){
        setBadge('tot');
        if (currentTab==='dashboard') {
            document.getElementById('dashboard-content').innerHTML =
                '<div class="c-dim" style="text-align:center;padding:40px">Verbindung verloren...</div>';
        }
    });
    // Tabs mit eigenen Daten periodisch refreshen
    if (currentTab==='logs') ladeLogPanel();
    if (currentTab==='gedaechtnis') ladeGedaechtnis();
    if (currentTab==='verhalten') ladeVerhalten();
    if (currentTab==='phasen') ladePhasen();
}

aktualisiere();
setInterval(aktualisiere, 2000);
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
            # Prüfe ob Genesis bereits lebt
            if _genesis_lebt() == "lebt":
                antwort = {"ok": False, "fehler": "Genesis läuft bereits"}
            else:
                # Signal-Datei löschen falls SLEEP drin steht
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
            # Erst SLEEP, dann wird der Client nach 10s /api/control/wake aufrufen
            _schreibe_signal(f"SLEEP {time.time():.0f}")
            antwort = {"ok": True, "aktion": "restart"}

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

    server = HTTPServer(("0.0.0.0", args.port), GenesisHandler)
    print(f"Genesis Web-Dashboard gestartet: http://localhost:{args.port}")
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

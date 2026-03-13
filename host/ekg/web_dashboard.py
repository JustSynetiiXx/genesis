"""Web-Dashboard für Genesis — Mobile-optimiert.

Zeigt Genesis-Status im Browser an. Liest nur, beeinflusst Genesis nicht.

Starten:
    python3 -m host.ekg.web_dashboard
    → http://localhost:8080

Keine externen Dependencies — nur Python stdlib.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
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


HTML_SEITE: str = """\
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>Genesis EKG</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    background: #1a1a1a;
    color: #00ff00;
    font-family: 'Courier New', monospace;
    font-size: 16px;
    padding: 8px;
    min-height: 100vh;
}
.offline {
    text-align: center;
    padding: 40px 20px;
    color: #555;
    font-size: 20px;
}
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
.section {
    border: 1px solid #333;
    border-radius: 6px;
    padding: 10px;
    margin-bottom: 8px;
}
.section-title {
    font-size: 13px;
    color: #666;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 6px;
    border-bottom: 1px solid #333;
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
    background: #333;
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
.warn-komfort { background: #1a5c1a; color: #00ff00; }
.warn-unbehagen { background: #5c5c00; color: #ffff00; }
.warn-stress { background: #5c3a00; color: #ff8800; }
.warn-panik { background: #5c0000; color: #ff0000; }
.warn-reflex { background: #5c0000; color: #ff0000; animation: blink 0.5s infinite; }
.warn-offline { background: #333; color: #666; }
@keyframes blink { 50% { opacity: 0.5; } }
.c-green { color: #00ff00; }
.c-yellow { color: #ffff00; }
.c-orange { color: #ff8800; }
.c-red { color: #ff4444; }
.c-cyan { color: #00cccc; }
.c-dim { color: #666; }
.timestamp {
    text-align: center;
    color: #444;
    font-size: 12px;
    padding-top: 6px;
}
/* Steuerung */
.controls {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 8px;
    align-items: center;
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
    color: #ccc;
    min-width: 44px;
    min-height: 44px;
    touch-action: manipulation;
    transition: background 0.2s, color 0.2s;
}
.controls button:active { transform: scale(0.95); }
.btn-sleep { border-color: #888800; color: #ffff00; }
.btn-sleep:hover { background: #3a3a00; }
.btn-sleep.active { background: #555500; color: #ffff00; }
.btn-sleep.done { background: #333; color: #666; }
.btn-wake { border-color: #008800; color: #00ff00; }
.btn-wake:hover { background: #003a00; }
.btn-wake.active { background: #005500; color: #00ff00; }
.btn-restart { border-color: #884400; color: #ff8800; }
.btn-restart:hover { background: #3a2200; }
.btn-restart.active { background: #553300; color: #ff8800; }
.btn-good { border-color: #008800; color: #00ff00; }
.btn-good:hover { background: #003a00; }
.btn-bad { border-color: #880000; color: #ff4444; }
.btn-bad:hover { background: #3a0000; }
.btn-flash-green { background: #005500 !important; color: #00ff00 !important; }
.btn-flash-red { background: #550000 !important; color: #ff4444 !important; }
.status-indicator {
    font-size: 14px;
    font-weight: bold;
    padding: 8px 12px;
    border-radius: 6px;
    margin-left: auto;
    white-space: nowrap;
}
.status-lebt { color: #00ff00; }
.status-schlaeft { color: #ffff00; }
.status-tot { color: #ff4444; }
/* Logs */
.log-panel {
    background: #111;
    border: 1px solid #333;
    border-radius: 6px;
    padding: 10px;
    margin-bottom: 8px;
    max-height: 300px;
    overflow-y: auto;
    font-size: 12px;
    line-height: 1.4;
    color: #00cc00;
}
.log-panel .section-title { margin-bottom: 6px; }
.log-line { white-space: pre-wrap; word-break: break-all; }
</style>
</head>
<body>
<div class="controls" id="controls">
    <button class="btn-sleep" id="btn-sleep" onclick="sendSignal('sleep')">Gute Nacht</button>
    <button class="btn-wake" id="btn-wake" onclick="sendSignal('wake')">Aufwecken</button>
    <button class="btn-restart" id="btn-restart" onclick="sendSignal('restart')">Neustart</button>
    <button class="btn-good" id="btn-good" onclick="sendSignal('good')">Gut</button>
    <button class="btn-bad" id="btn-bad" onclick="sendSignal('bad')">Schlecht</button>
    <span class="status-indicator" id="status-ind">...</span>
</div>
<div id="content"><div class="offline">Verbinde...</div></div>
<div class="log-panel" id="log-panel">
    <div class="section-title">Logs</div>
    <div id="log-content"></div>
</div>
<div class="timestamp" id="ts"></div>
<script>
function farbeFuerWert(wert, schwellen) {
    if (wert < schwellen[0]) return 'c-green';
    if (wert < schwellen[1]) return 'c-yellow';
    if (wert < schwellen[2]) return 'c-orange';
    return 'c-red';
}

function farbeInvertiert(wert, schwellen) {
    if (wert > schwellen[0]) return 'c-green';
    if (wert > schwellen[1]) return 'c-yellow';
    if (wert > schwellen[2]) return 'c-orange';
    return 'c-red';
}

function interpretiere(g) {
    var s = g.schmerz || 0, e = !!g.exploration, a = g.aktion || '', m = g.modus || '';
    if (s > 0.6 && e) return ['Es schreit', 'c-red'];
    if (a === 'pausieren') return ['Es schläft', 'c-cyan'];
    if (e && s < 0.15) return ['Es lernt', 'c-cyan'];
    if (s < 0.15 && !e) return ['Es ist zufrieden', 'c-green'];
    if (s > 0.35 && e) return ['Es hat Angst', 'c-orange'];
    if (!e) return ['Es erinnert sich', 'c-green'];
    if (m === 'wachphase') return ['Es ist aufgewacht', 'c-yellow'];
    return ['Es existiert', 'c-dim'];
}

var AKTIONEN = {
    'rechenintensitaet_hoch': 'Rechen ↑',
    'rechenintensitaet_runter': 'Rechen ↓',
    'rechenintensitaet_minimum': 'Rechen MIN',
    'speicher_freigeben': 'RAM freigeben',
    'speicher_freigeben_notfall': 'RAM Notfall!',
    'speicher_beanspruchen': 'RAM beanspruchen',
    'pausieren': 'Pausieren',
    'abtastrate_hoch': 'Abtastrate ↑',
    'abtastrate_runter': 'Abtastrate ↓',
    'nichts': 'Nichts tun'
};

function wachZeit(sek) {
    sek = sek || 0;
    var h = Math.floor(sek / 3600);
    var m = Math.floor((sek % 3600) / 60);
    var s = Math.floor(sek % 60);
    if (h > 0) return h + 'h ' + m + 'm';
    if (m > 0) return m + 'm ' + s + 's';
    return s + 's';
}

function bar(wert, farbe) {
    var pct = Math.max(0, Math.min(100, wert * 100));
    return '<div class="bar-container"><div class="bar-fill" style="width:' +
        pct + '%;background:' + farbe + '"></div></div>';
}

function render(daten) {
    var g = daten.genesis;
    var sen = daten.sensoren;
    var el = document.getElementById('content');

    if (!g) {
        el.innerHTML = '<div id="warnstufe" class="warn-offline">Genesis nicht aktiv</div>';
        return;
    }

    var schmerz = g.schmerz || 0;
    var wohl = g.wohlbefinden || 0;
    var stufe = g.warnstufe || 'unbekannt';
    var warnClass = 'warn-' + stufe;
    if (stufe === 'gefahr') warnClass = 'warn-panik';
    var interp = interpretiere(g);

    var aktion = g.aktion ? (AKTIONEN[g.aktion] || g.aktion) : '—';
    if (g.reflex_aktiv) aktion = '⚡ REFLEX';

    var cache = g.cache_mb || 0;
    var cacheClass = cache < 500 ? 'c-green' : (cache < 1000 ? 'c-yellow' : 'c-red');

    var rechen = g.rechen_level || 0;
    var rechenClass = rechen < 0.5 ? 'c-green' : (rechen < 0.8 ? 'c-yellow' : 'c-red');

    var schmerzFarbe = schmerz < 0.15 ? '#00ff00' : (schmerz < 0.35 ? '#ffff00' : (schmerz < 0.6 ? '#ff8800' : '#ff4444'));
    var wohlFarbe = wohl < 0.3 ? '#ff4444' : (wohl < 0.6 ? '#ffff00' : '#00ff00');

    var h = '';

    // Warnstufe
    h += '<div id="warnstufe" class="' + warnClass + '">' + stufe + '</div>';

    // Schmerz + Wohlbefinden nebeneinander
    h += '<div class="dual">';
    h += '<div class="section">';
    h += '<div class="section-title">Schmerz</div>';
    h += '<div class="big-number" style="color:' + schmerzFarbe + '">' + schmerz.toFixed(3) + '</div>';
    h += bar(schmerz, schmerzFarbe);
    h += '</div>';
    h += '<div class="section">';
    h += '<div class="section-title">Wohlbefinden</div>';
    h += '<div class="big-number" style="color:' + wohlFarbe + '">' + wohl.toFixed(3) + '</div>';
    h += bar(wohl, wohlFarbe);
    h += '</div>';
    h += '</div>';

    // Interpretation
    h += '<div class="section">';
    h += '<div class="interpretation ' + interp[1] + '">' + interp[0] + '</div>';
    h += '</div>';

    // Aktivität
    h += '<div class="section">';
    h += '<div class="section-title">Aktivität</div>';
    h += '<div class="row"><span class="label">Aktion</span><span class="value c-cyan">' + aktion + '</span></div>';
    h += '<div class="row"><span class="label">Modus</span><span class="value ' +
        (g.exploration ? 'c-yellow' : 'c-green') + '">' +
        (g.exploration ? 'Exploration' : 'Exploitation') + '</span></div>';
    h += '<div class="row"><span class="label">Cache</span><span class="value ' + cacheClass + '">' + cache.toFixed(0) + ' MB</span></div>';
    h += '<div class="row"><span class="label">Rechen-Level</span><span class="value ' + rechenClass + '">' + (rechen * 100).toFixed(0) + '%</span></div>';
    h += '<div class="row"><span class="label">Abtastrate</span><span class="value c-cyan">' + (g.abtastrate || 0).toFixed(1) + ' Hz</span></div>';
    h += '<div class="row"><span class="label">Wach seit</span><span class="value c-cyan">' + wachZeit(g.wach_seit) + '</span></div>';
    h += '</div>';

    // Lernen
    h += '<div class="section">';
    h += '<div class="section-title">Lernen</div>';
    h += '<div class="row"><span class="label">Erfahrungen heute</span><span class="value c-cyan">' + (g.erfahrungen_heute || 0) + '</span></div>';
    h += '<div class="row"><span class="label">Langzeit</span><span class="value c-cyan">' + (g.erfahrungen_langzeit || 0) + '</span></div>';
    h += '<div class="row"><span class="label">Tode</span><span class="value ' +
        ((g.tode_gesamt || 0) > 0 ? 'c-red' : 'c-green') + '">' + (g.tode_gesamt || 0) + '</span></div>';
    h += '</div>';

    // Vitalwerte
    h += '<div class="section">';
    h += '<div class="section-title">Vitalwerte</div>';
    var roh = g.rohwerte || {};
    var cpuTemp = roh.cpu_temp_tctl || 0;
    h += '<div class="row"><span class="label">CPU Temp</span><span class="value ' +
        farbeFuerWert(cpuTemp, [60, 75, 85]) + '">' + cpuTemp.toFixed(1) + '°C</span></div>';
    var vmRam = roh.vm_ram_frei_mb || 0;
    h += '<div class="row"><span class="label">VM RAM frei</span><span class="value ' +
        farbeInvertiert(vmRam, [500, 200, 50]) + '">' + vmRam.toFixed(0) + ' MB</span></div>';
    var hostCpu = roh.host_cpu_last || 0;
    h += '<div class="row"><span class="label">Host CPU</span><span class="value ' +
        farbeFuerWert(hostCpu, [50, 75, 90]) + '">' + hostCpu.toFixed(1) + '%</span></div>';
    h += '</div>';

    el.innerHTML = h;
}

var _restartPhase = 0; // 0=idle, 1=sleeping, 2=waking

function aktualisiereStatus(gStatus) {
    var ind = document.getElementById('status-ind');
    var labels = {'lebt': 'Genesis lebt', 'schlaeft': 'Genesis schläft', 'tot': 'Genesis ist tot'};
    ind.textContent = labels[gStatus] || '?';
    ind.className = 'status-indicator status-' + gStatus;
}

function sendSignal(typ) {
    var url = '';
    if (typ === 'sleep') url = '/api/signal/sleep';
    else if (typ === 'wake') url = '/api/control/wake';
    else if (typ === 'restart') url = '/api/control/restart';
    else if (typ === 'good') url = '/api/signal/good';
    else if (typ === 'bad') url = '/api/signal/bad';

    // Visuelles Feedback
    if (typ === 'good') {
        var bg = document.getElementById('btn-good');
        bg.classList.add('btn-flash-green');
        setTimeout(function() { bg.classList.remove('btn-flash-green'); }, 500);
    } else if (typ === 'bad') {
        var bb = document.getElementById('btn-bad');
        bb.classList.add('btn-flash-red');
        setTimeout(function() { bb.classList.remove('btn-flash-red'); }, 500);
    } else if (typ === 'sleep') {
        document.getElementById('btn-sleep').classList.add('active');
        setTimeout(function() {
            document.getElementById('btn-sleep').classList.remove('active');
            document.getElementById('btn-sleep').classList.add('done');
        }, 10000);
    } else if (typ === 'wake') {
        document.getElementById('btn-wake').classList.add('active');
        setTimeout(function() { document.getElementById('btn-wake').classList.remove('active'); }, 5000);
    } else if (typ === 'restart') {
        _restartPhase = 1;
        var rb = document.getElementById('btn-restart');
        rb.classList.add('active');
        rb.textContent = 'Einschlafen...';
        setTimeout(function() {
            rb.textContent = 'Aufwecken...';
            _restartPhase = 2;
            fetch('/api/control/wake', {method: 'POST'}).then(function() {
                setTimeout(function() {
                    rb.classList.remove('active');
                    rb.textContent = 'Neustart';
                    _restartPhase = 0;
                }, 3000);
            });
        }, 10000);
    }

    fetch(url, {method: 'POST'});
}

function aktualisiereLogPanel() {
    fetch('/api/logs')
        .then(function(r) { return r.json(); })
        .then(function(d) {
            var el = document.getElementById('log-content');
            if (!d.logs || d.logs.length === 0) {
                el.innerHTML = '<div class="log-line c-dim">Keine Logs vorhanden</div>';
                return;
            }
            var h = '';
            for (var i = 0; i < d.logs.length; i++) {
                h += '<div class="log-line">' + d.logs[i].replace(/</g, '&lt;') + '</div>';
            }
            el.innerHTML = h;
        })
        .catch(function() {});
}

function aktualisiere() {
    fetch('/api/status')
        .then(function(r) { return r.json(); })
        .then(function(d) {
            render(d);
            aktualisiereStatus(d.genesis_status || 'tot');
            document.getElementById('ts').textContent =
                new Date().toLocaleTimeString('de-DE');
            // Sleep-Button zurücksetzen wenn Genesis wieder lebt
            if (d.genesis_status === 'lebt') {
                document.getElementById('btn-sleep').classList.remove('done');
                document.getElementById('btn-sleep').textContent = 'Gute Nacht';
            }
        })
        .catch(function() {
            document.getElementById('content').innerHTML =
                '<div class="offline">Verbindung verloren...</div>';
            aktualisiereStatus('tot');
        });
    aktualisiereLogPanel();
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

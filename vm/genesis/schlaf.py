"""Schlaf-Wach-Zyklus — Einschlafen, Aufwachen, Konsolidierung, Todeslücke.

Sauberer Schlaf: SLEEP-Signal → Konsolidierung → Schlaf-Marker → Ende.
Tod: Kein Schlaf-Marker → Zeitlücke → Letzter Zustand war gefährlich.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from vm.config import LERNSCHWELLE_MITTEL, LERNSCHWELLE_STARK, WIEDERHOLUNGEN_MITTEL
from vm.genesis.gedaechtnis import (
    Erfahrung,
    Heartbeat,
    KurzzeitGedaechtnis,
    LangzeitGedaechtnis,
)


def schlaf_signal_vorhanden(signal_pfad: Path) -> bool:
    """Prüft ob ein SLEEP-Signal in der Signal-Datei steht.

    Args:
        signal_pfad: Pfad zur signal.txt im Shared Directory.

    Returns:
        True wenn SLEEP-Signal vorhanden.
    """
    try:
        inhalt: str = signal_pfad.read_text().strip()
        return inhalt.upper().startswith("SLEEP")
    except (FileNotFoundError, PermissionError, OSError):
        return False


def _konsolidiere(kurzzeit: KurzzeitGedaechtnis,
                  langzeit: LangzeitGedaechtnis) -> int:
    """Konsolidiert Kurzzeitgedächtnis ins Langzeitgedächtnis.

    - Starke Erfahrungen (|delta| > 0.3): Direkt übertragen
    - Wiederholte Muster: Zusammenfassen
    - Schwache Einzel-Erfahrungen: Verwerfen

    Args:
        kurzzeit: Kurzzeitgedächtnis (wird danach geleert).
        langzeit: Langzeitgedächtnis (wird aktualisiert).

    Returns:
        Anzahl konsolidierter Erfahrungen.
    """
    erfahrungen: list[Erfahrung] = kurzzeit.alle_erfahrungen()
    if not erfahrungen:
        return 0

    # Erfahrungen nach Zustand+Aktion gruppieren
    gruppen: dict[str, list[Erfahrung]] = defaultdict(list)
    for e in erfahrungen:
        key: str = json.dumps(e.zustand_vorher, ensure_ascii=False, sort_keys=True) + "|" + e.aktion
        gruppen[key].append(e)

    konsolidiert: int = 0

    for key, gruppe in gruppen.items():
        durchschnitt_delta: float = sum(e.schmerz_delta for e in gruppe) / len(gruppe)
        abs_delta: float = abs(durchschnitt_delta)

        # Starke Signale: Immer übertragen
        if abs_delta > LERNSCHWELLE_STARK:
            for e in gruppe:
                langzeit.aktualisiere(
                    e.zustand_vorher, e.aktion, e.schmerz_delta, e.zeitstempel
                )
            konsolidiert += len(gruppe)
        # Mittlere Signale: Nur wenn genug Wiederholungen
        elif abs_delta > LERNSCHWELLE_MITTEL and len(gruppe) >= WIEDERHOLUNGEN_MITTEL:
            # Zusammengefasst als einen Eintrag übertragen
            langzeit.aktualisiere(
                gruppe[0].zustand_vorher,
                gruppe[0].aktion,
                durchschnitt_delta,
                gruppe[-1].zeitstempel,
            )
            konsolidiert += 1
        # Schwache Einzel-Erfahrungen: Verwerfen (nichts tun)

    return konsolidiert


def einschlafen(kurzzeit: KurzzeitGedaechtnis,
                langzeit: LangzeitGedaechtnis,
                heartbeat: Heartbeat,
                letzter_zustand: dict[str, str],
                letzter_schmerz: float,
                signal_pfad: Path) -> int:
    """Sauberes Einschlafen.

    1. Konsolidierung: Kurzzeit → Langzeit
    2. Kurzzeitgedächtnis leeren
    3. Schlaf-Marker in Heartbeat setzen
    4. READY-Signal schreiben
    5. Prozess kann danach beendet werden

    Args:
        kurzzeit: Kurzzeitgedächtnis.
        langzeit: Langzeitgedächtnis.
        heartbeat: Heartbeat-Datenbank.
        letzter_zustand: Letzter kategorisierter Zustand.
        letzter_schmerz: Letzter Schmerzwert.
        signal_pfad: Pfad zur signal.txt.

    Returns:
        Anzahl konsolidierter Erfahrungen.
    """
    # 1. Konsolidierung
    konsolidiert: int = _konsolidiere(kurzzeit, langzeit)

    # 2. Kurzzeitgedächtnis leeren
    kurzzeit.leere()

    # 3. Schlaf-Marker setzen
    heartbeat.aktualisiere(letzter_zustand, letzter_schmerz, schlaf_marker=True)

    # 4. READY-Signal schreiben
    try:
        signal_pfad.write_text("READY\n")
    except OSError:
        pass  # Nicht kritisch

    return konsolidiert


def aufwachen(langzeit: LangzeitGedaechtnis,
              heartbeat: Heartbeat) -> dict[str, Any]:
    """Aufwachen und Zustand prüfen.

    1. Heartbeat lesen
    2. Schlaf vs. Tod erkennen
    3. Bei Tod: Erfahrung speichern (dieser Zustand war tödlich)
    4. Schlaf-Marker zurücksetzen

    Args:
        langzeit: Langzeitgedächtnis.
        heartbeat: Heartbeat-Datenbank.

    Returns:
        Dictionary mit:
        - 'typ': 'schlaf', 'tod' oder 'erststart'
        - 'letzter_zustand': Letzter bekannter Zustand (oder None)
        - 'letzter_schmerz': Letzter Schmerzwert (oder 0.0)
        - 'zeitluecke': Sekunden seit letztem Heartbeat (oder 0.0)
    """
    hb: dict[str, Any] | None = heartbeat.lese()

    if hb is None:
        # Kein Heartbeat vorhanden → Erststart
        heartbeat.aktualisiere({}, 0.0)
        return {
            "typ": "erststart",
            "letzter_zustand": None,
            "letzter_schmerz": 0.0,
            "zeitluecke": 0.0,
        }

    jetzt: float = time.time()
    zeitluecke: float = jetzt - hb["zeitstempel"]

    if hb["schlaf_marker"]:
        # Sauberer Schlaf → Guten Morgen
        heartbeat.setze_schlaf_marker(False)
        heartbeat.aktualisiere(hb["zustand"], hb["schmerz"])
        return {
            "typ": "schlaf",
            "letzter_zustand": hb["zustand"],
            "letzter_schmerz": hb["schmerz"],
            "zeitluecke": zeitluecke,
        }
    else:
        # Kein Schlaf-Marker → Tod!
        # Tod-Erfahrung speichern
        langzeit.speichere_tod(
            zeitstempel_tod=hb["zeitstempel"],
            zeitstempel_aufwachen=jetzt,
            letzter_zustand=hb["zustand"],
            letzter_schmerz=hb["schmerz"],
            war_schlaf=False,
        )

        # Lernsignal: Dieser Zustand war tödlich (maximale Stärke)
        if hb["zustand"]:
            langzeit.aktualisiere(
                hb["zustand"],
                "nichts_tun",  # Was auch immer getan wurde, es hat zum Tod geführt
                1.0,  # Maximaler Schmerz-Anstieg (positiv = schlecht)
                hb["zeitstempel"],
            )

        heartbeat.aktualisiere(hb["zustand"], hb["schmerz"])
        return {
            "typ": "tod",
            "letzter_zustand": hb["zustand"],
            "letzter_schmerz": hb["schmerz"],
            "zeitluecke": zeitluecke,
        }

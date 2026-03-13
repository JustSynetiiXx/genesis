"""Lernen — Kandidat D mit schmerzgesteuerter Exploration.

Das System lernt NICHT durch Regeln sondern durch Erfahrung:
- Was hat bei ähnlichem Zustand geholfen? → Wiederholen (Exploitation)
- Hoher Schmerz und nichts hilft? → Etwas Neues probieren (Exploration)
- Starkes Signal? → Sofort gelernt. Schwaches? → Braucht Wiederholungen.
"""

from __future__ import annotations

import json
import random
from typing import Any

from vm.config import (
    LERNSCHWELLE_MITTEL,
    LERNSCHWELLE_STARK,
    WIEDERHOLUNGEN_MITTEL,
    WIEDERHOLUNGEN_SCHWACH,
)
from vm.genesis.aktionen import ALLE_AKTION_NAMEN
from vm.genesis.gedaechtnis import (
    Erfahrung,
    GelernteAktion,
    KurzzeitGedaechtnis,
    LangzeitGedaechtnis,
)


def _zustand_key(zustand: dict[str, str]) -> str:
    """Erzeugt einen stabilen String-Key aus einem Zustand-Dict."""
    return json.dumps(zustand, ensure_ascii=False, sort_keys=True)


def exploration_wahrscheinlichkeit(schmerz: float,
                                    beste_erfahrung_delta: float | None) -> float:
    """Bestimmt wie wahrscheinlich eine zufällige Aktion gewählt wird.

    - Niedriger Schmerz + gute Erfahrung → fast 0% (bleib bei was funktioniert)
    - Hoher Schmerz + keine gute Erfahrung → fast 100% (probier was Neues)
    - Hoher Schmerz + gute Erfahrung existiert → 20-30%

    Args:
        schmerz: Aktueller Schmerzwert (0.0-1.0).
        beste_erfahrung_delta: Bestes bekanntes Delta für diesen Zustand,
                                oder None wenn Zustand unbekannt.

    Returns:
        Wahrscheinlichkeit zwischen 0.0 und 1.0.
    """
    if beste_erfahrung_delta is None:
        # Unbekannter Zustand → immer explorieren
        return 1.0

    # Basis-Exploration proportional zum Schmerz
    basis: float = schmerz * 0.5

    if beste_erfahrung_delta >= 0.0:
        # Beste bekannte Aktion hat nicht geholfen (delta >= 0 = gleich oder schlechter)
        # Mehr Exploration nötig
        return min(1.0, basis + 0.5)
    else:
        # Es gibt eine Aktion die geholfen hat
        if schmerz < 0.15:
            # Niedriger Schmerz, gute Erfahrung → fast nie explorieren
            return 0.05
        elif schmerz < 0.35:
            return 0.15
        else:
            # Hoher Schmerz trotz guter Erfahrung → manchmal Neues probieren
            return min(0.6, basis + 0.1)


def lernsignal_staerke(schmerz_delta: float) -> str:
    """Bestimmt wie stark eine Erfahrung gelernt wird.

    - |delta| > 0.3 → 'stark' — eine Erfahrung reicht
    - 0.1 < |delta| <= 0.3 → 'mittel' — braucht 3 Wiederholungen
    - |delta| <= 0.1 → 'schwach' — braucht 5 Wiederholungen

    Args:
        schmerz_delta: Veränderung des Schmerzes.

    Returns:
        'stark', 'mittel' oder 'schwach'.
    """
    absolut: float = abs(schmerz_delta)
    if absolut > LERNSCHWELLE_STARK:
        return "stark"
    elif absolut > LERNSCHWELLE_MITTEL:
        return "mittel"
    else:
        return "schwach"


def waehle_aktion(zustand: dict[str, str], schmerz: float,
                  kurzzeit: KurzzeitGedaechtnis,
                  langzeit: LangzeitGedaechtnis) -> tuple[str, bool]:
    """Wählt eine Aktion basierend auf Erfahrung und Schmerz.

    1. Zustand im Gedächtnis nachschlagen
    2. Wenn bekannt und es gibt eine gute Aktion → diese wählen (Exploitation)
    3. Je höher der Schmerz, desto wahrscheinlicher Exploration
    4. Wenn unbekannt → zufällig (Exploration)

    Args:
        zustand: Kategorisierter Zustand.
        schmerz: Aktueller Schmerzwert.
        kurzzeit: Kurzzeitgedächtnis.
        langzeit: Langzeitgedächtnis.

    Returns:
        Tuple von (aktion_name, ist_exploration).
    """
    # Langzeitgedächtnis hat Vorrang (konsolidiert, zuverlässiger)
    langzeit_aktionen: list[GelernteAktion] = langzeit.suche(zustand)

    # Kurzzeitgedächtnis durchsuchen
    kurzzeit_erfahrungen: list[Erfahrung] = kurzzeit.suche(zustand)

    # Beste bekannte Erfahrung ermitteln
    beste_delta: float | None = None

    if langzeit_aktionen:
        beste_delta = langzeit_aktionen[0].durchschnitt_delta  # Sortiert nach delta ASC

    if kurzzeit_erfahrungen:
        kurzzeit_bestes: float = min(e.schmerz_delta for e in kurzzeit_erfahrungen)
        if beste_delta is None or kurzzeit_bestes < beste_delta:
            # Nur überschreiben wenn Kurzzeit BESSER ist als Langzeit
            # (Langzeit hat Vorrang bei Widersprüchen)
            if beste_delta is None:
                beste_delta = kurzzeit_bestes

    # Exploration oder Exploitation?
    p_exploration: float = exploration_wahrscheinlichkeit(schmerz, beste_delta)

    if random.random() < p_exploration:
        # Exploration: Zufällige Aktion
        return random.choice(ALLE_AKTION_NAMEN), True

    # Exploitation: Beste bekannte Aktion wählen
    beste_aktion: str | None = None

    # Langzeit-Aktionen bevorzugen
    if langzeit_aktionen:
        # Negativstes Delta = am meisten Schmerz reduziert
        for ga in langzeit_aktionen:
            if ga.durchschnitt_delta < 0:
                beste_aktion = ga.aktion
                break

    # Fallback: Kurzzeit-Erfahrungen
    if beste_aktion is None and kurzzeit_erfahrungen:
        beste_kurzzeit: Erfahrung = min(kurzzeit_erfahrungen, key=lambda e: e.schmerz_delta)
        if beste_kurzzeit.schmerz_delta < 0:
            beste_aktion = beste_kurzzeit.aktion

    # Wenn immer noch keine gute Aktion gefunden → zufällig
    if beste_aktion is None:
        return random.choice(ALLE_AKTION_NAMEN), True

    return beste_aktion, False


def lerne(erfahrung: Erfahrung, kurzzeit: KurzzeitGedaechtnis,
          langzeit: LangzeitGedaechtnis) -> None:
    """Verarbeitet eine Erfahrung und speichert sie.

    - Immer im Kurzzeitgedächtnis speichern
    - Starke Signale sofort auch ins Langzeitgedächtnis
    - Mittlere/schwache Signale nur ins Kurzzeitgedächtnis (werden bei Schlaf konsolidiert)

    Args:
        erfahrung: Die zu verarbeitende Erfahrung.
        kurzzeit: Kurzzeitgedächtnis.
        langzeit: Langzeitgedächtnis.
    """
    # Immer im Kurzzeitgedächtnis speichern
    kurzzeit.speichere(erfahrung)

    # Starke Signale sofort ins Langzeitgedächtnis
    staerke: str = lernsignal_staerke(erfahrung.schmerz_delta)
    if staerke == "stark":
        langzeit.aktualisiere(
            erfahrung.zustand_vorher,
            erfahrung.aktion,
            erfahrung.schmerz_delta,
            erfahrung.zeitstempel,
        )

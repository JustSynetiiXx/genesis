"""Schmerz und Wohlbefinden — das Bewertungssystem von Genesis.

Schmerz fasst alle Abweichungen vom Komfort zusammen.
Wohlbefinden basiert auf Veränderung, nicht auf dem Gegenteil von Schmerz.
"""

from __future__ import annotations

from typing import Any


# --- Schmerz-Konfiguration ---
# Jeder Sensor hat Komfort/Maximum-Grenzen und ein Gewicht.
# Gewichte summieren sich zu 1.0.

SCHMERZ_CONFIG: dict[str, dict[str, Any]] = {
    "cpu_temp_tctl": {
        "komfort": 60.0,
        "maximum": 90.0,
        "gewicht": 0.20,
        "invertiert": False,
    },
    "vm_ram_frei_mb": {
        "komfort": 3500.0,
        "maximum": 500.0,
        "gewicht": 0.10,
        "invertiert": True,  # Weniger frei = mehr Schmerz
    },
    "eigen_cpu_prozent": {
        "komfort": 30.0,
        "maximum": 95.0,
        "gewicht": 0.20,
        "invertiert": False,
    },
    "eigen_ram_mb": {
        "komfort": 100.0,
        "maximum": 1000.0,
        "gewicht": 0.40,
        "invertiert": False,
    },
    "host_cpu_last": {
        "komfort": 50.0,
        "maximum": 95.0,
        "gewicht": 0.10,
        "invertiert": False,
    },
    "luefter_rpm": {
        "komfort": 1500.0,
        "maximum": 4000.0,
        "gewicht": 0.05,
        "invertiert": False,
    },
}


def _schmerz_beitrag(wert: float, komfort: float, maximum: float, invertiert: bool) -> float:
    """Berechnet den Schmerzbeitrag eines einzelnen Sensors.

    Args:
        wert: Aktueller Sensorwert.
        komfort: Wert ab dem kein Schmerz entsteht.
        maximum: Wert bei dem maximaler Schmerz entsteht.
        invertiert: True wenn niedrigere Werte mehr Schmerz bedeuten.

    Returns:
        Schmerzbeitrag zwischen 0.0 und 1.0.
    """
    if invertiert:
        # Bei invertiert: komfort=500, maximum=10
        # Wert 500 → kein Schmerz, Wert 10 → maximaler Schmerz
        if wert >= komfort:
            return 0.0
        if wert <= maximum:
            return 1.0
        return (komfort - wert) / (komfort - maximum)
    else:
        if wert <= komfort:
            return 0.0
        if wert >= maximum:
            return 1.0
        return (wert - komfort) / (maximum - komfort)


def berechne_schmerz(rohwerte: dict[str, float]) -> float:
    """Berechnet den Gesamtschmerz aus allen Sensorwerten.

    Args:
        rohwerte: Dictionary mit Sensor-Rohwerten.

    Returns:
        Schmerz zwischen 0.0 und 1.0.
    """
    gesamt: float = 0.0

    for sensor_name, config in SCHMERZ_CONFIG.items():
        wert: float = rohwerte.get(sensor_name, 0.0)
        beitrag: float = _schmerz_beitrag(
            wert,
            config["komfort"],
            config["maximum"],
            config["invertiert"],
        )
        gesamt += beitrag * config["gewicht"]

    return max(0.0, min(1.0, gesamt))


def _sensor_kategorie(sensor_name: str, wert: float) -> str:
    """Bestimmt die Zustandskategorie eines Sensors anhand seines Rohwerts.

    Args:
        sensor_name: Name des Sensors (Key in SCHMERZ_CONFIG).
        wert: Aktueller Rohwert.

    Returns:
        Menschlich lesbare Kategorie.
    """
    if sensor_name == "cpu_temp_tctl":
        if wert < 45.0:
            return "kühl"
        if wert < 60.0:
            return "normal"
        if wert < 75.0:
            return "warm"
        if wert < 85.0:
            return "heiß"
        return "kritisch"
    elif sensor_name == "vm_ram_frei_mb":
        if wert > 500.0:
            return "frei"
        if wert > 200.0:
            return "normal"
        if wert > 50.0:
            return "eng"
        return "voll"
    elif sensor_name == "eigen_cpu_prozent":
        if wert < 30.0:
            return "niedrig"
        if wert < 60.0:
            return "normal"
        if wert < 90.0:
            return "hoch"
        return "überlastet"
    elif sensor_name == "eigen_ram_mb":
        if wert < 100.0:
            return "niedrig"
        if wert < 300.0:
            return "normal"
        if wert < 600.0:
            return "hoch"
        return "kritisch"
    elif sensor_name == "host_cpu_last":
        if wert < 30.0:
            return "niedrig"
        if wert < 60.0:
            return "normal"
        if wert < 90.0:
            return "hoch"
        return "überlastet"
    elif sensor_name == "luefter_rpm":
        if wert < 1200.0:
            return "leise"
        if wert < 2000.0:
            return "normal"
        if wert < 3000.0:
            return "laut"
        return "maximum"
    return "unbekannt"


def berechne_schmerz_details(rohwerte: dict[str, float]) -> dict[str, dict[str, Any]]:
    """Berechnet den Schmerzbeitrag pro Sensor mit Rohwert und Kategorie.

    Args:
        rohwerte: Dictionary mit Sensor-Rohwerten.

    Returns:
        Dictionary mit pro Sensor: rohwert, beitrag (gewichtet), kategorie.
    """
    details: dict[str, dict[str, Any]] = {}

    for sensor_name, config in SCHMERZ_CONFIG.items():
        wert: float = rohwerte.get(sensor_name, 0.0)
        roh_beitrag: float = _schmerz_beitrag(
            wert,
            config["komfort"],
            config["maximum"],
            config["invertiert"],
        )
        gewichteter_beitrag: float = roh_beitrag * config["gewicht"]
        details[sensor_name] = {
            "rohwert": round(wert, 2),
            "beitrag": round(gewichteter_beitrag, 4),
            "kategorie": _sensor_kategorie(sensor_name, wert),
        }

    return details


def berechne_wohlbefinden(aktueller_schmerz: float, vorheriger_schmerz: float) -> float:
    """Berechnet Wohlbefinden basierend auf Schmerzveränderung.

    Nicht einfach 1 - Schmerz. Basiert auf VERÄNDERUNG:
    - Schmerz sinkt → Erleichterung (kurzer Anstieg)
    - Schmerz stabil niedrig → moderate Zufriedenheit
    - Schmerz stabil hoch oder steigend → null

    Args:
        aktueller_schmerz: Aktueller Schmerzwert (0.0-1.0).
        vorheriger_schmerz: Schmerzwert der letzten Iteration (0.0-1.0).

    Returns:
        Wohlbefinden zwischen 0.0 und 1.0.
    """
    delta: float = vorheriger_schmerz - aktueller_schmerz  # Positiv wenn Schmerz gesunken
    basis: float = max(0.0, 1.0 - aktueller_schmerz)      # Grundlevel
    erleichterung: float = max(0.0, delta * 2.0)           # Bonus bei Besserung
    return min(1.0, basis * 0.5 + erleichterung * 0.5)


def warnstufe(schmerz: float) -> str:
    """Bestimmt die Warnstufe basierend auf dem Schmerz.

    Args:
        schmerz: Aktueller Schmerzwert (0.0-1.0).

    Returns:
        Eine von: 'komfort', 'unbehagen', 'stress', 'panik', 'reflex'.
    """
    if schmerz < 0.15:
        return "komfort"
    elif schmerz < 0.35:
        return "unbehagen"
    elif schmerz < 0.60:
        return "stress"
    elif schmerz < 0.85:
        return "panik"
    else:
        return "reflex"

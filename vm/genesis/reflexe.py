"""Reflexe — Hardcoded Notfall-Reaktionen.

Reflexe haben VORRANG vor dem Lernmechanismus.
Sie feuern sofort bei kritischen Werten.
Reflexe erzeugen KEINE Erfahrung im Gedächtnis — sie sind unbewusst.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from vm.config import CPU_PROZENT_MAX


@dataclass
class Reflex:
    """Ein einzelner Reflex mit Bedingung und Aktion."""

    name: str
    bedingung: Callable[[dict[str, float]], bool]
    aktion: str
    beschreibung: str


# Die hardcoded Reflexe
REFLEXE: list[Reflex] = [
    Reflex(
        name="hitzeschutz",
        bedingung=lambda roh: roh.get("cpu_temp_tctl", 0.0) > 85.0,
        aktion="rechenintensitaet_minimum",
        beschreibung="CPU > 85°C → Eigene Aktivität auf Minimum",
    ),
    Reflex(
        name="ram_notfall",
        bedingung=lambda roh: roh.get("vm_ram_frei_mb", 9999.0) < 50.0,
        aktion="speicher_freigeben_notfall",
        beschreibung="VM-RAM < 50 MB → Sofort Speicher freigeben",
    ),
    Reflex(
        name="cpu_notfall",
        bedingung=lambda roh: roh.get("eigen_cpu_prozent", 0.0) > CPU_PROZENT_MAX * 0.9,
        aktion="rechenintensitaet_minimum",
        beschreibung=f"Eigene CPU > {CPU_PROZENT_MAX * 0.9:.0f}% → Sofort reduzieren",
    ),
]


def pruefe(rohwerte: dict[str, float]) -> list[Reflex]:
    """Prüft alle Reflexe und gibt die gefeuerten zurück.

    Args:
        rohwerte: Dictionary mit Sensor-Rohwerten.

    Returns:
        Liste der Reflexe die gefeuert haben (leer wenn keiner).
    """
    gefeuert: list[Reflex] = []
    for reflex in REFLEXE:
        if reflex.bedingung(rohwerte):
            gefeuert.append(reflex)
    return gefeuert

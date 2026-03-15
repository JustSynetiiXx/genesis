"""Konfiguration für mehrere Genesis-Instanzen (Klon-Infrastruktur).

Jede Instanz bekommt eigene DB- und Shared-Verzeichnisse.
Der Umgebungs-Dienst nutzt diese Pfade um alle Instanzen zu finden.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# --- Instanz-Definitionen ---
INSTANCES: dict[str, dict[str, Any]] = {
    "genesis-1": {
        "db_pfad": "/var/lib/genesis/",
        "shared_pfad": "/opt/genesis/shared/",
        "beschreibung": "Original-Instanz",
    },
    "genesis-2": {
        "db_pfad": "/var/lib/genesis-2/",
        "shared_pfad": "/opt/genesis/shared-2/",
        "beschreibung": "Klon 2",
    },
    "genesis-3": {
        "db_pfad": "/var/lib/genesis-3/",
        "shared_pfad": "/opt/genesis/shared-3/",
        "beschreibung": "Klon 3",
    },
}

# Zentrale Umgebungs-Status-Datei (geschrieben vom Umgebungs-Dienst)
UMGEBUNG_STATUS_PFAD: Path = Path("/opt/genesis/shared/umgebung_status.json")

# Standard-Instanz
DEFAULT_INSTANZ: str = "genesis-1"


def get_instanz_config(name: str) -> dict[str, Any]:
    """Gibt die Konfiguration einer Instanz zurück.

    Args:
        name: Name der Instanz (z.B. 'genesis-1').

    Returns:
        Dict mit db_pfad, shared_pfad, beschreibung.

    Raises:
        KeyError: Wenn die Instanz nicht existiert.
    """
    if name not in INSTANCES:
        raise KeyError(
            f"Instanz '{name}' nicht gefunden. "
            f"Verfügbar: {list(INSTANCES.keys())}"
        )
    return INSTANCES[name]


def get_instanz_pfade(name: str) -> tuple[Path, Path]:
    """Gibt DB- und Shared-Pfad einer Instanz als Path-Objekte zurück.

    Args:
        name: Name der Instanz.

    Returns:
        Tuple (db_pfad, shared_pfad).
    """
    cfg = get_instanz_config(name)
    return Path(cfg["db_pfad"]), Path(cfg["shared_pfad"])

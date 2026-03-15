#!/usr/bin/env python3
"""Reset-Tode: Löscht alle Tode-Einträge aus langzeit.db für alle Genesis-Instanzen.

Nutzt sqlite3 aus der Python-Standardbibliothek statt des sqlite3-CLI-Tools.
Löscht NUR die Tode-Tabelle, NICHT Langzeit- oder Kurzzeit-Lerndaten.
"""

import sqlite3
import sys
from pathlib import Path

DB_PFADE: list[str] = [
    "/var/lib/genesis/langzeit.db",
    "/var/lib/genesis-2/langzeit.db",
    "/var/lib/genesis-3/langzeit.db",
]


def main() -> None:
    """Löscht alle Tode-Einträge aus allen Instanzen."""
    print("=== Genesis: Tode zurücksetzen ===")
    print()

    # Übersicht anzeigen
    print("Folgende Datenbanken werden bereinigt:")
    gefunden: list[str] = []
    for db_pfad in DB_PFADE:
        if not Path(db_pfad).exists():
            print(f"  {db_pfad} — nicht gefunden (übersprungen)")
            continue
        try:
            conn = sqlite3.connect(db_pfad)
            cursor = conn.execute("SELECT COUNT(*) FROM tode")
            anzahl: int = cursor.fetchone()[0]
            conn.close()
            print(f"  {db_pfad} — {anzahl} Einträge in 'tode'")
            gefunden.append(db_pfad)
        except Exception as e:
            print(f"  {db_pfad} — Fehler: {e}")

    if not gefunden:
        print("\nKeine Datenbanken gefunden.")
        sys.exit(0)

    # Bestätigung
    print()
    antwort: str = input("Wirklich alle Tode löschen? (ja/nein): ").strip()
    if antwort != "ja":
        print("Abgebrochen.")
        sys.exit(0)

    # Löschen
    print()
    for db_pfad in gefunden:
        try:
            conn = sqlite3.connect(db_pfad)
            conn.execute("DELETE FROM tode")
            conn.commit()
            conn.close()
            print(f"  {db_pfad}: Tode gelöscht")
        except Exception as e:
            print(f"  {db_pfad}: Fehler: {e}")

    print()
    print("Fertig. Alle Tode-Einträge wurden entfernt.")
    print("Langzeit- und Kurzzeit-Lerndaten sind unverändert.")


if __name__ == "__main__":
    main()

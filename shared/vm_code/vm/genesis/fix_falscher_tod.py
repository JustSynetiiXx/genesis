"""Fix: Falschen Tod aus Langzeitgedächtnis löschen.

Genesis wurde sauber schlafen gelegt, aber wegen eines Bugs im finally-Block
von leben.py wurde der Schlaf-Marker überschrieben. Beim Neustart wurde der
saubere Schlaf als Tod erkannt und falsche Lern-Erfahrungen gespeichert.

Dieses Skript:
1. Löscht alle Tod-Einträge (war_schlaf=0) aus der tode-Tabelle
2. Löscht gelernte Erfahrungen die auf den Tod-Zustand verweisen
3. Gibt eine Zusammenfassung aus

Ausführung in der VM wenn Genesis pausiert oder schläft:
    python3 -m vm.genesis.fix_falscher_tod
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


DB_PFAD: Path = Path("/var/lib/genesis/langzeit.db")


def main(db_pfad: Path = DB_PFAD) -> None:
    """Löscht falsche Tod-Einträge und zugehörige Lernerfahrungen.

    Args:
        db_pfad: Pfad zur Langzeit-Datenbank.
    """
    if not db_pfad.exists():
        print(f"FEHLER: Datenbank nicht gefunden: {db_pfad}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_pfad))
    conn.execute("PRAGMA journal_mode=WAL")

    try:
        # --- 1. Falsche Tode finden und anzeigen ---
        cursor = conn.execute(
            """SELECT id, zeitstempel_tod, letzter_zustand, letzter_schmerz
               FROM tode WHERE war_schlaf = 0"""
        )
        falsche_tode = cursor.fetchall()

        if not falsche_tode:
            print("Keine falschen Tode gefunden. Nichts zu tun.")
            return

        print(f"Gefunden: {len(falsche_tode)} falsche(r) Tod/Tode\n")

        tod_zustaende: list[str] = []
        for row in falsche_tode:
            tod_id, zeitstempel, zustand_json, schmerz = row
            print(f"  Tod #{tod_id}:")
            print(f"    Zeitstempel: {zeitstempel}")
            print(f"    Zustand:     {zustand_json}")
            print(f"    Schmerz:     {schmerz}")
            print()
            tod_zustaende.append(zustand_json)

        # --- 2. Falsche Tode löschen ---
        conn.execute("DELETE FROM tode WHERE war_schlaf = 0")
        print(f"Gelöscht: {len(falsche_tode)} Tod-Eintrag/Einträge aus tode-Tabelle")

        # --- 3. Gelernte Einträge finden die auf Tod-Zustände verweisen ---
        geloeschte_lern = 0
        for zustand_json in tod_zustaende:
            # Suche Einträge die auf den Tod-Zustand verweisen
            # Das beinhaltet den "nichts_tun"-Eintrag den aufwachen() erzeugt
            cursor = conn.execute(
                """SELECT id, zustand, aktion, durchschnitt_delta, anzahl
                   FROM gelernt WHERE zustand = ?""",
                (zustand_json,),
            )
            betroffene = cursor.fetchall()

            if betroffene:
                print(f"\nGelernte Einträge für Tod-Zustand {zustand_json}:")
                for eintrag in betroffene:
                    eintrag_id, zustand, aktion, delta, anzahl = eintrag
                    print(f"  #{eintrag_id}: Aktion={aktion}, Delta={delta:.4f}, Anzahl={anzahl}")

                conn.execute(
                    "DELETE FROM gelernt WHERE zustand = ?",
                    (zustand_json,),
                )
                geloeschte_lern += len(betroffene)

        conn.commit()

        # --- 4. Zusammenfassung ---
        print("\n" + "=" * 50)
        print("ZUSAMMENFASSUNG")
        print("=" * 50)
        print(f"  Falsche Tode gelöscht:        {len(falsche_tode)}")
        print(f"  Lern-Einträge gelöscht:        {geloeschte_lern}")

        # Verbleibende Einträge
        cursor = conn.execute("SELECT COUNT(*) FROM tode")
        verbleibende_tode = cursor.fetchone()[0]
        cursor = conn.execute("SELECT COUNT(*) FROM gelernt")
        verbleibende_gelernt = cursor.fetchone()[0]
        print(f"  Verbleibende Tode (gesamt):    {verbleibende_tode}")
        print(f"  Verbleibende Lern-Einträge:    {verbleibende_gelernt}")
        print("\nDatenbank bereinigt.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()

"""Gedächtnis — Kurz- und Langzeitgedächtnis via SQLite.

Kurzzeitgedächtnis: Alle Erfahrungen des aktuellen Tages. Geht bei Tod verloren.
Langzeitgedächtnis: Konsolidierte Muster. Überlebt Neustart und Absturz.
Heartbeat: Letzter bekannter Zustand für Todeslücke-Erkennung.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Erfahrung:
    """Eine einzelne Erfahrung: Zustand → Aktion → Ergebnis."""

    zustand_vorher: dict[str, str]
    aktion: str
    zustand_nachher: dict[str, str]
    schmerz_vorher: float
    schmerz_nachher: float
    schmerz_delta: float
    zeitstempel: float


@dataclass
class GelernteAktion:
    """Eine gelernte Zustand-Aktion-Kombination aus dem Langzeitgedächtnis."""

    zustand: dict[str, str]
    aktion: str
    durchschnitt_delta: float
    anzahl: int
    letzte_erfahrung: float


class KurzzeitGedaechtnis:
    """Tages-Erfahrungen in SQLite. Geht bei Tod verloren."""

    def __init__(self, db_pfad: Path) -> None:
        self._db_pfad: Path = db_pfad
        self._conn: sqlite3.Connection = sqlite3.connect(str(db_pfad))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._erstelle_tabellen()

    def _erstelle_tabellen(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS erfahrungen (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                zeitstempel REAL NOT NULL,
                zustand_vorher TEXT NOT NULL,
                aktion TEXT NOT NULL,
                zustand_nachher TEXT NOT NULL,
                schmerz_vorher REAL NOT NULL,
                schmerz_nachher REAL NOT NULL,
                schmerz_delta REAL NOT NULL
            )
        """)
        self._conn.commit()

    def speichere(self, erfahrung: Erfahrung) -> None:
        """Speichert eine Erfahrung im Kurzzeitgedächtnis."""
        self._conn.execute(
            """INSERT INTO erfahrungen
               (zeitstempel, zustand_vorher, aktion, zustand_nachher,
                schmerz_vorher, schmerz_nachher, schmerz_delta)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                erfahrung.zeitstempel,
                json.dumps(erfahrung.zustand_vorher, ensure_ascii=False),
                erfahrung.aktion,
                json.dumps(erfahrung.zustand_nachher, ensure_ascii=False),
                erfahrung.schmerz_vorher,
                erfahrung.schmerz_nachher,
                erfahrung.schmerz_delta,
            ),
        )
        self._conn.commit()

    def suche(self, zustand: dict[str, str], aktion: str | None = None) -> list[Erfahrung]:
        """Sucht Erfahrungen für einen bestimmten Zustand.

        Args:
            zustand: Kategorisierter Zustand.
            aktion: Optional, um nach einer bestimmten Aktion zu filtern.

        Returns:
            Liste passender Erfahrungen.
        """
        zustand_json: str = json.dumps(zustand, ensure_ascii=False, sort_keys=True)
        if aktion is not None:
            cursor = self._conn.execute(
                """SELECT zeitstempel, zustand_vorher, aktion, zustand_nachher,
                          schmerz_vorher, schmerz_nachher, schmerz_delta
                   FROM erfahrungen
                   WHERE zustand_vorher = ? AND aktion = ?
                   ORDER BY zeitstempel DESC""",
                (zustand_json, aktion),
            )
        else:
            cursor = self._conn.execute(
                """SELECT zeitstempel, zustand_vorher, aktion, zustand_nachher,
                          schmerz_vorher, schmerz_nachher, schmerz_delta
                   FROM erfahrungen
                   WHERE zustand_vorher = ?
                   ORDER BY zeitstempel DESC""",
                (zustand_json,),
            )
        ergebnisse: list[Erfahrung] = []
        for row in cursor.fetchall():
            ergebnisse.append(Erfahrung(
                zustand_vorher=json.loads(row[1]),
                aktion=row[2],
                zustand_nachher=json.loads(row[3]),
                schmerz_vorher=row[4],
                schmerz_nachher=row[5],
                schmerz_delta=row[6],
                zeitstempel=row[0],
            ))
        return ergebnisse

    def alle_erfahrungen(self) -> list[Erfahrung]:
        """Gibt alle Erfahrungen zurück (für Konsolidierung)."""
        cursor = self._conn.execute(
            """SELECT zeitstempel, zustand_vorher, aktion, zustand_nachher,
                      schmerz_vorher, schmerz_nachher, schmerz_delta
               FROM erfahrungen ORDER BY zeitstempel"""
        )
        return [
            Erfahrung(
                zustand_vorher=json.loads(row[1]),
                aktion=row[2],
                zustand_nachher=json.loads(row[3]),
                schmerz_vorher=row[4],
                schmerz_nachher=row[5],
                schmerz_delta=row[6],
                zeitstempel=row[0],
            )
            for row in cursor.fetchall()
        ]

    def anzahl(self) -> int:
        """Gibt die Anzahl gespeicherter Erfahrungen zurück."""
        cursor = self._conn.execute("SELECT COUNT(*) FROM erfahrungen")
        return cursor.fetchone()[0]

    def leere(self) -> None:
        """Löscht alle Erfahrungen (nach Konsolidierung)."""
        self._conn.execute("DELETE FROM erfahrungen")
        self._conn.commit()

    def schliesse(self) -> None:
        """Schließt die Datenbankverbindung."""
        self._conn.close()


class LangzeitGedaechtnis:
    """Konsolidierte Erfahrungen. Überlebt Neustart und Absturz."""

    def __init__(self, db_pfad: Path) -> None:
        self._db_pfad: Path = db_pfad
        self._conn: sqlite3.Connection = sqlite3.connect(str(db_pfad))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._erstelle_tabellen()

    def _erstelle_tabellen(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS gelernt (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                zustand TEXT NOT NULL,
                aktion TEXT NOT NULL,
                durchschnitt_delta REAL NOT NULL,
                anzahl INTEGER NOT NULL,
                letzte_erfahrung REAL NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS tode (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                zeitstempel_tod REAL NOT NULL,
                zeitstempel_aufwachen REAL NOT NULL,
                letzter_zustand TEXT NOT NULL,
                letzter_schmerz REAL NOT NULL,
                war_schlaf INTEGER NOT NULL
            )
        """)
        # Index für schnelle Zustand-Suche
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_gelernt_zustand
            ON gelernt (zustand)
        """)
        self._conn.commit()

    def suche(self, zustand: dict[str, str]) -> list[GelernteAktion]:
        """Sucht gelernte Aktionen für einen Zustand.

        Args:
            zustand: Kategorisierter Zustand.

        Returns:
            Liste gelernter Aktionen, sortiert nach durchschnitt_delta (beste zuerst).
        """
        zustand_json: str = json.dumps(zustand, ensure_ascii=False, sort_keys=True)
        cursor = self._conn.execute(
            """SELECT zustand, aktion, durchschnitt_delta, anzahl, letzte_erfahrung
               FROM gelernt
               WHERE zustand = ?
               ORDER BY durchschnitt_delta ASC""",
            (zustand_json,),
        )
        return [
            GelernteAktion(
                zustand=json.loads(row[0]),
                aktion=row[1],
                durchschnitt_delta=row[2],
                anzahl=row[3],
                letzte_erfahrung=row[4],
            )
            for row in cursor.fetchall()
        ]

    def aktualisiere(self, zustand: dict[str, str], aktion: str,
                     delta: float, zeitstempel: float) -> None:
        """Aktualisiert oder erstellt einen Eintrag im Langzeitgedächtnis.

        Args:
            zustand: Kategorisierter Zustand.
            aktion: Ausgeführte Aktion.
            delta: Schmerz-Veränderung.
            zeitstempel: Zeitstempel der Erfahrung.
        """
        zustand_json: str = json.dumps(zustand, ensure_ascii=False, sort_keys=True)
        cursor = self._conn.execute(
            "SELECT id, durchschnitt_delta, anzahl FROM gelernt WHERE zustand = ? AND aktion = ?",
            (zustand_json, aktion),
        )
        row = cursor.fetchone()

        if row is not None:
            # Laufenden Durchschnitt aktualisieren
            alter_schnitt: float = row[1]
            alte_anzahl: int = row[2]
            neue_anzahl: int = alte_anzahl + 1
            neuer_schnitt: float = (alter_schnitt * alte_anzahl + delta) / neue_anzahl
            self._conn.execute(
                """UPDATE gelernt
                   SET durchschnitt_delta = ?, anzahl = ?, letzte_erfahrung = ?
                   WHERE id = ?""",
                (neuer_schnitt, neue_anzahl, zeitstempel, row[0]),
            )
        else:
            self._conn.execute(
                """INSERT INTO gelernt (zustand, aktion, durchschnitt_delta, anzahl, letzte_erfahrung)
                   VALUES (?, ?, ?, ?, ?)""",
                (zustand_json, aktion, delta, 1, zeitstempel),
            )
        self._conn.commit()

    def speichere_tod(self, zeitstempel_tod: float, zeitstempel_aufwachen: float,
                      letzter_zustand: dict[str, str], letzter_schmerz: float,
                      war_schlaf: bool) -> None:
        """Speichert ein Tod- oder Schlaf-Ereignis.

        Args:
            zeitstempel_tod: Zeitstempel des Herunterfahrens/Absturzes.
            zeitstempel_aufwachen: Zeitstempel des Aufwachens.
            letzter_zustand: Letzter bekannter Zustand.
            letzter_schmerz: Letzter bekannter Schmerzwert.
            war_schlaf: True wenn sauberer Schlaf, False wenn Tod/Absturz.
        """
        self._conn.execute(
            """INSERT INTO tode
               (zeitstempel_tod, zeitstempel_aufwachen, letzter_zustand,
                letzter_schmerz, war_schlaf)
               VALUES (?, ?, ?, ?, ?)""",
            (
                zeitstempel_tod,
                zeitstempel_aufwachen,
                json.dumps(letzter_zustand, ensure_ascii=False),
                letzter_schmerz,
                1 if war_schlaf else 0,
            ),
        )
        self._conn.commit()

    def anzahl_gelernt(self) -> int:
        """Gibt die Anzahl gelernter Zustand-Aktion-Paare zurück."""
        cursor = self._conn.execute("SELECT COUNT(*) FROM gelernt")
        return cursor.fetchone()[0]

    def anzahl_tode(self) -> int:
        """Gibt die Gesamtzahl der Tode zurück (ohne Schlaf)."""
        cursor = self._conn.execute("SELECT COUNT(*) FROM tode WHERE war_schlaf = 0")
        return cursor.fetchone()[0]

    def letzter_tod(self) -> dict[str, Any] | None:
        """Gibt den letzten Tod zurück (ohne Schlaf)."""
        cursor = self._conn.execute(
            """SELECT zeitstempel_tod, letzter_zustand, letzter_schmerz
               FROM tode WHERE war_schlaf = 0
               ORDER BY zeitstempel_tod DESC LIMIT 1"""
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return {
            "zeitstempel": row[0],
            "zustand": json.loads(row[1]),
            "schmerz": row[2],
        }

    def schliesse(self) -> None:
        """Schließt die Datenbankverbindung."""
        self._conn.close()


class Heartbeat:
    """Letzter bekannter Zustand — für Todeslücke-Erkennung.

    Wird alle paar Sekunden aktualisiert. Enthält Schlaf-Marker.
    """

    def __init__(self, db_pfad: Path) -> None:
        self._db_pfad: Path = db_pfad
        self._conn: sqlite3.Connection = sqlite3.connect(str(db_pfad))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._erstelle_tabellen()

    def _erstelle_tabellen(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS heartbeat (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                zeitstempel REAL NOT NULL,
                zustand TEXT NOT NULL,
                schmerz REAL NOT NULL,
                schlaf_marker INTEGER NOT NULL DEFAULT 0
            )
        """)
        self._conn.commit()

    def aktualisiere(self, zustand: dict[str, str], schmerz: float,
                     schlaf_marker: bool = False) -> None:
        """Aktualisiert den Heartbeat.

        Args:
            zustand: Aktueller kategorisierter Zustand.
            schmerz: Aktueller Schmerzwert.
            schlaf_marker: True wenn sauber eingeschlafen.
        """
        zustand_json: str = json.dumps(zustand, ensure_ascii=False, sort_keys=True)
        self._conn.execute(
            """INSERT INTO heartbeat (id, zeitstempel, zustand, schmerz, schlaf_marker)
               VALUES (1, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   zeitstempel = excluded.zeitstempel,
                   zustand = excluded.zustand,
                   schmerz = excluded.schmerz,
                   schlaf_marker = excluded.schlaf_marker""",
            (time.time(), zustand_json, schmerz, 1 if schlaf_marker else 0),
        )
        self._conn.commit()

    def lese(self) -> dict[str, Any] | None:
        """Liest den letzten Heartbeat.

        Returns:
            Dictionary mit zeitstempel, zustand, schmerz, schlaf_marker
            oder None wenn kein Heartbeat vorhanden.
        """
        cursor = self._conn.execute(
            "SELECT zeitstempel, zustand, schmerz, schlaf_marker FROM heartbeat WHERE id = 1"
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return {
            "zeitstempel": row[0],
            "zustand": json.loads(row[1]),
            "schmerz": row[2],
            "schlaf_marker": bool(row[3]),
        }

    def setze_schlaf_marker(self, marker: bool) -> None:
        """Setzt oder entfernt den Schlaf-Marker."""
        self._conn.execute(
            "UPDATE heartbeat SET schlaf_marker = ? WHERE id = 1",
            (1 if marker else 0,),
        )
        self._conn.commit()

    def schliesse(self) -> None:
        """Schließt die Datenbankverbindung."""
        self._conn.close()

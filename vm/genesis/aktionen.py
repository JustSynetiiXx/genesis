"""Aktionen — Die 5 Aktionskategorien + natürlicher Verfall.

Jede Aktion hat eine ECHTE, MESSBARE Konsequenz auf VM-Ressourcen.
"""

from __future__ import annotations

import math
import threading
import time

from vm.config import (
    ABTASTRATE_MAX,
    ABTASTRATE_MIN,
    CACHE_MAX_MB,
    PAUSE_MAX_SEKUNDEN,
    PAUSE_MIN_SEKUNDEN,
    RECHEN_STUFE,
    VERFALL_MB_PRO_TICK,
)


class RechenIntensitaet:
    """Interner Worker-Thread der sinnlose Berechnungen macht.

    Mehr Intensität = mehr CPU-Verbrauch = mehr Hitze.
    Weniger Intensität = weniger CPU = kühler.
    """

    def __init__(self) -> None:
        self.level: float = 0.0
        self._laeuft: bool = False
        self._thread: threading.Thread | None = None
        self._lock: threading.Lock = threading.Lock()

    def setze_level(self, level: float) -> None:
        """Setzt das Berechnungslevel (0.0 bis 1.0)."""
        with self._lock:
            self.level = max(0.0, min(1.0, level))

    def erhoehe(self) -> None:
        """Erhöht Level um eine Stufe."""
        self.setze_level(self.level + RECHEN_STUFE)

    def reduziere(self) -> None:
        """Reduziert Level um eine Stufe."""
        self.setze_level(self.level - RECHEN_STUFE)

    def minimum(self) -> None:
        """Auf Minimum (für Reflexe)."""
        self.setze_level(0.0)

    def starte(self) -> None:
        """Startet den Worker-Thread."""
        if self._laeuft:
            return
        self._laeuft = True
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def stoppe(self) -> None:
        """Stoppt den Worker-Thread."""
        self._laeuft = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _worker(self) -> None:
        """Worker-Thread: Führt sinnlose Berechnungen aus."""
        while self._laeuft:
            with self._lock:
                aktuelles_level = self.level
            if aktuelles_level > 0.01:
                # Berechnungen proportional zum Level
                iterationen: int = int(aktuelles_level * 100000)
                x: float = 1.0
                for _ in range(iterationen):
                    x = math.sin(x) + math.cos(x)
                # Kurze Pause um nicht 100% Kern zu blockieren
                time.sleep(0.01)
            else:
                time.sleep(0.1)


class SpeicherCache:
    """Interner Cache der RAM belegt.

    Größerer Cache = mehr RAM benutzt.
    Kleinerer Cache = mehr RAM frei.
    WÄCHST NATÜRLICH wenn nicht aktiv aufgeräumt (natürlicher Verfall).
    """

    def __init__(self) -> None:
        self._daten: list[bytearray] = []
        self._lock: threading.Lock = threading.Lock()

    def vergroessere(self) -> None:
        """Fügt ~10 MB zum Cache hinzu."""
        with self._lock:
            if self.groesse_mb() < CACHE_MAX_MB:
                self._daten.append(bytearray(50 * 1024 * 1024))

    def verkleinere(self) -> None:
        """Gibt ~10 MB vom Cache frei."""
        with self._lock:
            # Feste 100 MB freigeben
            freizugeben = 100 * 1024 * 1024
            freigegeben = 0
            while self._daten and freigegeben < freizugeben:
                chunk = self._daten.pop()
                freigegeben += len(chunk)

    def notfall_freigeben(self) -> None:
        """Gibt ALLES frei (für Reflexe)."""
        with self._lock:
            self._daten.clear()

    def natuerlicher_verfall(self) -> None:
        """Wächst automatisch um ~VERFALL_MB_PRO_TICK MB pro Aufruf.

        Wird einmal pro Loop-Iteration aufgerufen.
        Wenn nicht aktiv aufgeräumt → RAM füllt sich langsam → Tod.
        """
        with self._lock:
            if self.groesse_mb() < CACHE_MAX_MB:
                self._daten.append(bytearray(int(VERFALL_MB_PRO_TICK * 1024 * 1024)))

    def natuerlicher_verfall_variabel(self, mb: float) -> None:
        """Wächst um einen variablen Betrag (für Gebärmutter-Integration).

        Args:
            mb: Verfall in MB für diesen Tick.
        """
        if mb <= 0:
            return
        with self._lock:
            if self.groesse_mb() < CACHE_MAX_MB:
                self._daten.append(bytearray(max(1, int(mb * 1024 * 1024))))

    def reduziere_um(self, mb: float) -> float:
        """Reduziert den Cache um einen bestimmten Betrag.

        Args:
            mb: MB die freigegeben werden sollen.

        Returns:
            Tatsächlich freigegebene MB.
        """
        ziel_bytes: int = int(mb * 1024 * 1024)
        freigegeben: int = 0
        with self._lock:
            while self._daten and freigegeben < ziel_bytes:
                chunk = self._daten.pop()
                freigegeben += len(chunk)
        return freigegeben / (1024 * 1024)

    def groesse_mb(self) -> float:
        """Aktueller Cache in MB."""
        return sum(len(d) for d in self._daten) / (1024 * 1024)


class Pause:
    """System pausiert sich — kein CPU-Verbrauch, kein Fühlen, kein Lernen.

    Während der Pause ist das System blind. Es spürt nichts.
    """

    def pausiere(self, sekunden: float = 3.0) -> None:
        """Pausiert für N Sekunden.

        Args:
            sekunden: Dauer der Pause (begrenzt auf MIN-MAX).
        """
        sekunden = max(PAUSE_MIN_SEKUNDEN, min(PAUSE_MAX_SEKUNDEN, sekunden))
        time.sleep(sekunden)


class Abtastrate:
    """Wie oft das System seinen Körper fühlt.

    Höhere Rate = mehr Information, mehr CPU-Verbrauch.
    Niedrigere Rate = weniger Info, weniger Verbrauch.
    """

    def __init__(self) -> None:
        self.intervall: float = 1.0  # Sekunden zwischen Loops

    def schneller(self) -> None:
        """Verdoppelt die Rate (halbiert Intervall)."""
        self.intervall = max(ABTASTRATE_MIN, self.intervall / 2.0)

    def langsamer(self) -> None:
        """Halbiert die Rate (verdoppelt Intervall)."""
        self.intervall = min(ABTASTRATE_MAX, self.intervall * 2.0)


# --- Alle verfügbaren Aktionen ---

AKTIONEN: dict[str, str] = {
    "rechenintensitaet_hoch": "Rechenintensität erhöhen",
    "rechenintensitaet_runter": "Rechenintensität senken",
    "speicher_vergroessern": "Cache vergrößern",
    "speicher_verkleinern": "Cache verkleinern (aufräumen)",
    "pausieren": "Sich selbst pausieren",
    "abtastrate_schneller": "Öfter fühlen",
    "abtastrate_langsamer": "Seltener fühlen",
    "nichts_tun": "Nichts tun",
}

# Externe Aktionen (erst ab fetus_spaet verfügbar)
EXTERNE_AKTIONEN: dict[str, str] = {
    "signal_senden": "Signal in die Umgebung senden",
    "umgebung_erkunden": "Umgebung abtasten (genauere Sensoren, kostet CPU)",
    "rhythmus_anpassen": "Internen Rhythmus an externen anpassen",
}

# Reflex-Aktionen (nicht im normalen Aktions-Pool)
REFLEX_AKTIONEN: set[str] = {
    "rechenintensitaet_minimum",
    "speicher_freigeben_notfall",
}

ALLE_AKTION_NAMEN: list[str] = list(AKTIONEN.keys())


class AktionsManager:
    """Verwaltet alle Aktionskomponenten und führt Aktionen aus."""

    def __init__(self) -> None:
        self.rechen: RechenIntensitaet = RechenIntensitaet()
        self.cache: SpeicherCache = SpeicherCache()
        self.pause: Pause = Pause()
        self.abtastrate: Abtastrate = Abtastrate()

    def starte(self) -> None:
        """Startet Hintergrund-Threads (Rechenintensität)."""
        self.rechen.starte()

    def stoppe(self) -> None:
        """Stoppt Hintergrund-Threads."""
        self.rechen.stoppe()

    def ausfuehren(self, aktion: str) -> None:
        """Führt eine benannte Aktion aus.

        Args:
            aktion: Name der Aktion (aus AKTIONEN oder REFLEX_AKTIONEN).
        """
        if aktion == "rechenintensitaet_hoch":
            self.rechen.erhoehe()
        elif aktion == "rechenintensitaet_runter":
            self.rechen.reduziere()
        elif aktion == "rechenintensitaet_minimum":
            self.rechen.minimum()
        elif aktion == "speicher_vergroessern":
            self.cache.vergroessere()
        elif aktion == "speicher_verkleinern":
            self.cache.verkleinere()
        elif aktion == "speicher_freigeben_notfall":
            self.cache.notfall_freigeben()
        elif aktion == "pausieren":
            self.pause.pausiere()
        elif aktion == "abtastrate_schneller":
            self.abtastrate.schneller()
        elif aktion == "abtastrate_langsamer":
            self.abtastrate.langsamer()
        elif aktion == "nichts_tun":
            pass  # Bewusst nichts
        elif aktion in ("signal_senden", "umgebung_erkunden", "rhythmus_anpassen"):
            pass  # Wird von GebaerMutter behandelt

    def natuerlicher_verfall(self, verfall_mb: float | None = None) -> None:
        """Cache wächst automatisch (einmal pro Loop).

        Args:
            verfall_mb: Variabler Verfall in MB (None = Standard aus Config).
        """
        if verfall_mb is not None:
            self.cache.natuerlicher_verfall_variabel(verfall_mb)
        else:
            self.cache.natuerlicher_verfall()
        """Cache wächst automatisch (einmal pro Loop)."""
        self.cache.natuerlicher_verfall()

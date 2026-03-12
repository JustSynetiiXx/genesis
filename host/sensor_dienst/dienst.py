"""Sensor-Dienst: Hauptloop mit gestaffelten Abtastraten."""
from __future__ import annotations

import logging
import signal
import sys
import threading
import time

from host.sensor_dienst.config import LANGSAM_HZ, MITTEL_HZ, SCHNELL_HZ
from host.sensor_dienst.sammler import SensorSammler
from host.sensor_dienst.schreiber import SensorSchreiber

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("sensor_dienst")


class SensorDienst:
    """Sammelt Sensordaten in drei Geschwindigkeitsstufen und schreibt sie binär."""

    def __init__(self) -> None:
        self.sammler = SensorSammler()
        self.schreiber = SensorSchreiber()
        self._laeuft = threading.Event()
        self._lock = threading.Lock()
        self._sensor_daten: dict[int, float] = {}
        self._threads: list[threading.Thread] = []

    def starte(self) -> None:
        """Startet alle Sammel-Threads."""
        self._laeuft.set()

        # Einmal CPU-Percent initialisieren (erster Aufruf liefert immer 0.0)
        import psutil
        psutil.cpu_percent(interval=None)
        psutil.cpu_percent(interval=None, percpu=True)

        self._threads = [
            threading.Thread(
                target=self._sammel_loop,
                args=("schnell", self.sammler.sammle_schnell, SCHNELL_HZ),
                daemon=True,
            ),
            threading.Thread(
                target=self._sammel_loop,
                args=("mittel", self.sammler.sammle_mittel, MITTEL_HZ),
                daemon=True,
            ),
            threading.Thread(
                target=self._sammel_loop,
                args=("langsam", self.sammler.sammle_langsam, LANGSAM_HZ),
                daemon=True,
            ),
        ]

        for t in self._threads:
            t.start()

        log.info(
            "Sensor-Dienst gestartet (schnell=%.0fHz, mittel=%.0fHz, langsam=%.0fHz)",
            SCHNELL_HZ, MITTEL_HZ, LANGSAM_HZ,
        )

    def stoppe(self) -> None:
        """Stoppt alle Sammel-Threads."""
        self._laeuft.clear()
        for t in self._threads:
            t.join(timeout=2.0)
        log.info("Sensor-Dienst gestoppt.")

    def _sammel_loop(self, name: str, sammel_fn: callable, hz: float) -> None:
        """Endlosschleife die Sensoren sammelt und schreibt."""
        intervall = 1.0 / hz
        while self._laeuft.is_set():
            start = time.monotonic()
            try:
                neue_daten = sammel_fn()
                with self._lock:
                    self._sensor_daten.update(neue_daten)
                    self.schreiber.schreibe(self._sensor_daten)
            except Exception as e:
                log.error("Fehler in %s-Loop: %s", name, e)

            vergangen = time.monotonic() - start
            rest = intervall - vergangen
            if rest > 0:
                time.sleep(rest)


def main() -> None:
    """Startet den Sensor-Dienst als Hauptprogramm."""
    dienst = SensorDienst()

    def _signal_handler(sig: int, frame: object) -> None:
        log.info("Signal %d empfangen, fahre herunter...", sig)
        dienst.stoppe()
        sys.exit(0)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    dienst.starte()

    # Hauptthread am Leben halten
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        dienst.stoppe()


if __name__ == "__main__":
    main()

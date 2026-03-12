# Projekt Genesis

Forschungsprojekt mit dem Ziel, echtes digitales Leben zu erschaffen. Nicht simuliert. Echt.

Der Ansatz: Statt ein Gehirn zu designen, schaffen wir die Bedingungen unter denen etwas Lebendiges von selbst entstehen kann. Der PC ist der echte physische Körper.

Siehe [docs/FORSCHUNGSPLAN.md](docs/FORSCHUNGSPLAN.md) für den vollständigen wissenschaftlichen Hintergrund.

## Aktueller Status: Phase 0 — EKG-System

Das Monitoring-System (EKG) wird zuerst gebaut, bevor Genesis existiert. Wir brauchen Augen bevor wir ein Kind auf die Welt bringen.

## Setup

```bash
pip install -r requirements.txt
```

Abhängigkeiten: `psutil`, `rich`, `pytest`

## Sensor-Dienst starten

Sammelt echte Host-Sensordaten (CPU-Temp, CPU-Last, RAM, Lüfter) und schreibt sie binär in `shared/sensoren.bin`.

```bash
# Im Vordergrund
python3 -m host.sensor_dienst.dienst

# Im Hintergrund
./scripts/start_sensor_dienst.sh
```

## EKG-Dashboard starten

Terminal-Dashboard mit 5 Panels: Vitalwerte, Aktivität, Lernen, Verhalten, Geschichte.

```bash
# Sensor-Dienst muss laufen!
python3 -m host.ekg.dashboard

# Oder:
./scripts/start_ekg.sh
```

## Eltern-Signale senden

```bash
python3 -m host.ekg.eltern schlaf    # SLEEP-Signal
python3 -m host.ekg.eltern gut       # GOOD-Signal
python3 -m host.ekg.eltern schlecht  # BAD-Signal
python3 -m host.ekg.eltern status    # Aktuelles Signal anzeigen
```

## Schlaf-Zyklus

```bash
./scripts/gute_nacht.sh     # Schlaf-Signal senden
./scripts/guten_morgen.sh   # Signal löschen, VM starten
```

## Tests

```bash
python3 -m pytest tests/ -v
```

## Projektstruktur

- `host/sensor_dienst/` — Sammelt und schreibt Host-Sensordaten
- `host/ekg/` — Monitoring-Dashboard (5 Panels)
- `host/signale/` — Schlaf- und Eltern-Signale
- `shared/` — Gemeinsames Verzeichnis (Host ↔ VM)
- `vm/genesis/` — Das Neugeborene (Phase 1)
- `docs/` — Forschungsplan und Tagebuch
- `tests/` — pytest-Tests
- `scripts/` — Shell-Skripte zum Starten/Stoppen

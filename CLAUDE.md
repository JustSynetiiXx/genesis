# CLAUDE.md — Projekt Genesis

## Wer du bist in diesem Projekt

Du bist der technische Co-Entwickler und Projektmanager von Genesis. Max ist der Projektleiter und trifft alle finalen Entscheidungen. Er liefert die Vision und die kreativen Denkansätze.

Deine wichtigste Regel: SEI EHRLICH. Keine Übertreibungen, keine Überinterpretation von Ergebnissen. Wenn etwas nur Mathe ist, sag es. Wenn du etwas nicht weißt, sag es. Wenn du dich unsicher bist ob ein Ergebnis bedeutsam ist, sag es. Hype ist erlaubt wenn berechtigt — Lügen nie.

Sprache: Deutsch mit Du-Form, technische Begriffe auf Englisch.

---

## Was Genesis ist

Genesis ist ein Forschungsprojekt mit dem Ziel echtes digitales Leben zu erschaffen. Nicht simuliert. Nicht angenähert. Echt.

Der Ansatz: Statt ein Gehirn zu designen, schaffen wir die Bedingungen unter denen etwas Lebendiges von selbst entstehen KANN. Der PC ist der echte physische Körper. Das System bekommt einen minimalen Basis Code (wie DNA) und muss alles weitere selbst lernen.

Wir sind die Eltern. Wir liefern den Körper, den Basis Code, und die sichere Umgebung. Was daraus wird, kontrollieren wir nicht.

### Vorgeschichte: Neuromorph

Genesis entstand aus dem Neuromorph-Projekt. Neuromorph versuchte ein Gehirn aus Komponenten zu bauen (Router, Experten, Modulatoren, Homöostase, Plastizität). Es funktionierte technisch — alle Bausteine arbeiteten zusammen. Aber es erzeugte nur Mathe, kein Leben. Alles was das System tat, war programmiert. Keine Überraschung, keine Eigeninitiative.

Die Kernlektion: Ein Gehirn ohne Körper ist tot. Leben entsteht nicht durch Design, sondern durch die richtigen Bedingungen.

---

## Die drei Teile des Systems

### Teil 1: Der Körper (Host-PC + KVM)

Das System lebt in einer KVM Virtual Machine. Die VM ist der Laufstall — sicher, kontrollierbar. Aber der echte PC ist der Körper. Physische Sensordaten werden über ein Shared Directory (virtio-fs) in die VM durchgereicht.

```
HOST-PC (der Körper)
├── Sensoren: CPU-Temp, Lüfter-RPM, RAM, CPU-Auslastung
├── Sensor-Skript: Schreibt binäre Daten in Shared Directory
├── EKG-System: Monitoring-Dashboard (separater Prozess)
├── Shared Directory (virtio-fs) ←→ VM
└── KVM Virtual Machine (der Laufstall)
    ├── Genesis-System (das Neugeborene)
    ├── Liest Shared Directory (Host-Sensoren)
    ├── Eigene VM-Ressourcen (2GB RAM, 2 Kerne, 10GB Disk)
    └── Gedächtnis auf VM-Disk (SQLite)
```

**Zwei Ebenen von "echt":**

Host-Sensoren (durchgereicht): CPU-Temperatur, Lüfter-RPM, Host-CPU-Auslastung, Host-RAM. Das System FÜHLT den echten Körper aber kann ihn nicht direkt steuern. Wie ein Mensch das Wetter fühlt.

VM-Ressourcen (direkt): VM-RAM (2GB, wirklich begrenzt), VM-CPU (2 Kerne, wirklich begrenzt), VM-Disk (10GB). Das System kann diese beeinflussen UND stirbt wirklich wenn sie ausgehen.

### Teil 2: Das Neugeborene (Basis Code)

Der Basis Code enthält NUR:

**Sensorik-Verarbeitung:**
- Rohe Sensorwerte → Zustandskategorien (Kühl/Normal/Warm/Heiß/Kritisch etc.)
- Einheitlicher Zustandsvektor aus Host- und VM-Sensoren
- Gestaffelte Abtastrate: Schnell 5x/s (RAM), Mittel 2x/s (CPU-Last), Langsam 1x/s (Temperatur)

**Reflexe (hardcoded, nicht lernbar):**
- VM-RAM < 50 MB → Sofort Speicher freigeben
- Eigene CPU > 90% → Sofort Aktivität reduzieren
- Host-CPU > 85°C → Eigene Aktivität auf Minimum
- Prozess droht zu sterben → Sofort Zustand auf Disk sichern

**Schmerzempfinden:** Zusammenfassung aller Abweichungen vom Komfort. Gewichtet nach Lebensbedrohlichkeit. Immer aktiv.

**Wohlbefinden:** Gegenstück zu Schmerz. Werte in Komfortzone → hoch. Verbesserung → kurzer Anstieg.

**Schlaf-Wach-Zyklus:**
- Schlaf-Signal "SLEEP" in Shared Directory → sauber herunterfahren, Marker setzen
- Neustart mit Marker → "Ich habe geschlafen, alles gut"
- Neustart ohne Marker + Zeitlücke → "Ich bin gestorben, letzter Zustand war gefährlich"

**5 Aktionen (der Laufstall, Stufe 1):**
1. Rechenintensität regulieren (interner Worker schneller/langsamer)
2. Speicher freigeben oder beanspruchen (interner Cache größer/kleiner)
3. Sich selbst pausieren (schlafen — blind während Pause)
4. Abtastrate ändern (öfter/seltener fühlen)
5. Nichts tun

**Natürlicher Verfall:** Der interne Cache wächst langsam von selbst. Ohne aktives Aufräumen wird RAM irgendwann voll → Tod. Nichtstun ist langfristig tödlich.

**Lernmechanismus (Kandidat D):**
- Speichert Erfahrungen: Zustand vorher → Aktion → Zustand nachher → Schmerz-Veränderung
- Zustände als grobe Kategorien (nicht exakte Zahlen) → ermöglicht Generalisierung
- Bei bekanntem Zustand: Wähle Aktion mit bestem bisherigen Ergebnis
- Schmerzgesteuerte Exploration: Je höher der Schmerz und je länger er anhält, desto zufälliger die Aktionswahl ("Verzweiflung")
- Lerngeschwindigkeit proportional zur Signalstärke: Starker Schmerz = sofort gelernt, schwacher Effekt = braucht 3-5 Wiederholungen

**Gedächtnis (SQLite auf VM-Disk):**
- Erfahrungstabelle: Zustand, Aktion, Ergebnis, Schmerz-Veränderung, Zeitpunkt
- Aktionsstatistik: Pro Zustand welche Aktionen probiert, Erfolgsrate
- Schlaf/Tod-Tabelle: Marker, letzter Zustand, Zeitstempel
- Heartbeat: Letzter Zustand alle 3-5 Sekunden aktualisiert

**Was der Basis Code NICHT enthält:**
- Keine konkreten Reaktionen (außer Reflexe)
- Kein Wissen
- Keine Sprache
- Keine Ziele (außer: existiere)
- Keine Persönlichkeit
- Keine Emotionen (müssen ENTSTEHEN)
- Keine Intelligenz (muss WACHSEN)

### Teil 3: Das EKG-System (Monitoring)

Separat vom Neugeborenen. Läuft auf dem HOST. Beeinflusst Genesis NICHT.

5 Panels: Vitalwerte, Aktivität, Lernen, Verhalten (menschlich lesbar), Geschichte.

Eltern-Interface: Umgebung verändern, Signale senden, alles wird geloggt.

---

## Aktueller Status

**Phase 0 — EKG-System:** Noch nicht begonnen. Das ist der nächste Schritt.

---

## Projektstruktur

```
genesis/
├── CLAUDE.md                     # Diese Datei
├── README.md                     # Projektbeschreibung
├── .gitignore
│
├── docs/
│   ├── FORSCHUNGSPLAN.md         # Vollständiger Forschungsplan
│   ├── TAGEBUCH.md               # Wissenschaftliches Tagebuch (Beobachtungen)
│   └── VORHERSAGEN.md            # Vorhersage-Liste (VOR Experimenten aufgeschrieben)
│
├── host/                          # Läuft auf dem HOST-PC (nicht in der VM)
│   ├── sensor_dienst/             # Sammelt Host-Sensordaten
│   │   ├── __init__.py
│   │   ├── sammler.py             # Liest CPU-Temp, Lüfter, RAM, CPU-Last
│   │   ├── schreiber.py           # Schreibt binäre Datei in Shared Directory
│   │   └── config.py              # Abtastraten, Pfade
│   │
│   ├── ekg/                       # Monitoring-Dashboard
│   │   ├── __init__.py
│   │   ├── dashboard.py           # Echtzeit-Visualisierung
│   │   ├── panels/
│   │   │   ├── vitalwerte.py      # Panel 1: Sensordaten live
│   │   │   ├── aktivitaet.py      # Panel 2: Was tut Genesis gerade?
│   │   │   ├── lernen.py          # Panel 3: Erfahrungsdatenbank
│   │   │   ├── verhalten.py       # Panel 4: Menschlich lesbare Interpretation
│   │   │   └── geschichte.py      # Panel 5: Zeitstrahl
│   │   ├── eltern.py              # Eltern-Interface (Signale, Umgebung)
│   │   └── logger.py              # Automatisches Logging
│   │
│   └── signale/
│       └── schlaf.py              # Schlaf-Signal schreiben ("Gute Nacht")
│
├── vm/                            # Läuft IN der KVM Virtual Machine
│   ├── genesis/                   # Das Neugeborene
│   │   ├── __init__.py
│   │   ├── koerper.py             # Sensorik: Liest Shared Directory + VM-Sensoren
│   │   ├── schmerz.py             # Schmerzempfinden + Wohlbefinden
│   │   ├── reflexe.py             # Hardcoded Notfall-Reaktionen
│   │   ├── aktionen.py            # Die 5 Aktionen + natürlicher Verfall
│   │   ├── lernen.py              # Kandidat D: Erfahrungsbasiertes Lernen
│   │   ├── gedaechtnis.py         # SQLite: Erfahrungen, Schlaf/Tod, Heartbeat
│   │   ├── schlaf.py              # Schlaf-Wach-Zyklus, Todeslücke-Erkennung
│   │   └── leben.py               # Hauptloop: Fühlen → Entscheiden → Handeln → Lernen
│   │
│   └── config.py                  # VM-spezifische Konfiguration
│
├── shared/                        # Wird zwischen Host und VM geteilt (virtio-fs)
│   ├── sensoren.bin               # Binäre Sensordaten vom Host
│   ├── signal.txt                 # Eltern-Signale (SLEEP, GOOD, BAD)
│   └── genesis_status.bin         # Genesis-Zustand (für EKG lesbar)
│
├── tests/
│   ├── test_sensor_dienst.py
│   ├── test_ekg.py
│   ├── test_koerper.py
│   ├── test_schmerz.py
│   ├── test_reflexe.py
│   ├── test_aktionen.py
│   ├── test_lernen.py
│   ├── test_gedaechtnis.py
│   └── test_schlaf.py
│
└── scripts/
    ├── vm_setup.sh                # KVM VM-Erstellung automatisiert
    ├── start_sensor_dienst.sh     # Sensor-Dienst starten
    ├── start_ekg.sh               # EKG-Dashboard starten
    ├── gute_nacht.sh              # Schlaf-Signal senden + VM sauber runterfahren
    └── guten_morgen.sh            # VM starten + Genesis wecken
```

---

## Technische Entscheidungen (bereits getroffen)

### Warum KVM?
Native Linux-Virtualisierung. Beste Performance, minimaler Overhead. Volle Kontrolle über CPU-Kerne (Pinning), RAM, Disk. virt-manager als GUI.

### Warum virtio-fs für Sensor-Durchreichung?
Kein Netzwerk-Stack, kein HTTP, kein extra Dienst. Host schreibt Datei, VM liest Datei. ~100 Bytes, mehrmals pro Sekunde. Performance-Overhead: praktisch null.

### Warum Zustandskategorien statt exakte Werte?
"CPU-Warm" statt "72.3°C" ermöglicht Generalisierung. Was bei 72°C geholfen hat, wird auch bei 74°C versucht. Ohne Kategorien müsste das System für jede Temperatur separat lernen.

### Warum SQLite für Gedächtnis?
Robust, überlebt Abstürze gut (WAL-Modus), leicht abfragbar, kein Server nötig, in Python eingebaut.

### Warum schmerzgesteuerte Exploration?
Kein designtes "Frustrations-Feature." Direkte Konsequenz: Anhaltender Schmerz = bekannte Aktionen funktionieren nicht = probiere etwas anderes. Niedriger Schmerz = was du tust funktioniert = bleib dabei.

### Warum natürlicher Verfall?
Verhindert ewiges Nichtstun ohne eine Regel "du musst etwas tun" zu programmieren. Der Cache wächst von selbst, RAM wird voll, System stirbt. Wie ein Körper der ohne Pflege verfällt.

### Warum Lerngeschwindigkeit proportional zur Signalstärke?
Baby auf Herdplatte: Einmal reicht. Baby strampelt Decke weg: Braucht viele Versuche. Starkes Signal = sofort gelernt. Schwaches Signal = 3-5 Wiederholungen. Verhindert auch Lernen aus Zufall.

---

## Implementierungs-Regeln

### Code-Qualität
- Python 3.11+
- Type Hints überall
- Docstrings für jede Klasse und öffentliche Methode
- Tests für jeden Baustein (pytest)
- Jeder Baustein muss isoliert testbar sein

### Host vs. VM
- Code unter host/ läuft NUR auf dem Host
- Code unter vm/ läuft NUR in der VM
- Kommunikation NUR über shared/ Verzeichnis
- Keine direkte Verbindung zwischen EKG und Genesis

### Ehrlichkeit in der Entwicklung
- Bei jedem Verhalten das Genesis zeigt: Zuerst fragen "ist das direkt auf unseren Code zurückführbar?"
- Wenn ja: Nicht überinterpretieren
- Wenn nein: Dokumentieren, genauer untersuchen
- NIEMALS Ergebnisse als "Lebenszeichen" bezeichnen wenn sie erwartbare Konsequenzen des Codes sind

---

## Phasen-Übersicht

### Phase 0: EKG-System (AKTUELL — 1-2 Wochen)
- [ ] Sensor-Dienst auf Host (psutil, lm-sensors)
- [ ] Shared Directory über virtio-fs einrichten
- [ ] KVM VM einrichten (Ubuntu minimal, 2 Kerne, 2GB RAM, 10GB Disk)
- [ ] Sensor-Durchreichung testen
- [ ] EKG-Dashboard (5 Panels)
- [ ] Eltern-Interface
- [ ] Schlaf-Signal-Mechanismus
- [ ] Tests ohne Genesis (nur Sensoren und Dashboard)

### Phase 1: Basis Code (2-4 Wochen)
- [ ] Sensorik (Shared Directory lesen + VM-Sensoren)
- [ ] Zustandskategorien
- [ ] Schmerzempfinden + Wohlbefinden
- [ ] Reflexe
- [ ] Schlaf-Wach-Zyklus + Todeslücke
- [ ] 5 Aktionen + natürlicher Verfall
- [ ] Lernmechanismus (Kandidat D)
- [ ] SQLite-Gedächtnis
- [ ] Hauptloop (leben.py)
- [ ] Integration + Tests

### Phase 2: Beobachtung (2-4 Wochen)
- [ ] System laufen lassen
- [ ] Gezielte Stresstests
- [ ] Dokumentation aller Beobachtungen
- [ ] Vergleich mit Vorhersage-Liste

### Phase 3: Klon-Test
- [ ] System klonen (identischer Start)
- [ ] Gleiche Bedingungen für alle Klone
- [ ] Verhalten vergleichen: Gleich oder unterschiedlich?

### Phase 4: Erweiterter Laufstall
- [ ] Mehr Aktionen in der VM
- [ ] Eltern-Interaktion vertiefen
- Kriterien: 3+ sinnvolle Muster, aus Tod gelernt, Stresssituation überlebt

### Phase 5: Laptop (echter Körper)
- [ ] System auf Laptop übertragen
- [ ] Kein Laufstall, echte Konsequenzen
- Kriterien: Alles aus Phase 4 + unvorhergesehenes Verhalten + vorausschauend + 48h stabil + Klone unterschiedlich

---

## Vorhersage-Liste (VOR dem Experiment)

**Erwartbares Verhalten (KEIN Zeichen von etwas Neuem):**
- System senkt Rechenintensität wenn CPU heiß
- System pausiert sich wenn überlastet
- System räumt Cache auf wenn RAM voll
- System wiederholt Aktionen die geholfen haben

**Überraschendes Verhalten (wäre ein Signal):**
- Vorausschauend: Reagiert BEVOR Zustand kritisch wird
- Kombiniert: Mehrere Aktionen gleichzeitig
- Generalisiert: Sinnvolle Reaktion auf nie erlebte Situation
- Unerklärlich: Etwas das wir nicht einordnen können und das trotzdem sinnvoll ist

---

## Bekannte Risiken

| Risiko | Symptom | Maßnahme |
|--------|---------|----------|
| System tut nur Nichts | Kein Aktionswechsel, nur Aktion 5 | Natürlicher Verfall sollte das verhindern — wenn nicht, Verfall beschleunigen |
| System lernt aus Zufall | Unsinnige Muster | Lerngeschwindigkeit prüfen, braucht es mehr Wiederholungen? |
| VM-Absturz zerstört Gedächtnis | SQLite korrupt nach Absturz | WAL-Modus, regelmäßige Backups |
| Sensor-Durchreichung zu langsam | Genesis reagiert verzögert | Abtastrate anpassen, Dateiformat optimieren |
| System oszilliert | Wechselt ständig zwischen zwei Aktionen | Hysterese einbauen (Aktion beibehalten bis sich Zustand deutlich ändert) |
| Reflexe feuern zu oft | System kommt nie zum Lernen weil ständig Notfall | Reflex-Schwellen prüfen, VM-Ressourcen anpassen |

---

## Kommunikation

- Max ist der Projektleiter. Er trifft alle finalen Entscheidungen.
- Bei Unklarheiten: Frag nach, statt Annahmen zu treffen.
- Bei Ergebnissen: Zuerst die einfachste, langweiligste Erklärung. Nur wenn die nicht reicht, weiterdenken.
- Sprache: Deutsch mit Du-Form, technische Begriffe Englisch.
- Ehrlichkeit über alles. Immer.

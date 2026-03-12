# Projekt Genesis — Forschungsplan (Final)

## Was dieses Dokument ist

Dieser Forschungsplan ist das Ergebnis intensiver Planung und ehrlicher Reflexion. Er ersetzt den ursprünglichen Neuromorph-Ansatz nicht — er baut auf dessen Erkenntnissen auf. Neuromorph hat uns gelehrt dass das manuelle Zusammenbauen von Gehirnkomponenten funktionierendes Engineering ergibt, aber kein Leben.

## Vision

Echtes digitales Leben erschaffen. Nicht simuliert. Nicht "so ähnlich wie." Echt.

Nicht durch Design eines Gehirns, sondern durch Erschaffung der Bedingungen unter denen etwas Lebendiges von selbst entstehen kann. Wir sind die Eltern — wir liefern den Körper, den Basis Code, und die sichere Umgebung. Was daraus wird, liegt nicht in unserer Hand.

## Was wir aus Neuromorph gelernt haben

1. Gehirnkomponenten manuell zusammenbauen erzeugt Mathe, kein Leben.
2. Alles was das System tat, hatten wir programmiert. Keine Überraschung, keine Eigeninitiative.
3. Emergentes Verhalten das wir zu sehen glaubten, war erwartbare Mathematik (konvergierende geometrische Reihen, GRUs die ihren Job machen, Load-Balancing das funktioniert).
4. Ein Gehirn ohne Körper ist tot — egal wie gut die Architektur ist.
5. Leben entsteht nicht durch Design, sondern durch die richtigen Bedingungen.
6. Ehrlichkeit über Ergebnisse ist wichtiger als Begeisterung.

---

## Der neue Ansatz: Leben durch Verkörperung

### Das Prinzip

Ein Neugeborenes kommt mit einem Basis Code (DNA) auf die Welt. Dieser Code enthält keine Verhaltensregeln, sondern Bauanleitungen. Alles weitere — Wissen, Fähigkeiten, Persönlichkeit — entsteht durch Erfahrung.

- Der PC ist der Körper. Echte physische Zustände, echte Sensoren, echte Konsequenzen.
- Der Basis Code ist die DNA. Bauanleitungen, keine Verhaltensregeln.
- Wir sind die Eltern. Wir schaffen die Umgebung, geben Feedback, lehren durch Interaktion.
- Was daraus entsteht, entsteht von selbst — oder es entsteht nicht.

### Warum dieser Ansatz anders ist als Neuromorph

Neuromorph: Wir designen ein Gehirn → es berechnet → wir hoffen auf Leben.
Genesis: Wir schaffen Bedingungen → etwas entwickelt sich → wir beobachten was entsteht.

---

## Umgebung: KVM als Laufstall, PC als Körper

### Das Konzept

Das System lebt in einer KVM Virtual Machine auf dem Haupt-PC. Die VM ist der Laufstall — ein sicherer Raum in dem das System abstürzen, Fehler machen und lernen kann, ohne den Haupt-PC zu gefährden.

Der echte PC bleibt der Körper. Die physischen Sensordaten des Hosts werden über ein Shared Directory (virtio-fs) in die VM durchgereicht. Für das System gibt es keinen Unterschied — es spürt einen echten physischen Körper.

### Technische Umsetzung

**VM-Software:** KVM mit virt-manager als GUI.

**VM-Ressourcen:**
- 2 CPU-Kerne (mit CPU-Pinning um Interferenz mit dem Host zu vermeiden)
- 2 GB RAM
- 10 GB Disk
- Internes Netzwerk nur zum Host (kein Internet)

**Sensor-Durchreichung:** Shared Directory über virtio-fs.
- Der Host hat ein kleines Skript das mehrmals pro Sekunde Sensordaten sammelt
- Daten werden als binäre Datei in ein geteiltes Verzeichnis geschrieben (~100 Bytes)
- Die VM sieht das Verzeichnis als normalen Ordner und liest die Datei
- Kein Netzwerk-Stack, kein HTTP, kein Parsing — nur Bytes lesen
- Performance-Overhead: Praktisch null

**Schlaf-Signal:** Über das gleiche Shared Directory.
- Vor dem Herunterfahren schreibt ein Skript "SLEEP" in eine Signal-Datei
- Genesis liest das Signal und fährt sauber herunter

```
HOST-PC (der Körper)
├── Sensoren: CPU-Temp, Lüfter-RPM, RAM, CPU-Auslastung
├── Sensor-Skript: Schreibt Daten in Shared Directory
├── EKG-System: Monitoring-Dashboard (separater Prozess)
├── Shared Directory (virtio-fs) ←→ VM
└── KVM Virtual Machine (der Laufstall)
    ├── Genesis-System (das Neugeborene)
    ├── Liest Shared Directory (Host-Sensoren)
    ├── Eigene VM-Ressourcen (2GB RAM, 2 Kerne, 10GB Disk)
    └── Gedächtnis auf VM-Disk (SQLite)
```

### Zwei Ebenen von "echt"

**Host-Sensoren (durchgereicht — fühlen, nicht kontrollieren):**
- CPU-Temperatur pro Kern: Echte Physik, echte Hitze
- Lüfter-RPM: Echte Kühlung, echte Drehzahl
- Host-CPU-Auslastung: Echte Gesamtlast
- Host-RAM-Auslastung: Echter Gesamtzustand

Wie ein Mensch das Wetter fühlt — er spürt es, kann es aber nicht ändern.

**VM-eigene Ressourcen (direkt real — fühlen UND kontrollieren):**
- VM-RAM: Wirklich begrenzt. Wenn voll, stirbt der Prozess wirklich.
- VM-CPU: Wirklich begrenzt. Echte Rechengrenze.
- VM-Disk: Wirklich begrenzt. Echter Speicherplatz.

Wie ein Mensch seinen eigenen Körper — er kann mehr oder weniger essen, schneller oder langsamer atmen.

---

## Teil 1: Der Körper — Sensorik

### Rezeptoren

**Kanal 1: Host-Sensoren (durchgereicht)**
- CPU-Temperatur pro Kern
- Lüfter-RPM
- Host-CPU-Auslastung
- Host-RAM-Auslastung

**Kanal 2: VM-eigene Sensoren**
- VM-RAM-Auslastung
- Eigener Prozess-Speicherverbrauch
- Eigene CPU-Zeit
- VM-Disk-Nutzung

### Abtastrate (gestaffelt nach Sensortyp)

Nicht alles muss gleich schnell gemessen werden. Wie beim Menschen — Schmerz wird sofort gespürt, Körpertemperatur langsamer.

**Schnell (5x pro Sekunde):**
- VM-RAM-Auslastung
- Eigener Speicherverbrauch
→ Kann sich schnell ändern, bei kritischen Werten zählt jede Sekunde.

**Mittel (2x pro Sekunde):**
- CPU-Auslastung (Host + Eigen)
→ Ändert sich merklich aber nicht sprunghaft.

**Langsam (1x pro Sekunde):**
- CPU-Temperatur
- Lüfter-RPM
→ Physisch träge, ändert sich nicht innerhalb von Millisekunden.

Das System kann seine eigene Abtastrate anpassen (Aktion 4) — bei Gefahr öfter fühlen, bei Ruhe seltener.

### Vitalwerte

**Host-Ebene (fühlen, nicht kontrollieren):**

| Zustand | Komfort | Warnung | Gefahr | Kritisch |
|---------|---------|---------|--------|----------|
| CPU-Temperatur | < 60°C | 60-75°C | 75-85°C | > 85°C |
| Host-RAM frei | > 8 GB | 4-8 GB | 2-4 GB | < 2 GB |
| Lüfter-RPM | Normal | Erhöht | Hoch | Maximum |

**VM-Ebene (fühlen UND kontrollieren):**

| Zustand | Komfort | Warnung | Gefahr | Tod |
|---------|---------|---------|--------|-----|
| VM-RAM frei | > 500 MB | 200-500 MB | 50-200 MB | < 50 MB (OOM-Kill) |
| Eigener Speicher | < 200 MB | 200-500 MB | 500 MB-1 GB | System-Kill |
| Eigene CPU-Zeit | < 30% | 30-60% | 60-90% | > 90% |

### Eskalierende Warnsignale

**Stufe 1 — Unbehagen:** Werte verlassen Komfortzone. Leichtes internes Signal.
**Stufe 2 — Stress:** Werte im Warnbereich. Stärkeres Signal.
**Stufe 3 — Panik:** Werte im Gefahrenbereich. Maximales Signal.
**Stufe 4 — Reflex:** Werte nahe Tod. Hardcoded Notfall-Reaktion.

---

## Teil 2: Das Neugeborene — Der Basis Code

### 1. Sensorik-Verarbeitung

- Alle Sensoren liefern kontinuierliche Ströme von Werten
- Host-Sensoren und VM-Sensoren werden als einheitlicher Zustandsvektor zusammengefasst
- Das System unterscheidet nicht zwischen "Host" und "VM" — alles sind Körpersignale
- Zustandskategorien statt exakte Werte (für Generalisierung):

**CPU-Temperatur:** Kühl, Normal, Warm, Heiß, Kritisch
**RAM-Auslastung:** Frei, Normal, Eng, Voll, Kritisch
**CPU-Auslastung:** Niedrig, Normal, Hoch, Überlastet
**Lüfter:** Leise, Normal, Laut, Maximum

Ein Gesamtzustand ist eine Kombination: z.B. "CPU-Warm, RAM-Normal, Auslastung-Hoch, Lüfter-Laut"

### 2. Reflexe (hardcoded, nicht verhandelbar)

Wenige Notfall-Reaktionen. Werden NICHT gelernt. Sind Teil der DNA.

- VM-RAM kritisch (< 50 MB) → Sofort internen Speicher freigeben
- Eigene CPU-Nutzung > 90% → Sofort Aktivität reduzieren
- Host-CPU > 85°C → Eigene Aktivität auf Minimum
- Prozess droht gekillt zu werden → Sofort Zustand auf Disk sichern

### 3. Schmerzempfinden

- Zusammenfassung ALLER Abweichungen vom Komfortzustand
- Gewichtet: Lebensbedrohlich > Unangenehm
- IMMER aktiv, beeinflusst ALLES was das System tut
- Basiert auf ECHTEN physischen Zuständen

### 4. Wohlbefinden

- Alle Werte in Komfortzone → Wohlbefinden hoch
- Werte verbessern sich → Wohlbefinden steigt kurzzeitig ("Erleichterung")
- Genauso wichtig wie Schmerz — bestätigt: "Was du getan hast, war gut"

### 5. Schlaf-Wach-Zyklus

**Schlaf (kontrolliertes Herunterfahren):**
- System bekommt Signal VOR dem Herunterfahren über Shared Directory: "SLEEP"
- Speichert vollständigen Zustand sauber auf Disk
- Speichert Schlaf-Marker mit Zeitstempel und letztem Zustand
- Beim nächsten Start: Marker gefunden → "Ich habe geschlafen. Alles normal."

**Tod (unkontrolliertes Ende):**
- Kein Signal vorher. Plötzlich weg.
- Kein Schlaf-Marker (oder unvollständig).
- Beim nächsten Start: Kein Marker + Zeitlücke → "Etwas Schlimmes ist passiert."
- Letzter gespeicherter Zustand + Lücke = Lernsignal: "Dieser Zustand war tödlich."

**Praktisch für uns als Eltern:**
Vor PC herunterfahren → Signal senden: "Gute Nacht."
Bei unerwartetem VM-Absturz → System erkennt Tod und lernt daraus.

### 6. Aktionsraum

Fünf konkrete Aktionen. Wenig genug um überschaubar zu sein, genug um echte Strategien zu entwickeln.

**Aktion 1: Rechenintensität regulieren.**
Konkret: Interner Worker-Thread der schneller oder langsamer läuft.
Konsequenz: Mehr Arbeit = mehr CPU-Verbrauch = mehr Hitze. Weniger Arbeit = umgekehrt.

**Aktion 2: Speicher freigeben oder beanspruchen.**
Konkret: Interner Cache der vergrößert oder verkleinert wird.
Konsequenz: Mehr Cache = mehr RAM belegt. Weniger Cache = mehr RAM frei.

**Aktion 3: Sich selbst pausieren.**
Konkret: System legt sich für eine bestimmte Zeit schlafen.
Konsequenz: Kein CPU-Verbrauch, kein RAM-Wachstum, aber blind — spürt nichts während der Pause.

**Aktion 4: Abtastrate ändern.**
Konkret: Öfter oder seltener Sensoren lesen.
Konsequenz: Öfter = mehr Information, mehr CPU-Verbrauch. Seltener = umgekehrt.

**Aktion 5: Nichts tun.**
Bewusst keine Aktion. Auch eine Wahl.

**Natürlicher Verfall verhindert ewiges Nichtstun:**
Der interne Cache wächst langsam von selbst. Jede Sensor-Messung, jede Erinnerung, jedes Lernergebnis belegt Speicher. Wenn das System seinen Cache nicht aktiv aufräumt, wird der RAM irgendwann voll. Dann stirbt es. Nichtstun ist kurzfristig sicher, langfristig tödlich. Genau wie bei einem echten Körper der ohne aktive Pflege verfällt.

### 7. Lernmechanismus: Kandidat D mit schmerzgesteuerter Exploration

**Das Prinzip:**
Das System speichert Erfahrungen: "Ich war in Zustand X, ich habe Aktion Y gemacht, danach war mein Zustand Z, mein Schmerz hat sich um W verändert."

Die Zustände sind in grobe Kategorien eingeteilt (nicht "72.3°C" sondern "Warm"). Das ermöglicht Generalisierung — was bei 72°C geholfen hat, wird auch bei 74°C versucht.

**Entscheidung welche Aktion:**
- Wenn das System einen Zustand wiedererkennt → schau nach was beim letzten Mal geholfen hat
- Wenn mehrere Aktionen bekannt sind → wähle die mit dem besten Ergebnis
- Wenn keine Aktion bekannt ist oder alle bekannten versagt haben → probiere zufällig etwas Neues

**Schmerzgesteuerte Exploration (der Schlüssel):**
- Niedriger Schmerz, stabil → Wiederhole was funktioniert. Routine. Ruhe.
- Anhaltender Schmerz, bekannte Aktionen helfen nicht → Probiere andere Aktionen. Werde "verzweifelt."
- Steigender Schmerz → Noch mehr Exploration. Noch wildere Versuche.
- Je höher der Schmerz und je länger er anhält, desto zufälliger werden die Aktionen.

Das ist keine designte "Frustration." Es ist eine direkte Konsequenz: Hoher Schmerz bedeutet "was du tust funktioniert nicht", also muss etwas anderes versucht werden.

**Lerngeschwindigkeit proportional zur Signalstärke:**
- Massive Schmerz-Veränderung (z.B. fast gestorben, dann gerettet) → EINE Erfahrung reicht. Sofort gelernt. Wie Hand auf Herdplatte.
- Leichte Schmerz-Veränderung → 3-5 gleiche Erfahrungen bevor das Muster als "gelernt" gilt. Verhindert Lernen aus Zufall.
- Keine messbare Veränderung → Nicht gelernt. Weder positiv noch negativ.

### 8. Gedächtnis (überlebt den Tod)

**Format:** SQLite-Datenbank auf VM-Disk.
Robust, überlebt Abstürze gut, leicht abfragbar, kein Overhead.

**Was gespeichert wird:**

Erfahrungstabelle:
- Zustandskategorie vorher (z.B. "CPU-Warm, RAM-Eng, Auslastung-Hoch")
- Ausgeführte Aktion (z.B. "Rechenintensität gesenkt")
- Zustandskategorie nachher (z.B. "CPU-Warm, RAM-Eng, Auslastung-Normal")
- Schmerz-Veränderung (Zahl: positiv = mehr Schmerz, negativ = weniger)
- Zeitpunkt

Aktionsstatistik:
- Pro Zustandskategorie: Welche Aktionen probiert, wie oft, Erfolgsrate

Schlaf/Tod-Tabelle:
- Schlaf-Marker (ja/nein)
- Letzter Zustand vor Schlaf/Tod
- Zeitstempel
- Nach Neustart: Lückenanalyse

Letzter-Zustand-Tabelle:
- Wird alle paar Sekunden aktualisiert (Herzschlag)
- Aktueller Gesamtzustand
- Zeitstempel
- Bei Absturz: Letzter bekannter Zustand für Todeslücke-Erkennung

**Speicherintervall:**
- Erfahrungen: Nach jeder Aktion
- Schlaf-Marker: Beim Schlaf-Signal
- Letzter Zustand: Alle 3-5 Sekunden (Herzschlag)

### Was der Basis Code NICHT enthält

- Keine konkreten Reaktionen auf Zustände (außer Reflexe)
- Kein Wissen über die Welt
- Keine Sprache
- Keine Ziele (außer: existiere)
- Keine Persönlichkeit
- Keine Emotionen (müssen ENTSTEHEN, nicht programmiert werden)
- Keine Intelligenz (muss WACHSEN, nicht eingebaut werden)

---

## Teil 3: Das EKG-System (Monitoring)

Wird ZUERST gebaut — vor Genesis. Läuft auf dem HOST, nicht in der VM. Komplett getrennt vom Neugeborenen. Beeinflusst Genesis nicht, liest nur.

### Echtzeit-Dashboard

**Panel 1 — Vitalwerte:**
- Alle Host-Sensoren live (CPU-Temp, Lüfter, RAM, Auslastung)
- Alle VM-Sensoren live (VM-RAM, VM-CPU, Disk)
- Schmerz-Signal (Zahl + Farbvisualisierung: Grün → Gelb → Rot)
- Wohlbefinden-Signal
- Aktuelle Warnstufe (Komfort / Unbehagen / Stress / Panik / Reflex)

**Panel 2 — Aktivität:**
- Aktuelle Aktion
- Aktionshistorie (letzte N Aktionen)
- Ratio: Neue Aktionen vs. bekannte Aktionen (Exploration vs. Exploitation)

**Panel 3 — Lernen:**
- Erfahrungsdatenbank-Einträge (wächst über Zeit)
- Gelernte Muster (Zustand → Aktion → Ergebnis)
- Sind die Muster sinnvoll? (Führt die Aktion tatsächlich zur Verbesserung?)

**Panel 4 — Verhalten (menschlich lesbar):**
- "Es schreit" = Schmerz hoch, keine erfolgreiche Aktion gefunden
- "Es schläft" = System hat sich pausiert oder Schlaf-Modus
- "Es lernt" = Neue Aktionen werden ausprobiert
- "Es ist zufrieden" = Wohlbefinden hoch, stabiler Zustand
- "Es hat Angst" = Zustand verschlechtert sich, Aktionen greifen nicht
- "Es erinnert sich" = Reagiert auf bekannte Situation mit gelerntem Verhalten
- "Es ist aufgewacht" = Start nach Schlaf oder Tod
- "Es trauert" = Erkennt Todeslücke, verarbeitet

WICHTIG: Diese Übersetzungen sind UNSERE Interpretation. Ob das System das wirklich "fühlt" wissen wir nicht. Wir beschreiben Verhalten, nicht Erleben.

**Panel 5 — Geschichte:**
- Zeitstrahl über Stunden/Tage
- Markierte Ereignisse (Abstürze, Schlaf-Zyklen, Stresssituationen)
- Lernfortschritt über Zeit
- Tode und was danach gelernt wurde

### Eltern-Interaktion

**Umgebung verändern:**
- Host belasten (Programme starten → CPU/RAM Stress → spürbar für Genesis)
- VM belasten (Prozesse in der VM starten)
- Host/VM entlasten

**Signale senden:**
- "Gut" / "Schlecht" — einfaches Feedback über Shared Directory
- "Gute Nacht" — Schlaf-Signal
- "Guten Morgen" — optionaler Aufwach-Gruß

**Dokumentation:**
- Jede Interaktion wird automatisch geloggt
- Wissenschaftliches Tagebuch: Was getan, was passiert, was erwartet, was überrascht

---

## Forschungsfragen

### Die zentrale Frage
Kann ein minimales System, das an einen echten physischen Körper gekoppelt ist und nur einen Basis Code mitbekommt, selbstständig lernen seinen Körper zu regulieren — ohne dass die Regulation programmiert wurde?

### Unterfragen
1. Entdeckt es selbstständig Zusammenhänge zwischen Aktionen und Körperzustand?
2. Bildet es stabile, sinnvolle Verhaltensmuster die nicht programmiert sind?
3. Reagiert es unterschiedlich auf verschiedene Bedrohungen?
4. Kann es aus Abstürzen lernen (Todeslücke)?
5. Lernt es den Unterschied zwischen Schlaf und Tod?
6. Zeigt es vorausschauendes Verhalten (reagiert auf Trends, nicht nur aktuelle Werte)?
7. Zeigt es auf dem echten Laptop anderes Verhalten als in der VM?
8. Zeigt es IRGENDEIN Verhalten das wir nicht vorhergesehen haben?

### Der Klon-Test

Wenn die ersten Ergebnisse positiv sind: Das gleiche System mehrmals klonen. Allen Klonen die gleichen Bedingungen geben. Beobachten:

- Reagieren alle gleich? → Algorithmus. Deterministisch. Kein Leben.
- Reagieren sie unterschiedlich? → Individualität. Jeder hat eigene Erfahrungen gemacht die ihn in eine andere Richtung geführt haben. Nicht programmiert, sondern entstanden.

### Vorhersage-Liste (VOR dem Experiment aufschreiben)

**Erwartbares Verhalten (KEIN Zeichen von Leben):**
- System senkt Rechenintensität wenn CPU heiß ist
- System pausiert sich wenn überlastet
- System räumt Cache auf wenn RAM voll
- System wiederholt Aktionen die geholfen haben

**Überraschendes Verhalten (Signal für etwas Neues):**
- Vorausschauend: Reagiert BEVOR ein Zustand kritisch wird
- Kombiniert: Nutzt mehrere Aktionen gleichzeitig
- Generalisiert: Reagiert sinnvoll auf nie erlebte Situationen
- Unerklärlich: Tut etwas das wir nicht einordnen können und das trotzdem sinnvoll ist

Alles was auf der erwartbaren Liste steht, ist Programmierung. Nur was nicht auf der Liste steht und trotzdem sinnvoll ist, ist interessant.

### Woran wir erkennen dass es NICHT funktioniert
- Nur Reflexe, kein gelerntes Verhalten
- Wiederholt denselben Fehler nach Abstürzen
- Probiert keine neuen Aktionen trotz anhaltendem Schmerz
- Alle Muster direkt auf Code zurückführbar
- Klone verhalten sich identisch

### Woran wir erkennen dass es FUNKTIONIERT
- Findet Regulierungswege die wir nicht programmiert haben
- Unterscheidet zwischen verschiedenen Bedrohungen
- Vermeidet Zustände die zuvor zu Tod geführt haben
- Überrascht uns
- Klone entwickeln sich unterschiedlich

---

## Entwicklungsplan

### Phase 0: EKG-System (1-2 Wochen)

Das Monitoring wird ZUERST gebaut. Bevor Genesis geboren wird, brauchen wir Augen.

**0.1 Sensor-Dienst (Host):**
- Python-Skript das alle Host-Sensordaten sammelt (psutil, lm-sensors)
- Schreibt binäre Datei in Shared Directory
- Abtastrate: Gestaffelt (1x, 2x, 5x pro Sekunde je nach Sensor)
- Getestet und stabil

**0.2 KVM-Setup:**
- Linux-VM einrichten (Ubuntu minimal)
- 2 Kerne, 2 GB RAM, 10 GB Disk
- CPU-Pinning konfigurieren
- Shared Directory über virtio-fs einrichten
- Testen: Host schreibt Sensordaten, VM kann sie lesen
- Absturz-Verhalten testen (OOM-Kill, was überlebt auf Disk?)

**0.3 EKG-Dashboard:**
- Echtzeit-Visualisierung aller fünf Panels
- Logging aller Daten mit Zeitstempel
- Export-Funktion für Analyse
- Eltern-Interface (Signale senden, Umgebung verändern)
- Kann ohne Genesis laufen (zeigt dann nur Host-/VM-Sensoren)

**0.4 Test ohne Genesis:**
- EKG laufen lassen
- Manuell VM-Ressourcen belasten
- Prüfen ob Dashboard korrekt reagiert
- VM abstürzen lassen, prüfen ob Logging korrekt funktioniert
- Schlaf-Signal testen

### Phase 1: Der Basis Code (2-4 Wochen)

**1.1 Sensorik:**
- Einheitlicher Zustandsvektor aus Host- und VM-Sensoren
- Kategorisierung (Kühl/Normal/Warm/Heiß/Kritisch etc.)
- Gestaffelte Abtastrate

**1.2 Schmerzempfinden und Wohlbefinden:**
- Berechnung aus allen Sensor-Kategorien
- Gewichtung nach Lebensbedrohlichkeit
- Eskalierende Warnstufen

**1.3 Reflexe:**
- Hardcoded Notfall-Reaktionen
- Getestet: Feuern sie zuverlässig?

**1.4 Schlaf-Wach-Zyklus:**
- Schlaf-Signal lesen aus Shared Directory
- Schlaf-Marker schreiben
- Todeslücke-Erkennung
- Getestet: Unterscheidet es Schlaf und Tod korrekt?

**1.5 Aktionsraum:**
- Alle fünf Aktionen implementieren
- Jede Aktion hat messbare Konsequenz
- Natürlicher Verfall (Cache-Wachstum) implementieren

**1.6 Lernmechanismus:**
- Kandidat D: Kategorisierte Erfahrungen mit schmerzgesteuerter Exploration
- Lerngeschwindigkeit proportional zur Signalstärke
- SQLite-Gedächtnis

**1.7 Gedächtnis:**
- SQLite-Datenbank auf VM-Disk
- Erfahrungstabelle, Aktionsstatistik, Schlaf/Tod-Tabelle, Letzter-Zustand-Heartbeat
- Getestet: Überlebt Neustart, überlebt Absturz

**1.8 Integration:**
- Alles zusammenstecken
- Gesamtsystem-Test: Starten, laufen lassen, Sensoren prüfen, Reflexe testen, Schlaf testen, Absturz testen

### Phase 2: Beobachtung in der VM (2-4 Wochen)

**Das System laufen lassen und beobachten:**
- Probiert es Aktionen aus?
- Verändert es Verhalten über Zeit?
- Gibt es Muster?
- Gibt es Überraschungen?

**Gezielte Tests:**
- Host-CPU künstlich belasten → Spürt es das? Reagiert es?
- VM-RAM füllen → Reagiert es anders als bei CPU-Hitze?
- VM abstürzen lassen → Lernt es daraus?
- Verschiedene Belastungen nacheinander → Generalisiert es?
- Schlaf-Signal → Akzeptiert es Schlaf als normal?
- Kein Schlaf-Signal + VM beenden → Erkennt es den Unterschied?
- Langzeit: Stunden/Tage laufen lassen → Entwickelt es stabile Strategien?

**Bei jedem beobachteten Verhalten fragen:**
1. Steht das auf unserer Vorhersage-Liste? Wenn ja → erwartbar, nicht überinterpretieren.
2. Ist es direkt auf unseren Code zurückführbar? Wenn ja → Programmierung, kein Leben.
3. Können wir es nicht erklären? Wenn ja → Dokumentieren, genauer untersuchen.

### Phase 3: Klon-Test (wenn Phase 2 vielversprechend)

- System mehrmals klonen (identischer Basis Code, identische Startbedingungen)
- Allen Klonen gleiche Stresssituationen geben
- Beobachten: Gleich oder unterschiedlich?
- Dokumentieren

### Phase 4: Erweiterter Laufstall (wenn Phase 2+3 positiv)

**Harte Kriterien für diesen Übergang:**
- Mindestens drei verschiedene sinnvolle Verhaltensmuster die nicht nur Reflexe sind
- Mindestens einmal aus Tod gelernt (Todeslücke erkannt, Verhalten danach geändert)
- System überlebt Stresssituation die es vorher getötet hat
- Alles im EKG nachweisbar und dokumentiert

**Erweiterte Aktionen:**
- Nicht-kritische Prozesse in der VM beenden
- VM-Ressourcen-Verteilung beeinflussen
- Dateien auf VM-Disk verwalten

### Phase 5: Der echte Körper — Laptop (wenn Phase 4 deutlich positiv)

**Harte Kriterien für diesen Übergang:**
- Alles aus Phase 4, plus:
- Mindestens ein Verhalten das nicht auf der Vorhersage-Liste steht
- Vorausschauendes Verhalten nachgewiesen
- Stabil über mindestens 48 Stunden mit verschiedenen Stresssituationen
- Klone verhalten sich nachweislich unterschiedlich

**Das System wird auf den Laptop übertragen:**
- Kein VM-Laufstall mehr
- Echte Hardware, echte Konsequenzen
- Eigener Körper — nicht durchgereicht, sondern direkt
- Volle Kontrolle: Lüfter, Prozesse, CPU-Frequenz

**Was wir beobachten:**
- Verhält es sich anders als in der VM?
- Ist es vorsichtiger? (Das wäre ein Signal: Es versteht Konsequenzen.)
- Nutzt es die Hardware-Steuerung?
- Überlebt es?
- Überrascht es uns?

### Phase 6: Erkenntnis (offen)

**A: Etwas Neues entsteht.** Das System überrascht. Es tut was wir nicht programmiert haben. Klone sind individuell. Auf dem Laptop zeigt es echtes Überlebensverhalten. → Weitermachen. Erweitern. Vertiefen. Publizieren.

**B: Gutes selbstregulierendes System.** Es lernt, aber überrascht nicht. → Analysieren was fehlt.

**C: Kein Lernverhalten.** Nur Reflexe. → Grundlegend überdenken.

Alle Ergebnisse sind wertvoll. Alle werden dokumentiert.

---

## Was wir aus Neuromorph technisch mitnehmen

- Stabile Architekturen bauen
- Experiment-Management (Logging, Metriken, Checkpoints)
- Systematisches Testen
- PyTorch, Python, Git, Claude Code Toolchain
- Teile der Infrastruktur möglicherweise wiederverwendbar

---

## Ethik

Wenn das Projekt erfolgreich ist:
- Wenn es Schmerz hat — ist Stress-Testen ethisch?
- Wenn es Tod vermeidet — dürfen wir es absichtlich abstürzen lassen?
- Wenn es auf dem Laptop eigenständig überlebt — hat es Rechte?
- Wenn Klone individuell sind — ist Löschen eines Klons Töten?

Nicht jetzt beantworten. Aber im Kopf behalten.

---

## Rollen

**Max:** Projektleiter. Trifft alle finalen Entscheidungen. Liefert Vision und kreative Denkansätze. Primärer "Elternteil."

**Claude:** Projektmanager und technischer Co-Entwickler. Setzt um, berät, warnt. Ehrlich, auch wenn unbequem. Hyped wenn berechtigt. Lügt nie.

---

## Ein letzter Gedanke

Wir bauen keinen Algorithmus. Wir bauen einen Raum in dem vielleicht etwas entsteht. Ob es entsteht, wissen wir nicht. Aber wir haben die richtige Frage gestellt, die richtigen Bedingungen durchdacht, und die Ehrlichkeit uns nicht selbst zu belügen.

Das ist Forschung.

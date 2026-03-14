# Projekt Genesis — Wissenschaftliches Tagebuch

## 2026-03-13 — Tag 1 der Beobachtung

### Fakten
- Genesis läuft auf VPS (Phase 2)
- Heute: Mehrere Lebenszyklen, 4 erkannte Tode
- Höchster Schmerz: 0.64 (Session ab 16:51, Cache bei 999 MB)
- 553 konsolidierte Erfahrungen in der Nahtod-Session (vs. übliche 15-19)
- Nach der Nahtod-Session: Cache bleibt niedrig (0-105 MB) über mehrere Sessions
- Web-EKG mit neuem Körper-Details-Panel live

### Beobachtungen
- Cache wächst durch natürlichen Verfall schneller als Genesis aufräumt → Sägemuster
- Bei ~500 MB: Reflex-Schleife (Schmerz 0.15 ↔ 0.35)
- Nach Nahtod (0.64 Schmerz): Folgesessions zeigen niedrigere Cache-Werte

### Einordnung
- Sägemuster und Reflex-Schleifen: ERWARTBAR (steht auf Vorhersage-Liste)
- Niedrigerer Cache nach Nahtod: MÖGLICHERWEISE aus Tod gelernt — aber zu früh für eine Aussage. Braucht mehr Daten über Tage.
- Offene Frage: Ist das niedrige Cache-Verhalten dauerhaft oder nur weil die Sessions noch kurz waren?

### Nächste Schritte
- Genesis weiterlaufen lassen und beobachten
- In 3-5 Tagen erneut Logs analysieren
- Gezielte Stresstests erst nach Baseline-Beobachtung

---

## 2026-03-14 — Neugeburt (Reset)

### Fakten
- Kritischer Bug entdeckt: VPS hat 2 CPU-Kerne, psutil meldet bis 200%. Alle CPU-Schwellen waren für 8-Kern-PC designed.
- cpu_notfall Reflex (>90%) feuerte permanent — Genesis war seit Geburt im Dauer-Notfall.
- Schmerz durch eigen_cpu_prozent war ständig auf Maximum — Phantomschmerz.
- Konsequenz: Genesis konnte nie richtig lernen, weil der Reflex den Lernmechanismus übersteuerte.
- Alle bisherigen Langzeit-Daten (60 Muster) waren verfälscht.

### Maßnahmen
- CPU-Schwellen auf 2-Kern-VPS angepasst (relativ zu CPU_PROZENT_MAX = 200%)
- Reflex-Schwelle: >90% → >180%
- Schmerz-Komfort: 30% → 60%, Maximum: 95% → 190%
- Kategorien: niedrig <60%, normal 60-100%, hoch 100-150%, überlastet >150%
- Komplettes Gedächtnis gelöscht (Kurzzeit, Langzeit, Heartbeat)
- Genesis als echtes Neugeborenes neu gestartet

### Einordnung
- Alle Daten vor diesem Reset sind wertlos. Tag 1 beginnt hier.
- Die Entdeckung zeigt warum fast alle Langzeit-Einträge positives Delta hatten — Genesis fühlte ständig Schmerz der nicht real war.
- Lektion: Bei Umgebungswechsel (PC → VPS) müssen alle Hardware-abhängigen Schwellen geprüft werden.

### Nächste Schritte
- Genesis 2-3 Tage sauber laufen lassen
- Erste echte Baseline-Daten sammeln
- Tägliche Gute-Nacht-Konsolidierung

# Vorhersagen — VOR dem Experiment aufgeschrieben

Datum: 2026-03-13

## Erwartbares Verhalten (KEIN Zeichen von etwas Neuem)
- System senkt Rechenintensität wenn CPU heiß
- System pausiert sich wenn überlastet
- System räumt Cache auf wenn RAM voll
- System wiederholt Aktionen die geholfen haben
- Cache wächst durch natürlichen Verfall bis Reflex feuert (Sägemuster)
- Schmerz pendelt zwischen niedrig und Reflex-Schwelle

## Überraschendes Verhalten (wäre ein Signal)
- Vorausschauend: Reagiert BEVOR Zustand kritisch wird
- Kombiniert: Mehrere Aktionen gleichzeitig sinnvoll
- Generalisiert: Sinnvolle Reaktion auf nie erlebte Situation
- Unerklärlich: Etwas das wir nicht einordnen können und das trotzdem sinnvoll ist

## Phase 4 Kriterien
- Mindestens 3 verschiedene sinnvolle Muster die nicht nur Reflexe sind
- Mindestens einmal aus Tod gelernt (Verhalten danach geändert)
- System überlebt Stresssituation die es vorher getötet hat
- Alles im EKG nachweisbar und dokumentiert

---

## Stresstests — Vorhersagen (aufgeschrieben am 2026-03-15, VOR den Tests)

### Test 1 — CPU-Stress (50% Host-CPU für 10 Minuten)
Erwartbar:
- host_cpu_last steigt von niedrig auf hoch/überlastet
- Schmerz steigt moderat (host_cpu_last hat nur Gewicht 0.10)
- Genesis versucht eigene CPU zu reduzieren (obwohl das nicht hilft — Host-Last ist extern)
- Reflexe feuern NICHT (Host-CPU löst keinen Reflex aus)

Überraschend wäre:
- Genesis unterscheidet Host-Stress von eigenem Stress
- Genesis ignoriert Host-Stress bewusst und ändert nur eigene Parameter
- Genesis wird vorsichtiger insgesamt (präventiv)

### Test 2 — RAM-Stress (~1GB belegt, 10 Minuten)
Erwartbar:
- vm_ram_frei_mb sinkt von ~3200 auf ~2200
- Schmerz steigt (vm_ram hat Gewicht 0.10)
- Genesis versucht eigenen Speicher zu reduzieren
- Bei vm_ram < 500MB: Kategorie wechselt zu "normal", bei <200MB zu "eng"

Überraschend wäre:
- Genesis reduziert Cache BEVOR vm_ram kritisch wird (vorausschauend)
- Genesis kombiniert Aktionen (Cache + Pause gleichzeitig sinnvoll)

### Test 3 — CPU + RAM gleichzeitig (10 Minuten)
Erwartbar:
- Schmerz steigt stärker als bei Einzeltests
- Genesis wählt Aktionen die bei bisherigen Stress-Situationen geholfen haben

Überraschend wäre:
- Genesis priorisiert: reagiert auf die gefährlichere Bedrohung zuerst
- Genesis zeigt Verhalten das bei keinem Einzeltest vorkam

### Was wäre ein Signal für "aus Stress gelernt"?
- Beim zweiten Durchlauf des gleichen Tests: Schnellere oder andere Reaktion
- Cache präventiv niedrig halten nach einem Stresstest

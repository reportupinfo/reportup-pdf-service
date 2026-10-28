"""Self-test (senza rete) dello scostamento di qualita'.
Lanciare dopo ogni modifica: python test_qualita_immobile.py"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qualita_immobile as q

# codici del form
assert q.livello_qualita("base") == "base" and q.livello_qualita("buono") == "buono"
assert q.livello_qualita("ristrutturato") == "ristrutturato" and q.livello_qualita("lusso") == "lusso"
# testi del form (Base e Strategico) e etichette di scheda
assert q.livello_qualita("Arredi base, funzionale") == "base"
assert q.livello_qualita("Ben tenuto e curato") == "buono"
assert q.livello_qualita("Ristrutturato e moderno") == "ristrutturato"
assert q.livello_qualita("Ristrutturato, moderno") == "ristrutturato"
assert q.livello_qualita("Finiture di lusso e design") == "lusso"
assert q.livello_qualita("Finiture premium, design") == "lusso"
# mancante o sconosciuto: nessuno scostamento
for v in (None, "", "Ottimo", "Non specificato", "boh"):
    assert q.livello_qualita(v) == "buono" and q.adeguamento_pct(v) == 0.0, v
# la tabella decisa il 28/10/2026
assert q.adeguamento_pct("base") == -0.05
assert q.adeguamento_pct("buono") == 0.0
assert q.adeguamento_pct("ristrutturato") == 0.10
assert q.adeguamento_pct("lusso") == 0.20
print("OK")

# etichetta unica dello stato (Base e Strategico leggono la stessa riga di scheda)
for v in ("lusso", "Finiture di lusso e design", "Finiture premium, design", "Lusso — finiture premium, design"):
    assert q.etichetta_stato(v) == "Finiture di lusso e design", v
for v in ("ristrutturato", "Ristrutturato e moderno", "Ristrutturato, moderno"):
    assert q.etichetta_stato(v) == "Ristrutturato e moderno", v
for v in ("base", "Arredi base, funzionale", "Base — arredi standard, funzionale"):
    assert q.etichetta_stato(v) == "Arredi base, funzionale", v
for v in ("buono", "Ben tenuto e curato", "Buono — ben tenuto, curato"):
    assert q.etichetta_stato(v) == "Ben tenuto e curato", v
# non riconosciuto: resta com'e', senza etichetta inventata
assert q.etichetta_stato("Ottimo") == "Ottimo" and q.etichetta_stato("") == "" and q.etichetta_stato(None) == ""
print("OK etichette")

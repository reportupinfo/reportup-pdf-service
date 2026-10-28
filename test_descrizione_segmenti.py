"""Self-test (senza rete) dei segmenti della descrizione standard.
Lanciare dopo ogni modifica: python test_descrizione_segmenti.py"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import descrizione_segmenti as ds


def R(etichetta, dist, nome, modo, metri, minuti=None):
    return [etichetta, dist, nome, "Alto", {"modo": modo, "metri": metri, "minuti": minuti}]


# mare: tre fasce sui minuti reali
assert ds.frase_mare(R("Spiaggia più vicina", "460 m · 6 min a piedi", "Spiaggia Pubblica", "piedi", 460, 6)).startswith("A pochi minuti a piedi dal mare")
assert ds.frase_mare(R("Spiaggia più vicina", "1,2 km · 17 min a piedi", "Spiaggia X", "piedi", 1200, 17)).startswith("Non lontano dal mare")
assert ds.frase_mare(R("Spiaggia più vicina", "6,5 km · 15 min in auto", "Spiaggia di Fiumicello", "auto", 6500, 15)).startswith("Il mare è raggiungibile in auto")
assert ds.frase_mare(R("Spiaggia più vicina", "3 km · 8 min in auto", "Spiaggia Y", "auto", 3000, 8)).startswith("Non lontano dal mare")
assert ds.frase_mare([ "Spiaggia più vicina", "800 m (linea d'aria)", "Cala Z", "Alto"]).startswith("La spiaggia più vicina")   # senza misure: solo il fatto
assert ds.frase_mare(None) == ""
# costa senza spiaggia: solo entro 5 km
assert ds.frase_costa(0.6) == "L'immobile si trova a meno di 1 km dalla costa."
assert ds.frase_costa(2.4) == "L'immobile si trova a circa 2,4 km dalla costa."
assert ds.frase_costa(9) == "" and ds.frase_costa(None) == ""
# lago
assert ds.frase_lago(R("Lago", "120 m · 2 min a piedi", "Lago di Garda (Lungolago)", "piedi", 120, 2)).startswith("A pochi minuti a piedi dal lago")
assert ds.frase_lago(R("Lago", "circa 4 km (linea d'aria)", "Lago di Garda", "aria", 4000)).startswith("Il lago è raggiungibile in auto")
# montagna: quota solo dai 500 m
assert ds.frase_quota(1100) == "L'immobile si trova a circa 1.100 m di quota."
assert ds.frase_quota(120) == "" and ds.frase_quota(None) == ""
# centro: centrale, a breve distanza, fuori
assert ds.frase_centro(R("Centro del comune", "In centro", "Verona", "centro", 0, 0)) == "L'immobile si trova nel centro di Verona."
assert ds.frase_centro(R("Centro del comune", "850 m · 11 min a piedi", "Scalea", "piedi", 850, 11)).startswith("Posizione centrale")
assert ds.frase_centro(R("Centro del comune", "1,9 km · 22 min a piedi", "Scalea", "piedi", 1900, 22)).startswith("A breve distanza dal centro")
assert ds.frase_centro(R("Centro del comune", "5,8 km · 10 min in auto", "Ancona", "auto", 5800, 10)).startswith("A breve distanza dal centro")
assert ds.frase_centro(R("Centro del comune", "9,9 km · 13 min in auto", "Ancona", "auto", 9900, 13)).startswith("Fuori dal centro")
# casello e stazione: il nome non si ripete
f = ds.frase_casello(R("Casello autostradale", "3,7 km · 5 min in auto", "Casello di Ancona Sud - Osimo", "auto", 3700, 5))
assert f == "Ben collegato alla rete autostradale: il casello di Ancona Sud - Osimo dista 3,7 km · 5 min in auto.", f
f = ds.frase_casello(R("Casello autostradale", "47 km · 48 min in auto", "Casello Autostradale Polla", "auto", 47000, 48))
assert f == "Il casello autostradale più vicino, quello di Polla, dista 47 km · 48 min in auto.", f
f = ds.frase_stazione(R("Stazione ferroviaria", "1,0 km · 14 min a piedi", "Stazione di Ancona Torrette", "piedi", 1000, 14))
assert f == "Stazione ferroviaria raggiungibile a piedi: quella di Ancona Torrette dista 1,0 km · 14 min a piedi.", f
f = ds.frase_stazione(R("Stazione ferroviaria", "7,9 km · 14 min in auto", "Stazione Ancona Stadio", "auto", 7900, 14))
assert f == "La stazione ferroviaria più vicina, quella di Ancona Stadio, dista 7,9 km · 14 min in auto.", f
# comune (ISTAT): le grandi citta' non sono dichiarate capoluogo
rec = {"comune": "Scalea", "provincia": "Cosenza", "regione": "Calabria", "popolazione": "11232"}
assert ds.frase_comune(rec, "comune_minore") == "Scalea è un comune della provincia di Cosenza (Calabria), con 11.232 abitanti (dati ISTAT)."
assert "capoluogo di provincia" in ds.frase_comune({"comune": "Ancona", "provincia": "Ancona", "regione": "Marche", "popolazione": "99108"}, "capoluogo")
assert "capoluogo" not in ds.frase_comune({"comune": "Verona", "provincia": "Verona", "regione": "Veneto", "popolazione": "257838"}, "grande_citta")
assert ds.frase_comune(None, "capoluogo") == "" and ds.frase_comune({"comune": "X", "popolazione": ""}, "comune_minore") == ""
# punti fissi
assert ds.frase_poi_fisso("Trasporto pubblico", "Fermata Ospedale", "8 min a piedi") == "Trasporto pubblico: Fermata Ospedale, a 8 min a piedi."
assert ds.frase_poi_fisso("Servizi essenziali", "Conad", "in loco") == "Servizi essenziali: Conad, in loco."
assert ds.frase_poi_fisso("Servizi essenziali", "—", "—") == ""
# capienza
assert ds.target_capienza("2") == "coppie" and ds.target_capienza("4") == "famiglie e piccoli gruppi"
assert ds.target_capienza("6+") == "famiglie numerose e gruppi di amici"
# nessuna frase d'atmosfera, nessun aggettivo non verificabile in tutto il modulo
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "descrizione_segmenti.py"), encoding="utf-8").read()
for vietata in ("accogliente", "frenetic", "tranquillità", "atmosfera", "fascino", "caos", "senza pensieri", "confortevole"):
    assert vietata not in src.lower().split("# ── utilita'")[1], vietata
print("OK")

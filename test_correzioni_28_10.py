"""Test (senza rete) delle correzioni dopo il test Base/Strategico di Sorrento del 28/10/2026.
Lanciare dopo ogni modifica: python test_correzioni_28_10.py"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PDF_SECRET", "x")
os.environ.pop("GOOGLE_MAPS_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)
import app as A
import testi_report as tr

# 1. la descrizione non e' piu' tra i testi riscritti dall'IA ne' filtrati dal filtro cifre
assert "descrizione" not in A._CAMPI_ANALISI_STRATEGICO
desc = ("Trilocale di 70 m² situato in Corso Italia 25. Sorrento è un comune della provincia di Napoli (Campania), "
        "con 15.956 abitanti (dati ISTAT). Posizione centrale: il centro di Sorrento dista 590 m · 8 min a piedi.")
d = {"descrizione": desc, "analisi_posizione": "Zona turistica consolidata e ben collegata dalla costa verso il centro storico."}
A._rimuovi_cifre_economiche_dai_testi(d)
assert d["descrizione"] == desc, d["descrizione"]

# 2. FF&E: 2% del ricavo lordo, mai il segnaposto 372
assert tr.ffe_reserve({"ricavo_lordo": 63488}) == 1270
assert tr.ffe_reserve({"ricavo_lordo": 18600}) == 372
assert tr.ffe_testo({"ricavo_lordo": 63488}).startswith("2% x € 63.488 = € 1.270/anno")

# 3. moltiplicatori dotazioni: percentuale sul prezzo di mercato di riferimento, non sul prezzo finale
for prezzo_finale in (256, 305):
    d = {"prezzo_notte_stimato": prezzo_finale, "prezzo_riferimento_mercato": 244, "notti_anno": 248,
         "dotazioni_assenti": ["Piscina", "Parcheggio", "Giardino", "Lavatrice", "Ascensore"]}
    A._calcola_moltiplicatori_dotazioni(d)
    righe = {r[0]: r for r in d["moltiplicatori_dotazioni"]}
    assert righe["Piscina"][2] == 17 and righe["Piscina"][3] == 17 * 248, righe["Piscina"]
    assert righe["Parcheggio"][2] == 12 and righe["Giardino"][2] == 7 and righe["Ascensore"][2] == 5
# senza prezzo di riferimento (dati vecchi) ricade sul prezzo finale
d = {"prezzo_notte_stimato": 100, "notti_anno": 200, "dotazioni_assenti": ["Piscina"]}
A._calcola_moltiplicatori_dotazioni(d)
assert d["moltiplicatori_dotazioni"][0][2] == 7

# 4. scenari: testi del codice, numeri coerenti con le ipotesi dichiarate
d = {"occupazione_percent": 68, "prezzo_notte_stimato": 256, "ricavo_lordo": 63488, "totale_ricavi": 67932,
     "totale_costi": 22336, "notti_anno": 248, "profitto_netto": 45596, "rata_mutuo_mensile": 600,
     "mutuo_attivo": True,
     "scenario_real": {"note": "leggermente al di sotto della rata del mutuo"},
     "scenario_pess": {"note": "testo IA"}, "scenario_ott": {"note": "testo IA"}}
A._ricalcola_scenari_strategico(d)
p, r, o = d["scenario_pess"], d["scenario_real"], d["scenario_ott"]
assert (p["occupazione"], p["notti"], p["prezzo_medio"], p["ricavi_lordi"], p["costi_totali"], p["profitto_netto"]) == \
    (44, 161, 205, 33005, 14554, 18451), p
assert (o["occupazione"], o["notti"], o["prezzo_medio"], o["ricavi_lordi"], o["costi_totali"], o["profitto_netto"]) == \
    (82, 299, 302, 99328, 29331, 69997), o
assert r["profitto_netto"] == 45596 and r["ricavi_lordi"] == 67932
for sc in (p, r, o):
    assert "IA" not in sc["note"] and "mutuo" not in sc["note"].replace("rata del mutuo resta invariata", "")
assert "rata del mutuo resta invariata" in p["note"] and "rata del mutuo resta invariata" in o["note"]
assert "65%" in p["note"] and "120%" in o["note"] and "118%" in o["note"]

# 4b. il filtro cifre che gira dopo NON tocca i testi degli scenari scritti dal codice
A._rimuovi_cifre_economiche_dai_testi(d)
assert "65%" in d["scenario_pess"]["note"] and "120%" in d["scenario_ott"]["note"] and "7%" in d["scenario_real"]["note"], d

# 5. etichette scheda: Base (testo del form) e Strategico (codice) leggono la stessa riga
for stato in ("lusso", "Finiture di lusso e design", "Finiture premium, design"):
    assert A._prepara_etichette_scheda({"stato": stato})["scheda_stato"] == "Finiture di lusso e design"
for piano in ("1-3", "1°–3° piano"):
    assert A._prepara_etichette_scheda({"piano": piano})["scheda_piano"] == "1°–3° piano", piano
# 6. saggio di capitalizzazione per zona (6 centro / 7 intermedia / 8 periferia), mai un valore fuori fascia
import stagionalita_turistica as st
sag = lambda sub, cat, com, m: st.saggio_capitalizzazione_zona(sub, cat, com, m)[0]
assert sag(None, "capoluogo", "Verona", 800) == 6.0          # centro di capoluogo
assert sag(None, "capoluogo", "Verona", 2600) == 7.0         # capoluogo, fuori dal centro
assert sag("costiero", "comune_minore", "Sorrento", 590) == 6.0   # localita' turistica, in centro
assert sag("costiero", "comune_minore", "Sorrento", 4200) == 7.0
assert sag(None, "comune_minore", "Paese", 400) == 7.0       # paese senza vocazione, in centro
assert sag(None, "comune_minore", "Paese", 1800) == 8.0      # paese senza vocazione, periferia
assert sag(None, "capoluogo", "Verona", None) == 7.0         # distanza non nota: intermedia, mai un'ipotesi
assert sag(None, "comune_minore", "Paese", None) == 7.0
d = {"sottocategoria": "costiero", "categoria": "comune_minore", "comune": "Sorrento", "profitto_netto": 45596,
     "poi_extra": [["Centro del comune", "590 m · 8 min a piedi", "Sorrento", "Alto", {"modo": "piedi", "metri": 590, "minuti": 8}]]}
A._calcola_valore_asset(d)
assert d["saggio_capitalizzazione"] == 6.0 and d["valore_mercato"] == round(45596 / 6.0 * 100), d
assert "6%" in d["saggio_capitalizzazione_motivo"] and "5,5%-6,5%" in d["saggio_capitalizzazione_motivo"]
d = {"sottocategoria": None, "categoria": "comune_minore", "comune": "Paese", "profitto_netto": 10000,
     "poi_extra": [["Centro del comune", "3,1 km · 6 min in auto", "Paese", "Medio", {"modo": "auto", "metri": 3100, "minuti": 6}]]}
A._calcola_valore_asset(d)
assert d["saggio_capitalizzazione"] == 8.0 and "7%-9%" in d["saggio_capitalizzazione_motivo"], d

# 7. confronto affitto: morosita' "Nullo" sul B&B, mai "Eliminato"
import confronto_affitto
_tbl = confronto_affitto.tabella_confronto({"totale_ricavi": 50000, "totale_costi": 12000, "profitto_netto": 38000}, 500)
_celle = [c for riga in _tbl._cellvalues for c in riga]
assert "Nullo" in _celle and "Eliminato" not in _celle, _celle

print("OK")

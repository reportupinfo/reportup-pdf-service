"""Tetto sui m2 del confronto affitto, avviso servizi extra (31/10/2026, feedback
agriturismo Corato). La tipologia "Grande unita'" e' stata tolta il 31/10/2026 sera:
restano i posti letto 8/10/12. Senza rete.
Lanciare: python test_grande_unita_tetto_mq.py"""
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PDF_SECRET", "x")
os.environ.pop("GOOGLE_MAPS_API_KEY", None)
import app as A
import affitti_mercato
import confronto_affitto
import dati_form
import fitz

# --- mappa tipologia: camere e posti di default ---
assert A._match_tipologia("Appartamento 4+ locali") == (3, 6)
assert A._match_tipologia("appartamento_grande") == (3, 6)
assert A._match_tipologia("Villa / Casa indipendente") == (4, 8)
assert A._match_tipologia("Trilocale") == (2, 4)
assert A._match_tipologia("Grande unità") is None   # tipologia tolta

# --- posti letto: il valore del form vince sempre, anche 8/10/12 e il vecchio "6+" ---
assert A._posti_letto_default("villa", "12") == "12"
assert A._posti_letto_default("appartamento_grande", "10") == "10"
assert A._posti_letto_default("villa", "6+") == "6+"
assert A._posti_letto_default("trilocale", None) == "4"
for _p, _n in (("6", 6), ("8", 8), ("10", 10), ("12", 12), ("6+", 6)):
    assert A._numero_da_stringa(_p) == _n, _p        # guests per AirROI
assert A._moltiplicatore_capacita("12") > A._moltiplicatore_capacita("8") > A._moltiplicatore_capacita("6")

# --- costi per tipologia ---
assert A._costi_per_tipologia("appartamento_grande") == (50, 480, 1700, 650)
assert A._costi_per_tipologia("stanza_doppia") == (25, 225, 600, 220)
assert A._costi_per_tipologia("Appartamento 4+ locali") == (50, 480, 1700, 650)
assert A._costi_per_tipologia("Villa / Casa indipendente") == (70, 600, 2650, 900)

# --- competitor: 4 righe per le tipologie standard ---
assert len(A._costruisci_competitor_deterministico(193, "Villa / Casa indipendente")) == 4

# --- etichetta scheda dal codice dello Strategico ---
D0 = {"tipologia": "villa", "piano": "terra,1-3"}
A._prepara_etichette_scheda(D0)
assert D0["scheda_tipologia"] == "Villa / Casa indipendente" and D0["scheda_piano"] == "Piano terra + 1°–3° piano"

# --- superficie: tipica e tetto ---
assert affitti_mercato.superficie_tipica("Appartamento 4+ locali") == 110
assert affitti_mercato.superficie_massima(4) == 200
assert affitti_mercato.superficie_massima(8) == 320
assert affitti_mercato.superficie_massima(0) == 200
assert affitti_mercato.superficie_massima("n/d") == 200

# --- avviso sul tetto sotto la tabella dell'affitto ---
D1 = {"fonte_affitto_tradizionale": "mercato_reale", "affitto_mq_tetto": 200, "affitto_mq_dichiarati": 750}
d = confronto_affitto.disclaimer_mercato(D1)
assert "200 m²" in d and "750 m²" in d and d.startswith(affitti_mercato.DISCLAIMER)
assert confronto_affitto.disclaimer_mercato({"fonte_affitto_tradizionale": "mercato_reale"}) == affitti_mercato.DISCLAIMER

# --- avviso servizi extra sotto la tabella dei costi ---
t = dati_form.TESTO_COSTI_NON_INCLUSI
assert "servizi extra" in t and "reportup.info@gmail.com" in t and t.startswith("Non inclusi:")

# --- PDF: l'avviso e' in pagina 3, niente finisce sotto il piede pagina ---
fx = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixture_parita_base_strategico.json"), encoding="utf-8"))
fx.update({"tipologia": "Villa / Casa indipendente", "scheda_tipologia": "Villa / Casa indipendente", "affitto_mq_tetto": 200,
           "affitto_mq_dichiarati": 750, "fonte_affitto_tradizionale": "mercato_reale", "competitor": []})
pdf = fitz.open(stream=A.build_pdf_bytes(fx), filetype="pdf")
assert len(pdf) == 5, len(pdf)
p3 = pdf[2]
testo3 = " ".join(p3.get_text().split())
assert "servizi extra" in testo3 and "200 m²" in testo3
altezza = p3.rect.height
for blocco in p3.get_text("blocks"):
    # il piede pagina e' l'ultima fascia (circa 10 mm); il resto non deve scendere li'
    if "ReportUp · reportup.it" in blocco[4] or "Pag." in blocco[4]:
        continue
    assert blocco[3] < altezza - 14, ("testo troppo in basso", round(blocco[3]), blocco[4][:60])
assert "non esistono tipologie di mercato paragonabili" in " ".join(pdf[3].get_text().split())
print("OK posti 8/10/12, tetto m2, avviso servizi extra")

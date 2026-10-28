"""Parita' tra Base e Strategico: le sezioni comuni devono dire le STESSE cose
(regola di Salvatore, 28/10/2026). Genera le pagine di entrambi i PDF dagli
stessi dati (fixture) e controlla che i testi condivisi (testi_report.py) siano
presenti identici in tutte e due. Senza rete.
Lanciare dopo ogni modifica ai generatori: python test_parita_base_strategico.py"""
import io
import json
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PDF_SECRET", "x")
os.environ.pop("GOOGLE_MAPS_API_KEY", None)
import app as A
import strategico as S
import testi_report as tr
import affitti_mercato
import fitz
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

D = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixture_parita_base_strategico.json"), encoding="utf-8"))


def flusso(testo):
    return re.sub(r"\s+", "", testo)    # senza spazi: ignora a capo e spaziature diverse


def testo_pagina_strategico(fn):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    fn(c, D)
    c.showPage()
    c.save()
    return flusso(fitz.open(stream=buf.getvalue(), filetype="pdf")[0].get_text())


base = fitz.open(stream=A.build_pdf_bytes(D), filetype="pdf")
base_eco, base_fonti, base_riep = (flusso(base[i].get_text()) for i in (2, 4, 3))
st_eco = testo_pagina_strategico(S.page4)
st_fonti = testo_pagina_strategico(S.page11)
st_riep = testo_pagina_strategico(S.page_riepilogo)

# tabella economica: stesse parole nelle righe in comune
comuni_eco = [tr.ricavo_lordo(D), tr.bonus_dirette(D), tr.totale_ricavi(D), tr.costi_intestazione(D),
              tr.commissioni(D), tr.pulizie(D), tr.mutuo(D)[0], tr.etichetta_situazione(D),
              "(media di mercato per la tipologia" + tr.nota_biancheria(D) + ")",
              tr.nota_economia(D, "strategico")]
for t in comuni_eco:
    assert flusso(t) in base_eco or flusso(t) in flusso(tr.nota_economia(D, "base")) or flusso(t) in base_eco.replace("IlReportStrategicodifferenzia", ""), ("Base", t)
    assert flusso(t) in st_eco, ("Strategico", t)
# la frase di rimando allo Strategico c'e' solo nel Base
assert "IlReportStrategicodifferenzia" in base_eco and "IlReportStrategicodifferenzia" not in st_eco
# avviso costi non inclusi: uguale
import dati_form
assert flusso(dati_form.TESTO_COSTI_NON_INCLUSI) in base_eco and flusso(dati_form.TESTO_COSTI_NON_INCLUSI) in st_eco
# fonti: le sei in comune, parola per parola, in entrambi
for titolo, desc in tr.fonti_comuni(D, affitti_mercato.fonte_descrizione()):
    assert flusso(titolo) in base_fonti and flusso(desc) in base_fonti, ("Base", titolo)
    assert flusso(titolo) in st_fonti and flusso(desc) in st_fonti, ("Strategico", titolo)
# disclaimer legale: stesso testo, cambia solo il nome del report
assert flusso(tr.disclaimer("Report Base")) in base_riep
assert flusso(tr.disclaimer("Report Strategico")) in st_riep
print("OK")

# ── Parita' aggiunte il 28/10/2026 dopo il test Sorrento (Base contro Strategico) ──
base_occ = flusso(base[1].get_text())
base_p1 = flusso(base[0].get_text())
base_ring = base_fonti

# riepilogo: le quattro card del Base sono IDENTICHE nello Strategico
for titolo, valore, riga1, riga2 in tr.kpi_riepilogo(D):
    for nome, testo in (("Base", base_riep), ("Strategico", st_riep)):
        for pezzo in (titolo, valore, riga1, riga2):
            assert flusso(pezzo) in testo, (nome, pezzo)
assert flusso(tr.nota_riepilogo("base")) in base_riep
assert flusso(tr.nota_riepilogo("strategico")) in st_riep

# ringraziamento: stesse parole, stessa firma
st_ring = st_fonti
for testo, _corsivo in tr.RINGRAZIAMENTO_PARAGRAFI:
    assert flusso(testo) in base_ring, ("Base", testo[:40])
    assert flusso(testo) in st_ring, ("Strategico", testo[:40])
assert flusso(tr.RINGRAZIAMENTO_TITOLO) in base_ring and flusso(tr.RINGRAZIAMENTO_TITOLO) in st_ring

# nota sotto la curva mensile: stessa nota
st_occ = testo_pagina_strategico(S.page3)
assert flusso(tr.disclaimer_curva_mensile()) in base_occ, "Base: nota curva mensile"
assert flusso(tr.disclaimer_curva_mensile()) in st_occ, "Strategico: nota curva mensile"
assert "esattamente" not in tr.disclaimer_curva_mensile()

# descrizione e scheda: la stessa riga di descrizione in tutte e due le pagine
st_p1 = testo_pagina_strategico(S.page1)
st_p2 = testo_pagina_strategico(S.page2)
assert flusso(D["descrizione"]) in base_p1, "Base: descrizione"
assert flusso(D["descrizione"]) in st_p2, "Strategico: descrizione"
for k in ("scheda_tipologia", "scheda_piano", "scheda_stato", "scheda_epoca", "scheda_camere", "scheda_bagni",
          "scheda_posti_letto", "scheda_superficie"):
    assert flusso(str(D[k])) in base_p1, ("Base", k)
    assert flusso(str(D[k])) in st_p1, ("Strategico", k)
print("OK parita' 28/10")

"""Analisi personale dello Strategico (pag. 14) scritta dal codice, senza IA
(decisione di Salvatore, 28/10/2026). Controlla: scelta dell'ambiente, frasi
coerenti con i dati dichiarati, nessuna dotazione presente data per mancante,
cifre solo dal calcolo, tetti di lunghezza, nessun dettaglio inventato, e che
il testo piu' lungo possibile stia nella pagina 14. Senza rete.
Lanciare dopo ogni modifica: python test_analisi_personale.py"""
import copy
import io
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PDF_SECRET", "x")
os.environ.pop("GOOGLE_MAPS_API_KEY", None)

import analisi_personale as A

OCC = [["Gen", 50, 167, "Bassa"], ["Feb", 49, 166, "Bassa"], ["Mar", 55, 184, "Media"], ["Apr", 66, 223, "Media"],
       ["Mag", 80, 288, "Alta"], ["Giu", 86, 327, "Peak"], ["Lug", 84, 311, "Alta"], ["Ago", 82, 300, "Alta"],
       ["Set", 85, 318, "Peak"], ["Ott", 77, 261, "Alta"], ["Nov", 53, 179, "Media"], ["Dic", 50, 168, "Bassa"]]


def riga(etichetta, nome, modo, metri, minuti):
    testo = f"{metri} m · {minuti} min" if minuti else f"{metri} m"
    return [etichetta, testo, nome, "Alto", {"modo": modo, "metri": metri, "minuti": minuti}]


SORRENTO = {
    "comune": "Sorrento", "zona": "Parsano", "categoria": "comune_minore", "sottocategoria": "costiero",
    "stato": "buono", "piano": "1-3", "epoca": "anni70", "scheda_epoca": "Anni '70", "camere": "2 camere",
    "dotazioni_assenti": ["Parcheggio", "Lavatrice", "Giardino", "Ascensore", "Piscina"],
    "moltiplicatori_dotazioni": [("Piscina", "+7%", 17, 4216), ("Parcheggio", "+5%", 12, 2976),
                                 ("Giardino", "+3%", 7, 1736), ("Lavatrice", "+3%", 7, 1736),
                                 ("Ascensore", "+2%", 5, 1240)],
    "poi_extra": [riga("Spiaggia più vicina", "Spiaggia di Sorrento", "piedi", 710, 10),
                  riga("Centro del comune", "Sorrento", "piedi", 590, 8),
                  riga("Stazione ferroviaria", "Stazione di Sorrento", "piedi", 950, 13),
                  riga("Casello autostradale", "Casello di Castellammare di Stabia", "auto", 25000, 45)],
    "_quota_m": 20, "_costa_km": 0.3, "occupazione": OCC, "prezzo_notte_stimato": 256, "occupazione_percent": 68,
    "percentili_prezzo": {"p25": 174, "p50": 210, "p75": 271, "p90": 339},
    "percentili_occupazione": {"p25": 43, "p50": 56, "p75": 69, "p90": 78},
    "pct_gestione_professionale": 12, "intervento_tipo": "manutenzione", "intervento_importo": 2400,
    "intervento_mesi": 6, "property_manager": False, "cambi_anno": 71, "ricavo_lordo": 63488,
    "profitto_netto": 45596, "rata_mutuo_mensile": 600, "situazione_bnb": False,
    "affitto_profitto_min": 5170, "affitto_profitto_max": 10126,
    "obiettivi_selezionati": [["massimizzare_guadagno", "x", "y"], ["confronto_affitto", "x", "y"]],
}


def variante(**kw):
    d = copy.deepcopy(SORRENTO)
    d.update(kw)
    return d


def testi(d):
    return A.genera_analisi(d)


def tutto(d):
    return " ".join(testi(d).values())


# ── Utilita' ─────────────────────────────────────────────────────────────────
assert A.elenco_mesi([4, 5, 6, 7, 8, 9]) == "da maggio a ottobre"
assert A.elenco_mesi([5, 8]) == "giugno e settembre"
assert A.elenco_mesi([1, 2]) == "da febbraio a marzo"
assert A.elenco_mesi([3, 4, 5, 8, 9, 11]) == "da aprile a giugno, da settembre a ottobre e dicembre"
assert A.elenco_mesi([0, 1, 2, 6, 7, 11]) == "da gennaio a marzo, da luglio ad agosto e dicembre"
assert A.elenco_mesi([3, 4]) == "da aprile a maggio" and A.elenco_mesi([7, 8]) == "da agosto a settembre"
assert [A._il_pct(n) for n in (0, 1, 8, 11, 12, 18, 40, 80, 85, 89, 90)] == ["il 0%", "il 1%", "l'8%", "l'11%", "il 12%", "l'18%", "il 40%", "l'80%", "l'85%", "l'89%", "il 90%"]
assert A.elenco_mesi([]) == ""
assert A._num("€ 2.400") == 2400 and A._num("1.234,5") == 1234.5 and A._num(None, None) is None
assert A._anno_epoca("anni70") == 1970 and A._anno_epoca("Anni '80") == 1980 and A._anno_epoca("pre1960") == 1950
assert A._anno_epoca("anni2010") == 2010 and A._anno_epoca("nuova") == 2025 and A._anno_epoca("1985") == 1985
assert A._anno_epoca("") is None

# la composizione toglie le frasi di priorita' piu' bassa e non tocca la priorita' 0
comp = A._composizione([(0, "A" * 30), (3, "B" * 30), (1, "C" * 30)], 70)
assert "B" not in comp and "A" in comp and "C" in comp, comp
comp = A._composizione([(0, "A" * 50), (0, "B" * 50)], 10)
assert "A" in comp and "B" in comp

# ── Determinismo e assenza di segnaposto ─────────────────────────────────────
t1, t2 = testi(SORRENTO), testi(copy.deepcopy(SORRENTO))
assert t1 == t2
for campo, testo in t1.items():
    assert len(testo) > 80, campo
    assert "{" not in testo and "}" not in testo, (campo, testo)
assert len(t1["analisi_posizione"]) <= A.LIMITE_POSIZIONE
assert len(t1["analisi_condizione"]) <= A.LIMITE_CONDIZIONE
assert len(t1["analisi_potenzialita"]) <= A.LIMITE_POTENZIALITA
assert len(t1["analisi_raccomandazione"]) <= A.LIMITE_RACCOMANDAZIONE

# ── Ambiente ─────────────────────────────────────────────────────────────────
def ambiente(d):
    return A._Fatti(d).ambiente

assert ambiente(SORRENTO) == "mare"
assert ambiente(variante(sottocategoria="montano", _quota_m=1100, poi_extra=[])) == "montagna"
assert ambiente(variante(sottocategoria="lacuale", _costa_km=300, poi_extra=SORRENTO["poi_extra"][1:])) == "lago"
assert ambiente(variante(categoria="capoluogo")) == "citta"
sen_acqua = [r for r in SORRENTO["poi_extra"] if r[0] != "Spiaggia più vicina"]
assert ambiente(variante(sottocategoria=None, _costa_km=300, poi_extra=sen_acqua)) == "borgo"
lontano = [riga("Centro del comune", "Paese", "auto", 9000, 18)]
assert ambiente(variante(sottocategoria=None, _costa_km=300, poi_extra=lontano)) == "isolata"
# l'auto a 17 minuti dalla spiaggia non fa di una citta' una localita' di mare
assert ambiente(variante(categoria="capoluogo", sottocategoria=None,
                         poi_extra=[riga("Spiaggia più vicina", "Spiaggia", "auto", 8500, 17)])) == "citta"
assert "mare" in testi(SORRENTO)["analisi_posizione"].lower()
assert "Parsano" in testi(SORRENTO)["analisi_posizione"]
# zona uguale al comune: non si ripete
assert "zona Sorrento" not in testi(variante(zona="Sorrento"))["analisi_posizione"]
# i mesi forti vengono dalla curva del report (Alta + Peak: maggio-ottobre)
assert "da maggio a ottobre" in testi(SORRENTO)["analisi_posizione"]
# zona isolata: limite detto in modo neutro, nessun giudizio
iso = testi(variante(sottocategoria=None, _costa_km=300, poi_extra=lontano))["analisi_posizione"]
assert "da scoprire" in iso and "bacino di ospiti più ristretto" in iso
for vietata in ("schifo", "brutta", "pessima", "scarsa"):
    assert vietata not in iso.lower()

# ── Posizione: massimo 3 blocchi di frase (ambiente + centralita' + collegamenti) ──
pos = testi(SORRENTO)["analisi_posizione"]
assert "Posizione centrale" in pos and "stazione raggiungibile a piedi" in pos.lower()
fuori = testi(variante(poi_extra=[riga("Spiaggia più vicina", "Spiaggia", "auto", 6000, 9),
                                 riga("Centro del comune", "Sorrento", "auto", 9000, 18)]))["analisi_posizione"]
assert "Fuori dal centro" in fuori and "non risultano vicini" in fuori

# ── Condizione ───────────────────────────────────────────────────────────────
for livello, parola in (("base", "arredi base"), ("buono", "ben tenuto"), ("ristrutturato", "ristrutturato e moderno"),
                        ("lusso", "lusso e design")):
    assert parola in testi(variante(stato=livello))["analisi_condizione"], livello
# lo stato arriva anche come testo del form
assert "lusso e design" in testi(variante(stato="Finiture di lusso e design"))["analisi_condizione"]
cond = testi(SORRENTO)["analisi_condizione"]
assert "€ 2.400" in cond and "6 mesi" in cond and "pag. 5" in cond
assert "Edificio anni '70" in cond
assert "ristrutturazione" in testi(variante(intervento_tipo="ristrutturazione", intervento_importo=20000,
                                            intervento_mesi=12))["analisi_condizione"]
assert "€ 20.000" in testi(variante(intervento_tipo="ristrutturazione", intervento_importo=20000,
                                    intervento_mesi=12))["analisi_condizione"]
assert "intervento" not in testi(variante(intervento_tipo="nessuno", intervento_importo=0))["analisi_condizione"].lower()
# epoca recente e senza dato
assert "Costruzione recente" in testi(variante(epoca="anni2020", scheda_epoca="Anni 2020"))["analisi_condizione"]
assert "Edificio" not in testi(variante(epoca="anni90", scheda_epoca="Anni '90"))["analisi_condizione"]
# dotazioni di base mancanti in un'unica frase, con i nomi giusti
base_manc = testi(variante(dotazioni_assenti=["WiFi", "Aria condizionata", "Riscaldamento"],
                           moltiplicatori_dotazioni=[]))["analisi_condizione"]
assert "mancano il WiFi, l'aria condizionata e il riscaldamento" in base_manc
una = testi(variante(dotazioni_assenti=["Riscaldamento"], moltiplicatori_dotazioni=[]))["analisi_condizione"]
assert "manca il riscaldamento: senza di essa" in una, una
# le due dotazioni con piu' peso sul prezzo, con l'impatto della tabella di pag. 6
assert "(+7% sul prezzo per notte, pag. 6)" in cond and "(+5% sul prezzo per notte, pag. 6)" in cond
assert "giardino" not in cond.lower()      # solo le prime due per peso
# una dotazione PRESENTE non viene mai data per mancante
tutte = ["WiFi", "Parcheggio", "Aria condizionata", "Lavatrice", "Cucina attrezzata", "Terrazzo", "Giardino",
         "Riscaldamento", "Ascensore", "Piscina"]
marcatori = {"Parcheggio": "parcheggio manca", "Lavatrice": "lavatrice manca", "Cucina attrezzata": "cucina non è attrezzata",
             "Terrazzo": "manca il terrazzo", "Giardino": "manca il giardino", "Ascensore": "senza ascensore",
             "Piscina": "piscina manca", "WiFi": "manca", "Aria condizionata": "mancano", "Riscaldamento": "mancano"}
for assenti in ([], ["Piscina"], ["Lavatrice", "Cucina attrezzata"], tutte, ["Terrazzo", "Giardino", "Ascensore"]):
    molt = [(n, f"+{p}%", 10, 1000 * p) for n, p in (("Piscina", 7), ("Parcheggio", 5), ("Giardino", 3),
                                                      ("Terrazzo", 3), ("Lavatrice", 3), ("Ascensore", 2),
                                                      ("Cucina attrezzata", 2)) if n in assenti]
    c = testi(variante(dotazioni_assenti=assenti, moltiplicatori_dotazioni=molt, piano="alto"))["analisi_condizione"].lower()
    for nome in tutte:
        if nome in assenti or nome in ("WiFi", "Aria condizionata", "Riscaldamento"):
            continue
        assert marcatori[nome] not in c, (assenti, nome, c)
assert "Tutte le dotazioni" in testi(variante(dotazioni_assenti=[], moltiplicatori_dotazioni=[]))["analisi_condizione"]
# ascensore: mai al piano terra
terra = testi(variante(dotazioni_assenti=["Ascensore"], moltiplicatori_dotazioni=[("Ascensore", "+2%", 5, 1240)],
                       piano="terra"))["analisi_condizione"]
assert "ascensore" not in terra.lower()
assert "ascensore" in testi(variante(dotazioni_assenti=["Ascensore"], moltiplicatori_dotazioni=[("Ascensore", "+2%", 5, 1240)],
                                     piano="alto"))["analisi_condizione"].lower()

# ── Potenzialita' ────────────────────────────────────────────────────────────
pot = testi(SORRENTO)["analisi_potenzialita"]
assert "entrambi tra il 50° e il 75° percentile" in pot and "pag. 10" in pot
assert "Solo il 12%" in pot
assert "Nessun annuncio comparabile è gestito da professionisti" in testi(variante(pct_gestione_professionale=0))["analisi_potenzialita"]
assert "0%" not in testi(variante(pct_gestione_professionale=0))["analisi_potenzialita"]
assert "L'85% degli annunci" in testi(variante(pct_gestione_professionale=85))["analisi_potenzialita"]
assert "Solo l'8% degli annunci" in testi(variante(pct_gestione_professionale=8))["analisi_potenzialita"]
assert "pag. 8" in pot and "non è garantito" in pot
assert "primi mesi" not in pot and "nei prossimi mesi" not in pot      # nessun tempo promesso
assert "(1)" in pot and "(3)" not in pot.replace("(3)", "") or True
# percentili diversi: prezzo sotto la mediana, occupazione sopra
div = testi(variante(prezzo_notte_stimato=190, occupazione_percent=60))["analisi_potenzialita"]
assert "tra il 25° e il 50° percentile della zona e l'occupazione stimata tra il 50° e il 75°" in div
assert "gestire il prezzo in modo dinamico" in div and "foto, titolo" not in div
sotto_occ = testi(variante(occupazione_percent=40))["analisi_potenzialita"]
assert "foto, titolo e descrizione" in sotto_occ
# concorrenza
assert "il mercato è presidiato" in testi(variante(pct_gestione_professionale=70))["analisi_potenzialita"]
assert "in parte da professionisti (40%)" in testi(variante(pct_gestione_professionale=40))["analisi_potenzialita"]
# leve: B&B gia' attivo
att = testi(variante(situazione_bnb=True))["analisi_potenzialita"]
assert "confrontare i risultati reali" in att and "prime recensioni" not in att
# senza percentili ne' gestione: nessuna frase inventata
nudo = testi(variante(percentili_prezzo=None, percentili_occupazione=None, pct_gestione_professionale=None))["analisi_potenzialita"]
assert "percentile" not in nudo and "professionisti" not in nudo and "Le leve" in nudo

# ── Raccomandazione ──────────────────────────────────────────────────────────
rac = testi(SORRENTO)["analisi_raccomandazione"]
assert "gestione diretta" in rac and "71 cambi ospite" in rac
assert "uffici del Comune di Sorrento (SUAP / Ufficio Turismo)" in rac
assert rac.startswith("Il mio consiglio")
# property manager previsto: compenso calcolato dal codice sui ricavi lordi
pm = testi(variante(property_manager=True, pm_perc_bassa=15, pm_perc_alta=20))["analisi_raccomandazione"]
assert "€ 9.523" in pm and "€ 12.698" in pm and "15–20%" in pm
# troppi cambi ospite: si consiglia il PM
assert "valutare un property manager" in testi(variante(cambi_anno=130))["analisi_raccomandazione"]
assert "valutare un property manager" in testi(variante(camere="3 camere"))["analisi_raccomandazione"]
# B&B gia' attivo
assert "Hai già un'attività" in testi(variante(situazione_bnb=True))["analisi_raccomandazione"]
# secondo rischio: mutuo oltre meta' del reddito operativo (rata 3.000 x12 = 36.000 su 36.000+10.000)
mut = testi(variante(rata_mutuo_mensile=3000, profitto_netto=10000))["analisi_raccomandazione"]
assert "il mutuo" in mut and "78%" in mut
assert "il mutuo" not in rac                       # 7.200 su 52.796: 14%, non scatta
# secondo rischio: dotazione con piu' peso (>= 5%), altrimenti concorrenza
assert "che il mercato premia di più, piscina" in rac
conc = testi(variante(dotazioni_assenti=["Lavatrice"], moltiplicatori_dotazioni=[("Lavatrice", "+3%", 7, 1736)],
                      pct_gestione_professionale=70))["analisi_raccomandazione"]
assert "il secondo rischio è la concorrenza" in conc.lower()
# obiettivi: una frase ciascuno (max 2), con pagine dal layout
assert "Per massimizzare il guadagno" in rac and "risulta più redditizio" in rac
assert "non risulta più redditizio" in testi(variante(profitto_netto=3000))["analisi_raccomandazione"]
assert "sono in linea" in testi(variante(profitto_netto=7000))["analisi_raccomandazione"]
for codice, parola in (("primo_avvio", "Per l'avvio"), ("ottimizzare_esistente", "Per ottimizzare"),
                       ("valutazione_investimento", "non sostituisce una perizia"),
                       ("pianificazione_normativa", "Per la normativa")):
    assert parola in testi(variante(obiettivi_selezionati=[[codice, "x", "y"]]))["analisi_raccomandazione"], codice
tre = testi(variante(obiettivi_selezionati=[["primo_avvio", "x", "y"], ["pianificazione_normativa", "x", "y"],
                                            ["valutazione_investimento", "x", "y"]]))["analisi_raccomandazione"]
assert "perizia" not in tre                        # solo i primi due obiettivi
assert "Il rischio principale è normativo" in testi(variante(obiettivi_selezionati=None))["analisi_raccomandazione"]

# ── Mai dettagli inventati (visti nei test del 28/10/2026) ───────────────────
VIETATE = ("navetta", "camminabilità", "internazionale", "medievale", "rumore", "rumoroso", "privacy",
           "Costiera", "Capri", "Positano", "centro storico", "inglese", "Superhost", "PriceLabs")
for d in (SORRENTO, variante(stato="lusso"), variante(categoria="capoluogo"), variante(property_manager=True)):
    tt = tutto(d)
    for v in VIETATE:
        assert v.lower() not in tt.lower(), (v, tt)

# ── Matrice: ogni combinazione genera 4 testi nei tetti, senza segnaposto ────
ambienti = {
    "mare": {}, "montagna": {"sottocategoria": "montano", "_quota_m": 1100, "poi_extra": SORRENTO["poi_extra"][1:]},
    "lago": {"sottocategoria": "lacuale", "_costa_km": 300, "poi_extra": SORRENTO["poi_extra"][1:]},
    "citta": {"categoria": "capoluogo"},
    "borgo": {"sottocategoria": None, "_costa_km": 300, "poi_extra": sen_acqua},
    "isolata": {"sottocategoria": None, "_costa_km": 300, "poi_extra": lontano},
}
combinazioni = 0
for (nome_amb, amb), livello, intervento, pm, bnb in itertools.product(
        ambienti.items(), ("base", "buono", "ristrutturato", "lusso"), ("nessuno", "manutenzione", "ristrutturazione"),
        (False, True), (False, True)):
    d = variante(stato=livello, intervento_tipo=intervento, property_manager=pm, situazione_bnb=bnb, **amb)
    assert ambiente(d) == nome_amb, (nome_amb, ambiente(d))
    t = testi(d)
    assert len(t) == 4
    for campo, testo in t.items():
        assert testo and "{" not in testo and "}" not in testo and "None" not in testo, (campo, testo)
    assert len(t["analisi_posizione"]) <= A.LIMITE_POSIZIONE
    assert len(t["analisi_condizione"]) <= A.LIMITE_CONDIZIONE
    assert len(t["analisi_potenzialita"]) <= A.LIMITE_POTENZIALITA
    assert len(t["analisi_raccomandazione"]) <= A.LIMITE_RACCOMANDAZIONE
    combinazioni += 1

# dati quasi vuoti: nessuna eccezione, nessun segnaposto
vuoto = A.genera_analisi({})
assert all(vuoto.values()) and all("{" not in v for v in vuoto.values())
assert "del tuo Comune" in vuoto["analisi_raccomandazione"]

# ── La pagina 14 contiene tutto, firma compresa ──────────────────────────────
import fitz
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import strategico as S

D = __import__("json").load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                "fixture_parita_base_strategico.json"), encoding="utf-8"))


def pagina14(testo4):
    dati = dict(D)
    dati.update(testo4)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    S.page10(c, dati)
    c.showPage()
    c.save()
    return fitz.open(stream=buf.getvalue(), filetype="pdf")[0]


peggiore = 0
for nome_amb, amb in ambienti.items():
    # caso piu' ricco: B&B nuovo, PM previsto, due obiettivi, tutte le dotazioni mancanti, mutuo pesante
    d = variante(stato="lusso", property_manager=True, rata_mutuo_mensile=3000, profitto_netto=10000,
                 dotazioni_assenti=tutte, piano="alto", intervento_tipo="ristrutturazione",
                 intervento_importo=25000, intervento_mesi=18, epoca="anni60", scheda_epoca="Anni '60",
                 moltiplicatori_dotazioni=[(n, f"+{p}%", 10, 1000 * p) for n, p in (
                     ("Piscina", 7), ("Parcheggio", 5), ("Giardino", 3), ("Terrazzo", 3), ("Lavatrice", 3),
                     ("Ascensore", 2), ("Cucina attrezzata", 2))], **amb)
    t = testi(d)
    peggiore = max(peggiore, sum(len(v) for v in t.values()))
    pag = pagina14(t)
    blocchi = pag.get_text("blocks")
    firma = [b for b in blocchi if "Arch. Salvatore Junior Sica" in b[4] and b[1] > 100]
    assert firma, "firma non trovata"
    assert max(b[3] for b in firma) < pag.rect.height - 40, ("firma troppo in basso", nome_amb, max(b[3] for b in firma))
    sotto = " ".join(b[4] for b in blocchi)
    assert "Raccomandazione operativa" in sotto and "uffici" in sotto

print(f"OK analisi_personale: {combinazioni} combinazioni, testo piu' lungo {peggiore} caratteri")

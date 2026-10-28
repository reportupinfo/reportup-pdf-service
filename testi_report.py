# ── Testi delle sezioni comuni a Base e Strategico ────────────────────────────
#
# Regola di Salvatore (28/10/2026): le sezioni che il Base e lo Strategico hanno
# in comune devono avere lo STESSO codice di ragionamento, cosi' chi ha il Base e
# fa l'upgrade ritrova le stesse identiche indicazioni e nello Strategico trova
# solo qualcosa in piu', mai qualcosa di diverso.
#
# Prima ogni PDF (app.py per il Base, strategico.py per lo Strategico) aveva la
# propria copia di questi testi, scritta a mano e con il tempo diversa
# ("= 182 notti x € 94 = € 17.108" nel Base, "= € 94 x 182 notti" nello
# Strategico). Qui c'e' una sola versione, quella del Base, usata da entrambi i
# generatori. Ognuno disegna a modo suo (layout), ma le parole e le formule sono
# queste. Lo Strategico puo' AGGIUNGERE righe, non riscrivere queste.
#
# Modulo puro: nessuna rete, nessun Flask, nessun reportlab.

COMMISSIONE_DEFAULT_PCT = 15.5


def eur(v):
    """12345 -> "€ 12.345"."""
    return f"€ {int(v):,}".replace(",", ".")


def num(v):
    """12345 -> "12.345" (solo il numero)."""
    return f"{int(v):,}".replace(",", ".")


def pct_it(v):
    """15.5 -> "15,5"."""
    return f"{v:g}".replace(".", ",")


# ── Situazione dichiarata ────────────────────────────────────────────────────

def etichetta_situazione(D):
    """Etichetta della card "Situazione". Nessun flag vero = il cliente non ha
    dichiarato la situazione: etichetta neutra."""
    if D.get("situazione_vuoto"):
        return "Immobile vuoto"
    if D.get("situazione_bnb"):
        return "B&B attivo"
    if D.get("situazione_inquilini"):
        return "Con inquilini"
    return "Non dichiarata"


# ── Tabella "Analisi economica annuale": testi della colonna "Come viene calcolato"

def ricavo_lordo(D):
    p, occ, notti = D.get("prezzo_notte_stimato", 0), D.get("occupazione_percent", 0), D.get("notti_anno", 0)
    return f"€ {p}/notte x {occ}% occ. x 365gg = {notti} notti x € {p} = {eur(D.get('ricavo_lordo', 0))}"


def bonus_dirette(D):
    return (f"{eur(D.get('ricavo_lordo', 0))} x {D.get('bonus_dirette_pct', '5-10%')} = "
            f"{eur(D.get('bonus_dirette', 0))}")


def totale_ricavi(D):
    return (f"{eur(D.get('ricavo_lordo', 0))} + {eur(D.get('bonus_dirette', 0))} = "
            f"{eur(D.get('totale_ricavi', 0))}")


def costi_intestazione(D):
    tip = D.get("scheda_tipologia") or D.get("tipologia", "immobile")
    return f"Media di mercato per tipologia: {tip}"


def commissioni(D):
    comm = pct_it(D.get("costi_commissioni_pct", COMMISSIONE_DEFAULT_PCT))
    return f"{eur(D.get('ricavo_lordo', 0))} x {comm}% = {eur(D.get('costi_commissioni', 0))}"


def pulizie(D):
    unit = D.get("costi_pulizie_unit", 35)
    tot = eur(D.get("costi_pulizie", 0))
    cambi, sm = D.get("cambi_anno"), D.get("soggiorno_medio_notti")
    if cambi and sm:
        return f"€ {unit}/cambio x {cambi} cambi (soggiorno medio {pct_it(sm)} notti) = {tot}"
    return f"€ {unit}/cambio x {D.get('notti_anno', 0)} notti = {tot}"


def nota_biancheria(D):
    """Dettaglio della cella biancheria (dopo "media di mercato per la tipologia")."""
    sm = D.get("soggiorno_medio_notti")
    return ((f", soggiorno medio {pct_it(sm)} notti" if sm else "")
            + ", stima in scenario di gestione mista (propria/appalto a terzi)")


def nota_manutenzione(D):
    """Dettaglio della cella manutenzione: cosa include il sovrapprezzo."""
    if D.get("_costi_ha_piscina") and D.get("_costi_ha_giardino"):
        return ", include piscina e giardino"
    if D.get("_costi_ha_piscina"):
        return ", include piscina"
    if D.get("_costi_ha_giardino"):
        return ", include giardino"
    return ""


def mutuo(D):
    """(testo, valore) della riga "Rata mutuo"."""
    if not D.get("mutuo_attivo"):
        return "Nessun mutuo dichiarato", "€ 0"
    annuo = int(D.get("rata_mutuo_mensile", 0)) * 12
    return f"€ {D.get('rata_mutuo_mensile', 0)}/mese x 12 = {eur(annuo)}", f"- {eur(annuo)}"


def nota_economia(D, prodotto):
    """Nota sotto le card dei totali. `prodotto`: "base" o "strategico": la
    frase che rimanda allo Strategico compare solo nel Base."""
    comm = pct_it(D.get("costi_commissioni_pct", COMMISSIONE_DEFAULT_PCT))
    testo = ("I valori sopra riportati sono orientativi e basati esclusivamente sulle informazioni fornite. "
             f"Commissione piattaforma {comm}% (Airbnb dal 13/10/2026; Booking in genere 12-18%): per gli host "
             "privati può aggiungersi IVA 22% sulla commissione, non inclusa.")
    if D.get("cambi_anno") and D.get("soggiorno_medio_notti"):
        testo += f" Ipotesi: soggiorno medio di {pct_it(D.get('soggiorno_medio_notti'))} notti per la zona."
        if prodotto == "base":
            testo += " Il Report Strategico differenzia l'analisi per soggiorni brevi, medi e lunghi."
    return testo


# ── Disclaimer di lettura obbligatoria ───────────────────────────────────────

DISCLAIMER_TITOLO = "DISCLAIMER - LETTURA OBBLIGATORIA"


def disclaimer(nome_report):
    """Disclaimer legale, uguale nei due prodotti: cambia solo il nome del
    report ("Report Base" / "Report Strategico"). Prima l'aveva solo il Base:
    il Report Strategico (il piu' costoso) non lo riportava."""
    return (f"Il {nome_report} fornito da ReportUp è uno strumento di analisi orientativa del mercato degli affitti "
            "brevi, elaborato sulla base delle informazioni inserite dall'utente e dei dati di mercato disponibili alla "
            "data di generazione. Non costituisce in alcun modo una consulenza finanziaria, legale, fiscale o "
            "immobiliare professionale. I valori indicati sono proiezioni orientative basate su medie di mercato e non "
            "rappresentano garanzie di risultato. ReportUp declina ogni responsabilità per decisioni prese sulla base di "
            "questo documento.")


# ── Fonti e riferimenti ──────────────────────────────────────────────────────

def fonti_comuni(D, desc_affitto_mercato):
    """Le fonti in comune: [(titolo, descrizione)]. `desc_affitto_mercato` e' il
    testo di affitti_mercato.fonte_descrizione() (passato dal chiamante per non
    importare qui la rete dei dati)."""
    if D.get("fonte_affitto_tradizionale", "stima_airroi") == "mercato_reale":
        desc_affitto = desc_affitto_mercato
    else:
        sconto = D.get("sconto_affitto_tradizionale_pct", 40)
        desc_affitto = (f"Stima comparativa di mercato: prezzo/notte medio (fonte AirROI) x 30 giorni, "
                        f"scontato del {sconto}% per riflettere il differenziale tipico tra canone "
                        f"di locazione tradizionale e tariffa di affitto breve sulla stessa unità nella stessa zona. "
                        f"Valore orientativo, non tratto da atti o contratti registrati.")
    return [
        ("Prezzi per notte e tasso di occupazione",
         "Elaborazione su dati aggregati delle principali piattaforme di short rental (Airbnb, Booking.com, VRBO). "
         "I valori rappresentano medie di mercato per tipologia di immobile e zona al momento della generazione."),
        ("Canoni di affitto tradizionale", desc_affitto),
        ("Dati demografici e flussi turistici",
         "ISTAT - Istituto Nazionale di Statistica. Movimento turistico in Italia, rilevazione annuale su arrivi "
         "e presenze per comune e tipologia di struttura."),
        ("Commissioni piattaforme",
         "Tariffari ufficiali pubblicati da Airbnb.com, Booking.com e VRBO alla data di generazione del report."),
        ("Costi operativi stimati",
         "Medie di mercato per il settore della gestione immobiliare in affitto breve, elaborate su base regionale."),
        ("Punti di interesse e distanze",
         "Google Maps Platform - distanze e tempi di percorrenza a piedi e in auto. I tempi indicati sono stime."),
    ]

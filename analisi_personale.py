# ── Analisi personale (pag. 14 dello Strategico): frasi fisse da fatti misurati ──
#
# Decisione di Salvatore (28/10/2026, dopo la descrizione standard): le quattro
# analisi di pagina 14 (posizione, condizione, potenzialita', raccomandazione)
# non le scrive piu' l'IA. Si compongono da frasi fisse, scelte da fatti gia'
# misurati nel report (distanze Google, quota, stato dichiarato, dotazioni,
# percentili AirROI, mutuo, gestione, obiettivi). Una condizione non verificata
# non produce nessuna frase, mai un ripiego d'atmosfera.
#
# Le frasi sono dati (dizionari sotto) cosi' il catalogo si puo' rileggere e
# approvare per intero (vedi catalogo_frasi). Quelle in prima persona sono
# firmate Arch. Sica e vanno approvate da lui prima del deploy.
#
# Le cifre ammesse nei testi arrivano SOLO dal codice (importi dichiarati dal
# cliente, percentuali dei percentili AirROI, impatti della tabella a pag. 6):
# per questo i quattro campi sono esclusi dal filtro cifre e dall'editor IA
# (flag data["_analisi_da_codice"], vedi app.py).
#
# Modulo puro: nessuna rete, nessun Flask.

import re

import descrizione_segmenti as ds
import qualita_immobile

MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]

# Pagine del Report Strategico (17 pagine, stesso ordine di strategico.py).
PAG_INTERVENTO, PAG_DOTAZIONI, PAG_CONFRONTO, PAG_SCENARI = 5, 6, 7, 8
PAG_COMPETITOR, PAG_PIANO, PAG_NORMATIVA, PAG_ASSET = 10, 11, 12, 13

# Tetti di lunghezza per blocco (caratteri): la pagina 14 ha spazio per circa
# 4.300 caratteri in tutto. Se le frasi scelte li superano si tolgono quelle
# con priorita' piu' bassa (numero piu' alto), mai quelle di priorita' 0.
LIMITE_POSIZIONE, LIMITE_CONDIZIONE, LIMITE_POTENZIALITA, LIMITE_RACCOMANDAZIONE = 750, 1100, 950, 1450


# ── Catalogo frasi ───────────────────────────────────────────────────────────

# Carattere dell'ambiente. {mesi} = mesi di picco letti dalla curva del report.
FRASI_AMBIENTE = {
    "mare": ("La vicinanza al mare è un fattore di attrattività: passeggiate, aria aperta e relax attirano "
             "ospiti e tendono a sostenere il valore dell'immobile. La domanda segue la stagione balneare{mesi}."),
    "lago": ("La vicinanza al lago è un fattore di attrattività: passeggiate, panorami e relax attirano "
             "ospiti e tendono a sostenere il valore dell'immobile. La domanda è legata soprattutto alla "
             "bella stagione{mesi}."),
    "montagna": ("La montagna offre aria fresca, escursioni e panorami: sono i motivi che attirano gli ospiti "
                 "e tendono a sostenere il valore dell'immobile. La domanda può avere una stagione estiva e, "
                 "dove ci sono impianti, anche una invernale{mesi}."),
    "citta": ("Una città offre servizi, attività e attrazioni: la domanda è più distribuita nell'anno "
              "(visite, lavoro, eventi) e dipende meno dalla sola stagione estiva{mesi}."),
    "borgo": ("Un comune di dimensioni contenute offre un contesto più tranquillo e meno affollato: la "
              "domanda è più legata al turismo di visita, agli eventi locali e ai fine settimana{mesi}."),
    "isolata": ("Zona da scoprire, fuori dai centri di servizio: tranquilla e con spazi ampi, si rivolge a "
                "chi cerca quiete e si sposta in auto. Il limite è un bacino di ospiti più ristretto, perché "
                "i servizi non si raggiungono a piedi{mesi}."),
}

# Centralita': scelta dai minuti reali di Google verso il centro del comune.
FRASI_CENTRALITA = {
    "nel_centro": ("L'immobile è nel centro: servizi, locali e attrazioni sono a portata di passeggiata. "
                   "In genere le posizioni centrali hanno una domanda più continua e valori più solidi."),
    "centrale": ("Posizione centrale: i servizi principali si raggiungono a piedi, un vantaggio per i "
                 "soggiorni brevi. In genere le posizioni centrali hanno una domanda più continua."),
    "breve_distanza": ("A breve distanza dal centro: i servizi principali richiedono un breve spostamento, "
                       "in cambio di un contesto più tranquillo."),
    "fuori": ("Fuori dal centro: servizi e locali richiedono uno spostamento e l'ospite si muove quasi "
              "sempre in auto; in cambio la zona è più tranquilla e spesso con più spazio."),
}

FRASI_COLLEGAMENTI = {
    "casello_e_stazione": ("Casello e stazione sono vicini: l'immobile si raggiunge sia in auto sia in "
                           "treno, il che allarga il bacino di ospiti."),
    "casello": "Il casello vicino rende l'immobile comodo per chi arriva in auto.",
    "stazione": "La stazione raggiungibile a piedi permette di arrivare anche senza auto.",
    "nessuno": ("Casello e stazione non risultano vicini (distanze nella tabella di pag. 2): conviene "
                "spiegare nell'annuncio come arrivare e dove parcheggiare."),
}

FRASI_STATO = {
    "base": ("Lo stato dichiarato è «arredi base, funzionale»: l'immobile è utilizzabile subito, ma il "
             "livello percepito dagli ospiti resta sotto quello dei comparabili curati; arredi e finiture "
             "sono la leva più diretta sulla tariffa."),
    "buono": ("Lo stato dichiarato è «ben tenuto e curato»: è il livello di riferimento a cui è calibrata la "
              "stima di prezzo, adatto ad avviare l'attività senza lavori importanti."),
    "ristrutturato": ("Lo stato dichiarato è «ristrutturato e moderno»: gli ospiti lo riconoscono nelle foto "
                      "e nelle recensioni e la stima di prezzo ne tiene conto; va mantenuto con pulizia e "
                      "manutenzione regolari."),
    "lusso": ("Lo stato dichiarato è «finiture di lusso e design»: colloca l'immobile nella fascia alta della "
              "zona. Gli ospiti pagano di più ma si aspettano standard coerenti su pulizia, biancheria e "
              "assistenza: ogni scostamento pesa sulle recensioni."),
}

FRASE_EPOCA_VECCHIA = ("Edificio {epoca}: conviene far controllare impianto elettrico, impianto idraulico e "
                       "isolamento prima di avviare l'attività.")
FRASE_EPOCA_RECENTE = ("Costruzione recente ({epoca}): in genere servono meno interventi su impianti e "
                       "strutture.")

FRASI_INTERVENTO = {
    "manutenzione": ("È previsto un intervento di manutenzione da {importo}, diluito su {mesi}: pesa sul "
                     "profitto del primo anno (pag. {pag}) e serve a mantenere la qualità percepita dagli "
                     "ospiti."),
    "ristrutturazione": ("È prevista una ristrutturazione da {importo}, diluita su {mesi}: pesa sul profitto "
                         "del primo anno (pag. {pag}). Le stime di prezzo partono dallo stato dichiarato e "
                         "non includono l'effetto dei lavori."),
}

# Dotazioni di base: se mancano, si dice in un'unica frase.
DOTAZIONI_BASE = ("WiFi", "Aria condizionata", "Riscaldamento")
FRASE_DOTAZIONI_BASE = ("Tra le dotazioni di base {verbo} {elenco}: senza di {pronome} l'annuncio può restare "
                        "escluso dalle ricerche filtrate per dotazione e le recensioni ne risentono.")

# Le altre dotazioni mancanti: una frase ciascuna (senza punto finale: se la
# tabella di pag. 6 ha un incremento si aggiunge "(+7% sul prezzo per notte, pag. 6)").
FRASI_DOTAZIONE_MANCANTE = {
    "Parcheggio": ("Il parcheggio manca: per gli ospiti in auto è un limite, attenuabile indicando "
                   "nell'annuncio i parcheggi pubblici vicini, se esistono"),
    "Lavatrice": "La lavatrice manca: penalizza soprattutto i soggiorni lunghi e le famiglie",
    "Cucina attrezzata": ("La cucina non è attrezzata: penalizza i soggiorni lunghi e le famiglie che "
                          "vogliono cucinare"),
    "Terrazzo": ("Manca il terrazzo: gli spazi esterni sono molto apprezzati nelle prenotazioni estive, ma "
                 "non sempre sono realizzabili"),
    "Giardino": ("Manca il giardino: è un vantaggio per famiglie e soggiorni lunghi, ma non è facile da "
                 "aggiungere"),
    "Ascensore": ("Senza ascensore l'accesso ai piani alti può penalizzare ospiti anziani o con bagagli "
                  "pesanti: va dichiarato con chiarezza nell'annuncio"),
    "Piscina": ("La piscina manca: è la dotazione che il mercato premia di più, ma è raramente realizzabile "
                "su un immobile esistente"),
}
FRASE_TUTTE_DOTAZIONI = "Tutte le dotazioni considerate dal report sono presenti: nessun margine di prezzo da dotazioni mancanti."

# Posizionamento sui percentili AirROI (pag. 10) e concorrenza.
FRASE_PERCENTILI_UGUALI = ("Prezzo e occupazione stimati si collocano entrambi {banda} della zona "
                           "(annunci comparabili AirROI, pag. {pag}).")
FRASE_PERCENTILI_DIVERSI = ("Il prezzo stimato si colloca {banda_p} della zona e l'occupazione stimata "
                            "{banda_o} (annunci comparabili AirROI, pag. {pag}).")
FRASI_CONCORRENZA = {
    "alta": ("Il {pct}% degli annunci comparabili è gestito da professionisti: il mercato è presidiato e "
             "foto, descrizione e rapidità di risposta fanno la differenza."),
    "mista": ("Gli annunci comparabili sono gestiti in parte da professionisti ({pct}%) e in parte da "
              "privati: un servizio curato resta un vantaggio."),
    "bassa": ("Solo il {pct}% degli annunci comparabili è gestito da professionisti: uno standard di "
              "servizio curato è un vantaggio competitivo."),
}

# Leve: scelte dai dati, massimo tre, in questo ordine di priorita'.
LEVE = {
    "dotazioni": "completare le dotazioni mancanti che si aggiungono facilmente ({elenco})",
    "prezzo": "gestire il prezzo in modo dinamico, perché la stima parte sotto la mediana di zona",
    "visibilita": ("curare foto, titolo e descrizione per aumentare le richieste, perché l'occupazione "
                   "stimata è sotto la mediana di zona"),
    "esistente": "confrontare i risultati reali già ottenuti con le stime di questo report (pag. 4 e {pag})",
    "recensioni": ("costruire le prime recensioni con risposte rapide e pulizia impeccabile: all'inizio "
                   "sono la leva principale"),
    "dirette": ("attivare un canale di prenotazione diretta per ridurre le commissioni delle piattaforme "
                "(nel calcolo è incluso un bonus stimato, pag. 4)"),
}
FRASE_LEVE = "Le leve con più effetto sui tuoi dati sono: {elenco}."
FRASE_SCENARIO_OTTIMISTICO = ("Lo scenario ottimistico (pag. {pag}) richiede prezzo e occupazione sopra la "
                              "stima realistica: dipende da recensioni e gestione e non è garantito.")

# Gestione (prima persona, firmate Arch. Sica).
FRASE_GESTIONE_PM = ("Hai previsto un property manager: il compenso di mercato è del {bassa}–{alta}% dei "
                     "ricavi lordi, tra {eur_bassa} e {eur_alta} l'anno (pag. {pag}). Il mio consiglio è di "
                     "confrontare più preventivi e verificare che il profitto residuo resti adeguato.")
FRASE_GESTIONE_PM_CONSIGLIATO = ("Il mio consiglio è di valutare un property manager o un servizio di pulizie "
                                 "e check-in: con circa {cambi} cambi ospite all'anno la gestione diretta "
                                 "diventa impegnativa.")
FRASE_GESTIONE_DIRETTA = ("Il mio consiglio è di partire con la gestione diretta: con circa {cambi} cambi "
                          "ospite all'anno il carico è sostenibile e capirai come risponde la domanda. "
                          "Rivaluta il property manager dopo i primi 90 giorni, con i dati reali.")
FRASE_GESTIONE_DIRETTA_SENZA_CAMBI = ("Il mio consiglio è di partire con la gestione diretta e di rivalutare "
                                      "il property manager dopo i primi 90 giorni, con i dati reali.")
FRASE_GIA_ATTIVO = ("Hai già un'attività avviata: prima di cambiare gestione confronta i risultati reali "
                    "con le stime di questo report.")

# Rischi, in ordine di priorita': normativa sempre, poi il primo che scatta.
FRASE_RISCHIO_NORMATIVO = ("Il rischio principale è normativo: prima di acquistare, ristrutturare o avviare "
                           "l'attività verifica con gli uffici {comune} (SUAP / Ufficio "
                           "Turismo) che l'affitto breve sia consentito per il tuo immobile; se non lo è, "
                           "le stime di questo report non sono realizzabili.")
FRASE_RISCHIO_MUTUO = ("Il secondo rischio è il mutuo: la rata assorbe circa il {pct}% del reddito operativo "
                       "stimato, quindi una stagione sotto le attese incide molto sul margine.")
FRASE_RISCHIO_DOTAZIONE = ("Il secondo rischio è la dotazione mancante che il mercato premia di più, {nome}: "
                           "gli annunci che ce l'hanno partono avvantaggiati, quindi il tuo deve compensare "
                           "con foto, servizio e prezzo.")
FRASE_RISCHIO_CONCORRENZA = ("Il secondo rischio è la concorrenza: con tanti gestori professionali, un "
                             "annuncio curato è la condizione per essere visibili.")

FRASE_PARTENZA_NUOVO = ("Parti dalle pratiche amministrative (pag. {pag_norm}) e dal piano dei primi 90 "
                        "giorni (pag. {pag_piano}).")
FRASE_PARTENZA_ATTIVO = "Parti dal confronto tra i risultati reali e le stime di questo report."
FRASE_OPPORTUNITA = "L'opportunità da non perdere: {leva}."

# Una frase per obiettivo dichiarato nel form (massimo due, in ordine).
FRASI_OBIETTIVO = {
    "massimizzare_guadagno": ("Per massimizzare il guadagno, il punto di partenza sono il piano di prezzi "
                              "mese per mese (pag. {pag_confronto}) e la leva indicata sopra."),
    "confronto_affitto_meglio": ("Nel confronto con l'affitto tradizionale (pag. {pag_confronto}) il B&B "
                                 "risulta più redditizio, ma richiede più gestione e tempo; i valori sono al "
                                 "lordo delle imposte."),
    "confronto_affitto_peggio": ("Nel confronto con l'affitto tradizionale (pag. {pag_confronto}) il B&B non "
                                 "risulta più redditizio: valuta se la maggiore flessibilità giustifica il "
                                 "maggior impegno."),
    "confronto_affitto_pari": ("Nel confronto con l'affitto tradizionale (pag. {pag_confronto}) i due "
                               "risultati sono in linea: conta più l'impegno che vuoi dedicare che il "
                               "profitto."),
    "primo_avvio": ("Per l'avvio, segui il piano dei primi 90 giorni (pag. {pag_piano}) partendo dalla "
                    "normativa (pag. {pag_norm})."),
    "ottimizzare_esistente": ("Per ottimizzare un'attività già avviata, confronta prezzi e occupazione reali "
                              "con i percentili di zona (pag. {pag_competitor}) e con la tabella delle "
                              "dotazioni (pag. {pag_dot})."),
    "valutazione_investimento": ("Per valutarlo come investimento, tieni presente che il valore come asset "
                                 "(pag. {pag_asset}) deriva dal reddito stimato e non sostituisce una "
                                 "perizia di compravendita."),
    "pianificazione_normativa": ("Per la normativa, parti da pag. {pag_norm} e verifica sempre le regole "
                                 "del Comune con gli uffici competenti."),
}


# ── Utilita' ─────────────────────────────────────────────────────────────────

def _num(v, default=0.0):
    """Numero da int/float/stringa ("2400", "€ 2.400", "1.234,5"); default se non leggibile."""
    if isinstance(v, bool):
        return default
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d,.\-]", "", str(v or ""))
    if not s or s in ("-", ".", ","):
        return default
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1 or re.fullmatch(r"-?\d{1,3}\.\d{3}", s):
        s = s.replace(".", "")     # 2.400 / 1.234.567 = migliaia
    try:
        return float(s)
    except ValueError:
        return default


def _eur(n):
    return f"€ {ds.migliaia(round(n))}"


def _canonica(nome):
    """Nome canonico di una dotazione (lista chiusa del report)."""
    t = re.sub(r"[^a-z]", "", str(nome or "").lower())
    mappa = {"wifi": "WiFi", "parcheggio": "Parcheggio", "ariacondizionata": "Aria condizionata",
             "lavatrice": "Lavatrice", "cucinaattrezzata": "Cucina attrezzata", "terrazzo": "Terrazzo",
             "giardino": "Giardino", "riscaldamento": "Riscaldamento", "ascensore": "Ascensore",
             "piscina": "Piscina"}
    return mappa.get(t)


def _elenco(voci):
    voci = list(voci)
    if len(voci) <= 1:
        return "".join(voci)
    return ", ".join(voci[:-1]) + " e " + voci[-1]


def elenco_mesi(indici):
    """[4,5,6,7,8] -> "da maggio a settembre"; [5,8] -> "giugno e settembre"; [8,9,11] -> "da settembre a ottobre e dicembre"."""
    idx = sorted(set(i for i in indici if isinstance(i, int) and 0 <= i < 12))
    if not idx:
        return ""
    gruppi, corrente = [], [idx[0]]
    for i in idx[1:]:
        if i == corrente[-1] + 1:
            corrente.append(i)
        else:
            gruppi.append(corrente)
            corrente = [i]
    gruppi.append(corrente)
    parti = []
    for g in gruppi:
        if len(g) >= 2:
            parti.append(f"da {MESI[g[0]]} a {MESI[g[-1]]}")
        else:
            parti.append(MESI[g[0]])
    return _elenco(parti)


def _composizione(frasi, limite):
    """frasi = [(priorita', testo)]. Se il testo supera il limite toglie le frasi
    di priorita' piu' bassa (numero piu' alto); quelle di priorita' 0 restano."""
    frasi = [(p, t.strip()) for p, t in frasi if t and t.strip()]
    def testo(fs):
        return " ".join(t for _p, t in fs)
    while len(testo(frasi)) > limite:
        candidate = [f for f in frasi if f[0] > 0]
        if not candidate:
            break
        peggiore = max(candidate, key=lambda f: f[0])
        # a parita' di priorita' si toglie l'ultima
        for i in range(len(frasi) - 1, -1, -1):
            if frasi[i] == peggiore:
                del frasi[i]
                break
    return testo(frasi)


def _banda(valore, perc):
    """Fascia di percentile in cui cade il valore, in parole. perc = {p25,p50,p75,p90}."""
    try:
        p25, p50, p75 = perc["p25"], perc["p50"], perc["p75"]
    except (KeyError, TypeError):
        return None
    p90 = perc.get("p90") or 0
    if not (p25 and p50 and p75):
        return None
    if valore < p25:
        return "sotto il 25° percentile"
    if valore < p50:
        return "tra il 25° e il 50° percentile"
    if valore < p75:
        return "tra il 50° e il 75° percentile"
    if p90 and valore < p90:
        return "tra il 75° e il 90° percentile"
    return "sopra il 90° percentile" if p90 else "sopra il 75° percentile"


# ── Fatti derivati ───────────────────────────────────────────────────────────

class _Fatti:
    """Fatti letti una volta sola da data. Niente rete, niente IA."""

    def __init__(self, data):
        self.d = data
        self.comune = str(data.get("comune") or "").strip()
        self.extra = {str(r[0]): r for r in (data.get("poi_extra") or [])
                      if isinstance(r, (list, tuple)) and len(r) >= 3}
        self.livello = qualita_immobile.livello_qualita(data.get("stato"))
        self.assenti = [c for c in (_canonica(x) for x in (data.get("dotazioni_assenti") or [])) if c]
        self.moltiplicatori = {}
        for r in (data.get("moltiplicatori_dotazioni") or []):
            if isinstance(r, (list, tuple)) and len(r) >= 4:
                nome = _canonica(r[0])
                if nome:
                    self.moltiplicatori[nome] = (str(r[1]), _num(r[3]))
        self.piano = str(data.get("piano") or "").strip().lower()
        self.bnb_attivo = _vero(data.get("situazione_bnb"))
        self.pm_previsto = _vero(data.get("property_manager"))
        self.pct_prof = data.get("pct_gestione_professionale")
        self.ambiente = self._ambiente()
        self.centralita = self._centralita()
        self.leve = self._leve()

    def _fascia(self, etichetta):
        riga = self.extra.get(etichetta)
        return ds._fascia_acqua(ds._info(riga)) if riga else ""

    def _centro_info(self):
        riga = self.extra.get("Centro del comune")
        return ds._info(riga) if riga else {}

    def _ambiente(self):
        d = self.d
        categoria = str(d.get("categoria") or "").strip().lower()
        sub = str(d.get("sottocategoria") or "").strip().lower()
        quota = d.get("_quota_m")
        try:
            quota = int(quota)
        except (TypeError, ValueError):
            quota = None
        if sub == "montano" or (quota is not None and quota >= 600):
            return "montagna"
        if categoria in ("capoluogo", "grande_citta"):
            return "citta"
        costa = _num(d.get("_costa_km"), 999)
        if sub == "costiero" or self._fascia("Spiaggia più vicina") in ("vicino", "non_lontano") or costa <= 5:
            return "mare"
        if sub == "lacuale" or self._fascia("Lago") in ("vicino", "non_lontano"):
            return "lago"
        if self.centralita_grezza() == "fuori":
            return "isolata"
        return "borgo"

    def centralita_grezza(self):
        info = self._centro_info()
        if not info:
            return None
        if info.get("modo") == "centro":
            return "nel_centro"
        mp, ma = ds._min_piedi(info), ds._min_auto(info)
        if mp is not None and mp <= 15:
            return "centrale"
        if mp is not None or (ma is not None and ma <= 10):
            return "breve_distanza"
        return "fuori"

    def _centralita(self):
        return self.centralita_grezza()

    def casello_vicino(self):
        riga = self.extra.get("Casello autostradale")
        if not riga:
            return False
        info = ds._info(riga)
        ma = ds._min_auto(info)
        return (ma is not None and ma <= 10) or (info.get("modo") == "aria" and (info.get("metri") or 0) <= 8000)

    def stazione_vicina(self):
        riga = self.extra.get("Stazione ferroviaria")
        if not riga:
            return False
        mp = ds._min_piedi(ds._info(riga))
        return mp is not None and mp <= 15

    def mesi_picco(self):
        """Mesi "forti" della curva del report: Alta + Peak (solo Peak se Alta+Peak
        coprono tutto l'anno)."""
        righe = [r for r in (self.d.get("occupazione") or []) if isinstance(r, (list, tuple)) and len(r) >= 4]
        if len(righe) != 12:
            return []
        etichette = [str(r[3]).strip().lower() for r in righe]
        for gruppo in (("alta", "peak"), ("peak",)):
            idx = [i for i, e in enumerate(etichette) if e in gruppo]
            if idx and len(idx) < 12:
                return idx
        return []

    def bande(self):
        """(banda prezzo, banda occupazione) o (None, None)."""
        d = self.d
        bp = _banda(_num(d.get("prezzo_notte_stimato")), d.get("percentili_prezzo"))
        bo = _banda(_num(d.get("occupazione_percent")), d.get("percentili_occupazione"))
        return bp, bo

    def _sotto_mediana(self, valore, perc):
        try:
            return 0 < valore < perc["p50"]
        except (KeyError, TypeError):
            return False

    def _leve(self):
        d = self.d
        leve = []
        base_mancanti = [a for a in self.assenti if a in ("WiFi", "Aria condizionata", "Riscaldamento",
                                                          "Lavatrice", "Cucina attrezzata")]
        if base_mancanti:
            leve.append(LEVE["dotazioni"].format(elenco=_elenco(m.lower() if m != "WiFi" else m
                                                                for m in base_mancanti)))
        if self._sotto_mediana(_num(d.get("prezzo_notte_stimato")), d.get("percentili_prezzo")):
            leve.append(LEVE["prezzo"])
        if self._sotto_mediana(_num(d.get("occupazione_percent")), d.get("percentili_occupazione")):
            leve.append(LEVE["visibilita"])
        leve.append(LEVE["esistente"].format(pag=PAG_SCENARI) if self.bnb_attivo else LEVE["recensioni"])
        leve.append(LEVE["dirette"])
        return leve[:3]


def _vero(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    return str(v or "").strip().lower() in ("si", "sì", "s", "yes", "y", "true", "vero", "1", "on", "attivo")


# ── Blocchi ──────────────────────────────────────────────────────────────────

def _posizione(f):
    d = f.d
    zona = str(d.get("zona") or "").strip()
    mesi = elenco_mesi(f.mesi_picco())
    clausola = f"; nelle stime i mesi più forti sono {mesi}" if mesi else ""
    ambiente = FRASI_AMBIENTE[f.ambiente].format(mesi=clausola)
    if zona and zona not in ("—", "-") and zona.lower() != f.comune.lower():
        ambiente = f"{f.comune}, zona {zona}. " + ambiente
    frasi = [(0, ambiente)]
    # L'ambiente "isolata" e' gia' la frase di centralita' (fuori dal centro).
    if f.centralita and f.ambiente != "isolata":
        frasi.append((1, FRASI_CENTRALITA[f.centralita]))
    cas, staz = f.casello_vicino(), f.stazione_vicina()
    if cas and staz:
        frasi.append((2, FRASI_COLLEGAMENTI["casello_e_stazione"]))
    elif cas:
        frasi.append((2, FRASI_COLLEGAMENTI["casello"]))
    elif staz:
        frasi.append((2, FRASI_COLLEGAMENTI["stazione"]))
    elif f.centralita == "fuori":
        frasi.append((2, FRASI_COLLEGAMENTI["nessuno"]))
    return _composizione(frasi, LIMITE_POSIZIONE)


def _anno_epoca(valore):
    """Anno indicativo dall'epoca: codici del form (anni70, pre1960, nuova) o testo
    ("Anni '70", "1985"). None se non riconosciuta."""
    t = re.sub(r"[^a-z0-9]", "", str(valore or "").lower())
    if not t:
        return None
    if t.startswith("pre") or "ante" in t:
        return 1950
    if "nuova" in t:
        return 2025
    m = re.search(r"(19|20)\d{2}", t)
    if m:
        return int(m.group(0))
    m = re.search(r"anni(\d{2,4})", t)
    if m:
        n = m.group(1)
        if len(n) == 4:
            return int(n)
        return 1900 + int(n) if int(n) >= 50 else 2000 + int(n)
    return None


def _condizione(f):
    d = f.d
    frasi = [(0, FRASI_STATO[f.livello])]

    anno = _anno_epoca(d.get("epoca"))
    epoca = str(d.get("scheda_epoca") or d.get("epoca") or "").strip()
    epoca_txt = epoca[:1].lower() + epoca[1:] if epoca.lower().startswith(("anni", "ante")) else epoca.lower()
    if anno is not None and anno < 1990:
        frasi.append((2, FRASE_EPOCA_VECCHIA.format(epoca=epoca_txt or "di vecchia costruzione")))
    elif anno is not None and anno >= 2010:
        frasi.append((3, FRASE_EPOCA_RECENTE.format(epoca=epoca_txt or "anni recenti")))

    tipo = str(d.get("intervento_tipo") or "").strip().lower()
    importo = _num(d.get("intervento_importo"))
    mesi = int(_num(d.get("intervento_mesi")))
    if tipo in FRASI_INTERVENTO and importo > 0:
        durata = f"{mesi} mesi" if mesi > 1 else "1 mese" if mesi == 1 else "più mesi"
        frasi.append((1, FRASI_INTERVENTO[tipo].format(importo=_eur(importo), mesi=durata, pag=PAG_INTERVENTO)))

    base_mancanti = [a for a in DOTAZIONI_BASE if a in f.assenti]
    if base_mancanti:
        elenco = _elenco(a if a == "WiFi" else a.lower() for a in base_mancanti)
        uno = len(base_mancanti) == 1
        frasi.append((1, FRASE_DOTAZIONI_BASE.format(elenco=elenco, verbo="manca" if uno else "mancano",
                                                     pronome="essa" if uno else "esse")))

    altre = [a for a in f.assenti if a in FRASI_DOTAZIONE_MANCANTE]
    # L'ascensore pesa solo se il piano non e' terra (il codice 1-3 non distingue il 1° dal 3°).
    if f.piano in ("terra", "piano terra"):
        altre = [a for a in altre if a != "Ascensore"]
    # Le piu' pesanti sul prezzo per prime (tabella di pag. 6); a parita', ordine fisso.
    altre.sort(key=lambda a: (-f.moltiplicatori.get(a, ("", 0))[1], list(FRASI_DOTAZIONE_MANCANTE).index(a)))
    for rango, nome in enumerate(altre[:2]):
        testo = FRASI_DOTAZIONE_MANCANTE[nome]
        if nome in f.moltiplicatori:
            testo += f" ({f.moltiplicatori[nome][0]} sul prezzo per notte, pag. {PAG_DOTAZIONI})"
        frasi.append((2 + rango, testo + "."))
    if not f.assenti:
        frasi.append((3, FRASE_TUTTE_DOTAZIONI))
    return _composizione(frasi, LIMITE_CONDIZIONE)


def _potenzialita(f):
    d = f.d
    frasi = []
    bp, bo = f.bande()
    if bp and bo:
        if bp == bo:
            frasi.append((1, FRASE_PERCENTILI_UGUALI.format(banda=bp, pag=PAG_COMPETITOR)))
        else:
            frasi.append((1, FRASE_PERCENTILI_DIVERSI.format(banda_p=bp, banda_o=bo, pag=PAG_COMPETITOR)))
    pct = f.pct_prof
    if isinstance(pct, (int, float)) and not isinstance(pct, bool):
        chiave = "alta" if pct >= 60 else "mista" if pct >= 30 else "bassa"
        frasi.append((2, FRASI_CONCORRENZA[chiave].format(pct=int(round(pct)))))
    frasi.append((0, FRASE_LEVE.format(elenco="; ".join(f"({i}) {l}" for i, l in enumerate(f.leve, 1)))))
    frasi.append((0, FRASE_SCENARIO_OTTIMISTICO.format(pag=PAG_SCENARI)))
    return _composizione(frasi, LIMITE_POTENZIALITA)


def _quota_mutuo(d):
    rata = _num(d.get("rata_mutuo_mensile")) * 12
    if rata <= 0:
        return None
    reddito = _num(d.get("profitto_netto")) + rata
    return rata / reddito if reddito > 0 else None


def _codici_obiettivo(d):
    codici = []
    for o in (d.get("obiettivi_selezionati") or []):
        if isinstance(o, (list, tuple)) and o:
            codici.append(str(o[0]).strip())
    return codici


def _confronto_affitto(d):
    """"meglio" | "peggio" | "pari" | None: profitto B&B contro la fascia dell'affitto tradizionale."""
    profitto = _num(d.get("profitto_netto"), None) if d.get("profitto_netto") is not None else None
    lo = _num(d.get("affitto_profitto_min"), None) if d.get("affitto_profitto_min") is not None else None
    hi = _num(d.get("affitto_profitto_max"), None) if d.get("affitto_profitto_max") is not None else None
    if lo is None or hi is None:
        v = d.get("affitto_profitto")
        lo = hi = _num(v, None) if v is not None else None
    if profitto is None or lo is None or hi is None:
        return None
    if profitto > hi:
        return "meglio"
    if profitto < lo:
        return "peggio"
    return "pari"


def _raccomandazione(f):
    d = f.d
    frasi = []

    # Gestione
    cambi = _num(d.get("cambi_anno"))
    camere = _num(re.sub(r"\D", "", str(d.get("camere") or "")), 0)
    if f.pm_previsto:
        ricavi = _num(d.get("ricavo_lordo"))
        bassa, alta = int(_num(d.get("pm_perc_bassa"), 15)), int(_num(d.get("pm_perc_alta"), 20))
        if ricavi > 0:
            frasi.append((0, FRASE_GESTIONE_PM.format(
                bassa=bassa, alta=alta, eur_bassa=_eur(ricavi * bassa / 100), eur_alta=_eur(ricavi * alta / 100),
                pag=PAG_INTERVENTO)))
    elif cambi > 100 or camere >= 3:
        if cambi > 0:
            frasi.append((0, FRASE_GESTIONE_PM_CONSIGLIATO.format(cambi=int(round(cambi)))))
    elif cambi > 0:
        frasi.append((0, FRASE_GESTIONE_DIRETTA.format(cambi=int(round(cambi)))))
    else:
        frasi.append((0, FRASE_GESTIONE_DIRETTA_SENZA_CAMBI))
    if f.bnb_attivo:
        frasi.append((1, FRASE_GIA_ATTIVO))

    # Rischi: normativa sempre, poi il primo che scatta
    comune = f"del Comune di {f.comune}" if f.comune else "del tuo Comune"
    frasi.append((0, FRASE_RISCHIO_NORMATIVO.format(comune=comune)))
    quota = _quota_mutuo(d)
    pesanti = sorted(((nome, f.moltiplicatori[nome][0]) for nome in f.moltiplicatori
                      if _num(f.moltiplicatori[nome][0]) >= 5),
                     key=lambda x: -_num(x[1]))
    if quota is not None and quota > 0.5:
        frasi.append((1, FRASE_RISCHIO_MUTUO.format(pct=int(round(quota * 100)))))
    elif pesanti:
        frasi.append((2, FRASE_RISCHIO_DOTAZIONE.format(nome=pesanti[0][0].lower())))
    elif isinstance(f.pct_prof, (int, float)) and not isinstance(f.pct_prof, bool) and f.pct_prof >= 60:
        frasi.append((2, FRASE_RISCHIO_CONCORRENZA))

    # Da dove partire e opportunita'
    if f.bnb_attivo:
        frasi.append((1, FRASE_PARTENZA_ATTIVO))
    else:
        frasi.append((1, FRASE_PARTENZA_NUOVO.format(pag_norm=PAG_NORMATIVA, pag_piano=PAG_PIANO)))
    if f.leve:
        frasi.append((2, FRASE_OPPORTUNITA.format(leva=f.leve[0])))

    # Obiettivi dichiarati (massimo due)
    pag = dict(pag_confronto=PAG_CONFRONTO, pag_piano=PAG_PIANO, pag_norm=PAG_NORMATIVA,
               pag_competitor=PAG_COMPETITOR, pag_dot=PAG_DOTAZIONI, pag_asset=PAG_ASSET)
    for rango, codice in enumerate(_codici_obiettivo(d)[:2]):
        if codice == "confronto_affitto":
            esito = _confronto_affitto(d)
            if not esito:
                continue
            codice = f"confronto_affitto_{esito}"
        if codice in FRASI_OBIETTIVO:
            frasi.append((3 + rango, FRASI_OBIETTIVO[codice].format(**pag)))
    return _composizione(frasi, LIMITE_RACCOMANDAZIONE)


# ── API ──────────────────────────────────────────────────────────────────────

def genera_analisi(data):
    """Le quattro analisi di pagina 14, scritte dal codice. Stesse chiavi che
    strategico.page10 legge da data."""
    f = _Fatti(data)
    return {
        "analisi_posizione": _posizione(f),
        "analisi_condizione": _condizione(f),
        "analisi_potenzialita": _potenzialita(f),
        "analisi_raccomandazione": _raccomandazione(f),
    }

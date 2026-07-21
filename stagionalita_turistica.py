# ── Stagionalità turistica bimodale — sostituisce la curva inventata dall'AI ──
# per i comuni con vocazione turistica sia invernale (sci) che estiva.
#
# Origine del problema (Sessione 60): quando AirROI fornisce solo il livello
# annuo (adr/occupazione) e non la distribuzione_mensile reale, il codice in
# app.py riscala la curva stagionale generata dall'AI con un moltiplicatore
# costante — la FORMA resta quella inventata, tipicamente un unico picco
# estivo. Per una meta come Pescasseroli (sci Dic-Mar + escursionismo Lug-Ago)
# questo produce mesi invernali artificialmente bassi (30% invece di un
# realistico 70-80%).
#
# Fonte dati: nessun archivio nazionale aperto offre oggi il dettaglio
# mensile per comune con copertura completa e affidabile (verificato:
# ISTAT pubblica il dettaglio mensile solo a livello provinciale; il
# portale open data Abruzzo specifico non è al momento consultabile).
# Questa è quindi una curva di forma calibrata su pattern reali noti di
# stazioni turistiche invernali/estive italiane (settimana bianca,
# capodanno, ponte di carnevale, alta stagione estiva), non un dato
# puntuale per singolo comune — corregge la FORMA, il LIVELLO resta
# sempre quello reale di AirROI quando disponibile.
#
# Aggiornamento futuro: sostituire/integrare con dati reali laddove
# disponibili (Puglia e Sardegna hanno open data comunali funzionanti,
# vedi note in RU_Libro_Sessioni — fase 2).

# Indice 0=Gennaio ... 11=Dicembre. Valori relativi, non percentuali dirette:
# vengono normalizzati sulla media (stesso meccanismo già usato per
# distribuzione_mensile AirROI in _applica_stagionalita_airroi).
CURVA_BIMODALE_MONTANO_INVERNALE = [
    70,  # Gen — vacanze di Natale/Epifania, sci
    75,  # Feb — settimana bianca, carnevale
    55,  # Mar — coda stagione sci, weekend
    30,  # Apr — bassa stagione (tra sci e estate)
    28,  # Mag — bassa stagione
    40,  # Giu — inizio stagione estiva
    65,  # Lug — escursionismo, montagna estiva
    80,  # Ago — picco assoluto estivo
    42,  # Set — coda estate
    30,  # Ott — bassa stagione
    25,  # Nov — bassa stagione, pre-sci
    68,  # Dic — Natale, Capodanno, apertura stagione sci
]

# Curva di default attuale per "montano" a vocazione solo estiva — invariata,
# nessun rischio per i comuni di montagna senza turismo invernale rilevante.
# (Nessuna sostituzione: se il comune non è in COMUNI_VOCAZIONE_INVERNALE,
# resta la curva generata dall'AI come oggi.)

# Prima infarinatura di comuni italiani a vocazione turistica bimodale
# (sci + estate). Elenco non esaustivo (in Italia esistono oltre 280
# comprensori sciistici): copre i principali comprensori e le zone a
# maggior traffico. Da ampliare progressivamente.
COMUNI_VOCAZIONE_INVERNALE = {
    # Abruzzo — Alto Sangro e Parco Nazionale
    "pescasseroli", "roccaraso", "rivisondoli", "ovindoli", "opi",
    "scanno", "campo felice", "pescocostanzo", "rocca di mezzo",
    "barrea", "villetta barrea",
    # Trentino-Alto Adige
    "madonna di campiglio", "pinzolo", "folgarida", "marilleva",
    "canazei", "arabba", "livigno", "san martino di castrozza",
    "moena", "val gardena", "ortisei", "selva di val gardena",
    "corvara", "la villa", "vigo di fassa", "predazzo",
    # Veneto / Dolomiti
    "cortina d'ampezzo", "cortina d ampezzo", "auronzo di cadore",
    "san vito di cadore",
    # Valle d'Aosta
    "courmayeur", "cervinia", "breuil-cervinia", "valtournenche",
    "la thuile", "pila", "gressoney-la-trinite", "champoluc", "ayas",
    # Piemonte
    "sestriere", "sauze d'oulx", "sauze d oulx", "claviere",
    "cesana torinese", "san sicario", "bardonecchia", "limone piemonte",
    "macugnaga",
    # Lombardia
    "bormio", "santa caterina valfurva", "livigno", "madesimo",
    "aprica", "ponte di legno", "temu",
    # Emilia-Romagna / Toscana Appennino
    "abetone", "cutigliano", "sestola", "fanano", "monghidoro",
    # Lazio
    "terminillo", "campo felice",
    # Abruzzo — Gran Sasso
    "campo imperatore", "assergi",
    # Molise
    "campitello matese", "san massimo",
    # Calabria / Sicilia
    "camigliatello silano", "gambarie", "piano provenzana", "linguaglossa",
}


def comune_ha_vocazione_invernale(nome_comune):
    """True se il comune è nella lista di quelli a turismo sia invernale che estivo."""
    if not nome_comune:
        return False
    return nome_comune.strip().lower() in COMUNI_VOCAZIONE_INVERNALE


def curva_stagionale_bimodale(occ_annuale, adr_annuale):
    """
    Ricostruisce le 12 righe [mese, occupazione%, prezzo] usando la curva
    bimodale invece della curva AI, mantenendo la MEDIA reale AirROI
    (occ_annuale/adr_annuale). Ritorna righe compatibili col formato usato
    in app.py: [nome_mese, occupazione, prezzo].
    """
    return applica_curva(occ_annuale, adr_annuale, CURVA_BIMODALE_MONTANO_INVERNALE)


# ── Estensione Sessione 61 — curve di forma per TUTTE le categorie ───────────
# Obiettivo esplicito di Salvatore: l'AI non deve più inventare la FORMA
# stagionale in nessun caso in cui esista una categoria territoriale nota.
# L'AI resta in gioco solo per il LIVELLO annuo quando AirROI non ha mercato
# osservato (comportamento già esistente e invariato) — mai più per la forma
# dei 12 mesi.
#
# Anche queste curve, come quella bimodale sopra, sono modelli di forma
# calibrati su pattern noti di turismo italiano per categoria (mare, lago,
# montagna estiva, città), non dati puntuali per singolo comune. Sono
# comunque sempre preferibili all'invenzione libera dell'AI: stessa forma
# dichiarata e verificabile per tutti i comuni della stessa categoria,
# invece di una forma diversa e arbitraria ad ogni generazione.

CURVA_COSTIERO = [15, 15, 20, 35, 45, 65, 90, 95, 55, 30, 15, 20]
CURVA_LACUALE = [20, 22, 30, 45, 55, 65, 80, 85, 60, 42, 25, 28]
CURVA_MONTANO_ESTIVO = [20, 20, 25, 30, 38, 50, 75, 85, 50, 32, 20, 25]
CURVA_CITTA = [45, 48, 55, 65, 68, 65, 55, 40, 65, 68, 52, 58]
CURVA_GENERICA = [25, 25, 30, 38, 42, 48, 60, 62, 45, 35, 25, 30]


def smorza_peso_prezzo(peso_occ, smorzamento_basso=0.5, smorzamento_alto=0.65):
    """Attenua l'ampiezza di un peso stagionale prima di applicarlo al prezzo.
    Sessione 66: prima i mesi SOPRA media (peso_occ >= 1) non avevano NESSUNO
    smorzamento — la curva saliva piena, producendo picchi di prezzo
    eccessivi (es. curva costiero piena: +116% a luglio sul prezzo medio,
    quando il mercato reale è più vicino a un +45-50%). Ora anche il lato
    sopra media viene attenuato (smorzamento_alto), in modo simmetrico al
    meccanismo già esistente sotto media (smorzamento_basso) — un picco
    resta un picco, ma non raddoppia il prezzo medio. Segnalato da
    Salvatore, Sessione 66."""
    if peso_occ >= 1:
        return 1 + (peso_occ - 1) * smorzamento_alto
    return 1 + (peso_occ - 1) * smorzamento_basso


def mese_corrente_idx():
    import datetime
    return datetime.date.today().month - 1


def prezzo_mese_corrente(prezzo_medio, sottocategoria, categoria, comune,
                          distribuzione_mensile=None, mese_idx=None):
    """Stima il prezzo/notte per il MESE CORRENTE (non la media annua),
    partendo dal prezzo medio grezzo di AirROI. Usa la distribuzione
    mensile REALE di AirROI quando disponibile (dato di mercato vero),
    altrimenti la curva di forma per categoria territoriale, con lo stesso
    smorzamento simmetrico usato in applica_curva.

    Introdotta in Sessione 66 per allineare il Quick Report al Base: prima
    il Quick mostrava sempre il prezzo medio annuo piatto, mentre il Base
    (per lo stesso identico immobile, nello stesso giorno) mostrava nella
    tabella mensile il prezzo del mese corrente — spesso molto diverso in
    piena stagione, creando uno scostamento ingiustificato tra i due
    prodotti per lo stesso "adesso"."""
    if mese_idx is None:
        mese_idx = mese_corrente_idx()
    if distribuzione_mensile and len(distribuzione_mensile) == 12 and prezzo_medio:
        media = sum(distribuzione_mensile) / 12
        if media > 0:
            peso = distribuzione_mensile[mese_idx] / media
            peso_smorzato = smorza_peso_prezzo(peso)
            return max(1, round(prezzo_medio * peso_smorzato)), "airroi_reale"
    curva, fonte = ottieni_curva_stagionale(sottocategoria, categoria, comune)
    media = sum(curva) / 12
    peso_occ = curva[mese_idx] / media
    peso_prezzo = smorza_peso_prezzo(peso_occ)
    prezzo = max(1, round(prezzo_medio * peso_prezzo)) if prezzo_medio else None
    return prezzo, fonte


def applica_curva(occ_annuale, adr_annuale, curva, smorzamento_prezzo=0.5, tetto_massimo=85):
    """Versione generica: ricostruisce le 12 righe usando una qualsiasi
    curva di forma a 12 valori relativi, mantenendo la media reale.
    Ogni riga ha 4 campi [mese, occupazione, prezzo, stagione] — il PDF
    (app.py, stage_color) si aspetta sempre il 4° campo per colorare
    tabella e grafico; ometterlo causa un IndexError e un 500 in produzione
    (bug reale, Sessione 63/64, verificato dai log Render).

    tetto_massimo (Sessione 66): tetto per i MESI di picco, non solo per il
    livello annuo — prima era fisso a 100, per cui anche comuni senza vera
    vocazione turistica potevano mostrare mesi al 100% pieno. Va sempre
    passato lo stesso tetto calcolato con tetto_occupazione(fonte) per
    coerenza col livello annuo.

    Il prezzo usa una versione dell'ampiezza della curva SMORZATA SOLO SUL
    LATO BASSO (smorzamento_prezzo, default 0.5): i mesi sopra media restano
    identici alla curva piena (spesso coincidono con i 3 mesi "affidabili"
    confermati dal mercato reale AirROI — non vanno mai abbassati). Solo i
    mesi sotto media vengono attenuati verso l'alto: nella realtà un host in
    bassa stagione riduce le prenotazioni accettate più di quanto riduca la
    tariffa. Segnalato da Salvatore, Sessione 65: prima lo smorzamento era
    simmetrico e abbassava anche i picchi confermati — corretto qui."""
    mesi = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
            "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]
    media = sum(curva) / 12

    ordine = sorted(range(12), key=lambda i: curva[i], reverse=True)
    etichetta = [""] * 12
    for rank, i in enumerate(ordine):
        if rank < 2:
            etichetta[i] = "Peak"
        elif rank < 6:
            etichetta[i] = "Alta"
        elif rank < 9:
            etichetta[i] = "Media"
        else:
            etichetta[i] = "Bassa"

    righe = []
    for i, nome_mese in enumerate(mesi):
        peso_occ = curva[i] / media
        peso_prezzo = smorza_peso_prezzo(peso_occ, smorzamento_basso=smorzamento_prezzo)
        occ_mese = max(5, min(tetto_massimo, round(occ_annuale * peso_occ))) if occ_annuale else None
        prezzo_mese = max(1, round(adr_annuale * peso_prezzo)) if adr_annuale else None
        righe.append([nome_mese, occ_mese, prezzo_mese, etichetta[i]])
    return righe


# ── Correttivo occupazione per categoria — Sessione 65 ───────────────────────
# AirROI sottostima il livello annuo di occupazione (non solo la forma), ma
# in misura diversa a seconda della vocazione turistica del comune. Fonti:
# - Città (AirDNA): Roma 84%, Bologna 63%, Firenze 61%, Verona 66%,
#   Milano 57-58% -> media ~66% reale vs ~45% tipico grezzo AirROI.
# - Montano invernale: nessun dato AirDNA diretto, ma evidenza qualitativa
#   forte (Alto Sangro/Roccaraso "tutto esaurito" gen-mar 2025, +60%
#   presenze a gennaio) -> correttivo aggressivo confermato.
# - Costiero: Rimini 49%, Taormina 61% -> media ~55%.
# - Lacuale: Como 57% (singolo punto dato, insufficiente per differenziare).
# - Montano estivo / generico: Loiano (Appennino, paese non turistico) 45%,
#   Santarcangelo di Romagna 49%, Sassari 52% -> praticamente allineati al
#   dato grezzo AirROI. Qui un correttivo forte sarebbe im-preciso nella
#   direzione opposta (troppo ottimistico per un paese senza vocazione
#   turistica riconosciuta) -> correttivo lieve.
CORRETTIVO_OCCUPAZIONE_PER_CATEGORIA = {
    "citta": 1.45,
    "montano_invernale": 1.40,
    "costiero": 1.35,
    "lacuale": 1.35,
    "montano_estivo": 1.10,
    "generico": 1.10,
}

# ── Tetto massimo di occupazione — Sessione 66 ──────────────────────────────
# Il correttivo sopra (necessario perché AirROI sottostima) può, su comuni
# minori con buoni servizi ma senza vera vocazione turistica, produrre un
# livello annuo o dei picchi mensili irrealistici (100% pieno tutto l'anno
# non esiste in nessun mercato reale). Segnalato da Salvatore su Quarto (NA,
# comune minore costiero non distante da Napoli): con tetto unico all'85%
# il LIVELLO annuo restava plausibile, ma i MESI di picco (applica_curva)
# arrivavano comunque al 100% pieno perché quella funzione aveva un tetto
# proprio hardcoded a 100, indipendente da questo. Fix: un tetto per
# categoria, applicato SIA al livello annuo SIA ai picchi mensili — il 100%
# non deve mai comparire in nessun mese per nessun comune.
# - 98%: grandi città/capoluoghi e zone a vocazione turistica forte
#   (montano invernale) — la domanda vera può essere quasi sempre piena.
# - 95%: altre zone turistiche riconosciute (costiero, lacuale) ma senza
#   la stessa scala di un capoluogo o di una stazione sciistica maggiore.
# - 85%: comuni minori senza vocazione turistica specifica (montano estivo
#   generico, residenziale) — nessun mercato reale sta pieno quasi tutto
#   l'anno senza un motivo turistico forte.
TETTO_OCCUPAZIONE_PER_CATEGORIA = {
    "citta": 98,
    "montano_invernale": 98,
    "costiero": 95,
    "lacuale": 95,
    "montano_estivo": 85,
    "generico": 85,
}
OCCUPAZIONE_TETTO_MASSIMO = 85  # fallback per fonti non mappate, mantenuto per compatibilità


def tetto_occupazione(fonte):
    """Ritorna il tetto massimo di occupazione (%) per la fonte/categoria
    indicata (stessa etichetta di ottieni_curva_stagionale/correttivo_occupazione).
    Nessuna categoria arriva mai al 100%."""
    return TETTO_OCCUPAZIONE_PER_CATEGORIA.get(fonte, OCCUPAZIONE_TETTO_MASSIMO)


def correttivo_occupazione(sottocategoria, categoria, comune):
    """
    Ritorna (moltiplicatore, etichetta_fonte) da applicare al livello annuo
    di occupazione fornito da AirROI, secondo la stessa classificazione già
    usata per la curva stagionale (riuso di ottieni_curva_stagionale per
    coerenza fra le due logiche)."""
    _curva_ignorata, fonte = ottieni_curva_stagionale(sottocategoria, categoria, comune)
    return CORRETTIVO_OCCUPAZIONE_PER_CATEGORIA.get(fonte, 1.35), fonte


def ottieni_curva_stagionale(sottocategoria, categoria, comune):
    """
    Sceglie la curva di forma corretta in base a sottocategoria territoriale
    (costiero/lacuale/montano/None), categoria amministrativa
    (capoluogo/grande_citta/comune_minore) e vocazione invernale del comune.
    Ritorna (curva, etichetta_fonte) — l'etichetta va in data['fonte_stagionalita']
    per tracciabilità, stesso pattern già usato per fonte_prezzo/fonte_competitor.
    """
    sub = (sottocategoria or "").strip().lower()
    cat = (categoria or "").strip().lower()

    if sub == "montano":
        if comune_ha_vocazione_invernale(comune):
            return CURVA_BIMODALE_MONTANO_INVERNALE, "montano_invernale"
        return CURVA_MONTANO_ESTIVO, "montano_estivo"
    if sub == "costiero":
        return CURVA_COSTIERO, "costiero"
    if sub == "lacuale":
        return CURVA_LACUALE, "lacuale"
    if cat in ("capoluogo", "grande_citta"):
        return CURVA_CITTA, "citta"
    return CURVA_GENERICA, "generico"

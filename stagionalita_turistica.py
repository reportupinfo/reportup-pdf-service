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


def applica_curva(occ_annuale, adr_annuale, curva):
    """Versione generica: ricostruisce le 12 righe usando una qualsiasi
    curva di forma a 12 valori relativi, mantenendo la media reale.
    Ogni riga ha 4 campi [mese, occupazione, prezzo, stagione] — il PDF
    (app.py, stage_color) si aspetta sempre il 4° campo per colorare
    tabella e grafico; ometterlo causa un IndexError e un 500 in produzione
    (bug reale, Sessione 63/64, verificato dai log Render)."""
    mesi = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
            "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]
    media = sum(curva) / 12

    # Etichetta di stagione per rango relativo all'interno della curva stessa
    # (non per soglia assoluta di occupazione, perché il livello annuo può
    # essere basso o alto a seconda del comune): i 2 mesi più forti sono
    # "Peak", i successivi 4 "Alta", i successivi 3 "Media", il resto "Bassa"
    # — stessa distribuzione 2/4/3/3 usata storicamente nei report AI.
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
        peso = curva[i] / media
        occ_mese = max(5, min(100, round(occ_annuale * peso))) if occ_annuale else None
        prezzo_mese = max(1, round(adr_annuale * peso)) if adr_annuale else None
        righe.append([nome_mese, occ_mese, prezzo_mese, etichetta[i]])
    return righe


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

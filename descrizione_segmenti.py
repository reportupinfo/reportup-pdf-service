# ── Descrizione standard: frasi fisse scelte da condizioni oggettive ─────────
#
# Decisione di Salvatore (28/10/2026): nella descrizione dell'immobile niente
# IA e niente frasi d'atmosfera non verificabili ("lontano dai ritmi frenetici
# delle grandi citta'"). Solo i dati oggettivi (immobile dichiarato dal cliente,
# comune ISTAT, distanze reali di Google) legati da piccoli segmenti di frase
# standard, scelti in base a fatti misurati: se la spiaggia e' a 6 minuti a
# piedi si scrive "A pochi minuti a piedi dal mare", se e' a 8 km "Il mare e'
# raggiungibile in auto". Stesso codice per Base e Strategico.
#
# Ogni funzione ritorna una frase o "" (condizione non verificata: nessuna
# frase, mai un ripiego inventato). Modulo puro: nessuna rete, nessun Flask.
#
# Le righe POI "extra" hanno la forma
#   [etichetta, distanza_testo, nome, impatto, info]
# con info = {"modo": "piedi"|"auto"|"aria"|"centro", "metri": int, "minuti": int|None}
# (vedi territorio_poi.distanza_info).

import re


# ── Utilita' ─────────────────────────────────────────────────────────────────

def _info(riga):
    try:
        i = riga[4]
        return i if isinstance(i, dict) else {}
    except (IndexError, TypeError):
        return {}


def _campi(riga):
    """(distanza_testo, nome) di una riga extra."""
    return str(riga[1]).strip(), str(riga[2]).strip()


def _min_piedi(info):
    return info.get("minuti") if info.get("modo") == "piedi" else None


def _min_auto(info):
    return info.get("minuti") if info.get("modo") == "auto" else None


def migliaia(n):
    """11232 -> "11.232"."""
    return f"{int(n):,}".replace(",", ".")


def _senza_prefisso(nome, prefissi):
    return re.sub(prefissi, "", nome, count=1, flags=re.IGNORECASE).strip() or nome


# ── Immobile e dati dichiarati ───────────────────────────────────────────────

def frase_immobile(tipologia, superficie, indirizzo, zona, camere_frase, bagni_frase, posti_letto_frase, situata):
    """"Bilocale di 60 m² situato in Via X, zona Y, con 1 camera, 1 bagno e 4 posti letto." """
    tip = str(tipologia or "Immobile").strip()
    tip = tip[:1].upper() + tip[1:]
    zona_txt = f", zona {zona}" if zona else ""
    return f"{tip} di {superficie} {situata} in {indirizzo}{zona_txt}, con {camere_frase}, {bagni_frase} e {posti_letto_frase}."


def frase_dotazioni(dotazioni_frase):
    return f"Dotazioni dichiarate: {dotazioni_frase}." if dotazioni_frase else ""



# ── Comune (dati ISTAT) ──────────────────────────────────────────────────────

def frase_comune(record, categoria):
    """Fatti dal CSV ISTAT: provincia, regione, abitanti. record = riga di
    comuni.csv o None. Per le grandi citta' non si afferma "capoluogo": il CSV
    le classifica a parte e il dato non c'e'."""
    if not record:
        return ""
    nome, prov, reg = record.get("comune"), record.get("provincia"), record.get("regione")
    try:
        ab = int(float(record.get("popolazione")))
    except (TypeError, ValueError):
        return ""
    if not nome or ab <= 0:
        return ""
    if categoria == "capoluogo":
        return f"{nome} è capoluogo di provincia ({reg}), con {migliaia(ab)} abitanti (dati ISTAT)."
    if categoria == "grande_citta":
        return f"{nome} è una città di {migliaia(ab)} abitanti ({reg}, dati ISTAT)."
    return f"{nome} è un comune della provincia di {prov} ({reg}), con {migliaia(ab)} abitanti (dati ISTAT)."


# ── Posizione: centro ────────────────────────────────────────────────────────

def frase_centro(riga):
    """Posizione rispetto al centro: centrale (in centro o fino a 15 min a
    piedi), a breve distanza (fino a 25 min a piedi o 10 in auto), altrimenti
    fuori dal centro. Le soglie sono sui minuti reali di Google."""
    if not riga:
        return ""
    dist, nome = _campi(riga)
    info = _info(riga)
    if info.get("modo") == "centro":
        return f"L'immobile si trova nel centro di {nome}."
    mp, ma = _min_piedi(info), _min_auto(info)
    if mp is not None and mp <= 15:
        return f"Posizione centrale: il centro di {nome} dista {dist}."
    if mp is not None or (ma is not None and ma <= 10):
        return f"A breve distanza dal centro: il centro di {nome} dista {dist}."
    if info:
        return f"Fuori dal centro: il centro di {nome} dista {dist}."
    return f"Il centro di {nome} dista {dist}."


# ── Posizione: mare, lago, montagna ──────────────────────────────────────────

def _fascia_acqua(info):
    """"vicino" (fino a 10 min a piedi o 500 m), "non_lontano" (fino a 25 min a
    piedi, 10 min in auto o 2 km in linea d'aria), "auto" (oltre)."""
    mp, ma = _min_piedi(info), _min_auto(info)
    if mp is not None:
        return "vicino" if mp <= 10 else "non_lontano"
    if ma is not None:
        return "non_lontano" if ma <= 10 else "auto"
    if info.get("modo") == "aria":
        m = info.get("metri") or 0
        return "vicino" if m <= 500 else "non_lontano" if m <= 2000 else "auto"
    return ""


def frase_mare(riga):
    if not riga:
        return ""
    dist, nome = _campi(riga)
    f = _fascia_acqua(_info(riga))
    if f == "vicino":
        return f"A pochi minuti a piedi dal mare: la spiaggia più vicina, {nome}, dista {dist}."
    if f == "non_lontano":
        return f"Non lontano dal mare: la spiaggia più vicina, {nome}, dista {dist}."
    if f == "auto":
        return f"Il mare è raggiungibile in auto: la spiaggia più vicina, {nome}, dista {dist}."
    return f"La spiaggia più vicina, {nome}, dista {dist}."


def frase_spiaggia_principale(riga):
    if not riga:
        return ""
    dist, nome = _campi(riga)
    return f"Tra le spiagge più frequentate della zona, {nome}, a {dist}."


def frase_costa(costa_km):
    """Solo se Google non ha dato nessuna spiaggia ma la costa e' vicina (dato
    offline Natural Earth, distanza indicativa)."""
    try:
        km = float(costa_km)
    except (TypeError, ValueError):
        return ""
    if km > 5:
        return ""
    txt = "meno di 1 km" if km < 1 else f"circa {km:.1f} km".replace(".", ",") if km < 10 else f"circa {int(round(km))} km"
    return f"L'immobile si trova a {txt} dalla costa."


def frase_lago(riga):
    if not riga:
        return ""
    dist, nome = _campi(riga)
    f = _fascia_acqua(_info(riga))
    if f == "vicino":
        return f"A pochi minuti a piedi dal lago: {nome} dista {dist}."
    if f == "non_lontano":
        return f"Non lontano dal lago: {nome} dista {dist}."
    if f == "auto":
        return f"Il lago è raggiungibile in auto: {nome} dista {dist}."
    return f"{nome} dista {dist}."


def frase_quota(quota_m, soglia=500):
    """"L'immobile si trova a circa 1.100 m di quota." solo dalla soglia in su
    (la stessa con cui il report cerca la montagna di riferimento)."""
    try:
        q = int(quota_m)
    except (TypeError, ValueError):
        return ""
    return f"L'immobile si trova a circa {migliaia(q)} m di quota." if q >= soglia else ""


def frase_montagna(riga):
    if not riga:
        return ""
    dist, nome = _campi(riga)
    return f"Tra le cime più note dei dintorni, {nome}, a {dist}."


# ── Collegamenti ─────────────────────────────────────────────────────────────

def frase_casello(riga):
    if not riga:
        return ""
    dist, nome = _campi(riga)
    nome_c = _senza_prefisso(nome, r"^casello(\s+autostradale)?(\s+(di|del|della|dei))?\s+")
    info = _info(riga)
    ma = _min_auto(info)
    vicino = (ma is not None and ma <= 10) or (info.get("modo") == "aria" and (info.get("metri") or 0) <= 8000)
    if vicino:
        return f"Ben collegato alla rete autostradale: il casello di {nome_c} dista {dist}."
    return f"Il casello autostradale più vicino, quello di {nome_c}, dista {dist}."


def frase_stazione(riga):
    if not riga:
        return ""
    dist, nome = _campi(riga)
    nome_s = _senza_prefisso(nome.split(",")[-1].strip(), r"^stazione(\s+ferroviaria)?(\s+(di|del|della|dei))?\s+")
    mp = _min_piedi(_info(riga))
    if mp is not None and mp <= 15:
        return f"Stazione ferroviaria raggiungibile a piedi: quella di {nome_s} dista {dist}."
    return f"La stazione ferroviaria più vicina, quella di {nome_s}, dista {dist}."


# ── Punti di interesse fissi (trasporto, elemento caratteristico, servizi) ────

def frase_poi_fisso(etichetta, nome, distanza):
    """"Trasporto pubblico: Fermata X, a 8 min a piedi." """
    nome = str(nome or "").strip()
    d = str(distanza or "").strip()
    if not nome or nome == "—":
        return ""
    if d.lower().startswith("in loco"):
        return f"{etichetta}: {nome}, in loco."
    if d and d[0].isdigit():
        return f"{etichetta}: {nome}, a {d}."
    return f"{etichetta}: {nome}." if not d or d == "—" else f"{etichetta}: {nome} ({d})."


# ── Capienza ─────────────────────────────────────────────────────────────────

def target_capienza(posti_letto):
    """coppie / famiglie e piccoli gruppi / famiglie numerose e gruppi di amici."""
    try:
        n = int(str(posti_letto).rstrip("+").strip())
    except (ValueError, TypeError):
        n = 4
    if n <= 2:
        return "coppie"
    if n <= 4:
        return "famiglie e piccoli gruppi"
    return "famiglie numerose e gruppi di amici"


def frase_capienza(posti_letto_frase, target):
    return f"Capienza: {posti_letto_frase}, adatta a {target}."

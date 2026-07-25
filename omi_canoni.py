# ── Canoni di locazione OMI reali — sostituisce l'invenzione AI ─────────────
# Sessione 62. Dato reale: Agenzia delle Entrate, Osservatorio del Mercato
# Immobiliare, "Forniture dati OMI" — export nazionale richiesto da Salvatore
# tramite area riservata SPID, Semestre 2025/2 (elaborazione 13-mar-2026).
#
# Fonte: Agenzia Entrate - OMI (citazione obbligatoria per i dati OMI).
#
# Copertura: 7.376 comuni su ~7.904 (93%). Per i comuni assenti nel dataset
# OMI (di norma centri molto piccoli senza rilevazione) il chiamante deve
# usare il fallback esistente (stima AI, dichiarata come tale — mai più
# presentata come OMI quando non lo è davvero).
#
# Limite onesto: quando un comune ha più zone OMI (es. Pescasseroli: B1
# centro + R1 periferia), qui viene usata la MEDIA tra le zone, non la zona
# esatta dell'indirizzo — i perimetri di zona (.kml) permetterebbero il
# calcolo preciso ma non sono ancora integrati (7.889 file, uno per comune,
# operazione rimandata: vedi checklist). La media resta comunque un dato
# reale e aggiornato, molto più solido dell'invenzione libera dell'AI.
#
# Aggiornamento: ripetere l'estrazione (build_omi_canoni.py, non incluso qui)
# ogni volta che l'Agenzia pubblica un nuovo semestre (di norma marzo e
# settembre), scaricando di nuovo da Forniture OMI > Quotazioni immobiliari.

import json
import os

_PATH = os.path.join(os.path.dirname(__file__), "omi_canoni.json")
_DATI = None


def _carica():
    global _DATI
    if _DATI is None:
        try:
            with open(_PATH, encoding="utf-8") as f:
                _DATI = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            _DATI = {}
    return _DATI


# Superficie tipica per tipologia, usata solo quando il campo superficie del
# form è vuoto (è opzionale) — stessa logica di fallback per tipologia già
# in uso altrove nel file per i costi fissi.
_SUPERFICIE_TIPICA_PER_TIPOLOGIA = [
    ("villa", 180), ("casa indipendente", 180),
    ("appartamento", 110), ("4+", 110), ("grande", 110),
    ("trilocale", 85),
    ("bilocale", 60),
    ("doppia", 45),
    ("singola", 35), ("stanza", 35),
]


def _superficie_tipica(tipologia):
    t = str(tipologia or "").strip().lower()
    for frammento, mq in _SUPERFICIE_TIPICA_PER_TIPOLOGIA:
        if frammento in t:
            return mq
    return 65


def canone_omi_mq(codice_istat):
    """
    Ritorna (loc_min_mq, loc_max_mq, n_zone) — canone di locazione mensile
    EUR/m2, media tra le zone OMI del comune — oppure None se il comune
    non è nel dataset OMI 2025/2 o il codice non è valido.
    """
    if codice_istat is None:
        return None
    try:
        chiave = str(int(codice_istat))
    except (ValueError, TypeError):
        return None
    rec = _carica().get(chiave)
    if not rec:
        return None
    return rec["loc_min_mq"], rec["loc_max_mq"], rec["n_zone"]


def stima_affitto_tradizionale(codice_istat, superficie, tipologia):
    """
    Calcola il confronto con l'affitto tradizionale usando il canone OMI
    reale. Ritorna (affitto_ricavo, affitto_costi, affitto_profitto, fonte)
    con fonte='omi_reale', oppure None se il comune non è coperto da OMI
    (il chiamante deve allora usare il fallback esistente, senza dichiarare
    la fonte come OMI).
    """
    ris = canone_omi_mq(codice_istat)
    if ris is None:
        return None
    loc_min, loc_max, _n_zone = ris

    mq = superficie if isinstance(superficie, (int, float)) and superficie > 0 else _superficie_tipica(tipologia)

    canone_medio_mq = (loc_min + loc_max) / 2
    canone_mensile = mq * canone_medio_mq
    affitto_ricavo = round(canone_mensile * 12)

    # Costi di gestione affitto tradizionale (assicurazione, IMU, manutenzione
    # ordinaria): stima deterministica al 10% del canone annuo, con un minimo
    # e un massimo ragionevoli — non più un numero libero dell'AI.
    affitto_costi = max(500, min(2000, round(affitto_ricavo * 0.10)))
    affitto_profitto = affitto_ricavo - affitto_costi

    return affitto_ricavo, affitto_costi, affitto_profitto, "omi_reale"

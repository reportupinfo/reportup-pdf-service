# ── Canoni di locazione di mercato per comune (EUR/m2/mese) ─────────────────
# Fonte: affitti_mercato.csv (scraping annunci, ~5.350 comuni). Letto una sola
# volta in memoria al primo uso. Per i comuni NON presenti (o con riga non
# valida) il chiamante usa il fallback già esistente (OMI / AirROI).
#
# Il valore al m2 viene moltiplicato per la superficie dichiarata dal cliente:
# nessuna stima, nessun sconto.

import csv
import os
import re

_PATH = os.path.join(os.path.dirname(__file__), "affitti_mercato.csv")
_DATI = None

# Soglie di sanità sul canone medio: fuori da qui il dato è quasi certamente
# un errore di estrazione (es. unico annuncio di lusso) e si usa il fallback.
_MQ_MIN_PLAUSIBILE = 2.0
_MQ_MAX_PLAUSIBILE = 40.0


def _num(txt):
    try:
        return float(str(txt).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


# Comuni esclusi a mano: dato del CSV non attendibile, si usa il metodo base
# (codice ISTAT). 25063 = Valle di Cadore (41,33 EUR/m2 piatto, canone di lusso).
_ESCLUSI = {25063}

# Fascia usata quando min/max del CSV non sono affidabili a livello comunale.
_FASCIA = 0.15
_RATIO_MAX_AFFIDABILE = 2.5   # max/min oltre questo = range non credibile
_SOGLIA_PROVINCIALE = 3       # stessa coppia min/max su >=3 comuni = dato provinciale


def numero_da_testo(valore, default=None):
    """Estrae il primo numero da '70', '70 m2', '70,5 mq', '2 camere'.
    Il form/Make può passare la superficie con l'unità attaccata: un
    float() secco fallirebbe e il calcolo ricadrebbe sulla superficie tipica."""
    if isinstance(valore, (int, float)):
        return float(valore) or default
    m = re.search(r"\d+(?:[.,]\d+)?", str(valore or ""))
    if not m:
        return default
    return float(m.group(0).replace(",", ".")) or default


def _carica():
    global _DATI
    if _DATI is not None:
        return _DATI
    grezzi = []
    try:
        with open(_PATH, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                v = [_num(r.get("affitto_min_mq_mese")),
                     _num(r.get("affitto_medio_mq_mese")),
                     _num(r.get("affitto_max_mq_mese"))]
                if None in v:
                    continue
                v.sort()  # alcune righe hanno min/medio/max fuori ordine
                if not (_MQ_MIN_PLAUSIBILE <= v[1] <= _MQ_MAX_PLAUSIBILE):
                    continue
                try:
                    cod = int(r["codice_istat"])
                    if cod in _ESCLUSI:
                        continue
                    grezzi.append((cod, v))
                except (KeyError, ValueError, TypeError):
                    continue
    except FileNotFoundError:
        pass
    # Su molte righe (immobiliare.it) min/max sono quelli della provincia e
    # solo il medio è del comune: la stessa coppia compare su tanti comuni.
    # In quel caso, o se il range è inverosimile o assente, si mostra una
    # fascia stretta attorno al medio invece di un range che non è comunale.
    coppie = {}
    for _, v in grezzi:
        coppie[(v[0], v[2])] = coppie.get((v[0], v[2]), 0) + 1
    dati = {}
    for cod, v in grezzi:
        mn, md, mx = v
        affidabile = (
            coppie[(mn, mx)] < _SOGLIA_PROVINCIALE
            and mx > mn and mn > 0 and mx / mn <= _RATIO_MAX_AFFIDABILE
        )
        if not affidabile:
            mn, mx = md * (1 - _FASCIA), md * (1 + _FASCIA)
        dati[cod] = (round(mn, 2), md, round(mx, 2))
    _DATI = dati
    return _DATI


DISCLAIMER = (
    "Il valore minimo e quello massimo ti sembrano troppo distanti? In alcuni comuni, come Positano, "
    "i prezzi cambiano molto da una zona all'altra: la costa o il centro storico valgono molto più "
    "dell'entroterra, e il canone medio per m² mescola zone molto diverse. Il valore è calcolato "
    "sui canoni al m² del comune per la superficie che hai indicato: se tra minimo e massimo c'è "
    "una grande differenza, conviene un doppio controllo sui portali di annunci per la tua zona precisa."
)


def fonte_descrizione():
    return ("Canoni di locazione al m² rilevati da annunci attivi sul comune (minimo, medio, massimo), "
            "moltiplicati per la superficie dichiarata dell'immobile. Valore orientativo, non tratto da "
            "contratti registrati.")


def canone_mq(codice_istat):
    """(min, medio, max) EUR/m2/mese oppure None se comune non coperto."""
    try:
        chiave = int(codice_istat)
    except (ValueError, TypeError):
        return None
    return _carica().get(chiave)


def stima_affitto_mercato(codice_istat, superficie):
    """
    Confronto affitto tradizionale = canone/m2 x superficie dichiarata x 12.
    Ritorna dict con ricavo/profitto min-medio-max e costi, oppure None se il
    comune non è coperto (il chiamante usa allora il fallback esistente).
    I costi di gestione (assicurazione, IMU, manutenzione) restano al 10% del
    canone annuo medio, minimo 500 e massimo 2000, come nel metodo OMI.
    """
    ris = canone_mq(codice_istat)
    if ris is None or not superficie or superficie <= 0:
        return None
    mn, md, mx = ris
    ricavo = [round(v * superficie * 12) for v in (mn, md, mx)]
    costi = max(500, min(2000, round(ricavo[1] * 0.10)))
    return {
        "ricavo_min": ricavo[0], "ricavo": ricavo[1], "ricavo_max": ricavo[2],
        "costi": costi,
        "profitto_min": ricavo[0] - costi, "profitto": ricavo[1] - costi,
        "profitto_max": ricavo[2] - costi,
        "mq_min": mn, "mq_medio": md, "mq_max": mx,
    }

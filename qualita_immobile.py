# ── Qualita' dell'immobile: scostamento sul prezzo di mercato ────────────────
#
# Decisione di Salvatore (28/10/2026). Il prezzo AirROI (media dei comparabili
# della stessa tipologia) non dipende dalla qualita' dell'immobile: due
# appartamenti uguali per zona, tipologia e dotazioni, uno con arredi base e
# uno con finiture di lusso, avrebbero lo stesso prezzo. Il form chiede lo
# stato in 4 livelli; si prende "buono" (ben tenuto e curato) come livello di
# partenza, quello a cui corrisponde il prezzo di mercato, e gli altri tre si
# scostano in percentuale:
#
#     base          -5%    arredi base, funzionale
#     buono          0%    ben tenuto e curato            (riferimento)
#     ristrutturato +10%   ristrutturato e moderno
#     lusso         +20%   finiture di lusso e design
#
# Regola di calcolo: prezzo AirROI + incremento dotazioni (gia' in atto) +
# scostamento di qualita', sommati (come gia' fanno tra loro le dotazioni).
# Sono convenzioni ReportUp su medie nazionali, non dati di mercato: non
# compaiono in nessuna tabella del PDF, agiscono solo nel prezzo/notte (e di
# conseguenza in ricavi, tabella mensile, competitor, scenari) e nel canone
# dell'affitto tradizionale, cosi' il confronto resta alla pari.
#
# Modulo puro: nessuna rete, nessun Flask.

import re
import unicodedata

ADEGUAMENTO_PREZZO_PER_QUALITA = {
    "base": -0.05,
    "buono": 0.0,
    "ristrutturato": 0.10,
    "lusso": 0.20,
}


# Etichette dello stato come le scrive il form Base (statoMap): quelle che il
# cliente legge nella scheda immobile. Il Base le riceve gia' in chiaro, lo
# Strategico riceve i codici ("lusso"): senza una tabella unica la stessa
# riga si leggeva "Finiture di lusso e design" nel Base e "Finiture premium,
# design" nello Strategico (28/10/2026).
ETICHETTA_PER_QUALITA = {
    "base": "Arredi base, funzionale",
    "buono": "Ben tenuto e curato",
    "ristrutturato": "Ristrutturato e moderno",
    "lusso": "Finiture di lusso e design",
}


def _livello_riconosciuto(stato):
    """Livello se lo stato e' riconosciuto, altrimenti None."""
    t = unicodedata.normalize("NFKD", str(stato or "")).encode("ascii", "ignore").decode("ascii").lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    if re.search(r"lusso|premium|design|finiture", t):
        return "lusso"
    if re.search(r"ristruttur|moderno", t):
        return "ristrutturato"
    if re.search(r"\bbase\b|funzional|arredi", t):
        return "base"
    if re.search(r"\bbuono\b|ben tenuto|curato", t):
        return "buono"
    return None


def etichetta_stato(stato):
    """Etichetta unica dello stato per la scheda immobile. Uno stato non
    riconosciuto resta com'e' (mai un'etichetta inventata)."""
    livello = _livello_riconosciuto(stato)
    return ETICHETTA_PER_QUALITA[livello] if livello else str(stato or "").strip()


def livello_qualita(stato):
    """Livello ("base" | "buono" | "ristrutturato" | "lusso") dallo stato
    dichiarato nel form. Il form manda i codici ("base", "lusso"...) oppure il
    testo ("Finiture di lusso e design", "Ristrutturato e moderno", "Arredi
    base, funzionale", "Ben tenuto e curato"). Stato mancante o non
    riconosciuto: "buono", cioe' nessuno scostamento (mai un'ipotesi)."""
    return _livello_riconosciuto(stato) or "buono"


def adeguamento_pct(stato):
    """Scostamento in frazione (es. 0.10 = +10%) per lo stato dichiarato."""
    return ADEGUAMENTO_PREZZO_PER_QUALITA[livello_qualita(stato)]

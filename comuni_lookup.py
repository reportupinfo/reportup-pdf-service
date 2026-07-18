# ── Lookup comuni — Sessione 42 ──────────────────────────────────────────────
# Sostituisce la ricerca via Make (modulo 16, Data Store) con una ricerca
# deterministica in Python: zero crediti Make, gestione corretta di accenti,
# apostrofi, maiuscole/minuscole, nomi colloquiali e comuni omonimi.

import csv
import os
import unicodedata

CSV_PATH = os.path.join(os.path.dirname(__file__), "comuni.csv")

# Alias per nomi colloquiali diversi dal nome ufficiale del comune.
# Chiave e valore già in forma normalizzata (vedi _normalizza). Aggiungere
# qui nuove voci se in futuro emergono altri casi (basta editare questo file,
# nessuna modifica al resto del codice).
ALIAS = {
    "reggio emilia": "reggio nell emilia",
    "reggio calabria": "reggio di calabria",
}


def _normalizza(testo: str) -> str:
    """Minuscolo, senza accenti, senza apostrofi/punteggiatura, spazi singoli."""
    if not testo:
        return ""
    testo = testo.strip().lower()
    # Rimuove accenti (è -> e, ì -> i, ecc.) preservando le lettere di base.
    testo = unicodedata.normalize("NFKD", testo)
    testo = "".join(c for c in testo if not unicodedata.combining(c))
    # Apostrofi (dritti, tipografici) e punteggiatura varia -> spazio.
    for ch in ["'", "’", "`", "-", "."]:
        testo = testo.replace(ch, " ")
    # Spazi multipli -> singolo spazio.
    testo = " ".join(testo.split())
    return testo


_INDEX = None  # cache in memoria, costruito al primo utilizzo


def _carica_indice():
    global _INDEX
    if _INDEX is not None:
        return _INDEX

    indice = {}
    with open(CSV_PATH, encoding="utf-8") as f:
        for riga in csv.DictReader(f):
            chiave = _normalizza(riga["comune"])
            riga["_popolazione_num"] = int(riga.get("popolazione") or 0)
            indice.setdefault(chiave, []).append(riga)

    _INDEX = indice
    return _INDEX


def trova_comune(nome_comune: str, provincia: str = None) -> dict | None:
    """
    Ritorna il record del comune (dict con categoria, capoluogo, grande_citta,
    provincia, sigla_provincia, popolazione, wikipedia, ecc.) o None se non
    trovato. Gestisce accenti, maiuscole/minuscole, alias colloquiali e
    comuni omonimi (disambiguati per provincia se fornita, altrimenti per
    popolazione più alta).
    """
    indice = _carica_indice()
    chiave = _normalizza(nome_comune)
    chiave = ALIAS.get(chiave, chiave)

    candidati = indice.get(chiave)
    if not candidati:
        # Nessuna corrispondenza esatta: prova un confronto fuzzy per
        # catturare piccoli refusi (es. una lettera di troppo/mancante),
        # comune quando il nome arriva da un testo generato via AI.
        import difflib
        corrispondenze = difflib.get_close_matches(chiave, indice.keys(), n=1, cutoff=0.87)
        if not corrispondenze:
            return None
        candidati = indice[corrispondenze[0]]

    if len(candidati) == 1:
        return candidati[0]

    # Comune omonimo: se abbiamo la provincia, usiamola per disambiguare.
    if provincia:
        prov_norm = _normalizza(provincia)
        for c in candidati:
            if _normalizza(c["provincia"]) == prov_norm or c["sigla_provincia"].lower() == prov_norm:
                return c

    # Nessuna provincia utile: fallback sul comune più popoloso (stessa
    # logica già usata nel modulo 16 di Make, Sort per popolazione).
    return max(candidati, key=lambda c: c["_popolazione_num"])

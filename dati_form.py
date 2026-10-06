"""Dati dichiarati dal cliente, letti DIRETTAMENTE dal prompt costruito da Make.

Regola di Salvatore (6/10/2026): nulla di matematico passa per l'IA. Gli
scenari Make interpolano i valori del form dentro il prompt che mandano
all'IA (righe "Superficie: 60m2", "Rata mensile: ...", letterali JSON come
"rata_mutuo_mensile":0). Qui li si rilegge con regole fisse, cosi' il backend
puo' (a) costruire il JSON del Base senza chiamare l'IA e (b) sovrascrivere
nel JSON dello Strategico ogni dato utente che l'IA avrebbe potuto
trascrivere male (rata mutuo, importo e mesi dell'intervento, mq...).

Modulo puro: nessuna dipendenza da Flask o da app.py.
"""
import json
import re

_MARCATORE_JSON = "Restituisci ESATTAMENTE questo oggetto JSON"


def _linea(testo, etichetta_re):
    """Valore della prima riga che inizia con l'etichetta (case-sensitive)."""
    m = re.search(r"^[ \t]*" + etichetta_re + r"[ \t]*(.*?)[ \t]*$", testo, re.MULTILINE)
    return m.group(1).strip() if m else None


def _letterale(coda, chiave):
    """Primo letterale JSON `"chiave":valore` nella coda (true/false/numero/stringa)."""
    m = re.search(r'"' + re.escape(chiave) + r'"\s*:\s*(true|false|-?\d+(?:\.\d+)?|"(?:[^"\\]|\\.)*")', coda)
    if not m:
        return None
    v = m.group(1)
    if v == "true":
        return True
    if v == "false":
        return False
    if v.startswith('"'):
        try:
            return json.loads(v)
        except ValueError:
            return v.strip('"')
    return float(v) if "." in v else int(v)


def _numero(v, default=0):
    try:
        return int(round(float(str(v).replace(",", ".").strip())))
    except (TypeError, ValueError):
        return default


def parse_prompt(user):
    """Estrae i dati del cliente dal testo `user` del prompt Base o Strategico."""
    testo = str(user or "")
    # I letterali JSON si cercano SOLO dopo il marcatore: prima ci sono i testi
    # liberi del cliente (note), che non devono poter influire sui numeri.
    i = testo.find(_MARCATORE_JSON)
    coda = testo[i:] if i >= 0 else ""
    testa = testo[:i] if i >= 0 else testo

    def prima_riga(*etichette):
        for e in etichette:
            v = _linea(testa, e)
            if v is not None:
                return v
        return ""

    mq_raw = prima_riga(r"Superficie:")
    mq = _numero(re.sub(r"[^\d.,]", "", mq_raw.replace("m2", "")), 0)

    d = {
        "via": prima_riga(r"Via e numero civico[^:\n]*:"),
        "cap": re.sub(r"\D", "", prima_riga(r"CAP[^:\n]*:"))[:5],
        "comune": prima_riga(r"Comune:"),
        "provincia": prima_riga(r"Provincia:"),
        "tipologia": prima_riga(r"Tipologia:"),
        "mq": mq,
        "piano": prima_riga(r"Piano:"),
        "stato": prima_riga(r"Stato conservativo:"),
        "bagni": prima_riga(r"Numero bagni:"),
        "posti_letto": prima_riga(r"Posti letto:"),
        "epoca": prima_riga(r"Epoca costruzione:"),
        "dotazioni": prima_riga(r"Dotazioni presenti:"),
        "indirizzo_google": prima_riga(r"INDIRIZZO VERIFICATO GOOGLE:"),
        "quartiere_google": prima_riga(r"QUARTIERE VERIFICATO GOOGLE[^:\n]*:"),
    }
    d["lat"] = _letterale(coda, "lat")
    d["long"] = _letterale(coda, "long")
    for k in ("situazione_vuoto", "situazione_inquilini", "situazione_bnb", "situazione_mutuo", "mutuo_attivo",
              "property_manager", "di_proprieta"):
        d[k] = _letterale(coda, k)
    d["rata_mutuo_mensile"] = _numero(_letterale(coda, "rata_mutuo_mensile"), 0)
    d["intervento_tipo"] = _letterale(coda, "intervento_tipo")
    d["intervento_importo"] = _numero(_letterale(coda, "intervento_importo"), 0)
    d["intervento_mesi"] = _numero(_letterale(coda, "intervento_mesi"), 0)
    d["mq_stimati"] = _letterale(coda, "mq_stimati")
    return d


def via_civico_da_google(indirizzo_google, via_form=""):
    """"Via Domenico Ridola, 10, 75100 Matera MT, Italia" -> "Via Domenico Ridola 10".
    Se non riconoscibile, usa la via scritta nel form."""
    parti = [p.strip() for p in str(indirizzo_google or "").split(",")]
    if not parti or not parti[0]:
        return str(via_form or "").strip()
    via = parti[0]
    if len(parti) > 1 and re.fullmatch(r"\d+[A-Za-z]?(?:/\w+)?", parti[1]):
        via = f"{via} {parti[1]}"
    return via


def sigla_da_google(indirizzo_google):
    """Sigla provincia dall'indirizzo Google ("..., 75100 Matera MT, Italia")."""
    m = re.search(r"\b\d{5}\s+.+?\s([A-Z]{2})(?:,|$)", str(indirizzo_google or ""))
    return m.group(1) if m else ""


def applica_dati_utente(data, d, solo_se_presenti=True):
    """Sovrascrive in `data` i campi che il cliente ha dichiarato: l'IA non li
    tocca. Chiavi vuote/None nel prompt non cancellano il dato esistente."""
    if d.get("mq"):
        data["superficie"] = f"{d['mq']} m2"
        if "mq_stimati" in data or d.get("mq_stimati") is not None:
            data["mq_stimati"] = d["mq"]
    for k_data, k_d in (("tipologia", "tipologia"), ("piano", "piano"), ("stato", "stato"),
                        ("bagni", "bagni"), ("posti_letto", "posti_letto"), ("epoca", "epoca")):
        if d.get(k_d):
            data[k_data] = d[k_d]
    for k in ("situazione_vuoto", "situazione_inquilini", "situazione_bnb", "situazione_mutuo", "mutuo_attivo",
              "property_manager", "di_proprieta"):
        if d.get(k) is not None:
            data[k] = d[k]
    data["rata_mutuo_mensile"] = d.get("rata_mutuo_mensile", 0)
    if d.get("intervento_tipo") is not None:
        data["intervento_tipo"] = d["intervento_tipo"]
        data["intervento_importo"] = d.get("intervento_importo", 0)
        data["intervento_mesi"] = d.get("intervento_mesi", 0)
    return data


# Segnaposto numerici del template Base (stessi valori che l'IA riceveva nel
# prompt). NON sono stime: il backend li ricalcola SEMPRE con AirROI/tabelle.
_SEGNAPOSTO_NUMERICI_BASE = {
    "occupazione": [["Gen", 45, 60, "Bassa"], ["Feb", 48, 62, "Bassa"], ["Mar", 62, 75, "Media"],
                    ["Apr", 74, 88, "Alta"], ["Mag", 75, 88, "Alta"], ["Giu", 83, 98, "Alta"], ["Lug", 89, 108, "Peak"],
                    ["Ago", 91, 112, "Peak"], ["Set", 79, 92, "Alta"], ["Ott", 66, 77, "Media"],
                    ["Nov", 51, 62, "Media"], ["Dic", 56, 68, "Media"]],
    "prezzo_notte_stimato": 75, "occupazione_percent": 68, "notti_anno": 248, "ricavo_lordo": 18600,
    "bonus_dirette": 1302, "bonus_dirette_pct": "5-10%", "totale_ricavi": 19902, "costi_commissioni": 2790,
    "costi_commissioni_pct": 15, "costi_pulizie": 2893, "costi_pulizie_unit": 35, "costi_biancheria": 372,
    "costi_utenze": 800, "costi_manutenzione": 400, "totale_costi": 7255, "profitto_netto": 12647,
    "margine_percent": 64, "affitto_ricavo": 9600, "affitto_costi": 900, "affitto_profitto": 8700,
    "competitor": [["Monolocali zona", "12", "EUR 65", "71%", 4.6], ["Bilocali zona", "8", "EUR 85", "68%", 4.7],
                   ["Trilocali zona", "5", "EUR 110", "62%", 4.5], ["B&B e camere", "15", "EUR 55", "74%", 4.4]],
    "competitor_zona": "Zona centrale",
    "media_nazionale": ["Media nazionale B&B urbani", "—", "EUR 95", "64%", 4.5],
    "kpi_prezzo": 75, "kpi_prezzo_range": "Range zona: EUR 55-110", "kpi_occupazione": 68,
    "kpi_occ_range": "Media zona: 62-74%", "kpi_potenziale": 18600,
}


def costruisci_json_base(d, norm_dotazione, dotazioni_ammesse):
    """JSON d'ingresso del Base costruito SENZA IA dai dati del cliente e dai
    dati Google gia' verificati nel prompt. Tutti i numeri economici sono
    segnaposto sovrascritti dal motore di calcolo."""
    via = via_civico_da_google(d.get("indirizzo_google"), d.get("via"))
    sigla = sigla_da_google(d.get("indirizzo_google"))
    comune = d.get("comune") or ""
    indirizzo = f"{via}, {d.get('cap', '')}, {comune}" + (f" ({sigla})" if sigla else "")
    presenti = []
    for voce in re.split(r"[,;]", d.get("dotazioni") or ""):
        n = norm_dotazione(voce)
        if n in dotazioni_ammesse and n not in presenti:
            presenti.append(n)
    data = {
        "lat": d.get("lat"), "long": d.get("long"),
        "indirizzo": indirizzo,
        "tipologia": d.get("tipologia", ""),
        "superficie": f"{d.get('mq', 0)} m2",
        "piano": d.get("piano", ""), "stato": d.get("stato", ""),
        "camere": "0", "comune": comune,
        "zona": d.get("quartiere_google") if d.get("quartiere_google") not in (None, "", "nessuno") else "—",
        "epoca": d.get("epoca", ""), "bagni": d.get("bagni", ""), "posti_letto": d.get("posti_letto", ""),
        "dotazioni_presenti": presenti,
        "dotazioni_assenti": [x for x in dotazioni_ammesse if x not in presenti],
        "descrizione": "",
        "poi": [["—", "—", "—"] for _ in range(4)],
        "mutuo_attivo": bool(d.get("situazione_mutuo")),
    }
    for k in ("situazione_vuoto", "situazione_inquilini", "situazione_bnb", "situazione_mutuo"):
        data[k] = bool(d.get(k))
    data["rata_mutuo_mensile"] = d.get("rata_mutuo_mensile", 0)
    data.update(json.loads(json.dumps(_SEGNAPOSTO_NUMERICI_BASE)))
    return data

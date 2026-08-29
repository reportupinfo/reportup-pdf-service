"""
ReportUp PDF Service
Riceve JSON con i dati del report, genera il PDF branded, restituisce base64.
Deploy su Render.com (piano free).
"""

import os
import io
import re
import time
import base64
import math
import requests
from flask import Flask, request, jsonify
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER

import comuni_lookup
import territorio_gps
import stagionalita_turistica
import omi_canoni

app = Flask(__name__)

# ── AirROI: dato di mercato reale per il prezzo/notte ───────────────────────────
AIRROI_API_KEY = os.environ.get("AIRROI_API_KEY", "")
AIRROI_BASE = "https://api.airroi.com"

# ── Anthropic: chiamata AI grande dello Strategico (Sessione 27/8, bloccante
# risolto) — spostata qui da netlify/functions/ai-proxy.js perché le Netlify
# Functions hanno un limite fisso di ~30s e la chiamata da 91 campi/6000
# token dello Strategico lo supera sempre (504 Inactivity Timeout misurato).
# Render non ha quel limite, ma gunicorn sì (default 30s) — vedi render.yaml,
# serve --timeout alzato sullo startCommand o questo endpoint muore uguale.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

# ── Autenticazione endpoint server-to-server (chiamati solo da Make.com) ───────
# Non applicato a /quick-estimate e /verify-address: quelli sono chiamati
# direttamente dal browser (fetch lato client), quindi un segreto statico
# sarebbe visibile nel JS e non protegge nulla.
PDF_SECRET = os.environ.get("PDF_SECRET", "")


def require_internal_secret(fn):
    from functools import wraps

    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not PDF_SECRET:
            return jsonify({"error": "PDF_SECRET non configurato lato server"}), 500
        if request.headers.get("X-Internal-Secret", "") != PDF_SECRET:
            return jsonify({"error": "non autorizzato"}), 401
        return fn(*args, **kwargs)

    return wrapper


# /quick-estimate e /verify-address restano pubblici per design (chiamati da
# fetch lato browser, un segreto statico non li protegge — vedi sopra), ma
# fanno chiamate esterne a pagamento/quota (Google, AirROI) per ogni
# richiesta. Un controllo Origin leggero blocca lo scraping/abuso casuale da
# fuori sito senza richiedere manutenzione ricorrente (audit 23/8, finding
# #17). Non è una protezione forte (Origin è falsificabile da chi chiama via
# script anziché browser), ma alza la barriera contro l'abuso involontario.
ORIGINI_CONSENTITE_SUFFISSI = ("reportup.it", "netlify.app")


def require_origin_reportup(fn):
    from functools import wraps

    @wraps(fn)
    def wrapper(*args, **kwargs):
        if request.method == "OPTIONS":
            return fn(*args, **kwargs)
        origine = request.headers.get("Origin") or request.headers.get("Referer") or ""
        if origine:
            host = origine.split("//", 1)[-1].split("/", 1)[0].split(":", 1)[0].lower()
            if not any(host == s or host.endswith("." + s) for s in ORIGINI_CONSENTITE_SUFFISSI):
                print(f"[ORIGIN-CHECK] rifiutata origine={origine!r} host={host!r}")
                return jsonify({"error": "origine_non_consentita"}), 403
        return fn(*args, **kwargs)

    return wrapper


def _numero_da(d, *chiavi, default=None):
    for k in chiavi:
        v = d.get(k)
        if isinstance(v, (int, float)):
            return v
        if isinstance(v, str):
            try:
                return float(v.replace(",", "."))
            except ValueError:
                continue
    return default


def _tipologia_da_camere(n_camere):
    if n_camere is None:
        return "Annunci comparabili"
    # data.get("camere") puo' arrivare qui come stringa: _camere_deterministiche
    # ritorna str(m[0]) (Sessione 66), mentre le "bedrooms" AirROI dei
    # comparable_listings sono gia' numeriche. round() su str esplode
    # (TypeError: type str doesn't define __round__ method) — capitava ogni
    # volta che AirROI aveva abbastanza comparabili della zona (es. Napoli).
    if isinstance(n_camere, str):
        n_camere = _numero_da_stringa(n_camere, default=1)
    n = int(round(n_camere))
    return {0: "Monolocali", 1: "Bilocali"}.get(n, f"{n + 1} locali" if n >= 2 else "Monolocali")


def _occupazione_da_comparabili(comparable_listings, sconto=0.90):
    """Calcola l'occupazione media dai singoli annunci comparabili REALI di
    AirROI (non il dato percentili generico), quando ce ne sono abbastanza
    per essere affidabili. Sessione 66: confrontando i due dati nello stesso
    report — media percentili generica vs media annunci comparabili della
    stessa zona/tipologia — il secondo risulta sistematicamente più alto e
    più specifico (bilocali/monolocali veri della zona, non una media
    nazionale astratta). Il correttivo fisso per categoria (1.10 etc.)
    partiva dal dato più grezzo; qui, quando disponibile, usiamo il dato più
    reale direttamente.

    Lo sconto (default 0.90) tiene conto che un nuovo annuncio short-rental
    parte senza recensioni/storico: realisticamente performa un po' sotto la
    media di annunci già affermati, non identico. Ritorna None se i
    comparabili non hanno abbastanza dati di occupazione (soglia minima 3,
    stessa usata altrove per considerare il dato affidabile)."""
    if not comparable_listings:
        return None
    occ_vals = []
    for ann in comparable_listings:
        if not isinstance(ann, dict):
            continue
        occ = _numero_da(ann, "occupancy", "occupancy_rate")
        if occ is not None:
            if occ <= 1:
                occ = occ * 100
            occ_vals.append(occ)
    if len(occ_vals) < 3:
        return None
    media = sum(occ_vals) / len(occ_vals)
    return media * sconto


# ── Tabella competitor — deterministica, niente più AirROI/AI (Sessione 69) ──
# Salvatore: mostrare "Bilocali zona €82" (AirROI, conservativo, o peggio
# invenzione AI quando i comparabili mancano) accanto a "IL TUO IMMOBILE
# €120" (calcolato con le nostre regole + bonus dotazioni) confonde il
# cliente e non è nemmeno corretto — non sappiamo se i competitor abbiano
# le stesse dotazioni. Soluzione: la tabella competitor non usa più NESSUN
# dato esterno per il prezzo. La tipologia dichiarata mostra lo STESSO
# numero di "IL TUO IMMOBILE" (stesso valore per costruzione), le altre 3
# tipologie sono derivate con rapporti fissi decisi da noi — "aggressività"
# tarabile a mano, zero AI, zero media AirROI conservativa.
RATIO_PREZZO_TIPOLOGIA_COMPETITOR = {
    "Monolocali": 0.80,
    "Bilocali": 1.00,
    "Trilocali": 1.30,
    "B&B e camere": 0.65,
}

_BUCKET_COMPETITOR_PER_TIPOLOGIA = [
    ("stanza singola", "B&B e camere"), ("stanza doppia", "B&B e camere"),
    ("monolocale", "Monolocali"),
    ("bilocale", "Bilocali"),
    ("trilocale", "Trilocali"),
    ("quadrilocale", "Trilocali"), ("4 locali", "Trilocali"), ("appartamento grande", "Trilocali"),
    ("villa", "Trilocali"), ("casa indipendente", "Trilocali"),
]


def _bucket_competitor(tipologia):
    t = str(tipologia or "").strip().lower()
    for frammento, bucket in _BUCKET_COMPETITOR_PER_TIPOLOGIA:
        if frammento in t:
            return bucket
    return "Bilocali"


def _costruisci_competitor_deterministico(prezzo_immobile, tipologia, valuta="€"):
    """
    Ritorna le 4 righe della tabella competitor (tipologia, prezzo medio),
    calcolate SOLO dal nostro prezzo finale (prezzo_immobile, già corretto
    con AirROI + smorzamento + dotazioni). Nessun dato esterno, nessuna
    invenzione AI. Sessione 70: tolte anche le colonne N./Occupazione/Rating
    — mai avuto un dato reale differenziato per tipologia da mettere lì,
    meglio una tabella essenziale che fronzoli senza contenuto.
    """
    if not prezzo_immobile:
        return None
    bucket_immobile = _bucket_competitor(tipologia)
    base = prezzo_immobile / RATIO_PREZZO_TIPOLOGIA_COMPETITOR[bucket_immobile]
    righe = []
    for bucket in ["Monolocali", "Bilocali", "Trilocali", "B&B e camere"]:
        prezzo = (prezzo_immobile if bucket == bucket_immobile
                  else round(base * RATIO_PREZZO_TIPOLOGIA_COMPETITOR[bucket]))
        righe.append([bucket, f"{valuta} {prezzo}"])
    return righe


def _prezzo_da_comparabili_stessa_tipologia(comparable_listings, n_camere_immobile, minimo=3):
    """
    Sessione 68: prima 'IL TUO IMMOBILE' usava il prezzo del modello AirROI
    (/calculator/estimate, stima puntuale per lat/lng+camere) mentre la riga
    competitor della STESSA tipologia in tabella usava la media dei
    comparable_listings reali (endpoint diverso, campione diverso) — le due
    fonti possono divergere parecchio (caso reale: Napoli bilocale, modello
    €120 vs media reale annunci bilocali in zona €82, +46% ingiustificato
    agli occhi del cliente). Quando ci sono abbastanza annunci comparabili
    della STESSA tipologia dichiarata, ancoriamo il prezzo base a quella
    media reale invece che al modello: dotazioni/smorzamento si applicano
    comunque sopra, ma partendo dallo stesso numero mostrato in tabella
    competitor — coerenza garantita per costruzione, non per coincidenza.
    Ritorna il prezzo medio (float) o None se i comparabili della stessa
    tipologia sono insufficienti (fallback al modello, invariato).
    """
    if not comparable_listings:
        return None
    prezzi = []
    for ann in comparable_listings:
        if not isinstance(ann, dict):
            continue
        camere = _numero_da(ann, "bedrooms", "beds", "num_bedrooms")
        if camere is None:
            continue
        if _tipologia_da_camere(camere) != _tipologia_da_camere(n_camere_immobile):
            continue
        prezzo = _numero_da(ann, "average_daily_rate", "adr", "price", "daily_rate")
        if prezzo is not None:
            prezzi.append(prezzo)
    if len(prezzi) < minimo:
        return None
    return sum(prezzi) / len(prezzi)


def _numero_da_stringa(valore, default=1):
    try:
        m = re.search(r"\d+", str(valore))
        return int(m.group()) if m else default
    except Exception:
        return default


# /generate-pdf-direct e /extract-report-fields ricevono dallo stesso
# scenario Make, per lo stesso ordine, il medesimo testo AI grezzo — e
# chiamano entrambi _elabora_dati_report_base(), quindi entrambi finiscono
# qui. Essendo due richieste HTTP indipendenti, senza cache ognuna fa la
# propria chiamata ad AirROI: l'API può restituire risposte leggermente
# diverse a parità di parametri (vedi commento sul retry comparable_listings
# più sotto), e PDF/mail dello stesso ordine mostrano numeri economici
# diversi. TTL breve: copre lo scarto tipico tra le due chiamate Make per
# lo stesso ordine, senza rischiare dati stantii su richieste successive
# reali alla stessa coordinata.
_AIRROI_CACHE = {}
_AIRROI_CACHE_TTL_SECONDI = 900


def _airroi_lookup_e_stima(lat, lon, camere_raw=None, posti_letto_raw=None, bagni_raw=None, timeout_lookup=4, timeout_stima=6):
    if not AIRROI_API_KEY or lat in (None, "") or lon in (None, ""):
        print(f"[AIRROI] skip — chiave assente o coordinate mancanti (lat={lat!r}, lon={lon!r})")
        return None
    headers = {"X-API-KEY": AIRROI_API_KEY}
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        print(f"[AIRROI] skip — coordinate non convertibili in float (lat={lat!r}, lon={lon!r})")
        return None

    bedrooms = _numero_da_stringa(camere_raw, default=1)
    guests = _numero_da_stringa(posti_letto_raw, default=2)
    baths = _numero_da_stringa(bagni_raw, default=1)

    _cache_key = (round(lat_f, 5), round(lon_f, 5), bedrooms, guests, baths)
    _cached = _AIRROI_CACHE.get(_cache_key)
    if _cached and (time.monotonic() - _cached[0]) < _AIRROI_CACHE_TTL_SECONDI:
        print(f"[AIRROI] cache hit — chiave={_cache_key!r}, evita chiamata duplicata per lo stesso ordine")
        return _cached[1]

    try:
        r1 = requests.get(
            f"{AIRROI_BASE}/markets/lookup",
            params={"lat": lat_f, "lng": lon_f},
            headers=headers, timeout=timeout_lookup,
        )
        print(f"[AIRROI] lookup lat={lat_f} lon={lon_f} -> status={r1.status_code} body={r1.text[:300]}")
        if r1.status_code != 200:
            return None
        mercato = r1.json()
        if not mercato or not (mercato.get("locality") or mercato.get("region") or mercato.get("country")):
            print(f"[AIRROI] lookup non ha risolto nessuna localita': {mercato}")
            return None

        r2 = requests.get(
            f"{AIRROI_BASE}/calculator/estimate",
            params={
                "lat": lat_f, "lng": lon_f,
                "bedrooms": bedrooms, "baths": baths, "guests": guests,
                "currency": "native",
            },
            headers=headers, timeout=timeout_stima,
        )
        print(f"[AIRROI] estimate locality={mercato.get('locality')} district={mercato.get('district')} -> status={r2.status_code} body={r2.text[:300]}")
        if r2.status_code != 200:
            return None
        stima = r2.json()

        # Retry mirato — Sessione 67. Osservato su Quarto (23/7): a parità
        # esatta di parametri, alcune risposte di /calculator/estimate
        # arrivano SENZA comparable_listings (Quick: 4 comparabili; due Base
        # nello stesso giorno: 0). Quando succede, l'occupazione ricade sul
        # correttivo generico (più conservativo) e il report ne risente.
        # Una singola ripetizione della chiamata, solo in questo caso,
        # raddoppia la probabilità di agganciare il dato reale al costo di
        # una chiamata AirROI extra occasionale.
        _cl = stima.get("comparable_listings")
        if not (isinstance(_cl, list) and len(_cl) >= 3):
            print("[AIRROI] estimate senza comparable_listings — retry singolo")
            try:
                r2b = requests.get(
                    f"{AIRROI_BASE}/calculator/estimate",
                    params={
                        "lat": lat_f, "lng": lon_f,
                        "bedrooms": bedrooms, "baths": baths, "guests": guests,
                        "currency": "native",
                    },
                    headers=headers, timeout=timeout_stima,
                )
                if r2b.status_code == 200:
                    stima_b = r2b.json()
                    _cl_b = stima_b.get("comparable_listings")
                    if isinstance(_cl_b, list) and len(_cl_b) >= 3:
                        print(f"[AIRROI] retry riuscito — comparable_listings={len(_cl_b)}")
                        stima = stima_b
                    else:
                        print("[AIRROI] retry senza comparabili — si procede col dato disponibile")
            except Exception as _e_retry:
                print(f"[AIRROI] retry fallito ({_e_retry!r}) — si procede col dato disponibile")

        adr = stima.get("average_daily_rate")
        occ = stima.get("occupancy")
        if not adr or occ is None:
            print(f"[AIRROI] adr/occupancy mancanti nella risposta: {stima}")
            return None

        distribuzione_mensile = stima.get("monthly_revenue_distributions")
        if not (isinstance(distribuzione_mensile, list) and len(distribuzione_mensile) == 12
                and all(isinstance(v, (int, float)) and v > 0 for v in distribuzione_mensile)):
            distribuzione_mensile = None

        comparable_listings = stima.get("comparable_listings")
        if not (isinstance(comparable_listings, list) and len(comparable_listings) >= 3):
            comparable_listings = None

        # I percentili di ricavo arrivano da AirROI anche quando non ci sono
        # comparable_listings individuali: dato reale di mercato, usabile per
        # costruire un range di prezzo zona invece dell'invenzione AI.
        # Sessione 64.
        _perc_rev = stima.get("percentiles", {}).get("revenue") if isinstance(stima.get("percentiles"), dict) else None
        percentili_revenue = None
        if isinstance(_perc_rev, dict) and _perc_rev.get("p25") and _perc_rev.get("p75"):
            percentili_revenue = {
                "p25": float(_perc_rev["p25"]), "p50": float(_perc_rev.get("p50") or 0),
                "p75": float(_perc_rev["p75"]), "p90": float(_perc_rev.get("p90") or 0),
            }

        # Percentili prezzo/occupazione zona (B9, Sessione 79) — stessa fonte
        # di percentili_revenue sopra (mai usata nel PDF finora), qui invece
        # letta anche per average_daily_rate/occupancy: catturata una
        # risposta reale non troncata (via /debug-airroi-raw) per verificare
        # che questi campi esistessero davvero prima di costruirci sopra una
        # pagina — vedi RU_Log_Sessione_2026-08-27.
        _perc = stima.get("percentiles") if isinstance(stima.get("percentiles"), dict) else {}
        _perc_adr = _perc.get("average_daily_rate") if isinstance(_perc.get("average_daily_rate"), dict) else None
        percentili_prezzo = None
        if isinstance(_perc_adr, dict) and _perc_adr.get("p25") and _perc_adr.get("p75"):
            percentili_prezzo = {
                "p25": round(_perc_adr["p25"]), "p50": round(_perc_adr.get("p50") or 0),
                "p75": round(_perc_adr["p75"]), "p90": round(_perc_adr.get("p90") or 0),
            }
        _perc_occ = _perc.get("occupancy") if isinstance(_perc.get("occupancy"), dict) else None
        percentili_occupazione = None
        if isinstance(_perc_occ, dict) and _perc_occ.get("p25") and _perc_occ.get("p75"):
            percentili_occupazione = {
                "p25": round(_perc_occ["p25"] * 100), "p50": round((_perc_occ.get("p50") or 0) * 100),
                "p75": round(_perc_occ["p75"] * 100), "p90": round((_perc_occ.get("p90") or 0) * 100),
            }

        # Split gestione professionale/privata e posizionamento stagionale
        # (ultimi 90gg vs media 12 mesi) sugli stessi comparable_listings
        # reali già usati altrove (prezzo per tipologia). Soglia più alta (5)
        # di quella per il prezzo (3): qui il dato è una percentuale/media
        # aggregata, serve un campione un po' più solido per non essere
        # rumore. NON è un trend pluriennale — L90D è la stagione corrente,
        # TTM la media dell'intero anno: la pagina deve essere onesta su
        # questo, non spacciarlo per "il mercato sta crescendo".
        _cl_raw = stima.get("comparable_listings")
        pct_gestione_professionale = None
        n_comparabili_gestione = 0
        trend_stagionale = None
        if isinstance(_cl_raw, list) and len(_cl_raw) >= 5:
            _annunci_dict = [a for a in _cl_raw if isinstance(a, dict)]
            n_comparabili_gestione = len(_annunci_dict)
            _prof = [1 for a in _annunci_dict
                     if a.get("host_info", {}).get("professional_management") is True]
            pct_gestione_professionale = round(100 * len(_prof) / n_comparabili_gestione) if n_comparabili_gestione else None

            def _media_metrica(chiave):
                valori = [a["performance_metrics"][chiave] for a in _annunci_dict
                          if isinstance(a.get("performance_metrics"), dict)
                          and isinstance(a["performance_metrics"].get(chiave), (int, float))]
                return (sum(valori) / len(valori)) if valori else None

            _occ_ttm, _occ_l90d = _media_metrica("ttm_occupancy"), _media_metrica("l90d_occupancy")
            _adr_ttm, _adr_l90d = _media_metrica("ttm_avg_rate"), _media_metrica("l90d_avg_rate")
            _revpar_ttm, _revpar_l90d = _media_metrica("ttm_revpar"), _media_metrica("l90d_revpar")
            if None not in (_occ_ttm, _occ_l90d, _adr_ttm, _adr_l90d, _revpar_ttm, _revpar_l90d):
                trend_stagionale = {
                    "occupazione_ttm": round(_occ_ttm * 100), "occupazione_l90d": round(_occ_l90d * 100),
                    "prezzo_ttm": round(_adr_ttm), "prezzo_l90d": round(_adr_l90d),
                    "revpar_ttm": round(_revpar_ttm), "revpar_l90d": round(_revpar_l90d),
                }

        print(f"[AIRROI] OK — prezzo={round(float(adr))} occupazione={round(float(occ) * 100)}% distribuzione_mensile={'presente' if distribuzione_mensile else 'assente'} comparable_listings={len(comparable_listings) if comparable_listings else 0} percentili_revenue={'presente' if percentili_revenue else 'assente'} percentili_prezzo={'presente' if percentili_prezzo else 'assente'} gestione_prof={pct_gestione_professionale} trend_stagionale={'presente' if trend_stagionale else 'assente'}")
        risultato = {
            "prezzo_notte_stimato": round(float(adr)),
            "occupazione_percent": round(float(occ) * 100),
            "distribuzione_mensile": distribuzione_mensile,
            "comparable_listings": comparable_listings,
            "percentili_revenue": percentili_revenue,
            "percentili_prezzo": percentili_prezzo,
            "percentili_occupazione": percentili_occupazione,
            "pct_gestione_professionale": pct_gestione_professionale,
            "n_comparabili_gestione": n_comparabili_gestione,
            "trend_stagionale": trend_stagionale,
            "occupazione_frazione": float(occ),
        }
        _AIRROI_CACHE[_cache_key] = (time.monotonic(), risultato)
        return risultato
    except Exception as e:
        print(f"[AIRROI] eccezione: {e}")
        return None


def _calcola_moltiplicatori_dotazioni(data):
    """Solo Strategico: per ogni dotazione ASSENTE che nel modello
    deterministico del prezzo (INCREMENTO_PREZZO_PER_DOTAZIONE, la stessa
    tabella già usata per correggere il prezzo/notte reale di QUESTO
    immobile) ha un incremento reale, calcola l'impatto se il cliente la
    aggiungesse — su prezzo/notte e ricavo annuo. Righe ordinate per impatto
    decrescente. Niente coefficienti per stato/posti letto: non esiste un
    modello deterministico validato per quelli oggi (solo AirROI per il
    prezzo complessivo) — aggiungerne uno inventato di sana pianta sarebbe
    lo stesso problema appena risolto per il resto del report."""
    prezzo = data.get("prezzo_notte_stimato") or 0
    notti = data.get("notti_anno") or 0
    if not prezzo:
        return
    assenti_norm = {_norm_dotazione(d) for d in (data.get("dotazioni_assenti") or [])}
    righe = []
    for nome, incremento in INCREMENTO_PREZZO_PER_DOTAZIONE.items():
        if nome not in assenti_norm or incremento <= 0:
            continue
        delta_prezzo = round(prezzo * incremento)
        delta_ricavo = round(delta_prezzo * notti)
        righe.append((nome, f"+{round(incremento*100)}%", delta_prezzo, delta_ricavo))
    righe.sort(key=lambda r: r[3], reverse=True)
    data["moltiplicatori_dotazioni"] = righe


def _calcola_scenari_durata_soggiorno(data):
    """Solo Strategico (B7): stesso ricavo lordo/anno (occupazione e
    prezzo/notte non cambiano — sono un dato di mercato, non una scelta
    dell'host), ma cambi ospite/anno e quindi costi di pulizia molto diversi
    a seconda della durata media soggiorno che l'host sceglie di accettare
    (min-stay su Airbnb/Booking). Riusa la stessa formula cambi = notti /
    durata già validata da _arricchisci_report_deterministico (Sessione 67)
    — qui applicata a 3 durate fisse (breve/media reale di zona/lunga)
    invece che alla sola media di categoria. Biancheria/utenze/manutenzione/
    commissioni/mutuo restano costi fissi indipendenti dal numero di cambi
    (nessun modello deterministico validato oggi per farli scalare)."""
    prezzo = data.get("prezzo_notte_stimato") or 0
    notti = data.get("notti_anno") or 0
    ricavi_totali = data.get("totale_ricavi") or 0
    if not (prezzo and notti and ricavi_totali):
        return

    pulizia_unit = data.get("costi_pulizie_unit", 35)
    _costi_fissi = (
        data.get("costi_commissioni", 0) + data.get("costi_biancheria", 0)
        + data.get("costi_utenze", 0) + data.get("costi_manutenzione", 0)
        + (data.get("rata_mutuo_mensile", 0) * 12 if data.get("mutuo_attivo") else 0)
    )
    def _scenario(label, durata, nota):
        cambi = max(1, round(notti / durata))
        costi_pulizie = round(pulizia_unit * cambi)
        costi_totali = round(_costi_fissi + costi_pulizie)
        profitto = ricavi_totali - costi_totali
        return {
            "label": label, "durata": durata, "cambi": cambi,
            "costi_pulizie": costi_pulizie, "costi_totali": costi_totali,
            "profitto_netto": profitto,
            "margine": round(profitto / ricavi_totali * 100) if ricavi_totali else 0,
            "nota": nota,
        }

    # Durate fisse 2 / 7 / 14 notti. Prima la colonna centrale usava la media
    # reale di zona: su una città come Napoli vale 2 notti, quindi le prime due
    # colonne uscivano identiche (2 / 2 / 7) e il confronto non diceva niente.
    # Tre durate distanti mostrano davvero l'effetto del min-stay sui cambi.
    data["scenari_durata"] = [
        _scenario("SOGGIORNI BREVI", 2,
                  "Weekend e city break: min-stay 1-2 notti — massimo turnover, più pulizie"),
        _scenario("SOGGIORNI MEDI", 7,
                  "Min-stay settimanale: vacanze e smart working — turnover dimezzato"),
        _scenario("SOGGIORNI LUNGHI", 14,
                  "Min-stay quindicinale: soggiorni lunghi e trasferte — turnover minimo"),
    ]


def _calcola_valore_asset(data):
    """Solo Strategico (pag. 13). EBITDA e valore di mercato come asset B&B
    erano gli ultimi numeri economici ancora inventati dall'AI, mentre tutto
    il resto del report è deterministico dalla riapertura del cantiere: la
    pagina poteva quindi mostrare un EBITDA scollegato dal profitto netto
    stampato due pagine prima. Qui si ricalcolano dai valori reali già
    corretti — EBITDA = profitto netto, valore = EBITDA capitalizzato al
    saggio. valore_immobile_stimato resta un dato che oggi non abbiamo
    (nessuna fonte OMI di compravendita in pipeline): se l'AI non lo fornisce
    resta 0 e la pagina lo dichiara n/d, senza inventarlo."""
    saggio = data.get("saggio_capitalizzazione") or 7.0
    profitto = data.get("profitto_netto")
    if profitto is None:
        return
    data["ebitda_stimato"] = round(profitto)
    if saggio > 0:
        data["valore_mercato"] = round(profitto / saggio * 100)


# Mappa statica (non generata dall'AI, come da principio del progetto: il
# backend decide i fatti strutturali, l'AI scrive solo il testo libero) da
# obiettivo cliente a pagina del PDF Strategico più rilevante — usata da
# page_obiettivi in strategico.py. Numerazione allineata alla sequenza reale
# in build_strategico_pdf_bytes (17 pagine da quando è stato aggiunto il
# riepilogo finale): aggiornare qui se cambia l'ordine o il numero di pagine.
_OBIETTIVI_PAGINE_STRATEGICO = {
    "massimizzare_guadagno":    ("Pag. 6-10", "Moltiplicatori di valore, scenari economici, durata soggiorno e dati di mercato extra"),
    "confronto_affitto":        ("Pag. 7", "Confronto con l'affitto tradizionale"),
    "primo_avvio":              ("Pag. 11", "Piano d'azione primi 90 giorni"),
    "ottimizzare_esistente":    ("Pag. 6", "Moltiplicatori di valore — dotazioni"),
    "valutazione_investimento": ("Pag. 13", "Valore immobile come asset B&B"),
    "pianificazione_normativa": ("Pag. 12", "Normativa affitti brevi"),
}


def _mesi_affidabili(oggi=None):
    import datetime
    oggi = oggi or datetime.date.today()
    mese_partenza = (oggi.month - 1) if oggi.day <= 15 else oggi.month
    return [(mese_partenza + i) % 12 for i in range(3)]


_GIORNI_MESE = {
    "Gen": 31, "Feb": 28, "Mar": 31, "Apr": 30, "Mag": 31, "Giu": 30,
    "Lug": 31, "Ago": 31, "Set": 30, "Ott": 31, "Nov": 30, "Dic": 31,
}


def _calcola_trimestre_affidabile(data):
    """Solo Strategico (ToDo Sessione 65): media sui 3 mesi immediatamente
    successivi alla data di generazione — stessi indici già usati dal Base
    per evidenziare i 'mesi affidabili' nel grafico occupazione
    (_mesi_affidabili: dato AirROI reale, non stima annua diluita), qui
    trattati come sezione aggregata A PARTE — prezzo medio, occupazione
    media, ricavo atteso nel trimestre — accanto alla curva a 12 mesi già
    presente, non al posto di quella."""
    occ = data.get("occupazione") or []
    idx = data.get("mesi_affidabili_idx") or []
    righe = [occ[i] for i in idx if 0 <= i < len(occ)]
    if len(righe) != 3:
        return
    prezzi = [r[2] for r in righe]
    occupazioni = [r[1] for r in righe]
    ricavo_trimestre = sum(
        round(r[2] * _GIORNI_MESE.get(r[0], 30) * r[1] / 100) for r in righe
    )
    data["trimestre_mesi_label"] = " – ".join(r[0] for r in righe)
    data["trimestre_prezzo_medio"] = round(sum(prezzi) / len(prezzi))
    data["trimestre_occupazione_media"] = round(sum(occupazioni) / len(occupazioni))
    data["trimestre_ricavo_atteso"] = ricavo_trimestre


# ── Normalizzazione occupazione a 12 mesi — Sessione 72 ─────────────────────
# Bug reale (Positano, Sessione 72): quando l'AI dimentica un mese nel suo
# JSON (es. manca "Mag", 11 righe invece di 12), _applica_stagionalita_airroi
# qui sotto ha una guardia di sicurezza "len(occ) != 12: return occ" che, con
# un mese mancante, restituiva l'array INTATTO senza applicare nessuna
# correzione — né la curva generica (applica_curva), né la stagionalità
# reale AirROI. Il cliente vedeva la tabella segnaposto scritta nel prompt
# AI, con prezzi bassissimi e del tutto scollegati dal resto del report
# (es. prezzo/notte annuo € 284 ma tabella mensile che arrivava a € 112).
# Fix: ricostruire SEMPRE 12 righe nei 12 mesi canonici, in ordine, prima
# che qualunque logica di stagionalità venga applicata — così quella
# guardia (voluta, e giusta di per sé) non scatta mai più per questo
# motivo. I valori di un eventuale mese mancante sono solo un placeholder
# (copiati dal mese precedente): non hanno importanza perché vengono
# SEMPRE sovrascritti subito dopo da applica_curva o
# _applica_stagionalita_airroi, che ricalcolano ogni riga dal livello
# annuo reale (prezzo/occupazione corretti da AirROI). Su un report già
# corretto (12 mesi, ordine giusto — es. Napoli, Milano) questa funzione
# non cambia nulla: puro passthrough, zero rischio di regressione.
_MESI_CANONICI = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
                   "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]


def _normalizza_occupazione_12_mesi(occ):
    per_mese = {}
    for row in (occ or []):
        if not row:
            continue
        nome = str(row[0]).strip()[:3].capitalize()
        riga = list(row) + ["\u2014"] * max(0, 4 - len(row))
        per_mese[nome] = riga[:4]

    ricostruita = []
    precedente = None
    for nome in _MESI_CANONICI:
        if nome in per_mese:
            riga = [nome] + per_mese[nome][1:]
        elif precedente is not None:
            riga = [nome, precedente[1], precedente[2], precedente[3]]
        else:
            riga = [nome, 50, 0, "Media"]
        ricostruita.append(riga)
        precedente = riga
    return ricostruita


def _applica_stagionalita_airroi(occ, distribuzione_mensile, adr_annuale, occ_annuale=None, tetto_massimo=85):
    if not occ or not distribuzione_mensile or len(occ) != 12:
        return occ
    media = sum(distribuzione_mensile) / 12
    if media <= 0:
        return occ
    # Etichette stagione ricalcolate dal RANKING dei pesi reali AirROI —
    # Sessione 67. Prima restavano quelle scritte dall'AI nel template
    # (Lug/Ago sempre "Peak"): a Roma/Milano il dato reale ha i picchi in
    # primavera/autunno, e il PDF mostrava mesi "Media" al 98% accanto a
    # "Peak" all'87%. Stesso schema di applica_curva: top2=Peak, poi
    # 4=Alta, 3=Media, 3=Bassa.
    _ordine = sorted(range(12), key=lambda i: distribuzione_mensile[i], reverse=True)
    _etichetta = [""] * 12
    for _rank, _i in enumerate(_ordine):
        if _rank < 2:
            _etichetta[_i] = "Peak"
        elif _rank < 6:
            _etichetta[_i] = "Alta"
        elif _rank < 9:
            _etichetta[_i] = "Media"
        else:
            _etichetta[_i] = "Bassa"
    nuova = []
    for i, row in enumerate(occ):
        peso = distribuzione_mensile[i] / media
        # Smorzamento simmetrico sul prezzo (Sessione 66) — anche quando il
        # dato mensile è reale (AirROI), un picco non deve raddoppiare il
        # prezzo medio: stesso meccanismo già applicato alla curva curata,
        # per coerenza indipendentemente dalla fonte del dato.
        peso_prezzo = stagionalita_turistica.smorza_peso_prezzo(peso)
        prezzo_mese = max(1, round(adr_annuale * peso_prezzo))
        nuova_row = [row[0], row[1], prezzo_mese, _etichetta[i]] + list(row[4:])
        if occ_annuale is not None:
            # Sessione 67: smorzamento occupazione lato basso anche sulla
            # distribuzione mensile reale AirROI — nei mercati piccoli il suo
            # dato di bassa stagione eredita la stessa sottostima che
            # correggiamo altrove (stesso principio della curva bimodale).
            peso_occ_mese = stagionalita_turistica.smorza_peso_occupazione(peso)
            nuova_row[1] = max(5, min(tetto_massimo, round(occ_annuale * peso_occ_mese)))
        nuova.append(nuova_row)
    return nuova


# ── Colori brand ──────────────────────────────────────────────────────────────
BLUE_NIGHT   = HexColor("#0D1F2D")
BLUE_PRIMARY = HexColor("#2196C4")
TEAL         = HexColor("#0D9E5C")
TEAL_LIGHT   = HexColor("#E8F8F0")
GOLD         = HexColor("#C9A227")
GOLD_LIGHT   = HexColor("#FFF8E7")
RED          = HexColor("#C0392B")
RED_LIGHT    = HexColor("#FDEDEC")
CREAM        = HexColor("#FAF8F4")
MUTED        = HexColor("#7A8A96")
BORDER       = HexColor("#DDD4C8")
WHITE        = HexColor("#FFFFFF")
LIGHT_GRAY   = HexColor("#E8E8E8")
DARK_TEXT    = HexColor("#1A1A2E")

W, H = A4

AEROPORTI_ITALIA = [
    ("Aeroporto di Roma Fiumicino", 41.8003, 12.2389),
    ("Aeroporto di Roma Ciampino", 41.7994, 12.5949),
    ("Aeroporto di Milano Malpensa", 45.6306, 8.7281),
    ("Aeroporto di Milano Linate", 45.4451, 9.2767),
    ("Aeroporto di Bergamo Orio al Serio", 45.6739, 9.7042),
    ("Aeroporto di Venezia Marco Polo", 45.5053, 12.3519),
    ("Aeroporto di Treviso", 45.6484, 12.1944),
    ("Aeroporto di Bologna Marconi", 44.5354, 11.2887),
    ("Aeroporto di Firenze Peretola", 43.8100, 11.2051),
    ("Aeroporto di Pisa Galileo Galilei", 43.6839, 10.3927),
    ("Aeroporto di Napoli Capodichino", 40.8860, 14.2908),
    ("Aeroporto di Bari Palese", 41.1389, 16.7606),
    ("Aeroporto di Brindisi", 40.6576, 17.9470),
    ("Aeroporto di Catania Fontanarossa", 37.4668, 15.0664),
    ("Aeroporto di Palermo Falcone Borsellino", 38.1760, 13.0910),
    ("Aeroporto di Trapani Birgi", 37.9116, 12.4880),
    ("Aeroporto di Cagliari Elmas", 39.2515, 9.0543),
    ("Aeroporto di Olbia Costa Smeralda", 40.8987, 9.5176),
    ("Aeroporto di Alghero Fertilia", 40.6321, 8.2908),
    ("Aeroporto di Genova Sestri", 44.4133, 8.8375),
    ("Aeroporto di Torino Caselle", 45.2008, 7.6496),
    ("Aeroporto di Verona Villafranca", 45.3957, 10.8885),
    ("Aeroporto di Trieste Ronchi dei Legionari", 45.8275, 13.4722),
    ("Aeroporto di Ancona Falconara", 43.6163, 13.3623),
    ("Aeroporto di Pescara", 42.4316, 14.1810),
    ("Aeroporto di Lamezia Terme", 38.9054, 16.2423),
    ("Aeroporto di Reggio Calabria", 38.0712, 15.6516),
    ("Aeroporto di Comiso", 36.9948, 14.6071),
    ("Aeroporto di Perugia San Francesco d'Assisi", 43.0959, 12.5132),
    ("Aeroporto di Parma", 44.8245, 10.2964),
    ("Aeroporto di Rimini Federico Fellini", 44.0203, 12.6117),
    ("Aeroporto di Forli", 44.1944, 12.0701),
    ("Aeroporto di Salerno Costa d'Amalfi", 40.6204, 14.9114),
    ("Aeroporto di Foggia Gino Lisa", 41.4324, 15.5350),
    ("Aeroporto di Crotone", 39.0019, 17.0801),
    ("Aeroporto di Albenga", 44.0506, 8.1270),
    ("Aeroporto di Pantelleria", 36.8166, 11.9689),
    ("Aeroporto di Lampedusa", 35.4980, 12.6182),
]


DOTAZIONI_AMMESSE = ["WiFi", "Parcheggio", "Aria condizionata", "Lavatrice", "Cucina attrezzata",
                     "Terrazzo", "Giardino", "Riscaldamento", "Ascensore", "Piscina"]

_DOTAZIONI_SINONIMI = {
    "wifi": "WiFi", "wi-fi": "WiFi", "wi fi": "WiFi",
    "parcheggio": "Parcheggio",
    "aria_condizionata": "Aria condizionata", "aria condizionata": "Aria condizionata",
    "lavatrice": "Lavatrice",
    "cucina": "Cucina attrezzata", "cucina attrezzata": "Cucina attrezzata",
    "terrazzo": "Terrazzo", "terrazza": "Terrazzo",
    "terrazzo / giardino": "Terrazzo", "terrazzo/giardino": "Terrazzo",
    "giardino": "Giardino",
    "riscaldamento": "Riscaldamento",
    "ascensore": "Ascensore",
    "piscina": "Piscina",
}


def _norm_dotazione(d):
    return _DOTAZIONI_SINONIMI.get(str(d or "").strip().lower(), str(d or "").strip())


# ── Incremento prezzo/notte per dotazione — Sessione 66 ──────────────────────
# Non tutte le dotazioni influenzano il prezzo di mercato: WiFi, aria
# condizionata, riscaldamento e fino a 2 bagni sono ormai standard in
# qualsiasi annuncio short-rental e non giustificano un incremento (a
# differenza di quanto già fatto sui COSTI di gestione, dove restano
# rilevanti). Solo le dotazioni che aggiungono valore percepito reale hanno
# un incremento, deciso da Salvatore su base esperienza diretta (30.000+
# valutazioni): cucina attrezzata e ascensore leggermente sopra lo standard
# (+2%), giardino/terrazzo/lavatrice un vantaggio concreto ma comune (+3%),
# parcheggio (+5%, sempre richiesto e spesso assente), piscina (+7%, il
# fattore più raro e più valorizzato). Gli incrementi si sommano (additivi,
# non composti) se l'immobile ha più dotazioni valorizzate insieme.
INCREMENTO_PREZZO_PER_DOTAZIONE = {
    "Cucina attrezzata": 0.02,
    "Ascensore": 0.02,
    "Giardino": 0.03,
    "Terrazzo": 0.03,
    "Lavatrice": 0.03,
    "Parcheggio": 0.05,
    "Piscina": 0.07,
    # WiFi, Aria condizionata, Riscaldamento: 0 — standard di mercato, nessun incremento.
}


def _moltiplicatore_dotazioni(dotazioni_presenti):
    """Ritorna il moltiplicatore da applicare al prezzo/notte in base alle
    dotazioni dichiarate presenti (es. 1.05 = +5%). Dotazioni non elencate
    in INCREMENTO_PREZZO_PER_DOTAZIONE (WiFi, aria condizionata,
    riscaldamento, bagni) non aggiungono nulla — sono ormai standard."""
    presenti_norm = {_norm_dotazione(d) for d in (dotazioni_presenti or [])}
    incremento = sum(v for nome, v in INCREMENTO_PREZZO_PER_DOTAZIONE.items() if nome in presenti_norm)
    return 1 + incremento


# ── Camere per tipologia — Sessione 66 ───────────────────────────────────────
# Prima il campo "camere" veniva lasciato calcolare liberamente all'AI dal
# prompt ("[calcola da posti letto e superficie]"), senza nessuna verifica —
# e l'AI può sbagliare: un "Bilocale" è per definizione 1 camera da letto
# (due locali = camera + soggiorno/cucina), ma l'AI ha scritto "2" in un test
# reale (Quarto, Sessione 66), gonfiando artificialmente la stima AirROI
# (più camere dichiarate = stima più alta) rispetto al Quick, che usa questa
# stessa mappa fissa e quindi restava corretto. Stesso principio già
# applicato al Quick, ora deterministico anche nel Base: la tipologia
# decide le camere, non l'AI.
# ── Mappa unica Tipologia → Camere + Posti letto — Sessione 75 ────────────────
# FONTE DI VERITÀ UNICA per la relazione tipologia→camere→posti letto in tutto
# il sistema. Prima esistevano mappe parallele scollegate: questa mappa nel
# backend (camere), una diversa nei form Quick in JS (stanza doppia = 1 camera
# qui, 0 nel backend → disallineamento reale), e nessuna guida sui posti letto.
# Ora un solo posto decide entrambi, e i 3 form HTML replicano ESATTAMENTE
# questi stessi valori (mappa JS TIPOLOGIA_MAP con commento-sentinella:
# qualunque modifica qui va riportata identica nei 3 file HTML).
#
# camere = camere DA LETTO separate → è ciò che AirROI riceve come `bedrooms`.
#   Una stanza (singola/doppia) è essa stessa l'ambiente: 0 camere separate.
#   Un bilocale = 2 locali = 1 camera + soggiorno → 1 camera. E così via.
# posti_default = valore preselezionato nel form quando si sceglie la tipologia
#   (modificabile liberamente dall'utente, non è un vincolo).
#
# Ordine: dal più specifico al più generico, il primo frammento che matcha
# vince (es. "casa indipendente" prima di eventuali match parziali).
_TIPOLOGIA_MAP = [
    # (frammento_tipologia, camere, posti_default)
    # I frammenti sono confrontati in minuscolo con `in`: mettere i più
    # specifici PRIMA dei più generici. Le etichette reali inviate dai form
    # sono "Stanza singola", "Stanza doppia", "Bilocale", "Trilocale",
    # "Appartamento 4+ locali", "Villa / Casa indipendente" — i frammenti qui
    # sotto devono matchare quelle stringhe (verificato: "4+ locali" cattura
    # l'appartamento grande, "casa indipendente" e "villa" catturano l'ultima).
    ("stanza singola", 0, 1),
    ("stanza doppia", 0, 2),
    ("monolocale", 0, 2),
    ("bilocale", 1, 3),
    ("trilocale", 2, 4),
    ("quadrilocale", 3, 6),
    ("4+ locali", 3, 6),
    ("4 locali", 3, 6),
    ("appartamento grande", 3, 6),
    ("casa indipendente", 4, 8),
    ("villa", 4, 8),
]


def _match_tipologia(tipologia):
    """Ritorna la tupla (camere, posti_default) per la tipologia dichiarata,
    oppure None se non riconosciuta (testo libero non standard).

    Accetta sia le etichette leggibili inviate da Base/Strategico
    ("Appartamento 4+ locali") sia i value grezzi del select inviati dal Quick
    ("appartamento_grande"): gli underscore vengono normalizzati in spazi prima
    del confronto, così una sola mappa copre entrambe le forme."""
    t = str(tipologia or "").strip().lower().replace("_", " ")
    for frammento, camere, posti in _TIPOLOGIA_MAP:
        if frammento in t:
            return camere, posti
    return None


def _camere_deterministiche(tipologia, camere_ai):
    """Ritorna il numero di camere corretto per la tipologia dichiarata,
    ignorando quanto scritto dall'AI se riconosciamo la tipologia. Se la
    tipologia non è tra quelle note (es. testo libero non standard),
    manteniamo il valore dell'AI invece di inventare un fallback arbitrario."""
    m = _match_tipologia(tipologia)
    if m is not None:
        return str(m[0])
    return camere_ai


def _posti_letto_default(tipologia, posti_esistente=None):
    """Ritorna il numero di posti letto di default per la tipologia dichiarata.
    Se l'utente ha già fornito un valore di posti letto (posti_esistente),
    quello vince SEMPRE: il default serve solo come fallback quando il campo
    è vuoto/assente. Se la tipologia non è riconosciuta e non c'è un valore
    esistente, ritorna posti_esistente così com'è (nessun default inventato)."""
    if posti_esistente not in (None, "", "0"):
        return posti_esistente
    m = _match_tipologia(tipologia)
    if m is not None:
        return str(m[1])
    return posti_esistente


def _zona_sembra_valida(testo):
    t = str(testo or "").strip()
    if not t:
        return True
    return re.search(r'\b(of|the|zone|district|area)\b', t, re.IGNORECASE) is None


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def aeroporto_row(lat, lon, max_km=120):
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return ["\u2014", "\u2014", "\u2014"]

    best_name, best_dist, best_lat, best_lon = None, None, None, None
    for nome, alat, alon in AEROPORTI_ITALIA:
        d = _haversine_km(lat, lon, alat, alon)
        if best_dist is None or d < best_dist:
            best_dist, best_name, best_lat, best_lon = d, nome, alat, alon

    if best_dist is None or best_dist > max_km:
        return ["\u2014", "\u2014", "\u2014"]

    dist_km = round(best_dist)

    auto = territorio_gps.distanza_e_tempo_auto(lat, lon, best_lat, best_lon)
    if auto:
        km_auto, min_auto = auto
        distanza_str = f"{km_auto} km · {min_auto} min in auto"
        km_impatto = km_auto
    else:
        distanza_str = f"{dist_km} km (linea d'aria)"
        km_impatto = dist_km

    # Impatto sui km REALI su strada (quando disponibili), non sulla linea
    # d'aria — Sessione 67. Caso reale Atrani: 25 km in linea d'aria
    # dall'aeroporto di Salerno -> "Alto", ma la strada della Costiera ne
    # fa 44 in 68 minuti: per il lettore i due dati stridevano nella
    # stessa riga. Ora etichetta e distanza mostrata usano lo stesso numero.
    if km_impatto <= 30:
        impatto = "Alto"
    elif km_impatto <= 70:
        impatto = "Medio"
    else:
        impatto = "Basso"

    return [distanza_str, best_name, impatto]


# ── Helper ────────────────────────────────────────────────────────────────────

def draw_header(c, data):
    header_h = 16 * mm
    c.setFillColor(BLUE_NIGHT)
    c.rect(0, H - header_h, W, header_h, fill=1, stroke=0)
    lx, ly = 14 * mm, H - 10.5 * mm
    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(WHITE)
    c.drawString(lx, ly, "Report")
    tw = c.stringWidth("Report", "Helvetica-Bold", 13)
    c.setFillColor(BLUE_PRIMARY)
    c.drawString(lx + tw, ly, "Up")
    c.setFont("Helvetica", 8)
    c.setFillColor(WHITE)
    c.drawRightString(W - 14 * mm, H - 8 * mm, "Analisi di mercato B&B")
    c.setFont("Helvetica", 7)
    c.setFillColor(HexColor("#A8BCC8"))
    c.drawRightString(W - 14 * mm, H - 13 * mm,
                      f"Generato: {data.get('data_generazione', '')}  \u00b7  Valido 90 giorni")


TOTALE_PAGINE_BASE = 5


def draw_footer(c, page_num, total=TOTALE_PAGINE_BASE):
    footer_h = 9 * mm
    c.setFillColor(BLUE_NIGHT)
    c.rect(0, 0, W, footer_h, fill=1, stroke=0)
    c.setFont("Helvetica", 6.5)
    c.setFillColor(HexColor("#A8BCC8"))
    from datetime import date as _date
    c.drawString(14 * mm, 3.5 * mm,
                 f"\u00a9 {_date.today().year} ReportUp \u00b7 reportup.it  |  Documento orientativo - non costituisce consulenza professionale")
    # "Pag. 4 / 5" invece del solo numero: stesso formato dello Strategico,
    # che essendo lungo 17 pagine ha bisogno del totale per orientarsi.
    c.drawRightString(W - 14 * mm, 3.5 * mm, f"Pag. {page_num} / {total}")


def draw_section_header(c, x, y, w, text):
    h = 7 * mm
    c.setFillColor(BLUE_PRIMARY)
    c.rect(x, y - h, w, h, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(WHITE)
    c.drawString(x + 3 * mm, y - h + 2.2 * mm, text)
    return y - h


def draw_section_subtitle(c, x, y, text):
    c.setFont("Helvetica-Oblique", 7.5)
    c.setFillColor(MUTED)
    c.drawString(x, y, text)


def fmt_eur(val):
    return f"€ {int(val):,}".replace(",", ".")


def stage_color(stage):
    if stage == "Peak":  return GOLD
    if stage == "Alta":  return TEAL
    if stage == "Media": return BLUE_PRIMARY
    return MUTED


def wrap_text(c, text, x, y, max_w, font, size, line_h):
    segments = []
    remaining = text
    while "[B]" in remaining:
        pre, rest = remaining.split("[B]", 1)
        bold_text, remaining = rest.split("[/B]", 1)
        if pre:
            segments.append((pre, False))
        segments.append((bold_text, True))
    if remaining:
        segments.append((remaining, False))

    tokens = []
    for seg_text, is_bold in segments:
        for w in seg_text.split(" "):
            if w:
                tokens.append((w, is_bold))

    line_tokens = []
    line_w = 0

    def draw_line(lt, yy):
        cx = x
        for w, bold in lt:
            fn = "Helvetica-Bold" if bold else font
            c.setFont(fn, size)
            c.setFillColor(BLUE_NIGHT)
            c.drawString(cx, yy, w)
            cx += c.stringWidth(w + " ", fn, size)

    for tok, bold in tokens:
        fn = "Helvetica-Bold" if bold else font
        tw = c.stringWidth(tok + " ", fn, size)
        if line_w + tw > max_w and line_tokens:
            draw_line(line_tokens, y)
            y -= line_h
            line_tokens = [(tok, bold)]
            line_w = tw
        else:
            line_tokens.append((tok, bold))
            line_w += tw

    if line_tokens:
        draw_line(line_tokens, y)
        y -= line_h
    return y


def draw_wrapped_text(c, text, x, y, max_w, font_name, size, line_h, color=None):
    if color:
        c.setFillColor(color)
    words = text.split()
    line = ""
    for w in words:
        test = line + (" " if line else "") + w
        if c.stringWidth(test, font_name, size) > max_w:
            c.setFont(font_name, size)
            c.drawString(x, y, line)
            y -= line_h
            line = w
        else:
            line = test
    if line:
        c.setFont(font_name, size)
        c.drawString(x, y, line)
        y -= line_h
    return y


# ── Pagine ────────────────────────────────────────────────────────────────────

def page1(c, D):
    draw_header(c, D)
    draw_footer(c, 1)
    y = H - 22 * mm

    pill_label = "REPORT BASE"
    c.setFont("Helvetica-Bold", 10)
    pl_w = c.stringWidth(pill_label, "Helvetica-Bold", 10) + 12 * mm
    pl_h = 8 * mm
    c.setFillColor(BLUE_PRIMARY)
    c.roundRect(W / 2 - pl_w / 2, y - pl_h, pl_w, pl_h, 2 * mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.drawCentredString(W / 2, y - pl_h + 2.5 * mm, pill_label)
    y -= pl_h + 4 * mm

    sub_label = "IL TUO INVESTIMENTO"
    c.setFont("Helvetica", 8)
    sl_w = c.stringWidth(sub_label, "Helvetica", 8) + 10 * mm
    sl_h = 6 * mm
    c.setFillColor(BLUE_NIGHT)
    c.roundRect(W / 2 - sl_w / 2, y - sl_h, sl_w, sl_h, 1.5 * mm, fill=1, stroke=0)
    c.setFillColor(HexColor("#A8BCC8"))
    c.drawCentredString(W / 2, y - sl_h + 1.8 * mm, sub_label)
    y -= sl_h + 5 * mm

    box_h = 16 * mm
    c.setFillColor(BLUE_NIGHT)
    c.rect(14 * mm, y - box_h, W - 28 * mm, box_h, fill=1, stroke=0)
    c.setFillColor(WHITE)
    indirizzo_txt = D.get("indirizzo", "")
    max_w_ind = W - 36 * mm
    for font_size in [18, 16, 14, 12, 10]:
        c.setFont("Helvetica-Bold", font_size)
        if c.stringWidth(indirizzo_txt, "Helvetica-Bold", font_size) <= max_w_ind:
            break
    c.drawCentredString(W / 2, y - box_h / 2 - font_size * 0.18 * mm, indirizzo_txt)
    y -= box_h + 5 * mm

    y = draw_section_header(c, 14 * mm, y, W - 28 * mm, "Scheda immobile")
    y -= 2 * mm
    col_w = (W - 28 * mm) / 2
    # Le chiavi `scheda_*` (_prepara_etichette_scheda) portano l'etichetta già
    # leggibile — codici del form tradotti e unità di misura aggiunte ai numeri
    # nudi di camere/bagni/posti letto — e sono le stesse lette dallo
    # Strategico, così la scheda si legge identica sui due PDF. I campi
    # originali di D restano intatti: i calcoli a valle continuano a leggere
    # quelli.
    fields_l = [("Tipologia", D.get("scheda_tipologia") or D.get("tipologia", "")),
                ("Superficie", D.get("scheda_superficie") or D.get("superficie", "")),
                ("Piano", D.get("scheda_piano") or D.get("piano", "")),
                ("Stato", D.get("scheda_stato") or D.get("stato", "")),
                ("Camere", D.get("scheda_camere") or _concorda_numero(D.get("camere", ""), "camera", "camere"))]
    fields_r = [("Comune", D.get("comune", "")), ("Zona", D.get("zona", "")),
                ("Epoca", D.get("scheda_epoca") or D.get("epoca", "")),
                ("Bagni", D.get("scheda_bagni") or _concorda_numero(D.get("bagni", ""), "bagno", "bagni")),
                ("Posti letto", D.get("scheda_posti_letto") or _concorda_numero(D.get("posti_letto", ""), "posto letto", "posti letto"))]
    row_h = 7.5 * mm
    label_col_w = 28 * mm
    for i, ((ll, lv), (rl, rv)) in enumerate(zip(fields_l, fields_r)):
        ry = y - i * row_h
        c.setFillColor(WHITE if i % 2 == 0 else CREAM)
        c.rect(14 * mm, ry - row_h, W - 28 * mm, row_h, fill=1, stroke=0)
        c.setFillColor(HexColor("#E3F2FA"))
        c.rect(14 * mm, ry - row_h, label_col_w, row_h, fill=1, stroke=0)
        c.rect(14 * mm + col_w, ry - row_h, label_col_w, row_h, fill=1, stroke=0)
        c.setStrokeColor(BORDER)
        c.setLineWidth(0.3)
        c.line(14 * mm, ry - row_h, W - 14 * mm, ry - row_h)
        c.setFont("Helvetica-Bold", 7.5)
        c.setFillColor(BLUE_PRIMARY)
        c.drawString(17 * mm, ry - row_h + 2.5 * mm, ll)
        c.setFont("Helvetica", 7.5)
        c.setFillColor(DARK_TEXT)
        c.drawString(14 * mm + label_col_w + 2 * mm, ry - row_h + 2.5 * mm, lv)
        c.setStrokeColor(BORDER)
        c.line(14 * mm + col_w, ry, 14 * mm + col_w, ry - row_h)
        c.setFont("Helvetica-Bold", 7.5)
        c.setFillColor(BLUE_PRIMARY)
        c.drawString(14 * mm + col_w + 3 * mm, ry - row_h + 2.5 * mm, rl)
        c.setFont("Helvetica", 7.5)
        c.setFillColor(DARK_TEXT)
        c.drawString(14 * mm + col_w + label_col_w + 2 * mm, ry - row_h + 2.5 * mm, rv)
    y -= len(fields_l) * row_h + 4 * mm

    c.setFont("Helvetica", 7)
    c.setFillColor(TEAL)
    c.drawString(14 * mm, y, "Dotazioni presenti")
    y -= 5 * mm
    pill_h = 5.5 * mm
    px = 14 * mm
    presenti = [_norm_dotazione(d) for d in D.get("dotazioni_presenti", []) if _norm_dotazione(d) in DOTAZIONI_AMMESSE]
    assenti  = [_norm_dotazione(d) for d in D.get("dotazioni_assenti", [])  if _norm_dotazione(d) in DOTAZIONI_AMMESSE]
    tutte = set(presenti + assenti)
    for d in DOTAZIONI_AMMESSE:
        if d not in tutte:
            assenti.append(d)
    for d in presenti + assenti:
        presente = d in presenti
        fn = "Helvetica-Bold" if presente else "Helvetica"
        tw = c.stringWidth(d, fn, 7)
        pw = tw + 6 * mm
        if px + pw > W - 14 * mm:
            px = 14 * mm
            y -= pill_h + 1.5 * mm
        c.setFillColor(TEAL if presente else LIGHT_GRAY)
        c.roundRect(px, y - pill_h + 1 * mm, pw, pill_h, 2 * mm, fill=1, stroke=0)
        c.setFillColor(WHITE if presente else MUTED)
        c.setFont(fn, 7)
        c.drawString(px + 3 * mm, y - pill_h + 2.8 * mm, d)
        px += pw + 2 * mm
    y -= pill_h + 5 * mm

    c.setFont("Helvetica", 7)
    c.setFillColor(TEAL)
    c.drawString(14 * mm, y, "Situazione attuale dichiarata")
    y -= 5 * mm
    situazioni = [
        (f"Immobile vuoto: {'SI' if D.get('situazione_vuoto') else 'NO'}", D.get("situazione_vuoto")),
        (f"Inquilini attivi: {'SI' if D.get('situazione_inquilini') else 'NO'}", D.get("situazione_inquilini")),
        (f"B&B gia' attivo: {'SI' if D.get('situazione_bnb') else 'NO'}", D.get("situazione_bnb")),
        (f"Mutuo attivo: {'SI' if D.get('situazione_mutuo') else 'NO'}", D.get("situazione_mutuo")),
    ]
    px = 14 * mm
    for label, attivo in situazioni:
        fn = "Helvetica-Bold" if attivo else "Helvetica"
        tw = c.stringWidth(label, fn, 7)
        pw = tw + 6 * mm
        c.setFillColor(TEAL if attivo else LIGHT_GRAY)
        c.roundRect(px, y - pill_h + 1 * mm, pw, pill_h, 2 * mm, fill=1, stroke=0)
        c.setFillColor(WHITE if attivo else MUTED)
        c.setFont(fn, 7)
        c.drawString(px + 3 * mm, y - pill_h + 2.8 * mm, label)
        px += pw + 2 * mm
    y -= pill_h + 5 * mm

    y = draw_section_header(c, 14 * mm, y, W - 28 * mm, "Descrizione immobile")
    y -= 5 * mm
    y = wrap_text(c, D.get("descrizione", ""), 14 * mm, y, W - 28 * mm, "Helvetica", 8, 5.5 * mm)
    if D.get("_wikipedia_estratto"):
        c.setFont("Helvetica", 5.5)
        c.setFillColor(MUTED)
        c.drawString(14 * mm, y - 2.5 * mm, "Alcune informazioni territoriali sono tratte da fonti enciclopediche aperte (CC BY-SA).")


def page2(c, D):
    draw_header(c, D)
    draw_footer(c, 2)
    y = H - 22 * mm

    y = draw_section_header(c, 14 * mm, y, W - 28 * mm, "Posizione e punti di interesse")
    y -= 3 * mm
    draw_section_subtitle(c, 14 * mm, y, "Distanze e impatto sulla domanda di prenotazioni")
    y -= 6 * mm

    SLOT_LABELS = [
        "Trasporto pubblico",
        "Comune di riferimento",
        "Elemento caratteristico",
        "Servizi essenziali",
        "Aeroporto",
    ]

    poi_rows_raw = [list(row) for row in D.get("poi", [])]
    while len(poi_rows_raw) < 5:
        poi_rows_raw.append(["\u2014", "\u2014", "\u2014"])
    poi_rows_raw = poi_rows_raw[:5]
    poi_rows_raw[4] = aeroporto_row(D.get("lat"), D.get("long"))
    if str(D.get("categoria") or "").strip().lower() in ("capoluogo", "grande_citta"):
        poi_rows_raw[1] = ["\u2014", "\u2014", "\u2014"]

    style_cell_bold = ParagraphStyle("poiCellBold", fontName="Helvetica-Bold", fontSize=8, textColor=BLUE_NIGHT, leading=10)
    style_cell_reg  = ParagraphStyle("poiCellReg",  fontName="Helvetica",      fontSize=8, textColor=BLUE_NIGHT, leading=10)
    style_header    = ParagraphStyle("poiHeader",   fontName="Helvetica-Bold", fontSize=8, textColor=WHITE,      leading=10)

    header_labels = ["Categoria", "Distanza", "Punto di riferimento", "Impatto"]
    poi_data = [[Paragraph(h, style_header) for h in header_labels]]
    for label, row in zip(SLOT_LABELS, poi_rows_raw):
        mezzo_distanza, nome, impatto = (row + ["\u2014", "\u2014", "\u2014"])[:3]
        poi_data.append([
            Paragraph(label, style_cell_bold),
            Paragraph(str(mezzo_distanza), style_cell_reg),
            Paragraph(str(nome), style_cell_reg),
            Paragraph(str(impatto), style_cell_reg),
        ])

    col_w_poi = [(W - 28 * mm) * 0.20, (W - 28 * mm) * 0.22, (W - 28 * mm) * 0.42, (W - 28 * mm) * 0.16]
    tbl = Table(poi_data, colWidths=col_w_poi)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLUE_NIGHT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, CREAM]),
        ("GRID", (0, 0), (-1, -1), 0.25, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    tbl.wrapOn(c, W - 28 * mm, 200)
    tbl.drawOn(c, 14 * mm, y - tbl._height)
    y -= tbl._height + 7 * mm

    y = draw_section_header(c, 14 * mm, y, W - 28 * mm, "Occupazione stagionale")
    y -= 3 * mm
    draw_section_subtitle(c, 14 * mm, y, "Andamento mensile stimato - prezzi e tassi di riempimento")
    y -= 6 * mm
    occ = D.get("occupazione", [])
    mesi_affidabili_idx = set(D.get("mesi_affidabili_idx", []))
    VERDE_AFFIDABILE = HexColor("#D4F1DE")
    VERDE_DATO_REALE = HexColor("#2E9E4F")
    header_half = ["Mese", "Occup.", "€/notte", "Stage"]
    gap = 5 * mm
    half = (W - 28 * mm - gap) / 2
    col_w_half = [half * 0.20, half * 0.24, half * 0.32, half * 0.24]

    def make_half_style(rows, idx_offset):
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), BLUE_NIGHT), ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"), ("TEXTCOLOR", (0, 1), (-1, -1), BLUE_NIGHT),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, CREAM]),
            ("GRID", (0, 0), (-1, -1), 0.25, BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("BACKGROUND", (0, 1), (0, -1), HexColor("#E3F2FA")),
            ("TEXTCOLOR", (0, 1), (0, -1), BLUE_PRIMARY), ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ]
        for ri, row in enumerate(rows):
            sc = stage_color(row[3])
            style.append(("TEXTCOLOR", (3, ri + 1), (3, ri + 1), sc))
            style.append(("FONTNAME", (3, ri + 1), (3, ri + 1), "Helvetica-Bold"))
            if row[3] in ("Peak", "Alta"):
                style.append(("TEXTCOLOR", (1, ri + 1), (1, ri + 1), sc))
                style.append(("FONTNAME", (1, ri + 1), (1, ri + 1), "Helvetica-Bold"))
            if (ri + idx_offset) in mesi_affidabili_idx:
                style.append(("BACKGROUND", (0, ri + 1), (2, ri + 1), VERDE_AFFIDABILE))
                style.append(("BOX", (0, ri + 1), (2, ri + 1), 1.3, VERDE_DATO_REALE))
                style.append(("FONTSIZE", (0, ri + 1), (2, ri + 1), 9))
                style.append(("FONTNAME", (0, ri + 1), (2, ri + 1), "Helvetica-Bold"))
                style.append(("TEXTCOLOR", (1, ri + 1), (1, ri + 1), BLUE_NIGHT))
                style.append(("TOPPADDING", (0, ri + 1), (2, ri + 1), 5))
                style.append(("BOTTOMPADDING", (0, ri + 1), (2, ri + 1), 5))
        return style

    data_sx = [[o[0], f"{o[1]}%", f"€ {o[2]}", o[3]] for o in occ[:6]]
    data_dx = [[o[0], f"{o[1]}%", f"€ {o[2]}", o[3]] for o in occ[6:]]
    tbl_sx = Table([header_half] + data_sx, colWidths=col_w_half)
    tbl_sx.setStyle(TableStyle(make_half_style(data_sx, 0)))
    tbl_sx.wrapOn(c, half, 300)
    tbl_dx = Table([header_half] + data_dx, colWidths=col_w_half)
    tbl_dx.setStyle(TableStyle(make_half_style(data_dx, 6)))
    tbl_dx.wrapOn(c, half, 300)
    tbl_h = max(tbl_sx._height, tbl_dx._height)
    tbl_sx.drawOn(c, 14 * mm, y - tbl_h)
    tbl_dx.drawOn(c, 14 * mm + half + gap, y - tbl_h)
    y -= tbl_h + 5 * mm

    graph_h = 62 * mm
    graph_w = W - 28 * mm
    gx, gy = 14 * mm, y - graph_h
    c.setFillColor(WHITE)
    c.rect(gx, gy, graph_w, graph_h, fill=1, stroke=0)
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.3)
    c.rect(gx, gy, graph_w, graph_h, fill=0, stroke=1)
    legend_items = [("Bassa", MUTED), ("Media", BLUE_PRIMARY), ("Alta stagione", TEAL), ("Peak", GOLD), ("Dato reale attuale", HexColor("#2E9E4F"))]
    lx = gx + 3 * mm
    for lbl, col in legend_items:
        c.setFillColor(col)
        c.circle(lx + 1.5 * mm, gy + graph_h - 4 * mm, 1.5 * mm, fill=1, stroke=0)
        c.setFont("Helvetica", 6.5)
        c.setFillColor(MUTED)
        c.drawString(lx + 4 * mm, gy + graph_h - 5 * mm, lbl)
        lx += c.stringWidth(lbl, "Helvetica", 6.5) + 10 * mm
    bottom_margin = 17 * mm
    top_margin = 10 * mm
    plot_h = graph_h - bottom_margin - top_margin
    side_margin = 16 * mm
    min_r, max_r = 30, 95
    for pct in [30, 40, 50, 60, 70, 80, 90]:
        py_line = gy + bottom_margin + ((pct - min_r) / (max_r - min_r)) * plot_h
        c.setStrokeColor(BORDER)
        c.setLineWidth(0.25)
        c.line(gx + side_margin, py_line, gx + graph_w - side_margin, py_line)
        c.setFont("Helvetica", 5.5)
        c.setFillColor(MUTED)
        c.drawString(gx + 0.5 * mm, py_line - 1.5 * mm, f"{pct}%")
    side_margin = 16 * mm
    step = (graph_w - side_margin * 2) / 11
    points = []
    for i, row in enumerate(occ):
        px_dot = gx + side_margin + i * step
        rate = row[1]
        rate_clamped = max(min_r, min(max_r, rate))
        py_dot = gy + bottom_margin + ((rate_clamped - min_r) / (max_r - min_r)) * plot_h
        points.append((px_dot, py_dot, row[3], rate))
    c.setStrokeColor(TEAL)
    c.setLineWidth(1.5)
    p = c.beginPath()
    if not points:
        return
    p.moveTo(points[0][0], points[0][1])
    for pt in points[1:]:
        p.lineTo(pt[0], pt[1])
    c.drawPath(p, stroke=1, fill=0)
    for i, (px_dot, py_dot, stage, rate) in enumerate(points):
        col = stage_color(stage)
        affidabile = i in mesi_affidabili_idx
        r = 2.5 * mm if stage == "Peak" else 1.8 * mm
        if affidabile:
            r += 0.7 * mm
        c.setFillColor(col)
        c.circle(px_dot, py_dot, r, fill=1, stroke=0)
        if affidabile:
            c.setStrokeColor(VERDE_DATO_REALE)
            c.setLineWidth(1.2)
            c.circle(px_dot, py_dot, r + 1 * mm, fill=0, stroke=1)
            badge_w, badge_h = 8.5 * mm, 4.2 * mm
            bx, by = px_dot - badge_w / 2, py_dot + 2.2 * mm
            c.setFillColor(HexColor("#B9C7BE"))
            c.roundRect(bx + 0.3 * mm, by - 0.3 * mm, badge_w, badge_h, 1.2 * mm, fill=1, stroke=0)
            c.setFillColor(VERDE_DATO_REALE)
            c.roundRect(bx, by, badge_w, badge_h, 1.2 * mm, fill=1, stroke=0)
            c.setFont("Helvetica-Bold", 6.5)
            c.setFillColor(WHITE)
            c.drawCentredString(px_dot, by + 1.3 * mm, f"{rate}%")
        else:
            c.setFont("Helvetica-Bold", 6)
            c.setFillColor(BLUE_NIGHT)
            c.drawCentredString(px_dot, py_dot + 3 * mm, f"{rate}%")
    for i, row in enumerate(occ):
        px_dot = gx + side_margin + i * step
        affidabile = i in mesi_affidabili_idx
        c.setFont("Helvetica-Bold" if affidabile else "Helvetica", 7 if affidabile else 6)
        c.setFillColor(VERDE_DATO_REALE if affidabile else BLUE_NIGHT)
        c.drawCentredString(px_dot, gy + 8 * mm, row[0])
        c.setFont("Helvetica-Bold" if affidabile else "Helvetica", 6 if affidabile else 5.5)
        c.setFillColor(BLUE_NIGHT if affidabile else MUTED)
        c.drawCentredString(px_dot, gy + 4 * mm, f"€ {row[2]}")

    disclaimer_prezzi = (
        "I mesi in evidenza (i 3 piu' vicini alla data del report) mostrano il prezzo attualmente piu' affidabile, "
        "rilevato oggi sul mercato reale. Gli altri mesi sono affidabili alla data odierna, ma possono variare "
        "(tipicamente al rialzo) avvicinandosi al periodo di riferimento."
    )
    style_disclaimer = ParagraphStyle(
        "disclaimerPrezzi", fontName="Helvetica-Oblique", fontSize=6,
        textColor=MUTED, leading=7.5, alignment=TA_CENTER,
    )
    larghezza_utile = W - 28 * mm
    p_disclaimer = Paragraph(disclaimer_prezzi, style_disclaimer)
    _, h_disclaimer = p_disclaimer.wrap(larghezza_utile, 20 * mm)
    p_disclaimer.drawOn(c, 14 * mm, gy - 4 * mm - h_disclaimer)


def page3(c, D):
    draw_header(c, D)
    draw_footer(c, 3)
    y = H - 22 * mm

    y = draw_section_header(c, 14 * mm, y, W - 28 * mm, "Analisi economica annuale")
    y -= 3 * mm
    draw_section_subtitle(c, 14 * mm, y, "Proiezione costi e ricavi basata sulla situazione dichiarata")
    y -= 6 * mm

    style_media_mercato = ParagraphStyle(
        "mediaMercato", fontName="Helvetica", fontSize=7.5, textColor=BLUE_NIGHT, leading=9,
    )

    def _cella_media_mercato(valore_annuo, extra=""):
        # Il separatore delle migliaia si applica solo al numero: prima il
        # .replace(",", ".") colpiva l'intera frase e la virgola della nota
        # diventava un punto ("per la tipologia. soggiorno medio 2 notti").
        importo = f"{valore_annuo:,}".replace(",", ".")
        nota = f' <font size="6" color="#7A8A96">(media di mercato per la tipologia{extra})</font>'
        return Paragraph(f"€ {importo}/anno{nota}", style_media_mercato)

    p = D.get("prezzo_notte_stimato", 0)
    occ_pct = D.get("occupazione_percent", 0)
    notti = D.get("notti_anno", 0)
    comm_pct = D.get("costi_commissioni_pct", 15)
    pulizia_unit = D.get("costi_pulizie_unit", 35)
    _cambi = D.get("cambi_anno")
    _sm = D.get("soggiorno_medio_notti")
    _pulizie_tot = f"{D.get('costi_pulizie', 0):,}".replace(",", ".")
    if _cambi and _sm:
        _sm_txt = f"{_sm:g}".replace(".", ",")
        _formula_pulizie = (f"€ {pulizia_unit}/cambio x {_cambi} cambi "
                            f"(soggiorno medio {_sm_txt} notti) = € {_pulizie_tot}")
    else:
        _formula_pulizie = f"€ {pulizia_unit}/cambio x {notti} notti = € {_pulizie_tot}"
    # Etichetta leggibile, non il codice del form: qui usciva "bilocale"
    # minuscolo mentre lo Strategico scriveva "Bilocale" nella stessa riga.
    _tipologia_costi = D.get("scheda_tipologia") or D.get("tipologia", "immobile")
    _nota_costi_variabili = f"Media di mercato per tipologia: {_tipologia_costi}"
    # Sessione 68: nota breve sul soggiorno medio anche per la biancheria,
    # solo descrittiva — il valore resta fisso/anno per tipologia, NON
    # scala con i cambi reali (a differenza delle pulizie): su immobili
    # cittadini ad alta occupazione farlo scalare gonfierebbe il costo
    # invece di ridurlo, l'opposto di quanto richiesto.
    _sm_biancheria = (
        (f", soggiorno medio {_sm:g} notti".replace(".", ",") if _sm else "")
        + ", stima in scenario di gestione mista (propria/appalto a terzi)"
    )
    rata_mutuo = D.get("rata_mutuo_mensile", 0)
    mutuo_annuo = rata_mutuo * 12

    if D.get("situazione_vuoto"):
        sit_label = "Immobile vuoto"
    elif D.get("situazione_bnb"):
        sit_label = "B&B attivo"
    elif D.get("situazione_inquilini"):
        sit_label = "Con inquilini"
    else:
        sit_label = "Disponibile"
    sit_cards = [
        ("Situazione", sit_label, BLUE_PRIMARY, HexColor("#E3F2FA")),
        ("Prezzo stimato/notte", f"\u20ac {p}", TEAL, TEAL_LIGHT),
        ("Occupazione stimata", f"{occ_pct}%", GOLD, GOLD_LIGHT),
        ("Notti/anno stimate", f"{notti}", BLUE_NIGHT, CREAM),
    ]
    card_h, card_w = 16 * mm, (W - 34 * mm) / 4
    cx = 14 * mm
    for lbl, val, tc, bg in sit_cards:
        c.setFillColor(bg)
        c.roundRect(cx, y - card_h, card_w, card_h, 2 * mm, fill=1, stroke=0)
        c.setStrokeColor(tc)
        c.setLineWidth(0.8)
        c.roundRect(cx, y - card_h, card_w, card_h, 2 * mm, fill=0, stroke=1)
        c.setFont("Helvetica", 6.5)
        c.setFillColor(MUTED)
        c.drawCentredString(cx + card_w / 2, y - 4.5 * mm, lbl)
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(tc)
        c.drawCentredString(cx + card_w / 2, y - 11 * mm, val)
        cx += card_w + 2 * mm
    y -= card_h + 5 * mm

    eco_data = [
        ["Voce", "Come viene calcolato", "Valore"],
        ["RICAVI", "", ""],
        ["Ricavo lordo annuo stimato",
         f"€ {p}/notte x {occ_pct}% occ. x 365gg = {notti} notti x € {p} = {fmt_eur(D.get('ricavo_lordo', 0))}",
         fmt_eur(D.get("ricavo_lordo", 0))],
        ["Bonus prenotazioni dirette",
         f"€ {D.get('ricavo_lordo',0):,} x {D.get('bonus_dirette_pct','5-10%')} = € {D.get('bonus_dirette',0):,}".replace(",", "."),
         fmt_eur(D.get("bonus_dirette", 0))],
        ["TOTALE RICAVI",
         f"€ {D.get('ricavo_lordo',0):,} + € {D.get('bonus_dirette',0):,} = € {D.get('totale_ricavi',0):,}".replace(",", "."),
         fmt_eur(D.get("totale_ricavi", 0))],
        ["COSTI VARIABILI", _nota_costi_variabili, ""],
        ["Commissioni piattaforma Airbnb",
         f"€ {D.get('ricavo_lordo',0):,} x {comm_pct}% = € {D.get('costi_commissioni',0):,}".replace(",", "."),
         f"- {fmt_eur(D.get('costi_commissioni', 0))}"],
        ["Pulizie per cambio ospite", _formula_pulizie,
         f"- {fmt_eur(D.get('costi_pulizie', 0))}"],
        ["Biancheria e consumabili",
         _cella_media_mercato(D.get('costi_biancheria', 0), extra=_sm_biancheria),
         f"- {fmt_eur(D.get('costi_biancheria', 0))}"],
        ["Utenze aggiuntive stimate",
         _cella_media_mercato(D.get('costi_utenze', 0)),
         f"- {fmt_eur(D.get('costi_utenze', 0))}"],
        ["Manutenzione ordinaria",
         _cella_media_mercato(D.get('costi_manutenzione', 0), extra=(
             ", include piscina e giardino" if D.get("_costi_ha_piscina") and D.get("_costi_ha_giardino")
             else ", include piscina" if D.get("_costi_ha_piscina")
             else ", include giardino" if D.get("_costi_ha_giardino")
             else "")),
         f"- {fmt_eur(D.get('costi_manutenzione', 0))}"],
        ["Rata mutuo (se presente)",
         "Nessun mutuo dichiarato" if not D.get("mutuo_attivo") else f"€ {rata_mutuo}/mese x 12 = € {mutuo_annuo:,}".replace(",", "."),
         "€ 0" if not D.get("mutuo_attivo") else f"- {fmt_eur(mutuo_annuo)}"],
        ["Totale costi variabili", "", f"- {fmt_eur(D.get('totale_costi', 0))}"],
        ["PROFITTO NETTO STIMATO", "", fmt_eur(D.get("profitto_netto", 0))],
        ["Margine netto su ricavi totali", "", f"{D.get('margine_percent', 0)}%"],
    ]

    col_w_eco = [(W - 28 * mm) * 0.28, (W - 28 * mm) * 0.52, (W - 28 * mm) * 0.20]
    tbl_eco = Table(eco_data, colWidths=col_w_eco)
    style_eco = [
        ("BACKGROUND", (0, 0), (-1, 0), BLUE_NIGHT), ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"), ("TEXTCOLOR", (0, 1), (-1, -1), BLUE_NIGHT),
        ("ROWBACKGROUNDS", (0, 2), (-1, 4), [WHITE, CREAM]),
        ("ROWBACKGROUNDS", (0, 6), (-1, 11), [WHITE, CREAM]),
        ("GRID", (0, 0), (-1, -1), 0.25, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("BACKGROUND", (0, 1), (-1, 1), TEAL_LIGHT), ("TEXTCOLOR", (0, 1), (0, 1), TEAL),
        ("FONTNAME", (0, 1), (0, 1), "Helvetica-Bold"),
        ("BACKGROUND", (0, 4), (-1, 4), TEAL_LIGHT), ("TEXTCOLOR", (0, 4), (-1, 4), TEAL),
        ("FONTNAME", (0, 4), (-1, 4), "Helvetica-Bold"),
        ("BACKGROUND", (0, 5), (-1, 5), RED_LIGHT), ("TEXTCOLOR", (0, 5), (0, 5), RED),
        ("FONTNAME", (0, 5), (0, 5), "Helvetica-Bold"),
        ("TEXTCOLOR", (2, 6), (2, 11), RED),
        ("TEXTCOLOR", (2, 11), (2, 11), MUTED if not D.get("mutuo_attivo") else RED),
        ("BACKGROUND", (0, 12), (-1, 12), RED_LIGHT), ("TEXTCOLOR", (0, 12), (-1, 12), RED),
        ("FONTNAME", (0, 12), (-1, 12), "Helvetica-Bold"),
        ("BACKGROUND", (0, 13), (-1, 13), TEAL_LIGHT), ("TEXTCOLOR", (0, 13), (-1, 13), TEAL),
        ("FONTNAME", (0, 13), (-1, 13), "Helvetica-Bold"),
        ("BACKGROUND", (0, 14), (-1, 14), TEAL_LIGHT), ("TEXTCOLOR", (0, 14), (-1, 14), TEAL),
        ("FONTNAME", (0, 14), (-1, 14), "Helvetica-Bold"),
    ]
    tbl_eco.setStyle(TableStyle(style_eco))
    tbl_eco.wrapOn(c, W - 28 * mm, 500)
    tbl_eco.drawOn(c, 14 * mm, y - tbl_eco._height)
    y -= tbl_eco._height + 5 * mm

    total_w = W - 28 * mm
    big_w = total_w * 0.30
    small_w = (total_w - big_w - 6 * mm) / 3
    small_h, big_h = 18 * mm, 24 * mm
    cards = [
        ("Margine netto", f"{D.get('margine_percent', 0)}%", WHITE, BLUE_NIGHT, small_w, small_h),
        ("Totale ricavi", fmt_eur(D.get("totale_ricavi", 0)), TEAL_LIGHT, TEAL, small_w, small_h),
        ("Costi variabili totali", f"- {fmt_eur(D.get('totale_costi', 0))}", RED_LIGHT, RED, small_w, small_h),
        ("Il tuo guadagno stimato", fmt_eur(D.get("profitto_netto", 0)), GOLD_LIGHT, GOLD, big_w, big_h),
    ]
    cx = 14 * mm
    for lbl, val, bg, tc, cw, ch in cards:
        is_gold = (tc == GOLD)
        cy = y - big_h + (big_h - ch) / 2
        if is_gold:
            cy = y - big_h
        c.setFillColor(bg)
        c.roundRect(cx, cy, cw, ch, 2 * mm, fill=1, stroke=0)
        c.setStrokeColor(GOLD if is_gold else HexColor("#C8C8C8"))
        c.setLineWidth(1.5 if is_gold else 0.5)
        c.roundRect(cx, cy, cw, ch, 2 * mm, fill=0, stroke=1)
        c.setFont("Helvetica-Bold" if is_gold else "Helvetica", 8 if is_gold else 7)
        c.setFillColor(GOLD if is_gold else MUTED)
        c.drawCentredString(cx + cw / 2, y - big_h + ch - 5 * mm if not is_gold else cy + ch - 5 * mm, lbl)
        val_y = y - big_h + (big_h - small_h) / 2 + small_h / 2 - 4 * mm
        c.setFont("Helvetica-Bold", 14 if is_gold else 12)
        c.setFillColor(tc)
        c.drawCentredString(cx + cw / 2, val_y, val)
        cx += cw + 2 * mm
    y -= big_h + 4 * mm

    nota = ("I valori sopra riportati sono orientativi e basati esclusivamente sulle informazioni fornite. "
            "Non includono spese personali, fiscali o societarie.")
    if D.get("cambi_anno") and D.get("soggiorno_medio_notti"):
        _sm_nota = f"{D.get('soggiorno_medio_notti'):g}".replace(".", ",")
        nota += (f" Ipotesi: soggiorno medio di {_sm_nota} notti per la zona. "
                 "Il Report Strategico differenzia l'analisi per soggiorni brevi, medi e lunghi.")
    y = draw_wrapped_text(c, nota, 14 * mm, y - 2 * mm, W - 28 * mm, "Helvetica-Oblique", 6.5, 4 * mm, MUTED)
    y -= 4 * mm

    y = draw_section_header(c, 14 * mm, y, W - 28 * mm, "Confronto con affitto tradizionale")
    y -= 5 * mm
    _diff_ricavo = D.get('ricavo_lordo', 0) - D.get('affitto_ricavo', 0)
    _diff_profitto = D.get('profitto_netto', 0) - D.get('affitto_profitto', 0)

    def _fmt_diff(delta):
        segno = "+" if delta >= 0 else "-"
        numero = f"{abs(int(delta)):,}".replace(",", ".")
        return f"{segno}\u20ac {numero}"

    # Il valore preciso di affitto_ricavo/costi/profitto resta quello usato per
    # calcolare la Differenza (matematicamente corretta) \u2014 solo la colonna
    # "Affitto tradizionale" mostra un range +-10% invece del numero secco,
    # per non esporre una precisione sul mercato dell'affitto tradizionale
    # che il dato non ha davvero.
    def _fmt_range_eur(valore):
        basso = round(valore * 0.9)
        alto = round(valore * 1.1)
        return f"{fmt_eur(basso)} - {fmt_eur(alto)}"

    conf_data = [
        ["", "Affitto tradizionale", "B&B / Short rent", "Differenza"],
        ["Ricavo annuo lordo", _fmt_range_eur(D.get("affitto_ricavo", 0)), fmt_eur(D.get("ricavo_lordo", 0)),
         _fmt_diff(_diff_ricavo)],
        ["Costi di gestione", _fmt_range_eur(D.get("affitto_costi", 0)), fmt_eur(D.get("totale_costi", 0)), "--"],
        ["Profitto netto", _fmt_range_eur(D.get("affitto_profitto", 0)), fmt_eur(D.get("profitto_netto", 0)),
         _fmt_diff(_diff_profitto)],
        ["Flessibilit\u00e0 utilizzo", "Bassa", "Alta", "Molto alta"],
        ["Rischio morosit\u00e0", "Alto", "Nullo", "Eliminato"],
    ]
    _colore_ricavo = TEAL if _diff_ricavo >= 0 else RED
    _colore_profitto = TEAL if _diff_profitto >= 0 else RED
    col_w_conf = [(W - 28 * mm) * 0.28, (W - 28 * mm) * 0.22, (W - 28 * mm) * 0.22, (W - 28 * mm) * 0.28]
    tbl_conf = Table(conf_data, colWidths=col_w_conf)
    tbl_conf.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLUE_NIGHT), ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"), ("TEXTCOLOR", (0, 1), (-1, -1), BLUE_NIGHT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, CREAM]),
        ("GRID", (0, 0), (-1, -1), 0.25, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("TEXTCOLOR", (3, 1), (3, 1), _colore_ricavo), ("FONTNAME", (3, 1), (3, 1), "Helvetica-Bold"),
        ("TEXTCOLOR", (3, 3), (3, 3), _colore_profitto), ("FONTNAME", (3, 3), (3, 3), "Helvetica-Bold"),
        ("TEXTCOLOR", (3, 4), (3, 4), TEAL), ("FONTNAME", (3, 4), (3, 4), "Helvetica-Bold"),
        ("TEXTCOLOR", (3, 5), (3, 5), TEAL), ("FONTNAME", (3, 5), (3, 5), "Helvetica-Bold"),
    ]))
    tbl_conf.wrapOn(c, W - 28 * mm, 300)
    tbl_conf.drawOn(c, 14 * mm, y - tbl_conf._height)


def page4(c, D):
    draw_header(c, D)
    draw_footer(c, 4)
    y = H - 22 * mm

    # competitor_zona arriva dall'AI e può mancare: il trattino va aggiunto
    # solo se c'è davvero qualcosa dopo, altrimenti il titolo finisce con un
    # "-" penzolante ("Analisi competitor -").
    _zona_comp = str(D.get("competitor_zona") or D.get("zona") or "").strip()
    _suffisso_comp = f" - {_zona_comp}" if _zona_comp and _zona_comp != "—" else ""

    y = draw_section_header(c, 14 * mm, y, W - 28 * mm,
                            f"Analisi competitor{_suffisso_comp}")
    y -= 3 * mm
    draw_section_subtitle(c, 14 * mm, y, "Confronto diretto con gli annunci attivi nella zona")
    y -= 6 * mm
    comp_data = [[f"Tipologia annunci{_suffisso_comp}", "Prezzo med."]]
    for row in D.get("competitor", []):
        comp_data.append(list(row))
    # Sessione 70: tolte le colonne N./Occup./Rating — senza dati reali
    # dietro (N. e Rating mai avuti, Occup. identica su tutte le righe)
    # restavano solo fronzoli, non informazione. Resta solo tipologia e
    # prezzo medio, l'unico dato che calcoliamo davvero riga per riga.
    comp_data.append(["IL TUO IMMOBILE (stima)", f"€ {D.get('kpi_prezzo', 0)}"])
    col_w_comp = [(W - 28 * mm) * 0.65, (W - 28 * mm) * 0.35]
    tbl_comp = Table(comp_data, colWidths=col_w_comp)
    tbl_comp.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLUE_NIGHT), ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 1), (-1, -2), "Helvetica"), ("TEXTCOLOR", (0, 1), (-1, -2), BLUE_NIGHT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [WHITE, CREAM]),
        ("GRID", (0, 0), (-1, -1), 0.25, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND", (0, -1), (-1, -1), TEAL_LIGHT),
        ("TEXTCOLOR", (0, -1), (-1, -1), TEAL),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    tbl_comp.wrapOn(c, W - 28 * mm, 200)
    tbl_comp.drawOn(c, 14 * mm, y - tbl_comp._height)
    y -= tbl_comp._height + 7 * mm

    y = draw_section_header(c, 14 * mm, y, W - 28 * mm, "Riepilogo indicatori di mercato")
    y -= 3 * mm
    draw_section_subtitle(c, 14 * mm, y, "Sintesi conclusiva dei valori chiave calcolati per il tuo immobile")
    y -= 7 * mm
    kw = (W - 28 * mm - 6 * mm) / 4
    kh = 24 * mm
    kpis = [
        ("PREZZO MEDIO / NOTTE", f"€ {D.get('kpi_prezzo', 0)}", "per notte", D.get("kpi_prezzo_range", "")),
        ("TASSO DI OCCUPAZIONE", f"{D.get('kpi_occupazione', 0)}%", "stimato", D.get("kpi_occ_range", "")),
        ("POTENZIALE LORDO ANNUO", fmt_eur(D.get("kpi_potenziale", 0)), "all'anno",
         f"Con occupazione al {D.get('kpi_occupazione', 0)}%"),
        ("PROFITTO NETTO STIMATO", fmt_eur(D.get("profitto_netto", 0)), "netto stimato", "Dopo costi di gestione"),
    ]
    for i, (lbl, val, sub, nota) in enumerate(kpis):
        cx = 14 * mm + i * (kw + 2 * mm)
        c.setFillColor(GOLD_LIGHT)
        c.roundRect(cx, y - kh, kw, kh, 2 * mm, fill=1, stroke=0)
        c.setStrokeColor(GOLD)
        c.setLineWidth(1)
        c.roundRect(cx, y - kh, kw, kh, 2 * mm, fill=0, stroke=1)
        c.setFont("Helvetica-Bold", 6.5)
        c.setFillColor(GOLD)
        c.drawCentredString(cx + kw / 2, y - 4.5 * mm, lbl)
        c.setFont("Helvetica-Bold", 13)
        c.setFillColor(BLUE_NIGHT)
        c.drawCentredString(cx + kw / 2, y - 13 * mm, val)
        c.setFont("Helvetica", 6.5)
        c.setFillColor(MUTED)
        c.drawCentredString(cx + kw / 2, y - 17 * mm, sub)
        c.setFont("Helvetica", 6)
        c.setFillColor(MUTED)
        c.drawCentredString(cx + kw / 2, y - 21 * mm, nota)
    y -= kh + 3 * mm

    c.setFont("Helvetica-Oblique", 6.5)
    c.setFillColor(MUTED)
    c.drawString(14 * mm, y,
                 "Valori medi orientativi calcolati sui dati inseriti e sulle medie di mercato della zona.")
    y -= 9 * mm

    upsell_h = 32 * mm
    c.setFillColor(GOLD_LIGHT)
    c.roundRect(14 * mm, y - upsell_h, W - 28 * mm, upsell_h, 3 * mm, fill=1, stroke=0)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1)
    c.roundRect(14 * mm, y - upsell_h, W - 28 * mm, upsell_h, 3 * mm, fill=0, stroke=1)
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(BLUE_NIGHT)
    c.drawString(18 * mm, y - 7 * mm, "Vuoi il piano d\u2019azione completo?")

    # Il badge "IN ARRIVO" e la nota "in fase di sviluppo" che stavano qui sono
    # stati rimossi: lo Strategico è in lancio e acquistabile, tenerli avrebbe
    # scoraggiato l'upsell che questo riquadro esiste per fare.
    upsell_text = ("Il Report Strategico (€ 149) include tutto il Base piu': pricing stagionale mese per mese, "
                   "3 scenari economici (pessimistico / realistico / ottimistico), piano d'azione 90 giorni, "
                   "cap rate e valore asset, normativa affitti brevi locale e l'analisi personale "
                   "dell'Arch. Salvatore Junior Sica.")
    uy = y - 13 * mm
    uy = draw_wrapped_text(c, upsell_text, 18 * mm, uy, W - 36 * mm, "Helvetica", 7.5, 5 * mm, BLUE_NIGHT)
    c.setFont("Helvetica-Oblique", 7)
    c.setFillColor(MUTED)
    uy = draw_wrapped_text(
        c, "Disponibile su reportup.it — chi ha già acquistato il Report Base paga "
           "solo la differenza rispetto ai € 39 già pagati.",
        18 * mm, uy - 1 * mm, W - 36 * mm, "Helvetica-Oblique", 7, 4 * mm, MUTED,
    )
    y -= upsell_h + 6 * mm

    c.setFont("Helvetica-Bold", 7)
    c.setFillColor(MUTED)
    c.drawString(14 * mm, y, "DISCLAIMER - LETTURA OBBLIGATORIA")
    y -= 5 * mm
    disc = ("Il Report Base fornito da ReportUp e' uno strumento di analisi orientativa del mercato degli affitti brevi, "
            "elaborato sulla base delle informazioni inserite dall'utente e dei dati di mercato disponibili alla data "
            "di generazione. Non costituisce in alcun modo una consulenza finanziaria, legale, fiscale o immobiliare "
            "professionale. I valori indicati sono proiezioni orientative basate su medie di mercato e non rappresentano "
            "garanzie di risultato. ReportUp declina ogni responsabilita' per decisioni prese sulla base di questo documento.")
    draw_wrapped_text(c, disc, 14 * mm, y, W - 28 * mm, "Helvetica", 6.5, 4 * mm, MUTED)


def page5(c, D):
    draw_header(c, D)
    draw_footer(c, 5)
    y = H - 30 * mm

    y = draw_section_header(c, 14 * mm, y, W - 28 * mm, "Fonti e riferimenti")
    y -= 3 * mm
    draw_section_subtitle(c, 14 * mm, y, "Dati e metodologia alla base di questa analisi")
    y -= 6 * mm

    _fonte_affitto = D.get("fonte_affitto_tradizionale", "stima_airroi")
    if _fonte_affitto == "omi_reale":
        _desc_affitto = ("Osservatorio del Mercato Immobiliare (OMI) - Agenzia delle Entrate. Canone di "
                          "locazione medio al m² per la zona, ultimo semestre disponibile, applicato alla "
                          "superficie dichiarata dell'immobile. Dato ufficiale, aggiornamento semestrale.")
    else:
        _sconto_affitto = D.get("sconto_affitto_tradizionale_pct", 40)
        _desc_affitto = (f"Stima comparativa di mercato: prezzo/notte medio (fonte AirROI) x 30 giorni, "
                          f"scontato del {_sconto_affitto}% per riflettere il differenziale tipico tra canone "
                          f"di locazione tradizionale e tariffa di affitto breve sulla stessa unità nella stessa zona. "
                          f"Valore orientativo, non tratto da atti o contratti registrati.")

    fonti = [
        ("Prezzi per notte e\ntasso di occupazione",
         "Elaborazione su dati aggregati delle principali piattaforme di short rental (Airbnb, Booking.com, VRBO). "
         "I valori rappresentano medie di mercato per tipologia di immobile e zona al momento della generazione."),
        ("Canoni di affitto\ntradizionale", _desc_affitto),
        ("Dati demografici e\nflussi turistici",
         "ISTAT - Istituto Nazionale di Statistica. Movimento turistico in Italia, rilevazione annuale su arrivi "
         "e presenze per comune e tipologia di struttura."),
        ("Commissioni piattaforme",
         "Tariffari ufficiali pubblicati da Airbnb.com, Booking.com e VRBO alla data di generazione del report."),
        ("Costi operativi stimati",
         "Medie di mercato per il settore della gestione immobiliare in affitto breve, elaborate su base regionale."),
        ("Punti di interesse e\ndistanze",
         "Google Maps Platform - dati di percorrenza pedonale e su mezzo pubblico. I tempi indicati sono stime."),
    ]

    for fonte, desc in fonti:
        c.setFont("Helvetica-Bold", 7.5)
        c.setFillColor(BLUE_NIGHT)
        fy = y
        for fl in fonte.split("\n"):
            c.drawString(14 * mm, fy, fl)
            fy -= 4.5 * mm
        dy = y
        words = desc.split()
        line = ""
        for w in words:
            test = line + (" " if line else "") + w
            if c.stringWidth(test, "Helvetica", 7) > (W - 28 * mm) * 0.62:
                c.setFont("Helvetica", 7)
                c.setFillColor(MUTED)
                c.drawString(14 * mm + (W - 28 * mm) * 0.35, dy, line)
                dy -= 4.5 * mm
                line = w
            else:
                line = test
        if line:
            c.setFont("Helvetica", 7)
            c.setFillColor(MUTED)
            c.drawString(14 * mm + (W - 28 * mm) * 0.35, dy, line)
            dy -= 4.5 * mm
        bottom = min(fy, dy) - 1 * mm
        c.setStrokeColor(BORDER)
        c.setLineWidth(0.3)
        c.line(14 * mm, bottom, W - 14 * mm, bottom)
        y = bottom - 4 * mm

    y -= 8 * mm

    box_h = 82 * mm
    box_x, box_w = 14 * mm, W - 28 * mm
    box_y = y - box_h
    c.setFillColor(CREAM)
    c.roundRect(box_x, box_y, box_w, box_h, 3 * mm, fill=1, stroke=0)
    c.setStrokeColor(BLUE_PRIMARY)
    c.setLineWidth(1)
    c.roundRect(box_x, box_y, box_w, box_h, 3 * mm, fill=0, stroke=1)

    badge_font_size = 16
    c.setFont("Helvetica-Bold", badge_font_size)
    tw_report = c.stringWidth("Report", "Helvetica-Bold", badge_font_size)
    tw_up = c.stringWidth("Up", "Helvetica-Bold", badge_font_size)
    badge_w = tw_report + tw_up + 10 * mm
    badge_h = 9 * mm
    badge_x = W / 2 - badge_w / 2
    badge_y2 = y - badge_h - 5 * mm
    c.setFillColor(BLUE_NIGHT)
    c.roundRect(badge_x, badge_y2, badge_w, badge_h, 2 * mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.drawString(badge_x + 5 * mm, badge_y2 + 2.2 * mm, "Report")
    c.setFillColor(BLUE_PRIMARY)
    c.drawString(badge_x + 5 * mm + tw_report, badge_y2 + 2.2 * mm, "Up")
    iy = badge_y2 - 7 * mm

    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(BLUE_NIGHT)
    c.drawCentredString(W / 2, iy, "Grazie per aver scelto ReportUp.")
    iy -= 9 * mm

    paragrafi = [
        ("Sono l'Arch. Salvatore Junior Sica, e questo report porta con se' oltre un decennio di esperienza "
         "nel settore immobiliare italiano e piu' di 30.000 valutazioni effettuate sul territorio nazionale.", False),
        ("ReportUp nasce da un'idea semplice: rendere accessibile a chiunque l'analisi professionale che "
         "fino a ieri era riservata solo a chi poteva permettersi una consulenza privata.", False),
        ("Ogni report che esce porta il nostro nome, e questo per noi non e' mai un dettaglio.", True),
        ("Spero che questa analisi ti sia utile e ti aiuti a prendere la decisione giusta per il tuo immobile.", False),
    ]
    max_w_testo = box_w - 20 * mm
    for testo, corsivo in paragrafi:
        fn = "Helvetica-Oblique" if corsivo else "Helvetica"
        col = TEAL if corsivo else BLUE_NIGHT
        words = testo.split()
        line = ""
        for w in words:
            test = line + (" " if line else "") + w
            if c.stringWidth(test, fn, 8) > max_w_testo:
                c.setFont(fn, 8)
                c.setFillColor(col)
                c.drawCentredString(W / 2, iy, line)
                iy -= 5 * mm
                line = w
            else:
                line = test
        if line:
            c.setFont(fn, 8)
            c.setFillColor(col)
            c.drawCentredString(W / 2, iy, line)
            iy -= 5 * mm
        iy -= 2 * mm

    iy -= 2 * mm
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(BLUE_NIGHT)
    c.drawCentredString(W / 2, iy, "Arch. Salvatore Junior Sica")
    iy -= 6 * mm
    c.setFont("Helvetica", 8)
    c.setFillColor(MUTED)
    c.drawCentredString(W / 2, iy, "Fondatore \u2014 ReportUp | reportup.it")


# ── Generatore PDF ────────────────────────────────────────────────────────────


def _title_preserva_romani(testo):
    """Come str.title() ma senza rompere i numeri romani gia' scritti in
    maiuscolo nel dato originale — Sessione 67. Caso reale: "Rione IX
    Pigna" (Google) diventava "Rione Ix Pigna" nel PDF. Un token viene
    mantenuto MAIUSCOLO solo se (a) nell'originale era interamente
    maiuscolo e (b) e' un numero romano plausibile (I-XXXIX): cosi' parole
    come "DI"/"VI" scritte male dall'AI non restano urlate per errore ma
    i municipi/rioni romani si'."""
    _ROMANO = re.compile(r"^(X{0,3})(IX|IV|V?I{0,3})$")
    parole = str(testo or "").split(" ")
    out = []
    for w in parole:
        if w.isupper() and len(w) >= 2 and _ROMANO.match(w) and any(ch in w for ch in "IVX"):
            out.append(w)
        else:
            out.append(w.title())
    return " ".join(out)


def normalize_data(data):
    """Il prompt AI del Report Base (PROMPT_AI_REPORT_BASE.md) restituisce da
    tempo un JSON piatto con indirizzo/tipologia/occupazione gi\u00e0 in cima \u2014
    la guardia sotto \u00e8 quindi sempre vera nel flusso reale. Rimosso a
    Sessione 77 (audit 23/8, finding #16) il ramo di conversione da un
    vecchio formato annidato ("report.immobile.identificazione/
    caratteristiche") mai pi\u00f9 prodotto dall'AI: era codice morto e il suo
    dizionario sinonimi dotazioni era disallineato da _DOTAZIONI_SINONIMI
    (mancava "piscina", "cucina" invece di "Cucina attrezzata") \u2014 se mai
    fosse tornato raggiungibile avrebbe silenziosamente rotto il
    sovrapprezzo piscina/manutenzione gi\u00e0 corretto altrove (Sessione 67)."""
    return data


def _join_lista_e(items):
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " e " + items[-1]


def _concorda_numero(valore, singolare, plurale):
    # Il prompt Strategico chiede "bagni"/"posti_letto" già come frase (es. "1
    # bagno", "4 posti", vedi PROMPT_AI_REPORT_STRATEGICO.md) — int() sull'intera
    # stringa falliva sempre e il fallback ci appendeva comunque il plurale,
    # duplicando l'unità ("1 bagno bagni"). Estrarre la prima cifra, come già fa
    # _numero_da_stringa, gestisce sia i numeri nudi sia le frasi dell'AI.
    m = re.search(r"\d+", str(valore))
    if not m:
        return f"{valore} {plurale}"
    n = int(m.group())
    return f"{n} {singolare}" if n == 1 else f"{n} {plurale}"


# ── Etichette scheda immobile ─────────────────────────────────────────────────
# Il form manda codici secchi ("bilocale", "1-3", "anni70", "base"). Il Base li
# riceve già in chiaro solo perché il suo prompt AI li riscrive; lo Strategico
# no e stampava il codice grezzo nella scheda ("anni70", "1-3", "base").
# La conversione qui è deterministica e condivisa dai due prodotti, così la
# stessa riga di scheda si legge identica su entrambi i PDF senza dipendere da
# cosa decide di scrivere l'AI. I valori finiscono in chiavi `scheda_*`
# dedicate: `tipologia`/`piano`/`stato`/`epoca` restano intatti perché sono
# usati come chiavi di calcolo a valle (camere deterministiche, comparabili
# AirROI, nota costi per tipologia).
_LABEL_TIPOLOGIA = {
    "stanza_singola":      "Stanza singola",
    "stanza_doppia":       "Stanza doppia",
    "bilocale":            "Bilocale",
    "trilocale":           "Trilocale",
    "appartamento_grande": "Appartamento 4+ locali",
    "villa":               "Villa / Casa indipendente",
}
_LABEL_PIANO = {
    "terra":  "Piano terra",
    "1-3":    "1° – 3° piano",
    "alto":   "Piano alto (4°+)",
    "attico": "Attico / Mansarda",
}
_LABEL_STATO = {
    "base":          "Arredi base, funzionale",
    "buono":         "Ben tenuto e curato",
    "ristrutturato": "Ristrutturato, moderno",
    "lusso":         "Finiture premium, design",
}
_LABEL_EPOCA = {
    "pre1960":  "Ante 1960",
    "anni60":   "Anni '60",
    "anni70":   "Anni '70",
    "anni80":   "Anni '80",
    "anni90":   "Anni '90",
    "anni2000": "Anni 2000",
    "anni2010": "Anni 2010",
    "anni2020": "Anni 2020",
    "nuova":    "Nuova costruzione",
}


_VERO = {"si", "sì", "s", "yes", "y", "true", "vero", "1", "on", "attivo"}
_FALSO = {"no", "n", "false", "falso", "0", "off", "", "none", "null", "nessuno"}


def _flag_form(valore):
    """Converte in booleano un flag che arriva dal form passando per Make e per
    l'AI. Non basta la verità di Python: una stringa "no" o "false" è truthy e
    faceva accendere la pillola verde. Tutto ciò che non è esplicitamente vero
    vale falso — su una dichiarazione del cliente il default prudente è "non
    dichiarato", non "sì"."""
    if isinstance(valore, bool):
        return valore
    if isinstance(valore, (int, float)):
        return valore != 0
    testo = str(valore or "").strip().lower()
    if testo in _VERO:
        return True
    if testo in _FALSO:
        return False
    return False


def _normalizza_situazione(data):
    """Normalizza i quattro flag di situazione e intercetta il caso in cui non
    sono arrivati affatto. vuoto / inquilini / B&B attivo si escludono a
    vicenda: se risultano tutti e tre veri il dato non viene dal cliente ma è
    stato riempito a valle (l'AI, davanti a un segnaposto vuoto, mette true su
    tutto). In quel caso è più onesto non dichiarare nulla che stampare tre
    affermazioni che non possono coesistere."""
    for campo in ("situazione_vuoto", "situazione_inquilini", "situazione_bnb", "situazione_mutuo"):
        data[campo] = _flag_form(data.get(campo))

    # `mutuo_attivo` e `situazione_mutuo` sono lo stesso fatto con due nomi
    # (il primo usato dai calcoli, il secondo dalla scheda): allineati, e vero
    # solo se c'è davvero una rata, altrimenti la riga mutuo mostra "- € 0".
    _rata = data.get("rata_mutuo_mensile") or 0
    data["mutuo_attivo"] = (_flag_form(data.get("mutuo_attivo")) or data["situazione_mutuo"]) and _rata > 0
    data["situazione_mutuo"] = data["mutuo_attivo"]

    _esclusivi = ("situazione_vuoto", "situazione_inquilini", "situazione_bnb")
    if all(data.get(k) for k in _esclusivi):
        print("[SITUAZIONE] vuoto+inquilini+B&B tutti veri: combinazione impossibile, "
              "il dato del form non è arrivato fin qui — azzerati. Controllare la "
              "mappatura Make dei campi situazione_*.")
        for k in _esclusivi:
            data[k] = False

    if not data.get("dotazioni_presenti"):
        print("[DOTAZIONI] dotazioni_presenti vuoto: se il cliente ne aveva selezionate, "
              "il dato si è perso prima del PDF — il form invia il campo 'dotazioni', "
              "controllare la mappatura Make verso 'dotazioni_presenti'.")
    return data


def _etichetta_scheda(valore, mappa):
    """Traduce un codice del form nella sua etichetta leggibile. Se il valore
    non è un codice noto (caso Base: l'AI ha già scritto "Anni '70") viene
    restituito intatto — la funzione è idempotente e non riscrive mai testo
    già in chiaro."""
    grezzo = str(valore or "").strip()
    return mappa.get(grezzo.lower().replace(" ", "_"), grezzo)


def _prepara_etichette_scheda(data):
    data["scheda_tipologia"] = _etichetta_scheda(data.get("tipologia"), _LABEL_TIPOLOGIA)
    data["scheda_piano"]     = _etichetta_scheda(data.get("piano"), _LABEL_PIANO)
    data["scheda_stato"]     = _etichetta_scheda(data.get("stato"), _LABEL_STATO)
    data["scheda_epoca"]     = _etichetta_scheda(data.get("epoca"), _LABEL_EPOCA)
    data["scheda_camere"]      = _concorda_numero(data.get("camere", ""), "camera", "camere")
    data["scheda_bagni"]       = _concorda_numero(data.get("bagni", ""), "bagno", "bagni")
    data["scheda_posti_letto"] = _concorda_numero(data.get("posti_letto", ""), "posto letto", "posti letto")
    _sup = str(data.get("superficie") or "").strip()
    data["scheda_superficie"] = f"{_sup} m2" if _sup and "m" not in _sup.lower() else _sup
    return data


_WIKI_CACHE = {}

_WIKI_SEZIONI_PER_CATEGORIA = {
    "grande_citta":        ["Monumenti e luoghi d'interesse", "Luoghi di interesse", "Arte e cultura", "Patrimonio"],
    "capoluogo":           ["Monumenti e luoghi d'interesse", "Luoghi di interesse", "Arte e cultura", "Patrimonio"],
    "costiero":            ["Spiagge", "Territorio", "Turismo", "Sagre", "Tradizioni", "Cultura"],
    "lacuale":             ["Turismo", "Sport", "Territorio", "Sagre", "Tradizioni", "Cultura"],
    "montano":             ["Sport", "Turismo", "Sci", "Trekking", "Territorio", "Sagre", "Tradizioni"],  # NOTE: vedi anche stagionalita_turistica.py per la curva bimodale sci+estate
    "residenziale_minore": ["Sagre", "Tradizioni", "Cultura", "Economia", "Prodotti tipici", "Gastronomia"],
}


def _pulisci_wikitext(testo):
    for _ in range(5):
        testo = re.sub(r'\{\{[^{}]*\}\}', '', testo)
    testo = re.sub(r'<gallery[^>]*>.*?</gallery>', '', testo, flags=re.DOTALL)
    testo = re.sub(r'<ref[^>]*>.*?</ref>', '', testo, flags=re.DOTALL)
    testo = re.sub(r'<[^>]+>', '', testo)
    testo = re.sub(r'={2,}.*?={2,}', '', testo)
    for _ in range(5):
        nuovo = re.sub(r'\[\[(?:File|Immagine|Image|Media):[^\[\]]*\]\]', '', testo, flags=re.IGNORECASE)
        if nuovo == testo:
            break
        testo = nuovo
    for _ in range(5):
        nuovo = re.sub(r'\[\[(?:[^\[\]|]*\|)?([^\[\]]*)\]\]', r'\1', testo)
        if nuovo == testo:
            break
        testo = nuovo
    testo = re.sub(r'\[https?://\S+\s+([^\]]+)\]', r'\1', testo)
    testo = re.sub(r'\[https?://\S+\]', '', testo)
    testo = re.sub(r"'{2,3}", '', testo)
    righe = testo.split('\n')
    righe = [r for r in righe if not re.search(r'\.(jpg|jpeg|png|svg|gif|tiff|webp)', r, re.IGNORECASE)]
    testo = '\n'.join(righe)
    testo = re.sub(r'\([^)]{0,8}\)', '', testo)
    righe = testo.split('\n')
    righe = [r.strip() for r in righe if len(r.strip()) > 30 and not r.strip().startswith(('*', '#', ':', ';', '|', '!'))]
    testo = ' '.join(righe)
    for _ in range(3):
        nuovo = re.sub(
            r'\b(?:thumb|thumbnail|miniatura|riquadro|right|left|center|centro|'
            r'upright|border|verticale|senza_cornice|\d+\s*px)\b\s*\|',
            '', testo, flags=re.IGNORECASE)
        if nuovo == testo:
            break
        testo = nuovo
    testo = re.sub(r'\s+', ' ', testo).strip()
    testo = re.sub(r'\[+|\]+', '', testo)
    testo = re.sub(r'\s+', ' ', testo).strip()
    testo = re.sub(r'^[,;.\s]+', '', testo)

    # Sessione 67 — due residui osservati nei test reali:
    # 1) Didascalie di immagini sopravvissute alla pulizia wiki e finite nel
    #    testo come frasi orfane (Napoli: "Vista dal parco urbano dei
    #    Camaldoli."). Le didascalie sono frasi brevi che iniziano con un
    #    lessico descrittivo-fotografico: le eliminiamo solo se corte, per
    #    non toccare frasi di contenuto vero.
    # 2) Punti doppi da concatenazioni ("servizi turistici.." a Roccaraso).
    _frasi = re.split(r'(?<=[.!?])\s+', testo)
    _frasi = [f for f in _frasi if not (
        len(f) < 80 and re.match(
            r'(?i)^(vista|veduta|panorama|scorcio|facciata|interno|particolare|dettaglio)\s+(d|s)', f)
    )]
    testo = ' '.join(_frasi)
    testo = re.sub(r'\.{2,}', '.', testo)
    testo = re.sub(r'\s+', ' ', testo).strip()
    return testo


def _estrai_sezione_wikipedia(titolo, nome_sezione, timeout=3):
    try:
        resp_sections = requests.get(
            "https://it.wikipedia.org/w/api.php",
            params={
                "action": "parse",
                "page": titolo,
                "prop": "sections",
                "format": "json",
            },
            timeout=timeout,
            headers={"User-Agent": "ReportUp/1.0 (https://reportup.it)"},
        )
        if resp_sections.status_code != 200:
            return None
        dati_sections = resp_sections.json()
        sections = dati_sections.get("parse", {}).get("sections", [])

        section_index = None
        nome_lower = nome_sezione.lower()
        for s in sections:
            if nome_lower in s.get("line", "").lower():
                section_index = s.get("index")
                break
        if section_index is None:
            return None

        resp_text = requests.get(
            "https://it.wikipedia.org/w/api.php",
            params={
                "action": "parse",
                "page": titolo,
                "prop": "wikitext",
                "section": section_index,
                "format": "json",
            },
            timeout=timeout,
            headers={"User-Agent": "ReportUp/1.0 (https://reportup.it)"},
        )
        if resp_text.status_code != 200:
            return None
        wikitext = resp_text.json().get("parse", {}).get("wikitext", {}).get("*", "")
        if not wikitext:
            return None

        testo = _pulisci_wikitext(wikitext)

        if not testo or len(testo) < 30:
            subsections = [s for s in sections if
                           s.get("toclevel", 0) == 2 and
                           int(s.get("index", 0)) > int(section_index)]
            for sub in subsections[:4]:
                resp_sub = requests.get(
                    "https://it.wikipedia.org/w/api.php",
                    params={"action": "parse", "page": titolo,
                            "prop": "wikitext", "section": sub.get("index"),
                            "format": "json"},
                    timeout=timeout,
                    headers={"User-Agent": "ReportUp/1.0 (https://reportup.it)"},
                )
                if resp_sub.status_code != 200:
                    continue
                sub_wikitext = resp_sub.json().get("parse", {}).get("wikitext", {}).get("*", "")
                testo_sub = _pulisci_wikitext(sub_wikitext)
                if testo_sub and len(testo_sub) >= 30:
                    testo = testo_sub
                    break

        if not testo or len(testo) < 30:
            return None

        frasi = [f.strip() for f in testo.split(". ") if len(f.strip()) > 20]
        risultato = ""
        for frase in frasi[:4]:
            candidato = risultato + frase + ". "
            if len(candidato) > 320:
                break
            risultato = candidato
            if len(risultato) >= 80:
                break

        risultato = risultato.strip()
        return risultato if len(risultato) >= 30 else None

    except Exception:
        return None


def _estratto_wikipedia(wikipedia_url, categoria="residenziale_minore", sottocategoria=None, timeout=3):
    if not wikipedia_url:
        return None

    cache_key = f"{wikipedia_url}|{categoria}|{sottocategoria}"
    if cache_key in _WIKI_CACHE:
        return _WIKI_CACHE[cache_key]

    risultato = None
    try:
        titolo = wikipedia_url.rstrip("/").rsplit("/", 1)[-1]

        if categoria in ("grande_citta", "capoluogo"):
            sezioni_da_cercare = list(_WIKI_SEZIONI_PER_CATEGORIA.get(categoria, []))
            if sottocategoria and sottocategoria in _WIKI_SEZIONI_PER_CATEGORIA:
                extra = _WIKI_SEZIONI_PER_CATEGORIA[sottocategoria]
                sezioni_da_cercare = extra + [s for s in sezioni_da_cercare if s not in extra]
        else:
            cat_key = sottocategoria if sottocategoria else "residenziale_minore"
            sezioni_da_cercare = _WIKI_SEZIONI_PER_CATEGORIA.get(cat_key, _WIKI_SEZIONI_PER_CATEGORIA["residenziale_minore"])

        for nome_sezione in sezioni_da_cercare:
            testo = _estrai_sezione_wikipedia(titolo, nome_sezione, timeout=timeout)
            if testo:
                risultato = testo
                break

        if not risultato:
            resp = requests.get(
                f"https://it.wikipedia.org/api/rest_v1/page/summary/{titolo}",
                timeout=timeout,
                headers={"User-Agent": "ReportUp/1.0 (https://reportup.it)"},
            )
            if resp.status_code == 200:
                dati = resp.json()
                if dati.get("type") != "disambiguation":
                    estratto = dati.get("extract", "") or ""
                    estratto = re.sub(r"\([^)]*\)", "", estratto)
                    estratto = re.sub(r"\s+", " ", estratto).strip()
                    if estratto:
                        prima_frase = estratto.split(". ")[0].rstrip(". ").strip() + "."
                        if 30 <= len(prima_frase) <= 220 and "comune italiano" not in prima_frase:
                            risultato = prima_frase

    except Exception:
        risultato = None

    _WIKI_CACHE[cache_key] = risultato
    return risultato


def _target_da_posti_letto(posti_letto):
    try:
        n = int(str(posti_letto).rstrip("+").strip())
    except (ValueError, TypeError):
        n = 4
    if n <= 2:
        return "coppie"
    if n <= 4:
        return "famiglie e piccoli gruppi"
    return "famiglie numerose e gruppi di amici"


def _pulisci_distanza_per_frase(distanza):
    if not distanza or distanza in ("\u2014", "-"):
        return distanza
    t = str(distanza).strip()
    if t[:2].lower() == "a ":
        t = t[2:].strip()
    m = re.match(r'^piedi\s+(.+)$', t, flags=re.IGNORECASE)
    if m:
        return f"{m.group(1)} a piedi"
    m = re.match(r'^auto\s+(.+)$', t, flags=re.IGNORECASE)
    if m:
        return f"{m.group(1)} in auto"
    if not t[:1].isdigit():
        m2 = re.search(r'(\d[\d.,]*\s*(?:km|m|min\.?|ore|h))\s*$', t, flags=re.IGNORECASE)
        if m2 and m2.group(1).strip() != t:
            return m2.group(1).strip()
    return t


_COSTI_PER_TIPOLOGIA = [
    # Sessione 68: pulizie e biancheria ridotte del 20% rispetto ai valori
    # originali (tarati su servizio esterno professionale) per riflettere
    # lo scenario gestione diretta/informale, confermato da benchmark di
    # mercato (€20-40/cambio per unita' piccole-medie). Manutenzione invariata.
    # Sessione 69 (29/8/2026): utenze rialzate, erano sottostimate. Elettricita'
    # scalata per tipologia sui dati reali di Salvatore (bilocale 50€/mese,
    # villa 200€/mese) + 20€/mese internet fisso su tutte le tipologie.
    ("villa", 70, 600, 2650, 900), ("casa indipendente", 70, 600, 2650, 900),
    ("appartamento", 50, 480, 1700, 650), ("4+", 50, 480, 1700, 650), ("grande", 50, 480, 1700, 650),
    ("trilocale", 45, 400, 1200, 500),
    ("bilocale", 35, 320, 840, 350),
    ("doppia", 25, 225, 600, 220),
    ("singola", 20, 175, 480, 180), ("stanza", 20, 175, 480, 180),
]


def _costi_per_tipologia(tipologia):
    t = str(tipologia or "").strip().lower()
    for frammento, pulizie, biancheria, utenze, manutenzione in _COSTI_PER_TIPOLOGIA:
        if frammento in t:
            return pulizie, biancheria, utenze, manutenzione
    return 30, 240, 650, 300


def _calcola_costi_fissi_deterministici(data):
    pulizie, biancheria, utenze, manutenzione = _costi_per_tipologia(data.get("tipologia"))
    # Sessione 67: normalizzazione dei nomi PRIMA del check piscina/giardino.
    # Prima il confronto era sulle stringhe grezze scritte dall'AI
    # ("piscina" minuscolo non matchava "Piscina"): il sovrapprezzo
    # manutenzione scattava in modo casuale tra un run e l'altro (Quarto:
    # €500 con nota giardino; i 7 test nazionali: €350 senza nota, con le
    # stesse dotazioni). Stessa _norm_dotazione gia' usata dal
    # moltiplicatore prezzo e dalla scheda immobile.
    dotazioni = {_norm_dotazione(d) for d in (data.get("dotazioni_presenti") or [])}
    ha_piscina = "Piscina" in dotazioni
    ha_giardino = "Giardino" in dotazioni

    data["costi_pulizie_unit"] = pulizie
    data["costi_biancheria"] = biancheria
    data["costi_utenze"] = utenze
    data["costi_manutenzione"] = manutenzione + (400 if ha_piscina else 0) + (150 if ha_giardino else 0)
    data["_costi_ha_piscina"] = ha_piscina
    data["_costi_ha_giardino"] = ha_giardino


_ETICHETTE_SLOT_POI = {
    "trasporto pubblico", "comune di riferimento", "elemento caratteristico",
    "servizi essenziali", "aeroporto",
}


def _sembra_etichetta_categoria(testo):
    t = str(testo or "").strip().lower()
    if not t:
        return False
    if t in _ETICHETTE_SLOT_POI:
        return True
    return any(p in t for p in ("essenziali", "caratteristico", "trasporto pubblico", "di riferimento"))


def _sembra_distanza(testo):
    t = str(testo or "").strip().lower()
    if any(ch.isdigit() for ch in t):
        return True
    return any(p in t for p in ("piedi", "auto", "min", "km", "in loco"))


def _e_distanza_numerica(testo):
    return any(ch.isdigit() for ch in str(testo or ""))


def _impatto_deterministico(distanza_str, modalita="piedi"):
    """
    Calcola Alto/Medio/Basso da soglie fisse sulla distanza già estratta da
    Google Maps, invece di lasciarlo decidere all'AI. Sessione 64.
    modalita='piedi': per righe camminabili (trasporto pubblico, servizi essenziali).
    modalita='auto': per righe su scala di comune (comune di riferimento, elemento caratteristico).
    Ritorna None se non riesce a estrarre un numero — in quel caso il chiamante
    tiene il valore originale (dato assente/dash, o "In loco").
    """
    testo = str(distanza_str or "").strip().lower()
    if not testo or testo == "—":
        return None
    if "in loco" in testo:
        return "Alto"

    # Priorità ai km se presenti nel testo (es. "30 km auto"), altrimenti
    # ai minuti (es. "15 min a piedi") — evita ambiguità tra i due formati.
    m_km = re.search(r"([\d.,]+)\s*km", testo)
    if m_km:
        try:
            km = float(m_km.group(1).replace(",", "."))
        except ValueError:
            return None
        if modalita == "piedi":
            return "Alto" if km <= 1 else "Medio" if km <= 2.5 else "Basso"
        return "Alto" if km <= 15 else "Medio" if km <= 40 else "Basso"

    m_min = re.search(r"(\d+)\s*min", testo)
    if m_min:
        minuti = int(m_min.group(1))
        return "Alto" if minuti <= 10 else "Medio" if minuti <= 20 else "Basso"

    # Distanze in soli METRI ("250 m a piedi", "800 m") — Sessione 67.
    # Prima non venivano riconosciute (né km né min) e l'impatto restava
    # quello scritto dall'AI, con incoerenze reali nello stesso report
    # (Positano: "300 m" -> Alto ma "250 m" -> Basso). Il \b esclude "min".
    m_metri = re.search(r"(\d+)\s*m\b", testo)
    if m_metri:
        metri = int(m_metri.group(1))
        if modalita == "piedi":
            return "Alto" if metri <= 1000 else "Medio" if metri <= 2500 else "Basso"
        km_eq = metri / 1000
        return "Alto" if km_eq <= 15 else "Medio" if km_eq <= 40 else "Basso"

    return None


_PAROLE_MINUSCOLE_NOMI_POI = {"di", "del", "della", "dei", "delle", "dello", "da", "dal", "dalla",
                               "de", "e", "ed", "la", "le", "lo", "il", "i", "gli", "a", "al",
                               "alla", "in"}


def _titolo_nome_poi(nome):
    """Google/l'AI a volte restituiscono il nome di un punto di interesse con
    solo la PRIMA parola minuscola (es. "campo San Giacomo" invece di "Campo
    San Giacomo", osservato in produzione \u2014 Sessione 78/79). Corregge parola
    per parola, non l'intera stringa: una parola che ha gi\u00e0 una maiuscola al
    suo interno resta intatta (gestisce "San Giacomo", "d'Italia" ecc. senza
    romperli); una parola tutta minuscola viene capitalizzata, TRANNE le
    preposizioni/articoli noti quando non sono la prima parola (cos\u00ec "Duomo
    di Milano" resta "Duomo di Milano" e non diventa "Duomo Di Milano")."""
    t = str(nome or "").strip()
    if not t or t in ("\u2014", "-"):
        return nome
    parole = t.split(" ")
    out = []
    for idx, w in enumerate(parole):
        if any(ch.isupper() for ch in w):
            out.append(w)
        elif idx > 0 and w.lower() in _PAROLE_MINUSCOLE_NOMI_POI:
            out.append(w)
        else:
            out.append(w.capitalize())
    return " ".join(out)


def _correggi_poi_invertiti(poi):
    # Ordine fisso garantito dal prompt: 0=trasporto pubblico, 1=comune di
    # riferimento, 2=elemento caratteristico, 3=servizi essenziali.
    _modalita_per_riga = ["piedi", "auto", "auto", "piedi"]
    corrette = []
    for idx, row in enumerate(poi):
        distanza, nome, impatto = (list(row) + ["\u2014", "\u2014", "\u2014"])[:3]
        if _sembra_etichetta_categoria(nome) and not _sembra_distanza(distanza):
            distanza, nome = nome, distanza
        nome = _titolo_nome_poi(nome)
        modalita = _modalita_per_riga[idx] if idx < len(_modalita_per_riga) else "piedi"
        _impatto_calcolato = _impatto_deterministico(distanza, modalita)
        if _impatto_calcolato:
            impatto = _impatto_calcolato
        corrette.append([distanza, nome, impatto])
    return corrette


def _poi_riga_frase(poi, idx):
    try:
        distanza, nome, _impatto = (list(poi[idx]) + ["\u2014", "\u2014", "\u2014"])[:3]
    except (IndexError, TypeError):
        return ""
    if nome in ("\u2014", "", None):
        return ""
    distanza_pulita = _pulisci_distanza_per_frase(distanza)
    dp = str(distanza_pulita).strip()
    if dp.lower().startswith("in loco"):
        return f"{nome} si trova in loco."
    if not _e_distanza_numerica(dp):
        return f"{nome} \u2014 {dp}."
    return f"{nome} si trova a {dp}."


def genera_descrizione_standard(data):
    categoria   = str(data.get("categoria") or "comune_minore").strip().lower()
    sottocateg  = str(data.get("sottocategoria") or "residenziale_minore").strip().lower()

    tipologia   = str(data.get("tipologia", "Immobile"))
    indirizzo   = str(data.get("indirizzo", ""))
    comune      = str(data.get("comune", ""))
    zona        = str(data.get("zona", "") or "")
    superficie  = str(data.get("superficie", ""))
    camere      = str(data.get("camere", ""))
    bagni       = str(data.get("bagni", ""))
    posti_letto = str(data.get("posti_letto", ""))
    dotazioni   = data.get("dotazioni_presenti", []) or []
    poi         = data.get("poi", []) or []
    fatto_wiki  = data.get("_wikipedia_estratto")

    genere_femminile = any(t in tipologia.lower() for t in ["villa", "casa", "stanza", "camera"])
    situata = "situata" if genere_femminile else "situato"

    camere_frase      = _concorda_numero(camere, "camera", "camere")
    bagni_frase       = _concorda_numero(bagni, "bagno", "bagni")
    posti_letto_frase = _concorda_numero(posti_letto, "posto letto", "posti letto")

    def _fmt_dotazione(d):
        canonico = _norm_dotazione(d)
        return canonico if canonico == "WiFi" else canonico.lower()
    dotazioni_frase = _join_lista_e([_fmt_dotazione(d) for d in dotazioni]) if dotazioni else ""

    zona_inserita = ""
    if categoria in ("capoluogo", "grande_citta") and zona and zona.lower() not in ("—", "", comune.lower()):
        zona_inserita = f", zona {zona}"

    trasporto_frase = _poi_riga_frase(poi, 0)
    servizi_frase   = _poi_riga_frase(poi, 3)
    elemento_frase  = _poi_riga_frase(poi, 2)

    comune_rif_nome, comune_rif_distanza = "", ""
    try:
        _r = list(poi[1]) + ["\u2014", "\u2014", "\u2014"]
        comune_rif_distanza, comune_rif_nome = _r[0], _r[1]
        if comune_rif_nome in ("\u2014", "", None):
            comune_rif_nome = ""
    except (IndexError, TypeError):
        pass

    desc = (
        f"Accogliente {tipologia.lower()} di {superficie} {situata} in {indirizzo}{zona_inserita}, "
        f"con {camere_frase}, {bagni_frase} e {posti_letto_frase}. "
    )
    if dotazioni_frase:
        desc += f"L'immobile è dotato di {dotazioni_frase}: tutto il necessario per un soggiorno confortevole. "
    else:
        desc += "Un immobile pronto ad accogliere i tuoi ospiti. "

    if categoria in ("grande_citta", "capoluogo"):
        if trasporto_frase:
            desc += f"{trasporto_frase.rstrip('.')}, per muoversi in città senza pensieri. "
        if servizi_frase:
            desc += f"{servizi_frase.rstrip('.')}, a portata di mano per ogni necessità quotidiana. "
        if elemento_frase:
            desc += f"{elemento_frase} "
    else:
        if comune_rif_nome:
            _dist_comune_rif = str(_pulisci_distanza_per_frase(comune_rif_distanza)).strip()
            if _dist_comune_rif.lower().startswith("in loco"):
                desc += f"{comune_rif_nome} è in loco, punto di riferimento per servizi e collegamenti più ampi. "
            elif not _e_distanza_numerica(_dist_comune_rif):
                desc += (f"{comune_rif_nome} \u2014 {_dist_comune_rif}, "
                         f"punto di riferimento per servizi e collegamenti più ampi. ")
            else:
                desc += (f"A {_dist_comune_rif} si trova {comune_rif_nome}, "
                         f"punto di riferimento per servizi e collegamenti più ampi. ")
        if trasporto_frase:
            desc += f"{trasporto_frase} "
        if elemento_frase:
            desc += f"{elemento_frase} "
        if servizi_frase:
            desc += f"{servizi_frase.rstrip('.')} nelle vicinanze per le esigenze quotidiane. "

    if fatto_wiki:
        desc += fatto_wiki + " "

    target = _target_da_posti_letto(posti_letto)

    _chiusura_territorio = {
        "costiero": "affacciata sul mare",
        "lacuale":  "affacciata sul lago",
        "montano":  "immersa nella cornice delle montagne",
    }

    if categoria == "grande_citta":
        # Sessione 78 (audit 24/8): extra_territorio prima chiudeva con virgola
        # propria E precedeva "da dentro,", producendo 3 virgole di fila
        # ("città, affacciata sul mare, da dentro, con tutti..."). Spostato
        # dopo "da dentro" per una lettura più scorrevole.
        extra_territorio = f", {_chiusura_territorio[sottocateg]}" if sottocateg in _chiusura_territorio else ""
        desc += (
            f"Ideale per {target} che vogliono vivere la città da dentro{extra_territorio}, con tutti i comfort di casa. "
            "La metropoli offre un'offerta culturale, commerciale e di collegamenti tra le più ricche "
            "del paese, accessibile a piedi o con i mezzi direttamente dall'immobile."
        )
    elif categoria == "capoluogo":
        extra_territorio = f", {_chiusura_territorio[sottocateg]}" if sottocateg in _chiusura_territorio else ""
        desc += (
            f"Ideale per {target} in cerca di una base comoda nel cuore del capoluogo{extra_territorio}. "
            "La posizione garantisce accesso rapido ai principali punti di interesse della città, "
            "mantenendo i vantaggi di una zona vivibile e ben servita."
        )
    elif sottocateg == "costiero":
        desc += (
            f"Ideale per {target} in cerca del fascino della costa. "
            "La zona unisce l'atmosfera marittima a un buon equilibrio tra tranquillità, "
            "servizi e vita locale, lontano dai ritmi frenetici delle grandi città."
        )
    elif sottocateg == "lacuale":
        desc += (
            f"Ideale per {target} in cerca della quiete e della bellezza del lago. "
            "La zona offre l'atmosfera rilassata delle località lacustri, con un equilibrio "
            "tra natura, attività all'aperto e accesso ai servizi essenziali."
        )
    elif sottocateg == "montano":
        desc += (
            f"Ideale per {target} in cerca dell'aria di montagna e del silenzio che solo la quota sa dare. "
            "La zona offre la tranquillità tipica delle località montane, con un equilibrio "
            "tra natura, attività all'aperto e i comfort della vita moderna."
        )
    else:
        desc += (
            f"Ideale per {target} in cerca di tranquillità autentica, lontano dal caos urbano. "
            "La zona offre un ritmo di vita più lento, a contatto con la cultura e le tradizioni locali, "
            "con tutti i servizi essenziali a portata di mano."
        )

    return desc


def build_pdf_bytes(data):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle("ReportUp \u2014 Report Base")
    c.setAuthor("Arch. Salvatore Junior Sica \u00b7 ReportUp")
    for page_fn in [page1, page2, page3, page4, page5]:
        page_fn(c, data)
        c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()


# ── Endpoint ──────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "ReportUp PDF Service"})


@app.route("/categoria-comune", methods=["GET"])
@require_internal_secret
def categoria_comune():
    comune_q = request.args.get("comune", "")
    provincia_q = request.args.get("provincia")

    try:
        record = comuni_lookup.trova_comune(comune_q, provincia_q)

        if not record:
            return jsonify({
                "trovato": False,
                "categoria": "comune_minore",
                "comune": comune_q,
                "provincia": None,
                "sigla_provincia": None,
                "capoluogo": False,
                "grande_citta": False,
            })

        return jsonify({
            "trovato": True,
            "categoria": record["categoria"],
            "comune": record["comune"],
            "provincia": record["provincia"],
            "sigla_provincia": record["sigla_provincia"],
            "capoluogo": str(record.get("capoluogo", "")).strip().upper() == "TRUE",
            "grande_citta": str(record.get("grande_citta", "")).strip().upper() == "TRUE",
            "popolazione": record.get("popolazione"),
        })
    except Exception as e:
        print(f"[CATEGORIA-COMUNE] eccezione: {e}")
        return jsonify({"error": "errore_interno"}), 500


# ── QUICK REPORT — dati reali, senza AI (Sessione 50) ────────────────────────

GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

PREZZO_BASE_CATEGORIA = {
    "capoluogo": 75,
    "grande_citta": 65,
    "comune_minore": 45,
}
OCCUPAZIONE_BASE_FALLBACK = 50

MOLTIPLICATORE_SOTTOCATEGORIA = {
    "costiero": 1.30,
    "lacuale": 1.20,
    "montano": 1.15,
}


def _moltiplicatore_capacita(posti_letto_raw):
    posti = _numero_da_stringa(posti_letto_raw, default=2)
    extra = max(0, posti - 2)
    return round(1.0 + extra * 0.13, 3)


def _geocode_indirizzo(indirizzo, timeout=5):
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key or not indirizzo:
        return None
    try:
        resp = requests.get(
            GOOGLE_GEOCODE_URL,
            params={"address": f"{indirizzo}, Italia", "region": "it",
                    "language": "it", "key": api_key},
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None
        dati = resp.json()
        if dati.get("status") != "OK" or not dati.get("results"):
            print(f"[QUICK] geocode status non OK: {dati.get('status')}")
            return None
        risultato = dati["results"][0]
        loc = risultato["geometry"]["location"]

        # Sessione 76: Google segnala partial_match=true quando ha dovuto
        # "indovinare" per risolvere l'indirizzo (refuso corretto, civico
        # impreciso, ecc). Non è un segnale perfetto — a volte scatta anche
        # su indirizzi corretti ma poco mappati — quindi lo trattiamo come
        # avviso morbido a valle (verify-address/quick-estimate), MAI come
        # blocco: un falso allarme non deve mai impedire un pagamento
        # legittimo. Il geocode resta comunque valido e utilizzabile.
        partial_match = bool(risultato.get("partial_match", False))

        comune, provincia, cap = None, None, None
        for comp in risultato.get("address_components", []):
            tipi = comp.get("types", [])
            if "administrative_area_level_3" in tipi or "locality" in tipi:
                comune = comune or comp.get("long_name")
            if "administrative_area_level_2" in tipi:
                provincia = comp.get("short_name") or comp.get("long_name")
            if "postal_code" in tipi:
                cap = comp.get("long_name")

        return {
            "lat": loc["lat"], "lon": loc["lng"],
            "formatted_address": risultato.get("formatted_address"),
            "comune": comune, "provincia": provincia, "cap": cap,
            "partial_match": partial_match,
        }
    except Exception as e:
        print(f"[QUICK] geocode eccezione: {e}")
        return None


GOOGLE_STATICMAP_URL = "https://maps.googleapis.com/maps/api/staticmap"


def _fetch_static_map_png(lat, lon, timeout=6):
    """Immagine satellitare statica (Google Static Maps) per la pagina 1
    dello Strategico — sostituisce il placeholder "la mappa interattiva
    sarà integrata nella versione finale". Stessa chiave GOOGLE_MAPS_API_KEY
    già in uso per geocode/elevation/distance matrix, nessuna nuova env var.
    Costo trascurabile: una chiamata per report generato, non per visita."""
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key or lat in (None, "") or lon in (None, ""):
        return None
    try:
        resp = requests.get(
            GOOGLE_STATICMAP_URL,
            params={
                "center": f"{lat},{lon}",
                "zoom": 17,
                "size": "640x360",
                "scale": 2,
                "maptype": "satellite",
                "markers": f"color:red|{lat},{lon}",
                "key": api_key,
            },
            timeout=timeout,
        )
        if resp.status_code != 200 or not resp.content:
            print(f"[STATICMAP] status={resp.status_code} lat={lat!r} lon={lon!r}")
            return None
        return resp.content
    except Exception as e:
        print(f"[STATICMAP] eccezione: {e}")
        return None


GOOGLE_PLACES_NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"

POI_KEYWORD_PER_SOTTOCATEGORIA = {
    "montano": ("impianti sciistici", "⛷️"),
    "costiero": ("spiaggia", "🏖️"),
    "lacuale": ("lago", "🚤"),
}


def _cerca_poi_google(lat, lon, keyword, radius_m=15000, max_risultati=2, timeout=5):
    """
    Ricerca reale via Google Places Nearby Search.

    FIX (Sessione 54 — bug trovato a Pozzuoli il 7 luglio): la chiamata non
    specificava mai un criterio di ordinamento, quindi Google applicava il
    default "prominence" — ordina per popolarità/numero di recensioni, non
    per vicinanza. Risultato osservato: a Pozzuoli usciva "Spiaggia di
    Chiaia" (Napoli, molto più recensita) invece delle spiagge di Pozzuoli
    stesso, semplicemente perché più famosa su Google, non perché più vicina.

    Fix: `rankby=distance` (che in Places API richiede di NON passare
    `radius`, ma resta compatibile con `keyword`) ordina i risultati per
    vicinanza reale. In più, calcoliamo comunque la distanza haversine noi
    stessi e riordiniamo/filtriamo lato Python — doppia sicurezza, non ci si
    fida ciecamente dell'ordine restituito da un'API esterna per un dato che
    finisce stampato nel PDF/mail del cliente.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return []
    try:
        resp = requests.get(
            GOOGLE_PLACES_NEARBY_URL,
            params={"location": f"{lat},{lon}", "rankby": "distance", "keyword": keyword,
                    "language": "it", "key": api_key},
            timeout=timeout,
        )
        if resp.status_code != 200:
            return []
        dati = resp.json()
        if dati.get("status") not in ("OK", "ZERO_RESULTS"):
            print(f"[QUICK] Places status non OK per '{keyword}': {dati.get('status')}")
            return []
        risultati = []
        for r in dati.get("results", []):
            loc = r.get("geometry", {}).get("location", {})
            if r.get("name") and loc.get("lat") is not None and loc.get("lng") is not None:
                dist_km = _haversine_km(float(lat), float(lon), loc["lat"], loc["lng"])
                if dist_km * 1000 <= radius_m:
                    risultati.append({"nome": r["name"], "lat": loc["lat"], "lon": loc["lng"], "_dist_km": dist_km})
        # Riordino esplicito lato Python per vicinanza reale — non ci affidiamo
        # solo all'ordine restituito dall'API, anche con rankby=distance.
        risultati.sort(key=lambda x: x["_dist_km"])
        return risultati[:max_risultati]
    except Exception as e:
        print(f"[QUICK] Places eccezione per '{keyword}': {e}")
        return []


def _punti_interesse_quick(lat, lon, sottocategoria):
    punti = []

    if sottocategoria in POI_KEYWORD_PER_SOTTOCATEGORIA:
        keyword, icona = POI_KEYWORD_PER_SOTTOCATEGORIA[sottocategoria]
        for luogo in _cerca_poi_google(lat, lon, keyword, max_risultati=2):
            dist_km = round(_haversine_km(float(lat), float(lon), luogo["lat"], luogo["lon"]), 1)
            punti.append({"nome": luogo["nome"], "distanza": f"{dist_km} km in linea d'aria", "icon": icona})

    if len(punti) < 2:
        aero = aeroporto_row(lat, lon)
        if aero[1] != "\u2014":
            punti.append({"nome": aero[1], "distanza": aero[0], "icon": "✈️"})

    if len(punti) < 2 and sottocategoria not in POI_KEYWORD_PER_SOTTOCATEGORIA:
        for luogo in _cerca_poi_google(lat, lon, "attrazione turistica", max_risultati=1):
            dist_km = round(_haversine_km(float(lat), float(lon), luogo["lat"], luogo["lon"]), 1)
            punti.append({"nome": luogo["nome"], "distanza": f"{dist_km} km in linea d'aria", "icon": "📍"})

    return punti[:2]


@app.route("/verify-address", methods=["POST", "OPTIONS"])
@require_origin_reportup
def verify_address():
    """Chiamato dal form Base (Sessione 54) prima di mandare il cliente su
    Stripe: verifica che l'indirizzo sia realmente geolocalizzabile, per
    evitare pagamenti incassati senza che il report riesca mai a generarsi
    più avanti nella pipeline Make (il geocode fallirebbe silenziosamente).

    Sessione 76: aggiunto "precisione_incerta" — segnala quando Google ha
    dovuto correggere/indovinare l'indirizzo digitato (partial_match) invece
    di trovare una corrispondenza esatta. È un avviso morbido, MAI un
    blocco: "valido" resta l'unico campo che decide se procedere o no. Il
    frontend può mostrare un "controlla che sia scritto giusto" senza mai
    impedire il pagamento — Google trova comunque l'indirizzo, il rischio è
    solo estetico (es. un refuso che resta visibile nel PDF finale)."""
    if request.method == "OPTIONS":
        resp = jsonify({"ok": True})
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp

    def _risposta(payload, status=200):
        resp = jsonify(payload)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp, status

    body = request.get_json(force=True, silent=True) or {}
    indirizzo = (body.get("indirizzo") or "").strip()
    if not indirizzo or len(indirizzo) > 200:
        return _risposta({"valido": False, "precisione_incerta": False})

    try:
        geo = _geocode_indirizzo(indirizzo)
        return _risposta({
            "valido": bool(geo),
            "precisione_incerta": bool(geo and geo.get("partial_match")),
        })
    except Exception as e:
        print(f"[VERIFY-ADDRESS] eccezione: {e}")
        return _risposta({"error": "errore_interno"}, 500)


@app.route("/quick-estimate", methods=["POST", "OPTIONS"])
@require_origin_reportup
def quick_estimate():
    if request.method == "OPTIONS":
        resp = jsonify({"ok": True})
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp

    def _risposta(payload, status=200):
        resp = jsonify(payload)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp, status

    body = request.get_json(force=True, silent=True) or {}
    indirizzo = (body.get("indirizzo") or "").strip()
    if not indirizzo:
        return _risposta({"error": "indirizzo_mancante"}, 400)
    if len(indirizzo) > 200:
        return _risposta({"error": "indirizzo_troppo_lungo"}, 400)

    geo = _geocode_indirizzo(indirizzo)
    if not geo:
        return _risposta({
            "error": "indirizzo_non_trovato",
            "message": "Non riusciamo a localizzare questo indirizzo. Controlla via, città e CAP."
        }, 422)

    try:
        lat, lon = geo["lat"], geo["lon"]
        record_comune = comuni_lookup.trova_comune(geo.get("comune") or "", geo.get("provincia"))
        categoria = record_comune["categoria"] if record_comune else "comune_minore"
        sottocategoria = territorio_gps.classifica_sottocategoria(lat, lon)

        # Normalizzazione camere + posti letto dalla mappa unica (Sessione 75) —
        # rete di sicurezza backend: anche se il form Quick invia camere già
        # calcolate, le ricduciamo alla stessa fonte di verità di Base/Strategico
        # così AirROI riceve `bedrooms` e `guests` coerenti tra tutti i prodotti.
        # Il valore posti letto scelto dall'utente vince sempre sul default.
        _camere_quick = _camere_deterministiche(body.get("tipologia"), body.get("camere"))
        _posti_quick = _posti_letto_default(body.get("tipologia"), body.get("posti_letto"))

        airroi = _airroi_lookup_e_stima(
            lat, lon,
            camere_raw=_camere_quick,
            posti_letto_raw=_posti_quick,
            bagni_raw=body.get("bagni"),
        )
        print(f"[QUICK] indirizzo={indirizzo!r} lat={lat!r} lon={lon!r} categoria={categoria!r} sottocategoria={sottocategoria!r} "
              f"tipologia={body.get('tipologia')!r} camere_form={body.get('camere')!r}->norm={_camere_quick!r} "
              f"posti_form={body.get('posti_letto')!r}->norm={_posti_quick!r} bagni_raw={body.get('bagni')!r} "
              f"airroi_trovato={bool(airroi)} distribuzione_mensile_presente={bool(airroi and airroi.get('distribuzione_mensile'))}")

        if airroi:
            _prezzo_medio_grezzo = airroi["prezzo_notte_stimato"]
            _correttivo_occ, _fonte_occ = stagionalita_turistica.correttivo_occupazione(
                sottocategoria, categoria, record_comune["comune"] if record_comune else geo.get("comune")
            )
            _tetto_occ = stagionalita_turistica.tetto_occupazione(_fonte_occ)
            occupazione_percent = min(_tetto_occ, round(airroi["occupazione_percent"] * _correttivo_occ))
            # Prezzo del MESE CORRENTE (non la media annua piatta) — stessa logica
            # usata dal Base per la tabella mensile, così Quick e Base mostrano un
            # numero coerente per lo stesso "oggi" invece di un piatto vs un picco
            # non allineati. Sessione 66.
            prezzo_notte, _fonte_prezzo_mese = stagionalita_turistica.prezzo_mese_corrente(
                _prezzo_medio_grezzo, sottocategoria, categoria,
                record_comune["comune"] if record_comune else geo.get("comune"),
                distribuzione_mensile=airroi.get("distribuzione_mensile"),
            )
            fonte_prezzo = "airroi"
            n_comparabili = len(airroi["comparable_listings"]) if airroi.get("comparable_listings") else 0
            print(f"[QUICK] fonte={_fonte_occ!r} correttivo_occ={_correttivo_occ} tetto_occ={_tetto_occ} "
                  f"occupazione_grezza_airroi={airroi['occupazione_percent']!r} occupazione_percent_corretta={occupazione_percent} "
                  f"prezzo_medio_grezzo={_prezzo_medio_grezzo} mese_idx={stagionalita_turistica.mese_corrente_idx()} "
                  f"fonte_prezzo_mese={_fonte_prezzo_mese!r} prezzo_notte_mese_corrente={prezzo_notte}")
        else:
            base = PREZZO_BASE_CATEGORIA.get(categoria, PREZZO_BASE_CATEGORIA["comune_minore"])
            mult_zona = MOLTIPLICATORE_SOTTOCATEGORIA.get(sottocategoria, 1.0)
            mult_capacita = _moltiplicatore_capacita(_posti_quick)
            _prezzo_medio_grezzo = round(base * mult_zona * mult_capacita)
            prezzo_notte, _fonte_prezzo_mese = stagionalita_turistica.prezzo_mese_corrente(
                _prezzo_medio_grezzo, sottocategoria, categoria,
                record_comune["comune"] if record_comune else geo.get("comune"),
            )
            occupazione_percent = OCCUPAZIONE_BASE_FALLBACK
            fonte_prezzo = "stima_deterministica"
            n_comparabili = 0
            print(f"[QUICK] AirROI assente — fallback deterministico. prezzo_medio_grezzo={_prezzo_medio_grezzo} "
                  f"fonte_prezzo_mese={_fonte_prezzo_mese!r} prezzo_notte_mese_corrente={prezzo_notte}")

        # Il potenziale annuo lordo resta calcolato sul prezzo MEDIO annuo, non sul
        # prezzo del mese corrente appena mostrato: mischiare un prezzo di un
        # singolo mese con un numero di notti annuo darebbe un potenziale annuo
        # falsato (gonfiato in alta stagione, sottostimato in bassa stagione).
        notti_anno = round(365 * occupazione_percent / 100)
        potenziale_lordo = _prezzo_medio_grezzo * notti_anno

        if airroi and airroi.get("comparable_listings"):
            prezzi_comparabili = [
                _numero_da(a, "average_daily_rate", "adr", "price", "daily_rate")
                for a in airroi["comparable_listings"] if isinstance(a, dict)
            ]
            prezzi_comparabili = [p for p in prezzi_comparabili if p]
            media_locale = round(sum(prezzi_comparabili) / len(prezzi_comparabili)) if prezzi_comparabili else None
        else:
            media_locale = None

        if media_locale:
            _delta_percent_log = round((prezzo_notte - media_locale) / media_locale * 100)
            print(f"[QUICK] posizionamento reale vs comparabili locali: {_delta_percent_log}%")
            sopra_media = prezzo_notte >= media_locale
        else:
            sopra_media = None

        if sopra_media is True:
            posizionamento_messaggio = "Il tuo immobile è già posizionato sopra la media della zona: un ottimo punto di partenza."
        else:
            posizionamento_messaggio = "C'è margine di crescita per il tuo immobile in questa zona: il Report Base ti mostra esattamente come sfruttarlo."

        punti_interesse = _punti_interesse_quick(lat, lon, sottocategoria)

        print(f"[QUICK] RISPOSTA FINALE indirizzo={indirizzo!r} prezzo_notte={prezzo_notte} "
              f"occupazione_percent={occupazione_percent} notti_anno={notti_anno} potenziale_lordo={potenziale_lordo} "
              f"fonte_prezzo={fonte_prezzo!r}")

        return _risposta({
            "indirizzo": geo["formatted_address"],
            "comune": record_comune["comune"] if record_comune else geo.get("comune"),
            "categoria": categoria,
            "sottocategoria": sottocategoria,

            "fonte_prezzo": fonte_prezzo,
            "comparabili_airroi": n_comparabili,

            "prezzo_notte": prezzo_notte,
            "occupazione_percent": occupazione_percent,
            "notti_anno": notti_anno,
            "potenziale_lordo": potenziale_lordo,

            "posizionamento_messaggio": posizionamento_messaggio,

            "punti_interesse": punti_interesse,

            # Sessione 76: stesso avviso morbido di /verify-address, gratis qui
            # perché usa lo stesso geocode già fatto sopra. Il Quick può mostrare
            # "verifica che l'indirizzo sia scritto giusto" senza mai bloccare —
            # il report è comunque generato correttamente.
            "precisione_incerta": bool(geo.get("partial_match")),
        })
    except Exception as e:
        print(f"[QUICK] eccezione: {e}")
        return _risposta({"error": "errore_interno"}, 500)


def _elabora_dati_report_base(raw, lat=None, long=None):
    """Parsa il testo grezzo restituito dall'AI (HTTP2) e applica tutte le
    correzioni deterministiche + l'integrazione AirROI (vedi
    _arricchisci_report_deterministico, condivisa con lo Strategico),
    producendo il dict 'data' finale usato sia per generare il PDF sia per
    popolare i campi economici nella mail (modulo HTTP24/JSON25 su Make)."""
    import json as _json
    import re as _re
    cleaned = raw.strip()
    m = _re.search(r'```(?:json)?\s*(\{.*\})\s*```', cleaned, _re.DOTALL)
    if m:
        cleaned = m.group(1).strip()
    else:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start:end+1]

    data = _json.loads(cleaned)
    data = normalize_data(data)
    return _arricchisci_report_deterministico(data, lat=lat, long=long, generare_descrizione=True)


def _arricchisci_report_deterministico(data, lat=None, long=None, generare_descrizione=True, correggere_poi=True):
    """Applica a un dict `data` già JSON-parsato (Base o Strategico) tutte le
    correzioni deterministiche + l'integrazione AirROI condivise dai due
    prodotti: stagionalità, prezzo/occupazione reali, competitor, confronto
    affitto tradizionale, dotazioni_assenti, costi fissi. Usata sia da
    _elabora_dati_report_base sia da /generate-strategico (riapertura
    cantiere Strategico), così i due prodotti restano allineati sullo stesso
    motore di calcolo — lo Strategico aggiunge sopra solo i suoi campi
    esclusivi (scenari, piano 90gg, normativa, pricing mensile, ecc.),
    non li ricalcola da zero né lascia che l'AI inventi numeri che il Base
    calcola in modo deterministico.
    generare_descrizione=False per lo Strategico: usa una descrizione AI
    dedicata (prompt Strategico, più lunga e contestualizzata), non quella
    del Base.
    correggere_poi=False per lo Strategico: _correggi_poi_invertiti è
    costruita per lo schema POI del Base (4 slot FISSI — trasporto pubblico/
    comune di riferimento/elemento caratteristico/servizi essenziali — righe
    a 3 campi [distanza, nome, impatto], etichetta di categoria esterna via
    SLOT_LABELS). Lo Strategico usa invece N punti liberi con 4 campi ciascuno
    [nome, a_piedi, mezzo_pubblico, impatto] (vedi page2 in strategico.py):
    applicare la correzione del Base disallinea le colonne. Finché lo
    scenario Make dello Strategico non viene ricostruito per passare POI
    reali Google Places nel SUO formato, il campo resta generato dall'AI."""
    import re as _re

    # Sessione 72: l'AI a volte scrive un'occupazione con meno di 12 mesi
    # (bug reale Positano — mancava "Mag"). Ricostruiamo sempre 12 righe
    # canoniche PRIMA che curva/AirROI entrino in gioco — vedi commento
    # dettagliato su _normalizza_occupazione_12_mesi() più sopra nel file.
    if "occupazione" in data:
        _occ_mesi_ricevuti = [str(r[0]) for r in (data.get("occupazione") or []) if r]
        if len(_occ_mesi_ricevuti) != 12:
            print(f"[STAGIONALITA-DEBUG] occupazione AI con {len(_occ_mesi_ricevuti)} mesi invece di 12 "
                  f"(ricevuti: {_occ_mesi_ricevuti!r}) — ricostruita a 12 mesi canonici prima di applicare "
                  f"curva/AirROI, indirizzo={data.get('indirizzo')!r}")
        data["occupazione"] = _normalizza_occupazione_12_mesi(data.get("occupazione"))

    # Dotazioni assenti: pura sottrazione insiemistica (lista standard meno
    # quelle dichiarate presenti dal cliente) — zero margine di invenzione,
    # l'AI non decide più questo campo. Sessione 64.
    # Flag di situazione: normalizzati prima di qualsiasi calcolo che li legge
    # (mutuo nei costi, "Situazione" nella card, scenari).
    _normalizza_situazione(data)

    _dot_presenti_norm = [_norm_dotazione(d) for d in (data.get("dotazioni_presenti") or [])]
    data["dotazioni_assenti"] = [d for d in DOTAZIONI_AMMESSE if d not in _dot_presenti_norm]

    if lat and long:
        data["lat"] = lat
        data["long"] = long
    for campo in ["camere", "bagni", "posti_letto", "superficie", "piano", "stato", "epoca", "tipologia", "comune", "zona", "indirizzo"]:
        if campo in data and not isinstance(data[campo], str):
            data[campo] = str(data[campo])

    if "comune" in data:
        data["comune"] = _title_preserva_romani(data["comune"])
    if "zona" in data:
        data["zona"] = _title_preserva_romani(data["zona"]) if _zona_sembra_valida(data["zona"]) else "—"

    _record_comune = comuni_lookup.trova_comune(data.get("comune", ""), data.get("provincia"))
    if _record_comune:
        # Il nome del comune scritto dall'AI può contenere refusi (es. una
        # lettera di troppo); il CSV è la fonte di verità, sovrascriviamo
        # sempre con l'ortografia ufficiale invece di fidarci dell'AI.
        data["comune"] = _record_comune["comune"]
    data["categoria"] = _record_comune["categoria"] if _record_comune else "comune_minore"
    data["sottocategoria"] = territorio_gps.classifica_sottocategoria(data.get("lat"), data.get("long"))
    data["_wikipedia_estratto"] = _estratto_wikipedia(
        _record_comune.get("wikipedia") if _record_comune else None,
        categoria=data["categoria"],
        sottocategoria=data["sottocategoria"],
    )

    if "indirizzo" in data:
        import re as _re2
        addr = data["indirizzo"].strip()
        addr = _re2.sub(r'\s*(\d{5})\s*', r', \1, ', addr)
        addr = _re2.sub(r',\s*,', ',', addr)
        addr = _re2.sub(r'\s+', ' ', addr).strip().strip(',').strip()
        data["indirizzo"] = _title_preserva_romani(addr)
        if _record_comune and _record_comune.get("sigla_provincia"):
            _sigla_corretta = _record_comune["sigla_provincia"].upper()
            if _re.search(r'\([A-Za-z]{2}\)', data["indirizzo"]):
                data["indirizzo"] = _re.sub(r'\([A-Za-z]{2}\)', f"({_sigla_corretta})", data["indirizzo"])
            else:
                data["indirizzo"] = f"{data['indirizzo']} ({_sigla_corretta})"
        else:
            data["indirizzo"] = _re.sub(r'\(([A-Za-z]{2})\)', lambda m: f"({m.group(1).upper()})", data["indirizzo"])

    _calcola_costi_fissi_deterministici(data)
    # Sessione 69/70: il log diagnostico temporaneo che stava qui (dotazioni
    # grezze/normalizzate/piscina/giardino) è stato rimosso in Sessione 78
    # (audit 24/8) — il bug che doveva diagnosticare (normalizzazione dei
    # nomi dotazioni PRIMA del check piscina/giardino) è già corretto sopra,
    # in _calcola_costi_fissi_deterministici.

    # ── Confronto affitto tradizionale — ora da AirROI, non più da OMI ──
    # Sessione 68: rimosso l'appoggio ai canoni OMI (dato Salvatore: fuori
    # mercato su gran parte dei comuni). Il calcolo vero avviene più sotto,
    # dopo la correzione finale del prezzo/notte AirROI — vedi
    # stagionalita_turistica.stima_affitto_tradizionale().

    _cat = data.get("categoria", "comune_minore")
    _sub = data.get("sottocategoria", "residenziale_minore") or "residenziale_minore"
    _p = data.get("prezzo_notte_stimato", 0)

    # Camere corrette per tipologia (Sessione 66) — sovrascrive quanto
    # scritto dall'AI PRIMA di mandarlo ad AirROI, così la stima di prezzo
    # e la scheda immobile mostrata usano lo stesso numero corretto.
    data["camere"] = _camere_deterministiche(data.get("tipologia"), data.get("camere"))

    # Posti letto: se il form non ha inviato un valore (campo vuoto), usa il
    # default per tipologia dalla mappa unica (Sessione 75). Se l'utente ha
    # scelto un valore, quello resta intatto. Così AirROI riceve sempre un
    # `guests` sensato e la descrizione narrativa non resta senza posti letto.
    data["posti_letto"] = _posti_letto_default(data.get("tipologia"), data.get("posti_letto"))

    print(f"[AIRROI] chiamata per indirizzo={data.get('indirizzo')!r} lat={data.get('lat')!r} long={data.get('long')!r} email_destinatario={data.get('email')!r}")

    _occ_old = data.get("occupazione_percent", 0)

    _airroi = _airroi_lookup_e_stima(
        data.get("lat"), data.get("long"),
        camere_raw=data.get("camere"), posti_letto_raw=data.get("posti_letto"),
        bagni_raw=data.get("bagni"),
    )

    # Dati di mercato extra (B9) — solo Strategico li mostra (nuova pagina
    # in strategico.py), ma il campo viene popolato qui perché è la stessa
    # chiamata AirROI condivisa col Base; il Base semplicemente non li legge
    # mai (hardening .get() ovunque), zero rischio di regressione su di lui.
    if _airroi:
        for _campo in ("percentili_prezzo", "percentili_occupazione",
                       "pct_gestione_professionale", "n_comparabili_gestione",
                       "trend_stagionale"):
            if _airroi.get(_campo) is not None:
                data[_campo] = _airroi[_campo]

    # Correttivo occupazione AirROI — Sessione 65, differenziato per
    # categoria (vedi stagionalita_turistica.py per fonti e ragionamento).
    # Sostituisce il correttivo fisso 1.35 di ieri.
    _correttivo_occ, _fonte_correttivo = stagionalita_turistica.correttivo_occupazione(
        _sub, _cat, data.get("comune")
    )

    if _airroi:
        # Sessione 68: se ci sono abbastanza comparabili REALI della stessa
        # tipologia dichiarata (bilocale/trilocale/...), ancoriamo il prezzo
        # base a quella media invece che al modello puntuale AirROI — stesso
        # numero che finisce nella riga competitor corrispondente, quindi
        # nessun gap ingiustificato tra "IL TUO IMMOBILE" e "Bilocali zona"
        # nella stessa tabella. Vedi _prezzo_da_comparabili_stessa_tipologia.
        _prezzo_comparabili = _prezzo_da_comparabili_stessa_tipologia(
            _airroi.get("comparable_listings"), data.get("camere")
        )
        if _prezzo_comparabili is not None:
            _p_new = round(_prezzo_comparabili)
            data["fonte_prezzo"] = "comparabili_reali"
            print(f"[PREZZO] uso media comparabili reali stessa tipologia: € {_p_new} "
                  f"invece del modello AirROI (€ {round(_airroi['prezzo_notte_stimato'])})")
        else:
            _p_new = _airroi["prezzo_notte_stimato"]
            data["fonte_prezzo"] = "airroi"
        _tetto_occ = stagionalita_turistica.tetto_occupazione(_fonte_correttivo)
        _occ_comparabili = _occupazione_da_comparabili(_airroi.get("comparable_listings"))
        if _occ_comparabili is not None:
            _occ_new = min(_tetto_occ, round(_occ_comparabili))
            data["fonte_occupazione"] = "comparabili_reali"
            print(f"[OCCUPAZIONE] uso media comparabili reali (scontata 10%): {round(_occ_comparabili)}% "
                  f"invece del correttivo generico ({round(min(_tetto_occ, _airroi['occupazione_percent'] * _correttivo_occ))}%)")
        else:
            _occ_new = min(_tetto_occ, round(_airroi["occupazione_percent"] * _correttivo_occ))
            data["fonte_occupazione"] = "correttivo_percentili"

        # Posizionamento stagionale (pag. 10 Strategico, L90D/TTM): stesso
        # correttivo_occ + tetto applicati sopra all'occupazione_percent
        # principale, altrimenti questa tabella mostra l'occupazione AirROI
        # grezza (tipicamente ottimistica) mentre il resto del report usa
        # sempre il dato corretto — due numeri diversi per lo stesso concetto
        # nello stesso PDF. RevPAR ricalcolato di conseguenza (ADR x Occ%,
        # stessa formula del KPI di pag. 13) per restare coerente col prezzo.
        if data.get("trend_stagionale"):
            # dict() copia: "trend_stagionale" è lo stesso oggetto salvato in
            # _AIRROI_CACHE (15 min TTL). Mutarlo in-place applicherebbe il
            # correttivo una seconda volta a ogni cache-hit sullo stesso
            # indirizzo entro la TTL, drift cumulativo silenzioso.
            _ts = dict(data["trend_stagionale"])
            _ts["occupazione_l90d"] = min(_tetto_occ, round(_ts["occupazione_l90d"] * _correttivo_occ))
            _ts["occupazione_ttm"] = min(_tetto_occ, round(_ts["occupazione_ttm"] * _correttivo_occ))
            _ts["revpar_l90d"] = round(_ts["prezzo_l90d"] * _ts["occupazione_l90d"] / 100)
            _ts["revpar_ttm"] = round(_ts["prezzo_ttm"] * _ts["occupazione_ttm"] / 100)
            data["trend_stagionale"] = _ts
    else:
        _moltiplicatore = 1.05 if (_cat == "comune_minore" and _sub == "residenziale_minore") else 1.15
        _p_new = round(_p * _moltiplicatore) if _p else _p
        _occ_new = _occ_old
        _tetto_occ = stagionalita_turistica.tetto_occupazione(_fonte_correttivo)
        data["fonte_occupazione"] = "ai_stima"
        data["fonte_prezzo"] = "ai_stima"

    # Incremento per dotazioni di valore (Sessione 66) — applicato UNA VOLTA
    # qui, prima che _p_new si propaghi su tabella mensile, ricavi e KPI, così
    # il bonus vale in automatico ovunque compaia il prezzo, indipendente
    # dalla fonte (AirROI o stima AI). WiFi/aria condizionata/riscaldamento/
    # bagni non danno incremento — vedi INCREMENTO_PREZZO_PER_DOTAZIONE.
    if _p_new:
        _mult_dotazioni = _moltiplicatore_dotazioni(data.get("dotazioni_presenti"))
        if _mult_dotazioni != 1:
            _p_new = round(_p_new * _mult_dotazioni)
            # Sessione 68: percentuale salvata per il disclaimer nella tabella
            # competitor — spiega al cliente perché "IL TUO IMMOBILE" può
            # differire dalla media della stessa tipologia in tabella.
            data["dotazioni_bonus_pct"] = round((_mult_dotazioni - 1) * 100)

    # Sessione 69: tabella competitor tolta ad AirROI/AI del tutto — vedi
    # _costruisci_competitor_deterministico. Nessun fallback su comparabili
    # reali o percentili: la voce "stessa tipologia" deve combaciare SEMPRE
    # con "IL TUO IMMOBILE", mai un dato esterno scollegato.
    data["competitor"] = _costruisci_competitor_deterministico(_p_new, data.get("tipologia"))
    data["fonte_competitor"] = "calcolo_interno"

    # Sessione 78 (audit 24/8): il mutuo (rata mensile x 12 = costo annuo,
    # invariato — il report ragiona sempre su base annua) veniva sommato ai
    # costi qui sotto quando _p è valorizzato, E DI NUOVO in un blocco quasi
    # identico a fine funzione, sempre se mutuo_attivo. Stesso risultato
    # (nessun numero cambiava), solo calcolato due volte: rischio vero è che
    # in futuro un costo aggiunto solo qui sopra sparisca silenziosamente,
    # sovrascritto dal ricalcolo sotto che non lo conosce. Il flag evita la
    # doppia esecuzione; il blocco a fine funzione resta SOLO per il caso
    # _p mancante (fallback AI, mutuo mai sommato altrove in quel caso).
    _mutuo_gia_incluso_nel_totale = False

    if _p:
        data["prezzo_notte_stimato"] = _p_new
        data["occupazione_percent"] = _occ_new

        _notti_new = round(_occ_new / 100 * 365) if _occ_new else 0
        data["notti_anno"] = _notti_new
        data["kpi_occupazione"] = _occ_new

        _ricavo_lordo_new = round(_p_new * _notti_new)
        # Bonus prenotazioni dirette: 7% del ricavo lordo, punto centrale della
        # forbice 5-10% dichiarata in tabella. Prima si riscalava il valore
        # scritto dall'AI, che quindi restava una percentuale leggermente
        # diversa a ogni generazione: sullo stesso immobile il Base mostrava
        # € 2.228 e lo Strategico € 2.235. Ora è lo stesso numero su entrambi.
        _bonus_new = round(_ricavo_lordo_new * 0.07)
        data["bonus_dirette_pct"] = "5-10%"
        _totale_ricavi_new = _ricavo_lordo_new + _bonus_new

        _comm_pct = data.get("costi_commissioni_pct", 15)
        _pulizia_unit = data.get("costi_pulizie_unit", 35)
        _costi_commissioni_new = round(_ricavo_lordo_new * _comm_pct / 100)
        # Pulizie per CAMBIO ospite, non per notte — Sessione 67. Vedi
        # SOGGIORNO_MEDIO_PER_CATEGORIA in stagionalita_turistica.py per
        # motivazione e valori. cambi = notti / durata media soggiorno.
        _soggiorno_medio = stagionalita_turistica.soggiorno_medio(_fonte_correttivo)
        _cambi_new = max(1, round(_notti_new / _soggiorno_medio)) if _notti_new else 0
        data["cambi_anno"] = _cambi_new
        data["soggiorno_medio_notti"] = _soggiorno_medio
        _costi_pulizie_new = round(_pulizia_unit * _cambi_new)
        _costi_biancheria = data.get("costi_biancheria", 0)
        _costi_utenze = data.get("costi_utenze", 0)
        _costi_manutenzione = data.get("costi_manutenzione", 0)
        _mutuo_annuo = data.get("rata_mutuo_mensile", 0) * 12 if data.get("mutuo_attivo") else 0
        if data.get("mutuo_attivo") and data.get("rata_mutuo_mensile", 0):
            _mutuo_gia_incluso_nel_totale = True

        _totale_costi_new = (_costi_commissioni_new + _costi_pulizie_new
                              + _costi_biancheria + _costi_utenze
                              + _costi_manutenzione + _mutuo_annuo)
        _profitto_netto_new = _totale_ricavi_new - _totale_costi_new

        data["ricavo_lordo"] = _ricavo_lordo_new
        data["bonus_dirette"] = _bonus_new
        data["totale_ricavi"] = _totale_ricavi_new
        data["costi_commissioni"] = _costi_commissioni_new
        data["costi_pulizie"] = _costi_pulizie_new
        data["totale_costi"] = _totale_costi_new
        data["profitto_netto"] = _profitto_netto_new
        data["margine_percent"] = round(_profitto_netto_new / _totale_ricavi_new * 100) if _totale_ricavi_new else 0
        data["kpi_prezzo"] = _p_new
        data["kpi_potenziale"] = _ricavo_lordo_new

        # Range KPI ricalcolati sui valori REALI corretti (AirROI + smorzamento
        # + dotazioni), non più lasciati come testo libero scritto dall'AI.
        # Prima "kpi_occ_range"/"kpi_prezzo_range" restavano quello che l'AI
        # aveva scritto nel suo JSON, scollegati dal valore finale corretto in
        # Python — es. "Media zona: 65-72%" accanto a un'occupazione REALE del
        # 47% per lo stesso immobile, un'incoerenza vistosa nello stesso
        # report. Ora la fascia è sempre ancorata al valore vero. Sessione 66.
        # Banda ±25% -> ±20% (Sessione 78, audit 24/8): su richiesta di
        # Salvatore, restretta di 5 punti perché troppo larga da sembrare
        # poco credibile su un report a pagamento (es. "60-98%" di
        # occupazione). Resta comunque un range simmetrico attorno al valore
        # stimato, non un dato di mercato osservato riga per riga.
        data["kpi_prezzo_range"] = f"Range zona: € {max(1, round(_p_new * 0.80))}-{round(_p_new * 1.20)}"
        _occ_range_min = max(5, round(_occ_new * 0.80))
        _occ_range_max = min(_tetto_occ, round(_occ_new * 1.20))
        data["kpi_occ_range"] = f"Media zona: {_occ_range_min}-{_occ_range_max}%"

        try:
            _curva, _fonte_stagionalita = stagionalita_turistica.ottieni_curva_stagionale(
                _sub, _cat, data.get("comune")
            )
        except Exception as _err_stag:
            print(f"[STAGIONALITA] errore imprevisto, curva non sostituita: {_err_stag!r}")
            _curva, _fonte_stagionalita = None, None
        data["fonte_stagionalita"] = _fonte_stagionalita or "stima_ai"

        if "occupazione" in data and _curva:
            if _fonte_stagionalita == "montano_invernale":
                # Comune a doppia vocazione nota (sci + estate): la curva
                # bimodale curata vince SEMPRE, anche se AirROI fornisce una
                # sua distribuzione_mensile. Motivo: su mercati piccoli come
                # questi, AirROI ha visibilità limitata anche lei sulle
                # prenotazioni invernali — il suo dato "reale" rischierebbe
                # di ereditare la stessa sottostima invernale che stiamo
                # correggendo, solo da un'altra fonte. Verificato in Sessione
                # 63 su Pescasseroli: con priorità AirROI la curva tornava
                # a un unico picco estivo nonostante il fix.
                print(f"[STAGIONALITA] curva bimodale (priorità su AirROI) per comune={data.get('comune')!r}")
                data["occupazione"] = stagionalita_turistica.applica_curva(_occ_new, _p_new, _curva, tetto_massimo=_tetto_occ)
            elif _airroi and _airroi.get("distribuzione_mensile"):
                # Dato mensile REALE da AirROI: priorità massima, nessuna curva
                # sostitutiva necessaria — è il caso migliore possibile.
                data["occupazione"] = _applica_stagionalita_airroi(
                    data["occupazione"], _airroi["distribuzione_mensile"], _p_new,
                    occ_annuale=_occ_new, tetto_massimo=_tetto_occ,
                )
                data["fonte_stagionalita"] = "airroi_reale"
            else:
                # Il LIVELLO annuo (_occ_new/_p_new) è reale se c'è AirROI,
                # oppure stima AI col moltiplicatore fisso se il mercato non è
                # osservato (comportamento invariato, unico caso in cui l'AI
                # resta in gioco). La FORMA dei 12 mesi non è MAI più quella
                # inventata dall'AI: viene sempre dalla curva di categoria
                # territoriale (vedi stagionalita_turistica.py).
                print(f"[STAGIONALITA] curva '{_fonte_stagionalita}' applicata per comune={data.get('comune')!r}")
                data["occupazione"] = stagionalita_turistica.applica_curva(_occ_new, _p_new, _curva, tetto_massimo=_tetto_occ)

    data["mesi_affidabili_idx"] = _mesi_affidabili()

    # Confronto affitto tradizionale — Sessione 71: sistema MISTO.
    # Solo per "generico" (comune minore SENZA vocazione turistica nota:
    # non città/grande_città, non costiero/lacuale/montano) si tenta prima
    # il canone OMI reale (Agenzia Entrate, per m2 di zona) — dato Salvatore,
    # più affidabile dell'AirROI su questi comuni perché il mercato è
    # omogeneo e non guidato da logiche di breve termine. Città e comuni a
    # forte impronta turistica (costiero/lacuale/montano) restano SEMPRE sul
    # calcolo AirROI di Sessione 68 (validato su Napoli, mercato reale di
    # breve termine con cui l'OMI aggregato per zona non tiene il passo).
    #
    # Controllo di coerenza minima sulla superficie: una villa/casa con più
    # camere ma pochi m2 dichiarati (es. 4 camere su 50 m2) produce un canone
    # OMI sballato quanto l'AirROI di partenza — in quel caso si ignora il
    # dato dichiarato e si usa la superficie tipica per tipologia già
    # prevista in omi_canoni.py, più rappresentativa.
    _omi_risultato = None
    if _fonte_correttivo == "generico":
        _codice_istat_omi = _record_comune.get("codice_istat") if _record_comune else None
        try:
            _superficie_omi = float(data.get("superficie") or 0) or None
        except (TypeError, ValueError):
            _superficie_omi = None
        try:
            _camere_omi = float(data.get("camere") or 1) or 1
        except (TypeError, ValueError):
            _camere_omi = 1
        if _superficie_omi and _superficie_omi < _camere_omi * 20:
            print(f"[AFFITTO-OMI] superficie dichiarata {_superficie_omi}m2 non plausibile per "
                  f"{_camere_omi} camere: ignorata, uso superficie tipica per tipologia")
            _superficie_omi = None
        _omi_risultato = omi_canoni.stima_canone_omi(
            _codice_istat_omi, _superficie_omi, data.get("tipologia")
        )
        print(f"[AFFITTO-OMI] comune={data.get('comune')!r} codice_istat={_codice_istat_omi!r} "
              f"esito={'trovato' if _omi_risultato else 'non coperto, fallback AirROI'}")

    if _omi_risultato:
        (data["affitto_ricavo"], data["affitto_costi"], data["affitto_profitto"], _) = _omi_risultato
        data["sconto_affitto_tradizionale_pct"] = None
        data["fonte_affitto_tradizionale"] = "omi_reale"
    else:
        (data["affitto_ricavo"], data["affitto_costi"], data["affitto_profitto"],
         data["sconto_affitto_tradizionale_pct"]) = stagionalita_turistica.stima_affitto_tradizionale(
            data.get("prezzo_notte_stimato", 0), _fonte_correttivo
        )
        data["fonte_affitto_tradizionale"] = "stima_airroi"

    # Sessione 78 (audit 24/8): la correzione POI (swap colonne invertite,
    # impatto deterministico, casing nome) deve avvenire PRIMA della
    # descrizione narrativa, non dopo — genera_descrizione_standard legge
    # data["poi"] per le frasi su trasporto/servizi/elemento caratteristico,
    # e prima girava sul dato grezzo non corretto (es. "ciro amodio" minuscolo
    # finiva in descrizione anche quando la tabella POI mostrava già la
    # versione sistemata).
    if correggere_poi and "poi" in data:
        data["poi"] = _correggi_poi_invertiti(data["poi"])

    if generare_descrizione:
        data["descrizione"] = genera_descrizione_standard(data)

    if "occupazione" in data:
        data["occupazione"] = [list(row) for row in data["occupazione"]]
    if "competitor" in data:
        data["competitor"] = [list(row) for row in data["competitor"]]

    # Fallback SOLO per il caso "_p" mancante (niente prezzo/notte, il ramo
    # sopra non gira e il mutuo non è mai stato sommato): qui sotto è l'unico
    # punto che lo aggiunge. Quando il ramo sopra è girato regolarmente
    # (_mutuo_gia_incluso_nel_totale), il mutuo annuo (rata mensile x 12) è
    # già nel totale — non si ricalcola una seconda volta.
    if (not _mutuo_gia_incluso_nel_totale) and data.get("mutuo_attivo") and data.get("rata_mutuo_mensile", 0):
        rata_annua = int(data["rata_mutuo_mensile"]) * 12
        costi_base = (
            data.get("costi_commissioni", 0) +
            data.get("costi_pulizie", 0) +
            data.get("costi_biancheria", 0) +
            data.get("costi_utenze", 0) +
            data.get("costi_manutenzione", 0)
        )
        data["totale_costi"] = costi_base + rata_annua
        data["profitto_netto"] = data.get("totale_ricavi", 0) - data["totale_costi"]
        data["margine_percent"] = round(data["profitto_netto"] / data.get("totale_ricavi", 1) * 100)

    # Etichette leggibili della scheda immobile: ultimo passo, dopo che
    # camere/posti letto deterministici sono già stati corretti sopra.
    _prepara_etichette_scheda(data)

    # Comune e regione della sezione normativa (solo Strategico): li scrive
    # l'AI, ma il CSV dei comuni li ha già certi. Senza questo fallback, se
    # l'AI li omette la pagina esce con "Normativa affitti brevi —  / " e
    # "Regione · Comune di ·" — buchi visibili su un dato che conosciamo.
    if not data.get("comune_normativa"):
        data["comune_normativa"] = data.get("comune", "")
    if not data.get("regione_normativa") and _record_comune:
        data["regione_normativa"] = _record_comune.get("regione", "")

    return data


@app.route("/generate-pdf-direct", methods=["POST"])
@require_internal_secret
def generate_pdf_direct():
    raw = ""
    try:
        raw = request.get_data(as_text=True)
        data = _elabora_dati_report_base(raw, request.args.get("lat"), request.args.get("long"))

        pdf_bytes = build_pdf_bytes(data)
        comune = data.get('comune', 'report').replace(' ', '_')

        from flask import Response
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename=ReportUp_Base_{comune}.pdf',
                'Content-Length': str(len(pdf_bytes))
            }
        )

    except Exception as e:
        return jsonify({"error": str(e), "raw_preview": raw[:500]}), 500


# Campi economici finali (post-normalizzazione + AirROI) da restituire a Make
# per popolare le pillole del modulo Gmail (Report Base). Devono combaciare
# esattamente con RU_Output_Economico_v2 mappato nel modulo JSON(25) su Make.
_CAMPI_ECONOMICI_EMAIL = [
    "prezzo_notte_stimato", "occupazione_percent", "notti_anno", "ricavo_lordo",
    "bonus_dirette", "bonus_dirette_pct", "totale_ricavi",
    "costi_commissioni", "costi_commissioni_pct", "costi_pulizie", "costi_pulizie_unit",
    "costi_biancheria", "costi_utenze", "costi_manutenzione",
    "totale_costi", "profitto_netto", "margine_percent",
    "kpi_prezzo", "kpi_prezzo_range", "kpi_occupazione", "kpi_occ_range", "kpi_potenziale",
]


@app.route("/extract-report-fields", methods=["POST"])
@require_internal_secret
def extract_report_fields():
    """Riceve {"testo": "<risposta grezza dell'AI, HTTP2>"} da Make (modulo HTTP24)
    ed estrae i campi economici finali (post-normalizzazione + AirROI) in un
    JSON pulito, così il modulo JSON(25) su Make può mapparli come pillole
    nell'email del Report Base. Non genera nessun PDF."""
    raw = ""
    try:
        body = request.get_json(force=True, silent=True) or {}
        raw = body.get("testo", "")
        if not raw:
            return jsonify({"error": "Campo 'testo' mancante o vuoto nel body"}), 400

        data = _elabora_dati_report_base(raw)
        risultato = {campo: data.get(campo) for campo in _CAMPI_ECONOMICI_EMAIL}
        return jsonify(risultato)

    except Exception as e:
        return jsonify({"error": str(e), "raw_preview": raw[:500] if raw else ""}), 500


@app.route("/extract-strategico-fields", methods=["POST"])
@require_internal_secret
def extract_strategico_fields():
    """Come /extract-report-fields ma per lo Strategico: usa la pipeline
    deterministica con gli stessi parametri di /generate-strategico
    (generare_descrizione=False, correggere_poi=False), non quella del
    Base — altrimenti le pillole economiche nell'email (prezzo/occupazione/
    profitto) userebbero un motore diverso da quello che genera i numeri
    reali nel PDF allegato alla stessa email, stesso bug di disallineamento
    già risolto una volta tra Base e Strategico (riapertura cantiere,
    27/8). Non genera nessun PDF."""
    raw = ""
    try:
        import json as _json
        import re as _re
        body = request.get_json(force=True, silent=True) or {}
        raw = body.get("testo", "")
        if not raw:
            return jsonify({"error": "Campo 'testo' mancante o vuoto nel body"}), 400

        cleaned = raw.strip()
        m = _re.search(r'```(?:json)?\s*(\{.*\})\s*```', cleaned, _re.DOTALL)
        if m:
            cleaned = m.group(1).strip()
        else:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and end > start:
                cleaned = cleaned[start:end+1]

        data = _json.loads(cleaned)
        data = normalize_data(data)
        data = _arricchisci_report_deterministico(
            data,
            lat=request.args.get("lat"), long=request.args.get("long"),
            generare_descrizione=False, correggere_poi=False,
        )
        risultato = {campo: data.get(campo) for campo in _CAMPI_ECONOMICI_EMAIL}
        return jsonify(risultato)

    except Exception as e:
        return jsonify({"error": str(e), "raw_preview": raw[:500] if raw else ""}), 500


@app.route("/debug-airroi-raw", methods=["GET"])
@require_internal_secret
def debug_airroi_raw():
    """Diagnostico, non usato dal flusso di produzione (B9 - 'Punto 0'):
    risposta AirROI GREZZA e NON troncata, senza passare da
    _airroi_lookup_e_stima (che tiene solo adr/occupancy/distribuzione
    mensile/comparable_listings/percentili revenue e scarta il resto). I log
    di produzione troncano il body a 300 caratteri (vedi r2.text[:300] nella
    lookup normale) — mai bastato per vedere se l'API offre anche percentili
    prezzo/ADR, split host privati/gestionali, trend TTM/L90D prima di
    costruire la pagina B9 del Report Strategico."""
    lat = request.args.get("lat")
    lng = request.args.get("lng") or request.args.get("long")
    if not AIRROI_API_KEY:
        return jsonify({"error": "AIRROI_API_KEY non configurata lato server"}), 500
    if not lat or not lng:
        return jsonify({"error": "Parametri 'lat' e 'lng' obbligatori"}), 400
    try:
        lat_f, lng_f = float(lat), float(lng)
    except (TypeError, ValueError):
        return jsonify({"error": "lat/lng non convertibili in float"}), 400

    bedrooms = _numero_da_stringa(request.args.get("bedrooms"), default=1)
    guests = _numero_da_stringa(request.args.get("guests"), default=2)
    baths = _numero_da_stringa(request.args.get("baths"), default=1)
    headers = {"X-API-KEY": AIRROI_API_KEY}

    r1 = requests.get(f"{AIRROI_BASE}/markets/lookup",
                       params={"lat": lat_f, "lng": lng_f}, headers=headers, timeout=8)
    r2 = requests.get(
        f"{AIRROI_BASE}/calculator/estimate",
        params={"lat": lat_f, "lng": lng_f, "bedrooms": bedrooms, "baths": baths,
                 "guests": guests, "currency": "native"},
        headers=headers, timeout=10,
    )
    return jsonify({
        "markets_lookup": {"status": r1.status_code,
                            "body": r1.json() if r1.status_code == 200 else r1.text},
        "calculator_estimate": {"status": r2.status_code,
                                 "body": r2.json() if r2.status_code == 200 else r2.text},
    })


@app.route("/ai-generate", methods=["POST"])
@require_internal_secret
def ai_generate():
    """Mirror di netlify/functions/ai-proxy.js, stesso formato richiesta/
    risposta (system/user/model/max_tokens -> risposta grezza Messages API),
    così lo scenario Make deve solo ripuntare l'URL del modulo, non
    riscrivere il mapping dei campi."""
    if not ANTHROPIC_API_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY non configurata lato server"}), 500
    body = request.get_json(force=True, silent=True) or {}
    system_prompt = body.get("system", "")
    user_prompt = body.get("user", "")
    model = body.get("model") or "claude-haiku-4-5"
    max_tokens = int(body.get("max_tokens") or 3000)

    try:
        resp = requests.post(
            ANTHROPIC_URL,
            headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            },
            timeout=90,
        )
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 502

    try:
        return jsonify(resp.json()), resp.status_code
    except ValueError:
        return jsonify({"error": "risposta Anthropic non JSON", "status": resp.status_code,
                         "body": resp.text[:2000]}), 502


# ── ROUTE STRATEGICO ──────────────────────────────────────────────────────────
from strategico import build_strategico_pdf_bytes


def _ricalcola_scenari_strategico(data):
    """Ricalcola i tre scenari (pessimistico/realistico/ottimistico) sui
    valori deterministici finali di _arricchisci_report_deterministico
    (prezzo/occupazione/costi/profitto reali), non più su quelli inventati
    dall'AI. Rapporti presi da PROMPT_AI_REPORT_STRATEGICO.md: pessimistico
    occupazione -35%/prezzo -20%, ottimistico occupazione +20% (cap 90%)/
    prezzo +18%, costi proporzionali ai ricavi in ogni scenario. Se manca un
    dato base (prezzo/occupazione/ricavi a zero) lascia gli scenari scritti
    dall'AI: caso solo teorico, il ramo prezzo mancante della pipeline
    condivisa è un fallback di emergenza, non l'esito atteso."""
    _occ_r = data.get("occupazione_percent") or 0
    _prezzo_r = data.get("prezzo_notte_stimato") or 0
    _ricavo_lordo_r = data.get("ricavo_lordo") or 0
    _totale_ricavi_r = data.get("totale_ricavi") or 0
    _totale_costi_r = data.get("totale_costi") or 0
    _notti_r = data.get("notti_anno") or 0
    if not (_occ_r and _prezzo_r and _totale_ricavi_r):
        return

    _costi_ratio = (_totale_costi_r / _totale_ricavi_r) if _totale_ricavi_r else 0
    _bonus_ratio = ((_totale_ricavi_r - _ricavo_lordo_r) / _ricavo_lordo_r) if _ricavo_lordo_r else 0

    def _scenario(occ_mult, prezzo_mult):
        occ = min(90, round(_occ_r * occ_mult))
        prezzo = round(_prezzo_r * prezzo_mult)
        notti = round(365 * occ / 100)
        ricavo_lordo = round(prezzo * notti)
        ricavi_totali = round(ricavo_lordo * (1 + _bonus_ratio))
        costi = round(ricavi_totali * _costi_ratio)
        return {
            "occupazione": occ, "notti": notti, "prezzo_medio": prezzo,
            "ricavi_lordi": ricavi_totali, "costi_totali": costi,
            "profitto_netto": ricavi_totali - costi,
        }

    data["scenario_pess"] = {**(data.get("scenario_pess") or {}), "label": "PESSIMISTICO", **_scenario(0.65, 0.80)}
    data["scenario_real"] = {**(data.get("scenario_real") or {}), "label": "REALISTICO",
        "occupazione": _occ_r, "notti": _notti_r, "prezzo_medio": _prezzo_r,
        "ricavi_lordi": _totale_ricavi_r, "costi_totali": _totale_costi_r,
        "profitto_netto": data.get("profitto_netto") or 0}
    data["scenario_ott"] = {**(data.get("scenario_ott") or {}), "label": "OTTIMISTICO", **_scenario(1.20, 1.18)}


# Festività e ponti italiani per mese: sono fatti di calendario, non materia
# da far scrivere all'AI. Lasciati a lei uscivano sistematicamente sfasati —
# "Ferragosto" a luglio, "ponte del 1 novembre" a settembre, "Ognissanti" a
# ottobre con novembre vuoto, "Immaccolata" con due c.
_EVENTI_MESE = {
    "Gen": "Epifania e saldi invernali",
    "Feb": "Carnevale (date variabili)",
    "Mar": "Weekend cittadini e ponti scolastici",
    "Apr": "Pasqua (date variabili) e ponte del 25 aprile",
    "Mag": "Ponte del 1° maggio, clima favorevole",
    "Giu": "Ponte del 2 giugno, inizio stagione estiva",
    "Lug": "Alta stagione estiva, turismo internazionale",
    "Ago": "Ferragosto (15 agosto), picco annuale",
    "Set": "Coda estiva e turismo culturale",
    "Ott": "City break, fiere e clima mite",
    "Nov": "Ponte di Ognissanti (1° novembre)",
    "Dic": "Ponte dell'Immacolata (8 dicembre), Natale e Capodanno",
}


_MESI_ESTESI = {
    "Gen": ("Gennaio", "January"), "Feb": ("Febbraio", "February"),
    "Mar": ("Marzo", "March"),     "Apr": ("Aprile", "April"),
    "Mag": ("Maggio", "May"),      "Giu": ("Giugno", "June"),
    "Lug": ("Luglio", "July"),     "Ago": ("Agosto", "August"),
    "Set": ("Settembre", "September"), "Ott": ("Ottobre", "October"),
    "Nov": ("Novembre", "November"),   "Dic": ("Dicembre", "December"),
}


def _pricing_mensile_deterministico(data):
    """Ricostruisce il piano pricing mensile dai 12 mesi già calcolati in
    `occupazione` (prezzo e occupazione reali AirROI/curva di zona), invece di
    lasciarlo inventare all'AI.

    Prima erano due insiemi di numeri indipendenti: la pagina dell'analisi
    economica dichiarava un ricavo lordo annuo e la pagina del piano pricing ne
    totalizzava un altro, più basso di circa un terzo, per giunta etichettato
    "Scenario ottimistico". Due risposte diverse alla stessa domanda nello
    stesso report. Ricostruendolo qui il totale torna per costruzione.

    Ricavo mese = prezzo/notte x occupazione% x giorni del mese."""
    occ = data.get("occupazione") or []
    if len(occ) != 12:
        # Senza i 12 mesi deterministici si tiene quello che c'è, limitandosi
        # a correggere la colonna eventi.
        righe = data.get("pricing_mensile")
        if righe:
            nuove = []
            for riga in righe:
                riga = list(riga) + [""] * max(0, 6 - len(riga))
                _sigla = str(riga[0]).split("/")[0].strip()[:3].capitalize()
                riga[5] = _EVENTI_MESE.get(_sigla, "")
                nuove.append(riga)
            data["pricing_mensile"] = nuove
        return data

    grezzi = []
    for mese, occ_pct, prezzo, _stage in occ:
        sigla = str(mese).strip()[:3].capitalize()
        it, en = _MESI_ESTESI.get(sigla, (str(mese), str(mese)))
        giorni = _GIORNI_MESE.get(sigla, 30)
        grezzi.append([it, en, prezzo, occ_pct, prezzo * (occ_pct / 100) * giorni, sigla])

    # La somma dei 12 mesi pesati non coincide con prezzo medio x notti/anno
    # usato dall'analisi economica (medie diverse dello stesso mercato): senza
    # ancoraggio le due pagine chiuderebbero comunque su cifre diverse. Si
    # tiene la FORMA mensile reale e se ne riporta il LIVELLO sul ricavo lordo
    # del report, così la colonna somma esattamente il totale dichiarato.
    _lordo = data.get("ricavo_lordo") or 0
    _somma = sum(r[4] for r in grezzi)
    _fattore = (_lordo / _somma) if (_lordo and _somma) else 1.0

    righe = []
    for r in grezzi:
        it, en, prezzo, occ_pct, ricavo_raw, sigla = r
        righe.append([it, en, prezzo, occ_pct, round(ricavo_raw * _fattore), _EVENTI_MESE.get(sigla, "")])

    # Lo scarto di arrotondamento finisce sull'ultimo mese, così il totale a
    # video è identico al ricavo lordo al centesimo.
    if _lordo:
        _delta = _lordo - sum(r[4] for r in righe)
        righe[-1][4] += _delta

    data["pricing_mensile"] = righe
    return data


def _ricalcola_kpi_strategico(data):
    """ADR e RevPAR ricalcolati sui valori deterministici finali. Prima
    arrivavano dall'AI e restavano scollegati dalla formula stampata di fianco
    nella tabella economica: la riga diceva "Ricavo lordo / Notti occupate =
    € 31.828 / 292" (= 109) e la colonna Valore mostrava € 72, il numero
    inventato. Stessa incoerenza si propagava nel piè di pagina del piano
    pricing e nella pagina dati di mercato."""
    _ricavo_lordo = data.get("ricavo_lordo") or 0
    _notti = data.get("notti_anno") or 0
    _occ = data.get("occupazione_percent") or 0
    if _ricavo_lordo and _notti:
        data["adr"] = round(_ricavo_lordo / _notti)
        data["revpar"] = round(data["adr"] * _occ / 100)


# Parole chiave per ricondurre i punti di interesse liberi dello Strategico
# agli stessi 4 slot fissi del Base (il 5° è l'aeroporto, deterministico).
_POI_SLOT_KEYWORDS = (
    (0, ("metro", "metropolitan", "stazione", "treno", "ferroviar", "bus", "autobus",
         "tram", "funicolare", "porto", "traghett", "aliscaf", "capolinea")),
    (1, ("centro storico", "centro citt", "piazza", "comune", "municipio", "corso")),
    (2, ("museo", "castello", "palazzo", "duomo", "chiesa", "basilica", "cattedrale",
         "monument", "spiaggia", "lungomare", "parco", "lago", "teatro", "scavi",
         "attrazione", "borgo", "santuario", "terme", "impianti")),
    (3, ("supermercat", "market", "conad", "coop", "farmacia", "negozi", "alimentari",
         "servizi", "ospedale", "banca", "bar", "ristorant", "panificio", "edicola")),
)


def _poi_strategico_in_formato_base(data):
    """Converte i POI dello Strategico (N punti liberi a 4 campi
    [nome, a_piedi, mezzo_pubblico, impatto], scritti dall'AI) nello schema a
    5 slot fissi del Base ([distanza, nome, impatto] per slot). Serve a far
    girare sullo Strategico la stessa tabella "Posizione e punti di interesse"
    del Base — stesse colonne, stesse etichette di categoria, stessa riga
    aeroporto deterministica — invece delle colonne diverse che aveva prima.
    Ogni punto finisce nello slot suggerito dalle sue parole chiave; quelli non
    riconosciuti riempiono il primo slot ancora libero."""
    righe = [list(r) for r in (data.get("poi") or []) if r]
    if not righe:
        return data
    # Già in formato Base (3 campi): niente da convertire.
    if all(len(r) <= 3 for r in righe):
        return data

    slot = [None] * 4
    avanzi = []
    for r in righe:
        nome, a_piedi, descrittore, impatto = (list(r) + ["—"] * 4)[:4]
        testo = f"{nome} {descrittore}".lower()
        destinazione = None
        for idx, parole in _POI_SLOT_KEYWORDS:
            if slot[idx] is None and any(pa in testo for pa in parole):
                destinazione = idx
                break
        riga_base = [str(a_piedi), str(nome), str(impatto)]
        if destinazione is None:
            avanzi.append(riga_base)
        else:
            slot[destinazione] = riga_base
    for riga_base in avanzi:
        for idx in range(4):
            if slot[idx] is None:
                slot[idx] = riga_base
                break

    righe_base = [s if s else ["—", "—", "—"] for s in slot]
    # Stesse due regole del Base: 5° slot sempre l'aeroporto più vicino
    # (deterministico, non AI) e slot "Comune di riferimento" vuoto quando
    # l'immobile è già in un capoluogo o in una grande città.
    righe_base.append(aeroporto_row(data.get("lat"), data.get("long")))
    if str(data.get("categoria") or "").strip().lower() in ("capoluogo", "grande_citta"):
        righe_base[1] = ["—", "—", "—"]

    data["poi"] = righe_base
    return data


@app.route("/generate-strategico", methods=["POST"])
@require_internal_secret
def generate_strategico():
    import json as _json
    import re as _re
    raw = ""
    try:
        raw = request.get_data(as_text=True)
        cleaned = raw.strip()
        m = _re.search(r'```(?:json)?\s*(\{.*\})\s*```', cleaned, _re.DOTALL)
        if m:
            cleaned = m.group(1).strip()
        else:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and end > start:
                cleaned = cleaned[start:end+1]

        data = _json.loads(cleaned)
        data = normalize_data(data)

        # Riapertura cantiere Strategico: motore deterministico condiviso col
        # Base (_arricchisci_report_deterministico) — prezzo/occupazione reali
        # AirROI, stagionalità di zona, competitor deterministico, dotazioni_
        # assenti per sottrazione, confronto affitto misto OMI/AirROI. Prima
        # lo Strategico da €149 lasciava inventare questi numeri all'AI mentre
        # il Base da €39 li calcolava in modo deterministico — stesso identico
        # immobile poteva avere due prezzi/notte diversi tra i due prodotti.
        # generare_descrizione=False: lo Strategico tiene la sua descrizione
        # AI dedicata (più lunga, vedi PROMPT_AI_REPORT_STRATEGICO.md), non
        # quella breve del Base. correggere_poi=False: lo schema POI dello
        # Strategico (N punti liberi, 4 campi ciascuno) non è quello a 4 slot
        # fissi del Base — vedi nota in _arricchisci_report_deterministico.
        data = _arricchisci_report_deterministico(
            data,
            lat=request.args.get("lat"),
            long=request.args.get("long"),
            generare_descrizione=False,
            correggere_poi=False,
        )

        # Campi esclusivi Strategico, non toccati dalla pipeline condivisa.
        if "pricing_mensile" in data:
            data["pricing_mensile"] = [list(row) for row in data["pricing_mensile"]]
        if "normativa_extra" in data:
            data["normativa_extra"] = [list(row) for row in data["normativa_extra"]]
        if "piano_90" in data:
            for item in data["piano_90"]:
                if isinstance(item, dict) and "azioni" in item:
                    item["azioni"] = list(item["azioni"])

        # Media trimestre (3 mesi più affidabili, ToDo Sessione 65) — solo
        # Strategico, si affianca alla curva a 12 mesi, non la sostituisce.
        _calcola_trimestre_affidabile(data)

        # Moltiplicatori di valore (dotazioni) — solo Strategico, pag. 6.
        _calcola_moltiplicatori_dotazioni(data)

        # 3 scenari per durata soggiorno (B7) — solo Strategico, pag. 9.
        _calcola_scenari_durata_soggiorno(data)

        # Mappa obiettivo→pagina per page_obiettivi (deterministica, non AI).
        data["obiettivi_pagine"] = _OBIETTIVI_PAGINE_STRATEGICO

        # I tre scenari (pess/real/ott) vanno ricalcolati DOPO il motore
        # deterministico sopra: altrimenti resterebbero ancorati al prezzo/
        # occupazione/costi inventati dall'AI invece che ai valori reali
        # appena corretti, con lo scenario "realistico" scollegato dal resto
        # del PDF (stessa incoerenza che il Base ha già risolto per i KPI).
        _ricalcola_scenari_strategico(data)

        # ADR/RevPAR deterministici (prima venivano dall'AI e non tornavano
        # con la formula stampata di fianco).
        _ricalcola_kpi_strategico(data)

        # Colonna eventi del piano pricing dal calendario reale, non dall'AI.
        _pricing_mensile_deterministico(data)

        # POI nello schema a slot fissi del Base, così la pagina "Posizione e
        # punti di interesse" è la stessa tabella sui due prodotti.
        _poi_strategico_in_formato_base(data)

        # Dopo il ricalcolo scenari: usa il profitto netto deterministico
        # finale, non quello di partenza dell'AI.
        _calcola_valore_asset(data)

        # Mappa satellitare pag. 1 — stesse lat/long già usate per AirROI
        # sopra, nessuna chiamata geocode aggiuntiva. None se manca la
        # chiave o le coordinate: strategico.py ricade sul placeholder.
        data["_mappa_png"] = _fetch_static_map_png(data.get("lat"), data.get("long"))

        pdf_bytes = build_strategico_pdf_bytes(data)
        comune = data.get('comune', 'report').replace(' ', '_')

        from flask import Response
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename=ReportUp_Strategico_{comune}.pdf',
                'Content-Length': str(len(pdf_bytes))
            }
        )

    except Exception as e:
        return jsonify({"error": str(e), "raw_preview": raw[:500]}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

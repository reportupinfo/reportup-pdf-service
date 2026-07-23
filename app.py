"""
ReportUp PDF Service
Riceve JSON con i dati del report, genera il PDF branded, restituisce base64.
Deploy su Render.com (piano free).
"""

import os
import io
import re
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
    n = int(round(n_camere))
    return {0: "Monolocali", 1: "Bilocali"}.get(n, f"{n + 1} locali" if n >= 2 else "Monolocali")


def _media_nazionale_da_percentili(percentili_revenue, occupazione_frazione, valuta="€"):
    """
    Costruisce la riga 'Media nazionale' da dati REALI AirROI (percentili di
    ricavo annuo) quando non ci sono comparable_listings sufficienti per la
    tabella dettagliata. Converte ricavo -> prezzo/notte implicito dividendo
    per notti/anno stimate alla stessa occupazione. Meno preciso di annunci
    comparabili reali, ma è dato di mercato vero, non invenzione. Sessione 64.
    """
    if not percentili_revenue or not occupazione_frazione:
        return None
    notti_anno = occupazione_frazione * 365
    if notti_anno < 1:
        return None
    p25 = percentili_revenue.get("p25", 0) / notti_anno
    p75 = percentili_revenue.get("p75", 0) / notti_anno
    p50 = percentili_revenue.get("p50", 0) / notti_anno if percentili_revenue.get("p50") else (p25 + p75) / 2
    if p25 <= 0 or p75 <= 0:
        return None
    occ_pct = round(occupazione_frazione * 100)
    return ["Media di mercato AirROI (percentili)", "\u2014",
            f"{valuta} {round(p25)}-{round(p75)}", f"{occ_pct}%", "\u2014"]


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


def _costruisci_competitor_da_airroi(comparable_listings, valuta="€"):
    if not comparable_listings:
        return None
    gruppi = {}
    tutti_prezzi, tutte_occ, tutti_rating = [], [], []
    for ann in comparable_listings:
        if not isinstance(ann, dict):
            continue
        prezzo = _numero_da(ann, "average_daily_rate", "adr", "price", "daily_rate")
        occ = _numero_da(ann, "occupancy", "occupancy_rate")
        rating = _numero_da(ann, "rating", "review_rating", "star_rating", "overall_rating")
        camere = _numero_da(ann, "bedrooms", "beds", "num_bedrooms")
        if prezzo is None:
            continue
        if occ is not None and occ <= 1:
            occ = occ * 100
        tipologia = _tipologia_da_camere(camere)
        g = gruppi.setdefault(tipologia, {"prezzi": [], "occ": [], "rating": []})
        g["prezzi"].append(prezzo)
        tutti_prezzi.append(prezzo)
        if occ is not None:
            g["occ"].append(occ)
            tutte_occ.append(occ)
        if rating is not None:
            g["rating"].append(rating)
            tutti_rating.append(rating)

    if len(tutti_prezzi) < 3:
        return None

    righe = []
    for tipologia, g in sorted(gruppi.items(), key=lambda kv: -len(kv[1]["prezzi"])):
        n = len(g["prezzi"])
        prezzo_medio = round(sum(g["prezzi"]) / n)
        occ_media = round(sum(g["occ"]) / len(g["occ"])) if g["occ"] else "\u2014"
        rating_medio = round(sum(g["rating"]) / len(g["rating"]), 1) if g["rating"] else "\u2014"
        righe.append([tipologia, str(n), f"{valuta} {prezzo_medio}",
                      f"{occ_media}%" if occ_media != "\u2014" else "\u2014", str(rating_medio)])
    righe = righe[:4]

    media_prezzo = round(sum(tutti_prezzi) / len(tutti_prezzi))
    media_occ = round(sum(tutte_occ) / len(tutte_occ)) if tutte_occ else "\u2014"
    media_rating = round(sum(tutti_rating) / len(tutti_rating), 1) if tutti_rating else "\u2014"
    media_riga = ["Media annunci comparabili AirROI", "\u2014", f"{valuta} {media_prezzo}",
                  f"{media_occ}%" if media_occ != "\u2014" else "\u2014", str(media_rating)]

    return righe, media_riga


def _numero_da_stringa(valore, default=1):
    try:
        m = re.search(r"\d+", str(valore))
        return int(m.group()) if m else default
    except Exception:
        return default


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

        bedrooms = _numero_da_stringa(camere_raw, default=1)
        guests = _numero_da_stringa(posti_letto_raw, default=2)
        baths = _numero_da_stringa(bagni_raw, default=1)

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

        print(f"[AIRROI] OK — prezzo={round(float(adr))} occupazione={round(float(occ) * 100)}% distribuzione_mensile={'presente' if distribuzione_mensile else 'assente'} comparable_listings={len(comparable_listings) if comparable_listings else 0} percentili_revenue={'presente' if percentili_revenue else 'assente'}")
        return {
            "prezzo_notte_stimato": round(float(adr)),
            "occupazione_percent": round(float(occ) * 100),
            "distribuzione_mensile": distribuzione_mensile,
            "comparable_listings": comparable_listings,
            "percentili_revenue": percentili_revenue,
            "occupazione_frazione": float(occ),
        }
    except Exception as e:
        print(f"[AIRROI] eccezione: {e}")
        return None


def _mesi_affidabili(oggi=None):
    import datetime
    oggi = oggi or datetime.date.today()
    mese_partenza = (oggi.month - 1) if oggi.day <= 15 else oggi.month
    return [(mese_partenza + i) % 12 for i in range(3)]


def _applica_stagionalita_airroi(occ, distribuzione_mensile, adr_annuale, occ_annuale=None, tetto_massimo=85):
    if not occ or not distribuzione_mensile or len(occ) != 12:
        return occ
    media = sum(distribuzione_mensile) / 12
    if media <= 0:
        return occ
    nuova = []
    for i, row in enumerate(occ):
        peso = distribuzione_mensile[i] / media
        # Smorzamento simmetrico sul prezzo (Sessione 66) — anche quando il
        # dato mensile è reale (AirROI), un picco non deve raddoppiare il
        # prezzo medio: stesso meccanismo già applicato alla curva curata,
        # per coerenza indipendentemente dalla fonte del dato.
        peso_prezzo = stagionalita_turistica.smorza_peso_prezzo(peso)
        prezzo_mese = max(1, round(adr_annuale * peso_prezzo))
        nuova_row = [row[0], row[1], prezzo_mese] + list(row[3:])
        if occ_annuale is not None:
            nuova_row[1] = max(5, min(tetto_massimo, round(occ_annuale * peso)))
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
_CAMERE_PER_TIPOLOGIA = [
    ("stanza singola", 0), ("stanza doppia", 0), ("monolocale", 0),
    ("bilocale", 1),
    ("trilocale", 2),
    ("quadrilocale", 3), ("4 locali", 3), ("appartamento grande", 3),
    ("villa", 4), ("casa indipendente", 4),
]


def _camere_deterministiche(tipologia, camere_ai):
    """Ritorna il numero di camere corretto per la tipologia dichiarata,
    ignorando quanto scritto dall'AI se riconosciamo la tipologia. Se la
    tipologia non è tra quelle note (es. testo libero non standard),
    manteniamo il valore dell'AI invece di inventare un fallback arbitrario."""
    t = str(tipologia or "").strip().lower()
    for frammento, n in _CAMERE_PER_TIPOLOGIA:
        if frammento in t:
            return str(n)
    return camere_ai


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
    if dist_km <= 30:
        impatto = "Alto"
    elif dist_km <= 70:
        impatto = "Medio"
    else:
        impatto = "Basso"

    auto = territorio_gps.distanza_e_tempo_auto(lat, lon, best_lat, best_lon)
    if auto:
        km_auto, min_auto = auto
        distanza_str = f"{km_auto} km · {min_auto} min in auto"
    else:
        distanza_str = f"{dist_km} km (linea d'aria)"

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


def draw_footer(c, page_num):
    footer_h = 9 * mm
    c.setFillColor(BLUE_NIGHT)
    c.rect(0, 0, W, footer_h, fill=1, stroke=0)
    c.setFont("Helvetica", 6.5)
    c.setFillColor(HexColor("#A8BCC8"))
    c.drawString(14 * mm, 3.5 * mm,
                 "\u00a9 2025 ReportUp \u00b7 reportup.it  |  Documento orientativo - non costituisce consulenza professionale")
    c.drawRightString(W - 14 * mm, 3.5 * mm, f"Pag. {page_num}")


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
    fields_l = [("Tipologia", D.get("tipologia", "")), ("Superficie", D.get("superficie", "")),
                ("Piano", D.get("piano", "")), ("Stato", D.get("stato", "")), ("Camere", D.get("camere", ""))]
    fields_r = [("Comune", D.get("comune", "")), ("Zona", D.get("zona", "")),
                ("Epoca", D.get("epoca", "")), ("Bagni", D.get("bagni", "")), ("Posti letto", D.get("posti_letto", ""))]
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
    for pct in [40, 50, 60, 70, 80, 90]:
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
        nota = f' <font size="6" color="#7A8A96">(media di mercato per la tipologia{extra})</font>'
        return Paragraph(f"€ {valore_annuo:,}/anno{nota}".replace(",", "."), style_media_mercato)

    p = D.get("prezzo_notte_stimato", 0)
    occ_pct = D.get("occupazione_percent", 0)
    notti = D.get("notti_anno", 0)
    comm_pct = D.get("costi_commissioni_pct", 15)
    pulizia_unit = D.get("costi_pulizie_unit", 35)
    _tipologia_costi = D.get("tipologia", "immobile")
    _nota_costi_variabili = f"Media di mercato per tipologia: {_tipologia_costi}"
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
         f"€ {p}/notte x {occ_pct}% occ. x 365gg = € {p} x {notti} notti",
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
        ["Pulizie per cambio ospite",
         f"€ {pulizia_unit}/cambio x {notti} notti = € {D.get('costi_pulizie',0):,}".replace(",", "."),
         f"- {fmt_eur(D.get('costi_pulizie', 0))}"],
        ["Biancheria e consumabili",
         _cella_media_mercato(D.get('costi_biancheria', 0)),
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
    y = draw_wrapped_text(c, nota, 14 * mm, y - 2 * mm, W - 28 * mm, "Helvetica-Oblique", 6.5, 4 * mm, MUTED)
    y -= 4 * mm

    y = draw_section_header(c, 14 * mm, y, W - 28 * mm, "Confronto con affitto tradizionale")
    y -= 5 * mm
    _diff_ricavo = D.get('ricavo_lordo', 0) - D.get('affitto_ricavo', 0)
    _diff_profitto = D.get('profitto_netto', 0) - D.get('affitto_profitto', 0)

    def _fmt_diff(delta):
        segno = "+" if delta >= 0 else "-"
        numero = f"{abs(int(delta)):,}".replace(",", ".")
        return f"\u20ac {segno}{numero}"

    conf_data = [
        ["", "Affitto tradizionale", "B&B / Short rent", "Differenza"],
        ["Ricavo annuo lordo", fmt_eur(D.get("affitto_ricavo", 0)), fmt_eur(D.get("ricavo_lordo", 0)),
         _fmt_diff(_diff_ricavo)],
        ["Costi di gestione", fmt_eur(D.get("affitto_costi", 0)), fmt_eur(D.get("totale_costi", 0)), "--"],
        ["Profitto netto", fmt_eur(D.get("affitto_profitto", 0)), fmt_eur(D.get("profitto_netto", 0)),
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

    y = draw_section_header(c, 14 * mm, y, W - 28 * mm,
                            f"Analisi competitor - {D.get('competitor_zona', '')}")
    y -= 3 * mm
    draw_section_subtitle(c, 14 * mm, y, "Confronto diretto con gli annunci attivi nella zona")
    y -= 6 * mm
    comp_data = [["Tipologia annunci - " + D.get("competitor_zona", ""), "N.", "Prezzo med.", "Occup.", "Rating"]]
    for row in D.get("competitor", []):
        comp_data.append(list(row))
    mn = D.get("media_nazionale", ["Media nazionale B&B urbani", "\u2014", "€ 95", "64%", "4.5"])
    comp_data.append(list(mn))
    comp_data.append(["IL TUO IMMOBILE (stima)", "\u2014",
                      f"€ {D.get('kpi_prezzo', 0)}", f"{D.get('kpi_occupazione', 0)}%", "\u2014"])
    n_med = len(comp_data) - 2
    col_w_comp = [(W - 28 * mm) * 0.42, (W - 28 * mm) * 0.10, (W - 28 * mm) * 0.18,
                  (W - 28 * mm) * 0.15, (W - 28 * mm) * 0.15]
    tbl_comp = Table(comp_data, colWidths=col_w_comp)
    tbl_comp.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLUE_NIGHT), ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 1), (-1, -3), "Helvetica"), ("TEXTCOLOR", (0, 1), (-1, -3), BLUE_NIGHT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -3), [WHITE, CREAM]),
        ("GRID", (0, 0), (-1, -1), 0.25, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND", (0, n_med), (-1, n_med), HexColor("#F0F0F0")),
        ("TEXTCOLOR", (0, n_med), (-1, n_med), MUTED),
        ("FONTNAME", (0, n_med), (-1, n_med), "Helvetica-Oblique"),
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

    upsell_h = 30 * mm
    c.setFillColor(GOLD_LIGHT)
    c.roundRect(14 * mm, y - upsell_h, W - 28 * mm, upsell_h, 3 * mm, fill=1, stroke=0)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1)
    c.roundRect(14 * mm, y - upsell_h, W - 28 * mm, upsell_h, 3 * mm, fill=0, stroke=1)
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(BLUE_NIGHT)
    c.drawString(18 * mm, y - 7 * mm, "Vuoi il piano d\u2019azione completo?")
    upsell_text = ("Il Report Strategico (€ 149) include tutto il Base piu': pricing stagionale mese per mese, "
                   "3 scenari economici (pessimistico / realistico / ottimistico), piano d'azione 90 giorni, "
                   "cap rate e valore asset, normativa affitti brevi locale e l'analisi personale "
                   "dell'Arch. Salvatore Junior Sica.")
    uy = y - 13 * mm
    uy = draw_wrapped_text(c, upsell_text, 18 * mm, uy, W - 36 * mm, "Helvetica", 7.5, 5 * mm, BLUE_NIGHT)
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(GOLD)
    c.drawString(18 * mm, uy, "Scopri il Report Strategico su reportup.it  |  € 149 - pagamento unico")
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

    _fonte_affitto = D.get("fonte_affitto_tradizionale", "stima_ai")
    if _fonte_affitto == "omi_reale":
        _desc_affitto = ("Osservatorio del Mercato Immobiliare (OMI) - Agenzia delle Entrate, Semestre 2025/2. "
                          "Canone di locazione medio EUR/m2 della zona, applicato alla superficie dichiarata.")
    else:
        _desc_affitto = ("Stima di mercato — dato OMI non disponibile per questo comune nel semestre corrente. "
                          "Valore orientativo, non tratto dalla banca dati OMI.")

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

def normalize_data(data):
    if "tipologia" in data and "indirizzo" in data and "occupazione" in data:
        return data

    flat = {}

    report = data.get("report", {})
    immobile_nested = report.get("immobile", {})
    immobile_flat   = data.get("immobile", {})
    imm = immobile_nested if immobile_nested else immobile_flat

    ident = imm.get("identificazione", {})
    car   = imm.get("caratteristiche", {})

    flat["indirizzo"] = (ident.get("indirizzo") or imm.get("indirizzo") or data.get("indirizzo", ""))
    flat["comune"]    = (ident.get("comune") or imm.get("comune") or data.get("comune", ""))
    flat["zona"]      = (ident.get("zona") or imm.get("zona") or flat["comune"])

    flat["tipologia"] = (car.get("tipologia") or imm.get("tipologia") or data.get("tipologia", ""))
    sup = (car.get("superficie") or imm.get("superficie") or data.get("superficie", ""))
    flat["superficie"] = f"{sup} m\u00b2" if isinstance(sup, (int, float)) else str(sup)
    flat["piano"]     = (car.get("piano") or imm.get("piano") or data.get("piano", ""))
    flat["stato"]     = (car.get("stato") or imm.get("stato") or data.get("stato", ""))
    flat["epoca"]     = (car.get("epoca") or imm.get("epoca") or data.get("epoca", ""))

    camere = (car.get("numeroStanze") or imm.get("camere") or imm.get("numeroStanze") or data.get("camere", ""))
    flat["camere"] = (f"{camere} camera" if isinstance(camere, int) and camere == 1
                      else f"{camere} camere" if isinstance(camere, int) else str(camere))

    bagni = (car.get("numeroBagni") or imm.get("bagni") or imm.get("numeroBagni") or data.get("bagni", ""))
    flat["bagni"] = (f"{bagni} bagno" if isinstance(bagni, int) and bagni == 1
                     else f"{bagni} bagni" if isinstance(bagni, int) else str(bagni))

    posti = (car.get("postiLetto") or imm.get("posti_letto") or imm.get("postiLetto") or data.get("posti_letto", ""))
    flat["posti_letto"] = f"{posti} posti" if isinstance(posti, int) else str(posti)

    dot_raw = (imm.get("dotazioni") or data.get("dotazioni") or {})
    _nomi = {
        "wifi": "WiFi", "aria_condizionata": "Aria condizionata",
        "ariaCondizionata": "Aria condizionata", "cucina": "Cucina",
        "riscaldamento": "Riscaldamento", "televisione": "TV", "tv": "TV",
        "ascensore": "Ascensore", "balcone": "Balcone", "terrazza": "Terrazza",
        "giardino": "Giardino", "garage": "Garage", "cantina": "Cantina",
        "parcheggio": "Parcheggio"
    }
    if isinstance(dot_raw, dict):
        flat["dotazioni_presenti"] = (data.get("dotazioni_presenti")
                                       or [_nomi.get(k, k) for k, v in dot_raw.items() if v])
        flat["dotazioni_assenti"]  = (data.get("dotazioni_assenti")
                                       or [_nomi.get(k, k) for k, v in dot_raw.items() if not v])
    elif isinstance(dot_raw, list):
        flat["dotazioni_presenti"] = [_nomi.get(d, d) for d in dot_raw]
        flat["dotazioni_assenti"]  = []
    else:
        flat["dotazioni_presenti"] = data.get("dotazioni_presenti", [])
        flat["dotazioni_assenti"]  = data.get("dotazioni_assenti", [])

    for f in ["situazione_vuoto", "situazione_inquilini", "situazione_bnb", "situazione_mutuo"]:
        flat[f] = data.get(f, imm.get(f, False))

    flat["descrizione"] = (imm.get("descrizioneEstesa") or imm.get("descrizione") or data.get("descrizione", ""))

    for field in [
        "poi", "occupazione", "prezzo_notte_stimato", "occupazione_percent",
        "notti_anno", "ricavo_lordo", "bonus_dirette", "bonus_dirette_pct",
        "totale_ricavi", "costi_commissioni", "costi_commissioni_pct",
        "costi_pulizie", "costi_pulizie_unit", "costi_biancheria",
        "costi_utenze", "costi_manutenzione", "totale_costi",
        "profitto_netto", "margine_percent", "mutuo_attivo", "rata_mutuo_mensile",
        "affitto_ricavo", "affitto_costi", "affitto_profitto",
        "competitor", "competitor_zona", "media_nazionale",
        "kpi_prezzo", "kpi_prezzo_range", "kpi_occupazione",
        "kpi_occ_range", "kpi_potenziale", "data_generazione", "lat", "long",
        "categoria"
    ]:
        val = data.get(field, report.get(field, imm.get(field)))
        if val is not None:
            flat[field] = val

    return flat


def _join_lista_e(items):
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " e " + items[-1]


def _concorda_numero(valore, singolare, plurale):
    try:
        n = int(str(valore).strip())
    except (ValueError, TypeError):
        return f"{valore} {plurale}"
    return f"{n} {singolare}" if n == 1 else f"{n} {plurale}"


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
    ("villa", 85, 750, 1300, 900), ("casa indipendente", 85, 750, 1300, 900),
    ("appartamento", 65, 600, 1000, 650), ("4+", 65, 600, 1000, 650), ("grande", 65, 600, 1000, 650),
    ("trilocale", 55, 500, 850, 500),
    ("bilocale", 45, 400, 650, 350),
    ("doppia", 30, 280, 450, 220),
    ("singola", 25, 220, 350, 180), ("stanza", 25, 220, 350, 180),
]


def _costi_per_tipologia(tipologia):
    t = str(tipologia or "").strip().lower()
    for frammento, pulizie, biancheria, utenze, manutenzione in _COSTI_PER_TIPOLOGIA:
        if frammento in t:
            return pulizie, biancheria, utenze, manutenzione
    return 35, 300, 500, 300


def _calcola_costi_fissi_deterministici(data):
    pulizie, biancheria, utenze, manutenzione = _costi_per_tipologia(data.get("tipologia"))
    dotazioni = set(data.get("dotazioni_presenti") or [])
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

    return None


def _correggi_poi_invertiti(poi):
    # Ordine fisso garantito dal prompt: 0=trasporto pubblico, 1=comune di
    # riferimento, 2=elemento caratteristico, 3=servizi essenziali.
    _modalita_per_riga = ["piedi", "auto", "auto", "piedi"]
    corrette = []
    for idx, row in enumerate(poi):
        distanza, nome, impatto = (list(row) + ["\u2014", "\u2014", "\u2014"])[:3]
        if _sembra_etichetta_categoria(nome) and not _sembra_distanza(distanza):
            distanza, nome = nome, distanza
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
        extra_territorio = f", {_chiusura_territorio[sottocateg]}," if sottocateg in _chiusura_territorio else ""
        desc += (
            f"Ideale per {target} che vogliono vivere la città{extra_territorio} da dentro, con tutti i comfort di casa. "
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
def categoria_comune():
    comune_q = request.args.get("comune", "")
    provincia_q = request.args.get("provincia")

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
        }
    except Exception as e:
        print(f"[QUICK] geocode eccezione: {e}")
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
def verify_address():
    """Chiamato dal form Base (Sessione 54) prima di mandare il cliente su
    Stripe: verifica che l'indirizzo sia realmente geolocalizzabile, per
    evitare pagamenti incassati senza che il report riesca mai a generarsi
    più avanti nella pipeline Make (il geocode fallirebbe silenziosamente)."""
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
        return _risposta({"valido": False})

    geo = _geocode_indirizzo(indirizzo)
    return _risposta({"valido": bool(geo)})


@app.route("/quick-estimate", methods=["POST", "OPTIONS"])
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

    geo = _geocode_indirizzo(indirizzo)
    if not geo:
        return _risposta({
            "error": "indirizzo_non_trovato",
            "message": "Non riusciamo a localizzare questo indirizzo. Controlla via, città e CAP."
        }, 422)

    lat, lon = geo["lat"], geo["lon"]
    record_comune = comuni_lookup.trova_comune(geo.get("comune") or "", geo.get("provincia"))
    categoria = record_comune["categoria"] if record_comune else "comune_minore"
    sottocategoria = territorio_gps.classifica_sottocategoria(lat, lon)

    airroi = _airroi_lookup_e_stima(
        lat, lon,
        camere_raw=body.get("camere"),
        posti_letto_raw=body.get("posti_letto"),
        bagni_raw=body.get("bagni"),
    )
    print(f"[QUICK] indirizzo={indirizzo!r} lat={lat!r} lon={lon!r} categoria={categoria!r} sottocategoria={sottocategoria!r} "
          f"camere_raw={body.get('camere')!r} posti_letto_raw={body.get('posti_letto')!r} bagni_raw={body.get('bagni')!r} "
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
        mult_capacita = _moltiplicatore_capacita(body.get("posti_letto"))
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
    })


def _elabora_dati_report_base(raw, lat=None, long=None):
    """Parsa il testo grezzo restituito dall'AI (HTTP2) e applica tutte le
    correzioni deterministiche + l'integrazione AirROI, producendo il dict
    'data' finale usato sia per generare il PDF sia per popolare i campi
    economici nella mail (modulo HTTP24/JSON25 su Make)."""
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

    # Dotazioni assenti: pura sottrazione insiemistica (lista standard meno
    # quelle dichiarate presenti dal cliente) — zero margine di invenzione,
    # l'AI non decide più questo campo. Sessione 64.
    _dot_presenti_norm = [_norm_dotazione(d) for d in (data.get("dotazioni_presenti") or [])]
    data["dotazioni_assenti"] = [d for d in DOTAZIONI_AMMESSE if d not in _dot_presenti_norm]

    if lat and long:
        data["lat"] = lat
        data["long"] = long
    for campo in ["camere", "bagni", "posti_letto", "superficie", "piano", "stato", "epoca", "tipologia", "comune", "zona", "indirizzo"]:
        if campo in data and not isinstance(data[campo], str):
            data[campo] = str(data[campo])

    if "comune" in data:
        data["comune"] = data["comune"].title()
    if "zona" in data:
        data["zona"] = data["zona"].title() if _zona_sembra_valida(data["zona"]) else "—"

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
        data["indirizzo"] = addr.title()
        if _record_comune and _record_comune.get("sigla_provincia"):
            _sigla_corretta = _record_comune["sigla_provincia"].upper()
            if _re.search(r'\([A-Za-z]{2}\)', data["indirizzo"]):
                data["indirizzo"] = _re.sub(r'\([A-Za-z]{2}\)', f"({_sigla_corretta})", data["indirizzo"])
            else:
                data["indirizzo"] = f"{data['indirizzo']} ({_sigla_corretta})"
        else:
            data["indirizzo"] = _re.sub(r'\(([A-Za-z]{2})\)', lambda m: f"({m.group(1).upper()})", data["indirizzo"])

    _calcola_costi_fissi_deterministici(data)

    # ── Confronto affitto tradizionale — dato OMI reale quando disponibile ──
    # Sessione 62: prima questi 3 campi arrivavano interamente dall'AI (mai
    # verificati, causa dell'errore Brera €1.000 vs reale €1.800-2.200 già
    # segnalato in checklist). Ora, se il comune è coperto dal dataset OMI
    # 2025/2, li ricalcoliamo in modo deterministico dal canone reale
    # EUR/m2. Se il comune non è coperto, restano quelli dell'AI —
    # dichiarati come stima, mai spacciati per OMI.
    _istat = _record_comune.get("codice_istat") if _record_comune else None
    _superficie_num = None
    _sup_raw = data.get("superficie")
    if _sup_raw is not None:
        _match_sup = _re.search(r"[\d.,]+", str(_sup_raw))
        if _match_sup:
            try:
                _superficie_num = float(_match_sup.group(0).replace(",", "."))
            except ValueError:
                _superficie_num = None
    try:
        _omi_affitto = omi_canoni.stima_affitto_tradizionale(
            _istat, _superficie_num, data.get("tipologia")
        ) if _istat else None
    except Exception as _err_omi:
        print(f"[OMI] errore imprevisto, fallback a stima AI: {_err_omi!r}")
        _omi_affitto = None
    if _omi_affitto:
        data["affitto_ricavo"], data["affitto_costi"], data["affitto_profitto"], data["fonte_affitto_tradizionale"] = _omi_affitto
        print(f"[OMI] canone reale applicato per comune={data.get('comune')!r} istat={_istat}")
    else:
        data["fonte_affitto_tradizionale"] = "stima_ai"
        print(f"[OMI] comune={data.get('comune')!r} non coperto dal dataset OMI 2025/2 — resta stima AI")

    _cat = data.get("categoria", "comune_minore")
    _sub = data.get("sottocategoria", "residenziale_minore") or "residenziale_minore"
    _p = data.get("prezzo_notte_stimato", 0)

    # Camere corrette per tipologia (Sessione 66) — sovrascrive quanto
    # scritto dall'AI PRIMA di mandarlo ad AirROI, così la stima di prezzo
    # e la scheda immobile mostrata usano lo stesso numero corretto.
    data["camere"] = _camere_deterministiche(data.get("tipologia"), data.get("camere"))

    print(f"[AIRROI] chiamata per indirizzo={data.get('indirizzo')!r} lat={data.get('lat')!r} long={data.get('long')!r} email_destinatario={data.get('email')!r}")

    _occ_old = data.get("occupazione_percent", 0)

    _airroi = _airroi_lookup_e_stima(
        data.get("lat"), data.get("long"),
        camere_raw=data.get("camere"), posti_letto_raw=data.get("posti_letto"),
        bagni_raw=data.get("bagni"),
    )

    # Correttivo occupazione AirROI — Sessione 65, differenziato per
    # categoria (vedi stagionalita_turistica.py per fonti e ragionamento).
    # Sostituisce il correttivo fisso 1.35 di ieri.
    _correttivo_occ, _fonte_correttivo = stagionalita_turistica.correttivo_occupazione(
        _sub, _cat, data.get("comune")
    )

    if _airroi:
        _p_new = _airroi["prezzo_notte_stimato"]
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
        data["fonte_prezzo"] = "airroi"
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

    if _airroi and _airroi.get("comparable_listings"):
        _comp_airroi = _costruisci_competitor_da_airroi(_airroi["comparable_listings"])
        if _comp_airroi:
            _righe_comp, _media_comp = _comp_airroi
            data["competitor"] = _righe_comp
            data["media_nazionale"] = _media_comp
            data["fonte_competitor"] = "airroi"
        else:
            data["fonte_competitor"] = "ai_stima"
    else:
        data["fonte_competitor"] = "ai_stima"

    # Fallback intermedio: nessun annuncio comparabile individuale, ma AirROI
    # fornisce comunque i percentili di ricavo reali del mercato — meglio di
    # niente, usiamoli per la riga "Media nazionale" invece di lasciarla
    # 100% inventata dall'AI. Le 4 righe competitor dettagliate restano AI
    # (non ricostruibili senza annunci individuali). Sessione 64.
    if data["fonte_competitor"] == "ai_stima" and _airroi and _airroi.get("percentili_revenue"):
        _media_reale = _media_nazionale_da_percentili(
            _airroi["percentili_revenue"], _airroi.get("occupazione_frazione")
        )
        if _media_reale:
            data["media_nazionale"] = _media_reale
            data["fonte_competitor"] = "airroi_percentili"

    if _p:
        data["prezzo_notte_stimato"] = _p_new
        data["occupazione_percent"] = _occ_new

        _notti_new = round(_occ_new / 100 * 365) if _occ_new else 0
        data["notti_anno"] = _notti_new
        data["kpi_occupazione"] = _occ_new

        _ricavo_lordo_new = round(_p_new * _notti_new)
        _ricavo_lordo_old = data.get("ricavo_lordo", 0)
        _bonus_old = data.get("bonus_dirette", 0)
        _bonus_new = round(_bonus_old * (_ricavo_lordo_new / _ricavo_lordo_old)) if _ricavo_lordo_old else _bonus_old
        _totale_ricavi_new = _ricavo_lordo_new + _bonus_new

        _comm_pct = data.get("costi_commissioni_pct", 15)
        _pulizia_unit = data.get("costi_pulizie_unit", 35)
        _costi_commissioni_new = round(_ricavo_lordo_new * _comm_pct / 100)
        _costi_pulizie_new = round(_pulizia_unit * _notti_new)
        _costi_biancheria = data.get("costi_biancheria", 0)
        _costi_utenze = data.get("costi_utenze", 0)
        _costi_manutenzione = data.get("costi_manutenzione", 0)
        _mutuo_annuo = data.get("rata_mutuo_mensile", 0) * 12 if data.get("mutuo_attivo") else 0

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
        data["kpi_prezzo_range"] = f"Range zona: € {max(1, round(_p_new * 0.75))}-{round(_p_new * 1.25)}"
        _occ_range_min = max(5, round(_occ_new * 0.75))
        _occ_range_max = min(_tetto_occ, round(_occ_new * 1.25))
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

    data["descrizione"] = genera_descrizione_standard(data)

    if "occupazione" in data:
        data["occupazione"] = [list(row) for row in data["occupazione"]]
    if "poi" in data:
        data["poi"] = _correggi_poi_invertiti(data["poi"])
    if "competitor" in data:
        data["competitor"] = [list(row) for row in data["competitor"]]

    if data.get("mutuo_attivo") and data.get("rata_mutuo_mensile", 0):
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

    return data


@app.route("/generate-pdf-direct", methods=["POST"])
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


# ── ROUTE STRATEGICO ──────────────────────────────────────────────────────────
from strategico import build_strategico_pdf_bytes

@app.route("/generate-strategico", methods=["POST"])
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
        if request.args.get("lat") and request.args.get("long"):
            data["lat"] = request.args.get("lat")
            data["long"] = request.args.get("long")

        for campo in ["camere", "bagni", "posti_letto", "superficie", "piano", "stato", "epoca", "tipologia", "comune", "zona", "indirizzo"]:
            if campo in data and not isinstance(data[campo], str):
                data[campo] = str(data[campo])

        if "comune" in data:
            data["comune"] = data["comune"].title()
        if "zona" in data:
            data["zona"] = data["zona"].title() if _zona_sembra_valida(data["zona"]) else "—"

        _record_comune = comuni_lookup.trova_comune(data.get("comune", ""), data.get("provincia"))
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
            data["indirizzo"] = addr.title()
            if _record_comune and _record_comune.get("sigla_provincia"):
                _sigla_corretta = _record_comune["sigla_provincia"].upper()
                if _re2.search(r'\([A-Za-z]{2}\)', data["indirizzo"]):
                    data["indirizzo"] = _re2.sub(r'\([A-Za-z]{2}\)', f"({_sigla_corretta})", data["indirizzo"])
                else:
                    data["indirizzo"] = f"{data['indirizzo']} ({_sigla_corretta})"
            else:
                data["indirizzo"] = _re2.sub(r'\(([A-Za-z]{2})\)', lambda m: f"({m.group(1).upper()})", data["indirizzo"])

        _calcola_costi_fissi_deterministici(data)

        if "occupazione" in data:
            data["occupazione"] = [list(row) for row in data["occupazione"]]
        if "poi" in data:
            data["poi"] = _correggi_poi_invertiti(data["poi"])
        if "competitor" in data:
            data["competitor"] = [list(row) for row in data["competitor"]]
        if "pricing_mensile" in data:
            data["pricing_mensile"] = [list(row) for row in data["pricing_mensile"]]
        if "normativa_extra" in data:
            data["normativa_extra"] = [list(row) for row in data["normativa_extra"]]
        if "piano_90" in data:
            for item in data["piano_90"]:
                if isinstance(item, dict) and "azioni" in item:
                    item["azioni"] = list(item["azioni"])

        if data.get("mutuo_attivo") and data.get("rata_mutuo_mensile", 0):
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

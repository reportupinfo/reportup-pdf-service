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

import comuni_lookup
import territorio_gps

app = Flask(__name__)

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

# ── Aeroporti italiani — lista fissa con coordinate (25/06/2026) ──────────────
# Calcolo distanza/aeroporto di riferimento fatto qui in Python, non da Make/AI:
# zero invenzioni, zero chiamata API aggiuntiva. Aggiornare solo se aprono/chiudono
# scali commerciali (evento raro).
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


def _haversine_km(lat1, lon1, lat2, lon2):
    """Distanza in linea d'aria tra due coordinate, in km."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def aeroporto_row(lat, lon, max_km=120):
    """
    Restituisce la riga [distanza, nome, impatto] per l'aeroporto piu' vicino.
    L'aeroporto piu' vicino si individua SEMPRE con la linea d'aria (calcolo
    Python, zero costo) — ma la distanza mostrata all'utente e' quella REALE
    in auto (km + minuti), via Google Distance Matrix, perche' e' il dato che
    conta per chi deve arrivarci (Sessione 45, feedback Salvatore). Se l'API
    non risponde (rete, chiave assente, isole senza strada), si ricade sulla
    linea d'aria come prima — nessun errore visibile nel PDF.
    """
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
    return f"EUR {int(val):,}".replace(",", ".")


def stage_color(stage):
    if stage == "Peak":  return GOLD
    if stage == "Alta":  return TEAL
    if stage == "Media": return BLUE_PRIMARY
    return MUTED


def wrap_text(c, text, x, y, max_w, font, size, line_h):
    """Stampa testo con a-capo automatico. Supporta tag [B]...[/B]."""
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
    """Testo semplice con a-capo."""
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

    # Pill REPORT BASE
    pill_label = "REPORT BASE"
    c.setFont("Helvetica-Bold", 10)
    pl_w = c.stringWidth(pill_label, "Helvetica-Bold", 10) + 12 * mm
    pl_h = 8 * mm
    c.setFillColor(BLUE_PRIMARY)
    c.roundRect(W / 2 - pl_w / 2, y - pl_h, pl_w, pl_h, 2 * mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.drawCentredString(W / 2, y - pl_h + 2.5 * mm, pill_label)
    y -= pl_h + 4 * mm

    # Pill IL TUO INVESTIMENTO
    sub_label = "IL TUO INVESTIMENTO"
    c.setFont("Helvetica", 8)
    sl_w = c.stringWidth(sub_label, "Helvetica", 8) + 10 * mm
    sl_h = 6 * mm
    c.setFillColor(BLUE_NIGHT)
    c.roundRect(W / 2 - sl_w / 2, y - sl_h, sl_w, sl_h, 1.5 * mm, fill=1, stroke=0)
    c.setFillColor(HexColor("#A8BCC8"))
    c.drawCentredString(W / 2, y - sl_h + 1.8 * mm, sub_label)
    y -= sl_h + 5 * mm

    # Box indirizzo — font scaling dinamico: riduce fino a 10pt per indirizzi lunghi
    box_h = 16 * mm
    c.setFillColor(BLUE_NIGHT)
    c.rect(14 * mm, y - box_h, W - 28 * mm, box_h, fill=1, stroke=0)
    c.setFillColor(WHITE)
    indirizzo_txt = D.get("indirizzo", "")
    max_w_ind = W - 36 * mm  # margine interno box
    for font_size in [18, 16, 14, 12, 10]:
        c.setFont("Helvetica-Bold", font_size)
        if c.stringWidth(indirizzo_txt, "Helvetica-Bold", font_size) <= max_w_ind:
            break
    c.drawCentredString(W / 2, y - box_h / 2 - font_size * 0.18 * mm, indirizzo_txt)
    y -= box_h + 5 * mm

    # Scheda immobile
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

    # Dotazioni
    c.setFont("Helvetica", 7)
    c.setFillColor(TEAL)
    c.drawString(14 * mm, y, "Dotazioni presenti")
    y -= 5 * mm
    pill_h = 5.5 * mm
    px = 14 * mm
    DOTAZIONI_AMMESSE = ["WiFi", "Parcheggio", "Aria condizionata", "Lavatrice", "Cucina attrezzata",
                         "Terrazzo", "Giardino", "Riscaldamento", "Ascensore", "Piscina"]
    def _norm(d):
        d = d.strip()
        mapping = {
            "wifi": "WiFi", "wi-fi": "WiFi", "wi fi": "WiFi",
            "parcheggio": "Parcheggio",
            "aria_condizionata": "Aria condizionata", "aria condizionata": "Aria condizionata",
            "lavatrice": "Lavatrice",
            "cucina": "Cucina attrezzata", "cucina attrezzata": "Cucina attrezzata",
            "terrazzo": "Terrazzo", "terrazzo / giardino": "Terrazzo", "terrazzo/giardino": "Terrazzo",
            "giardino": "Giardino",
            "riscaldamento": "Riscaldamento",
            "ascensore": "Ascensore",
            "piscina": "Piscina",
        }
        return mapping.get(d.lower(), d)
    presenti = [_norm(d) for d in D.get("dotazioni_presenti", []) if _norm(d) in DOTAZIONI_AMMESSE]
    assenti  = [_norm(d) for d in D.get("dotazioni_assenti", [])  if _norm(d) in DOTAZIONI_AMMESSE]
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

    # Situazione attuale
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

    # Descrizione
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

    # POI — STRUTTURA A 5 SLOT FISSI (25/06/2026)
    y = draw_section_header(c, 14 * mm, y, W - 28 * mm, "Posizione e punti di interesse")
    y -= 3 * mm
    draw_section_subtitle(c, 14 * mm, y, "Distanze e impatto sulla domanda di prenotazioni")
    y -= 6 * mm

    # Etichette di slot FISSE, scritte qui in Python: non arrivano mai da Make/AI.
    # Garantisce ordine e numero di righe sempre identici, per qualsiasi comune.
    SLOT_LABELS = [
        "Trasporto pubblico",
        "Comune di riferimento",
        "Elemento caratteristico",
        "Servizi essenziali",
        "Aeroporto",
    ]

    poi_rows_raw = [list(row) for row in D.get("poi", [])]
    # Sicurezza: se Make invia meno di 5 righe, le mancanti si completano con trattini
    # (mai una riga inventata); se ne invia più di 5, le eccedenti vengono ignorate.
    while len(poi_rows_raw) < 5:
        poi_rows_raw.append(["\u2014", "\u2014", "\u2014"])
    poi_rows_raw = poi_rows_raw[:5]
    # Slot 5 (Aeroporto, indice 4) e' SEMPRE calcolato qui in Python, non da Make/AI:
    # sovrascrive qualsiasi cosa arrivi da fuori per questa riga specifica.
    poi_rows_raw[4] = aeroporto_row(D.get("lat"), D.get("long"))

    # Celle come Paragraph: il testo va sempre a capo dentro la propria colonna,
    # non invade mai quella vicina anche con nomi/distanze molto lunghi.
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

    # Occupazione stagionale
    y = draw_section_header(c, 14 * mm, y, W - 28 * mm, "Occupazione stagionale")
    y -= 3 * mm
    draw_section_subtitle(c, 14 * mm, y, "Andamento mensile stimato - prezzi e tassi di riempimento")
    y -= 6 * mm
    occ = D.get("occupazione", [])
    header_half = ["Mese", "Occup.", "EUR/notte", "Stage"]
    gap = 5 * mm
    half = (W - 28 * mm - gap) / 2
    col_w_half = [half * 0.20, half * 0.24, half * 0.32, half * 0.24]

    def make_half_style(rows):
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
        return style

    data_sx = [[o[0], f"{o[1]}%", f"EUR {o[2]}", o[3]] for o in occ[:6]]
    data_dx = [[o[0], f"{o[1]}%", f"EUR {o[2]}", o[3]] for o in occ[6:]]
    tbl_sx = Table([header_half] + data_sx, colWidths=col_w_half)
    tbl_sx.setStyle(TableStyle(make_half_style(data_sx)))
    tbl_sx.wrapOn(c, half, 300)
    tbl_dx = Table([header_half] + data_dx, colWidths=col_w_half)
    tbl_dx.setStyle(TableStyle(make_half_style(data_dx)))
    tbl_dx.wrapOn(c, half, 300)
    tbl_h = max(tbl_sx._height, tbl_dx._height)
    tbl_sx.drawOn(c, 14 * mm, y - tbl_h)
    tbl_dx.drawOn(c, 14 * mm + half + gap, y - tbl_h)
    y -= tbl_h + 5 * mm

    # Grafico linea occupazione
    graph_h = 62 * mm
    graph_w = W - 28 * mm
    gx, gy = 14 * mm, y - graph_h
    c.setFillColor(WHITE)
    c.rect(gx, gy, graph_w, graph_h, fill=1, stroke=0)
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.3)
    c.rect(gx, gy, graph_w, graph_h, fill=0, stroke=1)
    legend_items = [("Bassa", MUTED), ("Media", BLUE_PRIMARY), ("Alta stagione", TEAL), ("Peak", GOLD)]
    lx = gx + 3 * mm
    for lbl, col in legend_items:
        c.setFillColor(col)
        c.circle(lx + 1.5 * mm, gy + graph_h - 4 * mm, 1.5 * mm, fill=1, stroke=0)
        c.setFont("Helvetica", 6.5)
        c.setFillColor(MUTED)
        c.drawString(lx + 4 * mm, gy + graph_h - 5 * mm, lbl)
        lx += c.stringWidth(lbl, "Helvetica", 6.5) + 10 * mm
    # Zona grafico: 16mm in basso riservati alle label (mese + EUR), punti partono da 17mm
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
        # Clamp rate nel range per sicurezza
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
    for px_dot, py_dot, stage, rate in points:
        col = stage_color(stage)
        c.setFillColor(col)
        r = 2.5 * mm if stage == "Peak" else 1.8 * mm
        c.circle(px_dot, py_dot, r, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 6)
        c.setFillColor(BLUE_NIGHT)
        c.drawCentredString(px_dot, py_dot + 3 * mm, f"{rate}%")
    # Label mese e EUR sotto la linea del grafico — sempre fuori dalla zona pallini
    for i, row in enumerate(occ):
        px_dot = gx + side_margin + i * step
        c.setFont("Helvetica", 6)
        c.setFillColor(BLUE_NIGHT)
        c.drawCentredString(px_dot, gy + 8 * mm, row[0])
        c.setFont("Helvetica", 5.5)
        c.setFillColor(MUTED)
        c.drawCentredString(px_dot, gy + 4 * mm, f"EUR {row[2]}")

    # Disclaimer prezzi sotto grafico
    disclaimer_prezzi = (
        "I valori indicati rappresentano medie su base annua. In comuni ad alto impatto turistico i prezzi "
        "reali in alta stagione possono essere superiori del 5-10% rispetto alle stime qui riportate."
    )
    c.setFont("Helvetica-Oblique", 6)
    c.setFillColor(MUTED)
    c.drawCentredString(W / 2, gy - 4 * mm, disclaimer_prezzi)


def page3(c, D):
    draw_header(c, D)
    draw_footer(c, 3)
    y = H - 22 * mm

    y = draw_section_header(c, 14 * mm, y, W - 28 * mm, "Analisi economica annuale")
    y -= 3 * mm
    draw_section_subtitle(c, 14 * mm, y, "Proiezione costi e ricavi basata sulla situazione dichiarata")
    y -= 6 * mm

    p = D.get("prezzo_notte_stimato", 0)
    occ_pct = D.get("occupazione_percent", 0)
    notti = D.get("notti_anno", 0)
    comm_pct = D.get("costi_commissioni_pct", 15)
    pulizia_unit = D.get("costi_pulizie_unit", 35)
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
         f"EUR {p}/notte x {occ_pct}% occ. x 365gg = EUR {p} x {notti} notti",
         fmt_eur(D.get("ricavo_lordo", 0))],
        ["Bonus prenotazioni dirette",
         f"EUR {D.get('ricavo_lordo',0):,} x {D.get('bonus_dirette_pct','5-10%')} = EUR {D.get('bonus_dirette',0):,}".replace(",", "."),
         fmt_eur(D.get("bonus_dirette", 0))],
        ["TOTALE RICAVI",
         f"EUR {D.get('ricavo_lordo',0):,} + EUR {D.get('bonus_dirette',0):,} = EUR {D.get('totale_ricavi',0):,}".replace(",", "."),
         fmt_eur(D.get("totale_ricavi", 0))],
        ["COSTI VARIABILI", "", ""],
        ["Commissioni piattaforma Airbnb",
         f"EUR {D.get('ricavo_lordo',0):,} x {comm_pct}% = EUR {D.get('costi_commissioni',0):,}".replace(",", "."),
         f"- {fmt_eur(D.get('costi_commissioni', 0))}"],
        ["Pulizie per cambio ospite",
         f"EUR {pulizia_unit}/cambio x {notti} notti = EUR {D.get('costi_pulizie',0):,}".replace(",", "."),
         f"- {fmt_eur(D.get('costi_pulizie', 0))}"],
        ["Biancheria e consumabili",
         f"Range EUR 300-700/anno | conv. adottata: EUR {D.get('costi_biancheria',0):,}".replace(",", "."),
         f"- {fmt_eur(D.get('costi_biancheria', 0))}"],
        ["Utenze aggiuntive stimate",
         f"Range EUR 500-1.000/anno | conv. adottata: EUR {D.get('costi_utenze',0):,}".replace(",", "."),
         f"- {fmt_eur(D.get('costi_utenze', 0))}"],
        ["Manutenzione ordinaria",
         f"Range EUR 200-600/anno | conv. adottata: EUR {D.get('costi_manutenzione',0):,}".replace(",", "."),
         f"- {fmt_eur(D.get('costi_manutenzione', 0))}"],
        ["Rata mutuo (se presente)",
         "Nessun mutuo dichiarato" if not D.get("mutuo_attivo") else f"EUR {rata_mutuo}/mese x 12 = EUR {mutuo_annuo:,}".replace(",", "."),
         "EUR 0" if not D.get("mutuo_attivo") else f"- {fmt_eur(mutuo_annuo)}"],
        ["Totale costi variabili", "", f"- {fmt_eur(D.get('totale_costi', 0))}"],
        ["PROFITTO NETTO STIMATO", "", fmt_eur(D.get("profitto_netto", 0))],
        ["Margine netto su ricavi lordi", "", f"{D.get('margine_percent', 0)}%"],
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

    # 4 card riepilogo
    total_w = W - 28 * mm
    big_w = total_w * 0.30
    small_w = (total_w - big_w - 6 * mm) / 3
    small_h, big_h = 18 * mm, 24 * mm
    cards = [
        ("Margine netto", f"{D.get('margine_percent', 0)}%", WHITE, BLUE_NIGHT, small_w, small_h),
        ("Ricavo lordo stimato", fmt_eur(D.get("ricavo_lordo", 0)), TEAL_LIGHT, TEAL, small_w, small_h),
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
        c.drawCentredString(cx + cw / 2, cy + ch - 5 * mm, lbl)
        val_y = y - big_h + (big_h - small_h) / 2 + small_h / 2 - 4 * mm
        c.setFont("Helvetica-Bold", 14 if is_gold else 12)
        c.setFillColor(tc)
        c.drawCentredString(cx + cw / 2, val_y, val)
        cx += cw + 2 * mm
    y -= big_h + 4 * mm

    # Nota
    nota = ("I valori sopra riportati sono orientativi e basati esclusivamente sulle informazioni fornite. "
            "Non includono spese personali, fiscali o societarie.")
    y = draw_wrapped_text(c, nota, 14 * mm, y - 2 * mm, W - 28 * mm, "Helvetica-Oblique", 6.5, 4 * mm, MUTED)
    y -= 4 * mm

    # Confronto affitto
    y = draw_section_header(c, 14 * mm, y, W - 28 * mm, "Confronto con affitto tradizionale")
    y -= 5 * mm
    conf_data = [
        ["", "Affitto tradizionale", "B&B / Short rent", "Differenza"],
        ["Ricavo annuo lordo", fmt_eur(D.get("affitto_ricavo", 0)), fmt_eur(D.get("ricavo_lordo", 0)),
         f"+{fmt_eur(D.get('ricavo_lordo', 0) - D.get('affitto_ricavo', 0))}"],
        ["Costi di gestione", fmt_eur(D.get("affitto_costi", 0)), fmt_eur(D.get("totale_costi", 0)), "--"],
        ["Profitto netto", fmt_eur(D.get("affitto_profitto", 0)), fmt_eur(D.get("profitto_netto", 0)),
         f"+{fmt_eur(D.get('profitto_netto', 0) - D.get('affitto_profitto', 0))}"],
        ["Flessibilit\u00e0 utilizzo", "Bassa", "Alta", "Molto alta"],
        ["Rischio morosit\u00e0", "Alto", "Nullo", "Eliminato"],
    ]
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
        ("TEXTCOLOR", (3, 1), (3, 1), TEAL), ("FONTNAME", (3, 1), (3, 1), "Helvetica-Bold"),
        ("TEXTCOLOR", (3, 3), (3, 3), TEAL), ("FONTNAME", (3, 3), (3, 3), "Helvetica-Bold"),
        ("TEXTCOLOR", (3, 4), (3, 4), TEAL), ("FONTNAME", (3, 4), (3, 4), "Helvetica-Bold"),
        ("TEXTCOLOR", (3, 5), (3, 5), TEAL), ("FONTNAME", (3, 5), (3, 5), "Helvetica-Bold"),
    ]))
    tbl_conf.wrapOn(c, W - 28 * mm, 300)
    tbl_conf.drawOn(c, 14 * mm, y - tbl_conf._height)


def page4(c, D):
    draw_header(c, D)
    draw_footer(c, 4)
    y = H - 22 * mm

    # Competitor
    y = draw_section_header(c, 14 * mm, y, W - 28 * mm,
                            f"Analisi competitor - {D.get('competitor_zona', '')}")
    y -= 3 * mm
    draw_section_subtitle(c, 14 * mm, y, "Confronto diretto con gli annunci attivi nella zona")
    y -= 6 * mm
    comp_data = [["Tipologia annunci - " + D.get("competitor_zona", ""), "N.", "Prezzo med.", "Occup.", "Rating"]]
    for row in D.get("competitor", []):
        comp_data.append(list(row))
    mn = D.get("media_nazionale", ["Media nazionale B&B urbani", "\u2014", "EUR 95", "64%", "4.5"])
    comp_data.append(list(mn))
    comp_data.append(["IL TUO IMMOBILE (stima)", "\u2014",
                      f"EUR {D.get('kpi_prezzo', 0)}", f"{D.get('kpi_occupazione', 0)}%", "\u2014"])
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

    # KPI
    y = draw_section_header(c, 14 * mm, y, W - 28 * mm, "Riepilogo indicatori di mercato")
    y -= 3 * mm
    draw_section_subtitle(c, 14 * mm, y, "Sintesi conclusiva dei valori chiave calcolati per il tuo immobile")
    y -= 7 * mm
    kw = (W - 28 * mm - 6 * mm) / 4
    kh = 24 * mm
    kpis = [
        ("PREZZO MEDIO / NOTTE", f"EUR {D.get('kpi_prezzo', 0)}", "per notte", D.get("kpi_prezzo_range", "")),
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

    # Upsell box
    upsell_h = 30 * mm
    c.setFillColor(GOLD_LIGHT)
    c.roundRect(14 * mm, y - upsell_h, W - 28 * mm, upsell_h, 3 * mm, fill=1, stroke=0)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1)
    c.roundRect(14 * mm, y - upsell_h, W - 28 * mm, upsell_h, 3 * mm, fill=0, stroke=1)
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(BLUE_NIGHT)
    c.drawString(18 * mm, y - 7 * mm, "Vuoi il piano d\u2019azione completo?")
    upsell_text = ("Il Report Strategico (EUR 149) include tutto il Base piu': pricing stagionale mese per mese, "
                   "3 scenari economici (pessimistico / realistico / ottimistico), piano d'azione 90 giorni, "
                   "cap rate e valore asset, normativa affitti brevi locale e l'analisi personale "
                   "dell'Arch. Salvatore Junior Sica.")
    uy = y - 13 * mm
    uy = draw_wrapped_text(c, upsell_text, 18 * mm, uy, W - 36 * mm, "Helvetica", 7.5, 5 * mm, BLUE_NIGHT)
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(GOLD)
    c.drawString(18 * mm, uy, "Scopri il Report Strategico su reportup.it  |  EUR 149 - pagamento unico")
    y -= upsell_h + 6 * mm

    # Disclaimer
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

    fonti = [
        ("Prezzi per notte e\ntasso di occupazione",
         "Elaborazione su dati aggregati delle principali piattaforme di short rental (Airbnb, Booking.com, VRBO). "
         "I valori rappresentano medie di mercato per tipologia di immobile e zona al momento della generazione."),
        ("Canoni di affitto\ntradizionale",
         "Osservatorio del Mercato Immobiliare (OMI) - Agenzia delle Entrate. Banca dati delle quotazioni "
         "immobiliari, aggiornamento semestrale."),
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

    # Box ringraziamento
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
    """
    Gestisce 3 formati possibili di output AI:
    1. Flat: {"tipologia": ..., "indirizzo": ..., "occupazione": [...]}
    2. Annidato report.*: {"report": {"immobile": {"caratteristiche": {...}}}}
    3. Annidato immobile.*: {"immobile": {"tipologia": ..., "dotazioni": [...]}}
    """
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


# ── Descrizione standard per categoria (Sessione 41) ─────────────────────────
# File madre dei template: RU_09_Descrizioni_Standard.docx
# Sovrascrive sempre il campo "descrizione" dell'AI: zero invenzioni geografiche,
# coerenza garantita con la tabella POI gia' verificata.
# Per oggi: capoluogo / grande_citta usano il template dedicato con zona; tutto
# il resto (comune_minore) usa il template residenziale, in attesa della
# sotto-classificazione costiero/lacuale/montano (sessione dedicata).

def _join_lista_e(items):
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " e " + items[-1]


def _concorda_numero(valore, singolare, plurale):
    """Restituisce 'N singolare' se N==1, altrimenti 'N plurale'. Tollera stringhe/valori non numerici."""
    try:
        n = int(str(valore).strip())
    except (ValueError, TypeError):
        return f"{valore} {plurale}"
    return f"{n} {singolare}" if n == 1 else f"{n} {plurale}"


_WIKI_CACHE = {}

# Sezioni Wikipedia da cercare per categoria, in ordine di priorità.
# Per ogni categoria: prima sezione trovata con testo utile vince.
_WIKI_SEZIONI_PER_CATEGORIA = {
    "grande_citta":        ["Monumenti e luoghi d'interesse", "Luoghi di interesse", "Arte e cultura", "Patrimonio"],
    "capoluogo":           ["Monumenti e luoghi d'interesse", "Luoghi di interesse", "Arte e cultura", "Patrimonio"],
    "costiero":            ["Spiagge", "Territorio", "Turismo", "Sagre", "Tradizioni", "Cultura"],
    "lacuale":             ["Turismo", "Sport", "Territorio", "Sagre", "Tradizioni", "Cultura"],
    "montano":             ["Sport", "Turismo", "Sci", "Trekking", "Territorio", "Sagre", "Tradizioni"],
    "residenziale_minore": ["Sagre", "Tradizioni", "Cultura", "Economia", "Prodotti tipici", "Gastronomia"],
}


def _pulisci_wikitext(testo):
    """
    Pulisce il wikitext grezzo di Wikipedia rimuovendo markup, template,
    riferimenti e lasciando solo testo leggibile in italiano.
    """
    # Rimuovi template {{...}} anche annidati
    for _ in range(5):
        testo = re.sub(r'\{\{[^{}]*\}\}', '', testo)
    # Rimuovi gallery <gallery>...</gallery>
    testo = re.sub(r'<gallery[^>]*>.*?</gallery>', '', testo, flags=re.DOTALL)
    # Rimuovi tag HTML con contenuto
    testo = re.sub(r'<ref[^>]*>.*?</ref>', '', testo, flags=re.DOTALL)
    testo = re.sub(r'<[^>]+>', '', testo)
    # Rimuovi intestazioni == Titolo == di qualsiasi livello
    testo = re.sub(r'={2,}.*?={2,}', '', testo)
    # Rimuovi link a file/immagini [[File:...]] [[Immagine:...]]
    testo = re.sub(r'\[\[(?:File|Immagine|Image|Media):[^\]]*\]\]', '', testo, flags=re.IGNORECASE)
    # Rimuovi link interni [[Testo|Display]] → Display, [[Testo]] → Testo
    testo = re.sub(r'\[\[(?:[^\]|]*\|)?([^\]]*)\]\]', r'\1', testo)
    # Rimuovi link esterni
    testo = re.sub(r'\[https?://\S+\s+([^\]]+)\]', r'\1', testo)
    testo = re.sub(r'\[https?://\S+\]', '', testo)
    # Rimuovi formattazione '''grassetto''' e ''corsivo''
    testo = re.sub(r"'{2,3}", '', testo)
    # Rimuovi righe che contengono nomi di file immagine (.jpg .png .svg ecc)
    righe = testo.split('\n')
    righe = [r for r in righe if not re.search(r'\.(jpg|jpeg|png|svg|gif|tiff|webp)', r, re.IGNORECASE)]
    testo = '\n'.join(righe)
    # Rimuovi parentesi con codici/coordinate/anni brevi
    testo = re.sub(r'\([^)]{0,8}\)', '', testo)
    # Rimuovi righe troppo corte o che iniziano con * # : ; (liste wikitext)
    righe = testo.split('\n')
    righe = [r.strip() for r in righe if len(r.strip()) > 30 and not r.strip().startswith(('*', '#', ':', ';', '|', '!'))]
    testo = ' '.join(righe)
    # Normalizza spazi
    testo = re.sub(r'\s+', ' ', testo).strip()
    return testo


def _estrai_sezione_wikipedia(titolo, nome_sezione, timeout=3):
    """
    Cerca una sezione specifica nella pagina Wikipedia e ne restituisce
    le prime 2-3 frasi utili, pulite dal wikitext.
    Ritorna None se la sezione non esiste o non contiene testo utile.
    """
    try:
        # Prima: ottieni l'indice delle sezioni
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

        # Trova il numero della sezione cercata (confronto case-insensitive, parziale)
        section_index = None
        nome_lower = nome_sezione.lower()
        for s in sections:
            if nome_lower in s.get("line", "").lower():
                section_index = s.get("index")
                break
        if section_index is None:
            return None

        # Seconda: scarica il wikitext di quella sezione
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

        # Se la sezione principale è vuota (es. Roma "Monumenti" è solo gallerie),
        # prova le sottosezioni immediate cercando testo utile
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

        # Prendi le prime frasi complete fino a ~300 caratteri
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
    """
    Estrae testo fattuale dalla pagina Wikipedia del comune, cercando
    sezioni tematiche specifiche per categoria (monumenti per grandi città,
    sagre/tradizioni per comuni minori, spiagge per costieri, ecc.).
    Fallback sulla prima frase introduttiva se nessuna sezione è trovata.
    Cache in memoria: stessa URL non rifà chiamate di rete nella stessa sessione.
    Licenza: Wikipedia CC BY-SA — attribuzione nel footer PDF (pagina 1).
    """
    if not wikipedia_url:
        return None

    cache_key = f"{wikipedia_url}|{categoria}|{sottocategoria}"
    if cache_key in _WIKI_CACHE:
        return _WIKI_CACHE[cache_key]

    risultato = None
    try:
        titolo = wikipedia_url.rstrip("/").rsplit("/", 1)[-1]

        # Determina quale lista di sezioni usare.
        # Un capoluogo/grande_citta può essere ANCHE costiero/lacuale/montano (es. Cagliari,
        # Napoli, Trieste): in quel caso si uniscono le sezioni tema-città con quelle
        # tema-territorio, provando prima le seconde perché più distintive del posto.
        if categoria in ("grande_citta", "capoluogo"):
            sezioni_da_cercare = list(_WIKI_SEZIONI_PER_CATEGORIA.get(categoria, []))
            if sottocategoria and sottocategoria in _WIKI_SEZIONI_PER_CATEGORIA:
                extra = _WIKI_SEZIONI_PER_CATEGORIA[sottocategoria]
                sezioni_da_cercare = extra + [s for s in sezioni_da_cercare if s not in extra]
        else:
            cat_key = sottocategoria if sottocategoria else "residenziale_minore"
            sezioni_da_cercare = _WIKI_SEZIONI_PER_CATEGORIA.get(cat_key, _WIKI_SEZIONI_PER_CATEGORIA["residenziale_minore"])

        # Prova ogni sezione in ordine finché una funziona
        for nome_sezione in sezioni_da_cercare:
            testo = _estrai_sezione_wikipedia(titolo, nome_sezione, timeout=timeout)
            if testo:
                risultato = testo
                break

        # Fallback: prima frase introduttiva (come prima)
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
                        # Scarta frasi puramente amministrative ("X è un comune italiano...")
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


def _poi_riga_frase(poi, idx):
    """Frase pronta dalla riga POI all'indice idx, o stringa vuota se assente."""
    try:
        distanza, nome, _impatto = (list(poi[idx]) + ["\u2014", "\u2014", "\u2014"])[:3]
    except (IndexError, TypeError):
        return ""
    if nome in ("\u2014", "", None):
        return ""
    return f"{nome} si trova a {distanza}."


def genera_descrizione_standard(data):
    """
    Descrizione standard a 4 blocchi fissi (Sessione 44 — vedi RU_09_Descrizioni_Standard.docx):
    Blocco 1: immobile (tipologia, superficie, camere, bagni, posti letto, TUTTE le dotazioni)
    Blocco 2: contesto (dati verificati tabella POI — trasporto, comune rif, elemento, servizi)
    Blocco 3: attrattiva (Wikipedia tematico per categoria — condizionale, omesso se assente)
    Blocco 4: target e chiusura evocativa (deterministica per categoria)
    Zero invenzioni: ogni frase si basa solo su dati verificati già presenti in data.
    """
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

    # Concordanza genere
    genere_femminile = any(t in tipologia.lower() for t in ["villa", "casa", "stanza", "camera"])
    situata = "situata" if genere_femminile else "situato"

    # Camere/bagni/posti letto con concordanza
    camere_frase      = _concorda_numero(camere, "camera", "camere")
    bagni_frase       = _concorda_numero(bagni, "bagno", "bagni")
    posti_letto_frase = _concorda_numero(posti_letto, "posto letto", "posti letto")

    # Dotazioni — TUTTE quelle presenti, scritte come frase fluente (non lista tecnica)
    def _fmt_dotazione(d):
        return d if d == "WiFi" else d.lower()
    dotazioni_frase = _join_lista_e([_fmt_dotazione(d) for d in dotazioni]) if dotazioni else ""

    # Zona — solo per capoluogo e grande_citta, solo se diversa dal nome comune
    zona_inserita = ""
    if categoria in ("capoluogo", "grande_citta") and zona and zona.lower() not in ("—", "", comune.lower()):
        zona_inserita = f", zona {zona}"

    # POI — riga 0 trasporto, riga 1 comune rif, riga 2 elemento caratteristico, riga 3 servizi
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

    # ── BLOCCO 1: l'immobile ──────────────────────────────────────────────────
    desc = (
        f"Accogliente {tipologia.lower()} di {superficie} {situata} in {indirizzo}{zona_inserita}, "
        f"con {camere_frase}, {bagni_frase} e {posti_letto_frase}. "
    )
    if dotazioni_frase:
        desc += f"L'immobile è dotato di {dotazioni_frase}: tutto il necessario per un soggiorno confortevole. "
    else:
        desc += "Un immobile pronto ad accogliere i tuoi ospiti. "

    # ── BLOCCO 2: il contesto ─────────────────────────────────────────────────
    if categoria in ("grande_citta", "capoluogo"):
        if trasporto_frase:
            desc += f"{trasporto_frase.rstrip('.')}, per muoversi in città senza pensieri. "
        if servizi_frase:
            desc += f"{servizi_frase.rstrip('.')}, a portata di mano per ogni necessità quotidiana. "
        if elemento_frase:
            desc += f"{elemento_frase} "
    else:
        if comune_rif_nome:
            desc += (f"A {comune_rif_distanza} si trova {comune_rif_nome}, "
                     f"punto di riferimento per servizi e collegamenti più ampi. ")
        if trasporto_frase:
            desc += f"{trasporto_frase} "
        if servizi_frase:
            desc += f"{servizi_frase.rstrip('.')} nelle vicinanze per le esigenze quotidiane. "

    # ── BLOCCO 3: l'attrattiva (Wikipedia — condizionale) ────────────────────
    if fatto_wiki:
        desc += fatto_wiki + " "

    # ── BLOCCO 4: target e chiusura evocativa ────────────────────────────────
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
    """Genera il PDF in memoria e restituisce bytes."""
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
    """
    Sostituisce il modulo 16 (Data store) su Make — Sessione 42.
    Usa comuni_lookup.py: gestisce accenti, apostrofi, maiuscole/minuscole,
    alias colloquiali (es. "Reggio Emilia") e comuni omonimi (via provincia).
    Chiamata da Make: GET /categoria-comune?comune=...&provincia=... (provincia opzionale)
    """
    comune_q = request.args.get("comune", "")
    provincia_q = request.args.get("provincia")

    record = comuni_lookup.trova_comune(comune_q, provincia_q)

    if not record:
        # Nessun match: stesso default già usato come fallback in app.py
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


@app.route("/generate-pdf", methods=["POST"])
def generate_pdf():
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"error": "JSON body richiesto"}), 400

        # Normalizza struttura annidata → flat
        data = normalize_data(data)

        # Normalizza occupazione: accetta sia liste che tuple
        if "occupazione" in data:
            data["occupazione"] = [list(row) for row in data["occupazione"]]
        if "poi" in data:
            data["poi"] = [list(row) for row in data["poi"]]
        if "competitor" in data:
            data["competitor"] = [list(row) for row in data["competitor"]]

        pdf_bytes = build_pdf_bytes(data)
        pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

        return jsonify({
            "success": True,
            "pdf_base64": pdf_b64,
            "filename": f"ReportUp_Base_{data.get('comune', 'report').replace(' ', '_')}.pdf"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/generate-pdf-binary", methods=["POST"])
def generate_pdf_binary():
    """
    Accetta il JSON grezzo dell'AI (eventualmente con backtick markdown).
    Pulisce, parsa, genera il PDF e lo restituisce come base64.
    """
    import json as _json
    import re as _re
    raw = ""
    try:
        raw = request.get_data(as_text=True)

        # Pulizia backtick robusta: estrai tutto tra { e } più esterni
        cleaned = raw.strip()
        # Prova prima con regex per blocco ```json...```
        m = _re.search(r'```(?:json)?\s*(\{.*\})\s*```', cleaned, _re.DOTALL)
        if m:
            cleaned = m.group(1).strip()
        else:
            # Estrai dal primo { all'ultimo }
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and end > start:
                cleaned = cleaned[start:end+1]

        data = _json.loads(cleaned)

        # Normalizza struttura annidata → flat
        data = normalize_data(data)

        # Normalizza array
        if "occupazione" in data:
            data["occupazione"] = [list(row) for row in data["occupazione"]]
        if "poi" in data:
            data["poi"] = [list(row) for row in data["poi"]]
        if "competitor" in data:
            data["competitor"] = [list(row) for row in data["competitor"]]

        pdf_bytes = build_pdf_bytes(data)
        pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

        return jsonify({
            "success": True,
            "pdf_base64": pdf_b64,
            "filename": f"ReportUp_Base_{data.get('comune', 'report').replace(' ', '_')}.pdf"
        })

    except Exception as e:
        return jsonify({"error": str(e), "raw_preview": raw[:500] if 'raw' in dir() else ""}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

@app.route("/generate-pdf-direct", methods=["POST"])
def generate_pdf_direct():
    """
    Accetta il JSON grezzo dell'AI, genera il PDF e lo restituisce
    come file binario diretto con Content-Type: application/pdf.
    """
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
        # Override lat/long con i valori VERI del geocode Make (Sessione 45):
        # quelli scritti dall'AI nel JSON possono essere leggermente imprecisi
        # (va bene per l'aeroporto, soglia larga; non va bene per costa/lago/
        # quota, soglie strette in km). Se Make passa ?lat=...&long=... in
        # query string, questi vincono sempre su quanto scritto dall'AI.
        if request.args.get("lat") and request.args.get("long"):
            data["lat"] = request.args.get("lat")
            data["long"] = request.args.get("long")
        # Normalizza campi stringa
        for campo in ["camere", "bagni", "posti_letto", "superficie", "piano", "stato", "epoca", "tipologia", "comune", "zona", "indirizzo"]:
            if campo in data and not isinstance(data[campo], str):
                data[campo] = str(data[campo])

        # Capitalizza comune e zona
        if "comune" in data:
            data["comune"] = data["comune"].title()
        if "zona" in data:
            data["zona"] = data["zona"].title()

        # Categoria comune — Sessione 42: calcolata qui in modo deterministico
        # da comuni_lookup.py (CSV 7.904 comuni), gestisce accenti, apostrofi,
        # maiuscole/minuscole, alias colloquiali e omonimi. Sovrascrive sempre
        # qualsiasi valore arrivato da Make/AI: zero crediti Make per questo
        # dato, zero rischio di mismatch case-sensitive come visto con Roma.
        _record_comune = comuni_lookup.trova_comune(data.get("comune", ""), data.get("provincia"))
        data["categoria"] = _record_comune["categoria"] if _record_comune else "comune_minore"
        # Sottocategoria (costiero/lacuale/montano) — GPS del punto esatto, non del
        # comune (Sessione 45): risolve i comuni estesi (es. Giugliano centro vs
        # Varcaturo) dove la vecchia sottocategoria statica per comune era sbagliata
        # per metà degli indirizzi reali.
        data["sottocategoria"] = territorio_gps.classifica_sottocategoria(data.get("lat"), data.get("long"))
        data["_wikipedia_estratto"] = _estratto_wikipedia(
            _record_comune.get("wikipedia") if _record_comune else None,
            categoria=data["categoria"],
            sottocategoria=data["sottocategoria"],
        )

        # Formatta indirizzo: capitalizza e aggiungi virgole attorno al CAP
        if "indirizzo" in data:
            import re as _re2
            addr = data["indirizzo"].strip()
            # Trova CAP (5 cifre) e aggiunge virgole attorno
            addr = _re2.sub(r'\s*(\d{5})\s*', r', \1, ', addr)
            # Rimuovi virgole doppie e spazi multipli
            addr = _re2.sub(r',\s*,', ',', addr)
            addr = _re2.sub(r'\s+', ' ', addr).strip().strip(',').strip()
            # Capitalizza ogni parola
            data["indirizzo"] = addr.title()
            # Fix deterministico sigla provincia: forza maiuscolo la sigla tra parentesi
            # es. "(Bs)" → "(BS)" — l'AI non rispetta il vincolo nel prompt (bug storico S38)
            data["indirizzo"] = _re.sub(r'\(([A-Za-z]{2})\)', lambda m: f"({m.group(1).upper()})", data["indirizzo"])

        # Rialzo prezzi deterministico per categoria (Sessione 44)
        # residenziale_minore +5%, tutto il resto +15%
        # Applicato PRIMA del ricalcolo economico per propagare su tutti i valori derivati.
        _cat = data.get("categoria", "comune_minore")
        _sub = data.get("sottocategoria", "residenziale_minore") or "residenziale_minore"
        _moltiplicatore = 1.05 if (_cat == "comune_minore" and _sub == "residenziale_minore") else 1.15
        _p = data.get("prezzo_notte_stimato", 0)
        if _p:
            _p_new = round(_p * _moltiplicatore)
            _ratio = _p_new / _p if _p else 1
            data["prezzo_notte_stimato"] = _p_new
            # Propaga il rialzo su tutti i valori economici derivati dal prezzo
            for _k in ["ricavo_lordo", "totale_ricavi", "bonus_dirette",
                       "costi_commissioni", "costi_pulizie", "profitto_netto",
                       "kpi_prezzo", "kpi_potenziale", "affitto_ricavo"]:
                if data.get(_k):
                    data[_k] = round(data[_k] * _ratio)
            # Propaga su tabella occupazione (colonna prezzi EUR/notte, indice 2)
            if "occupazione" in data:
                data["occupazione"] = [
                    [row[0], row[1], round(row[2] * _ratio) if len(row) > 2 else row[2]] + list(row[3:])
                    for row in data["occupazione"]
                ]

        # Descrizione standard per categoria: sovrascrive sempre quella dell'AI
        # (Sessione 41 — vedi RU_09_Descrizioni_Standard.docx)
        data["descrizione"] = genera_descrizione_standard(data)

        if "occupazione" in data:
            data["occupazione"] = [list(row) for row in data["occupazione"]]
        if "poi" in data:
            data["poi"] = [list(row) for row in data["poi"]]
        if "competitor" in data:
            data["competitor"] = [list(row) for row in data["competitor"]]

        # Ricalcolo totale_costi e profitto_netto includendo rata mutuo annua
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
# ── ROUTE STRATEGICO ──────────────────────────────────────────────────────────
from strategico import build_strategico_pdf_bytes

@app.route("/generate-strategico", methods=["POST"])
def generate_strategico():
    """
    Accetta il JSON grezzo dell'AI (Strategico), genera il PDF 13 pagine
    e lo restituisce come file binario diretto con Content-Type: application/pdf.
    Pattern identico a /generate-pdf-direct.
    """
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

        # Normalizza campi stringa
        for campo in ["camere", "bagni", "posti_letto", "superficie", "piano", "stato", "epoca", "tipologia", "comune", "zona", "indirizzo"]:
            if campo in data and not isinstance(data[campo], str):
                data[campo] = str(data[campo])

        # Capitalizza comune e zona
        if "comune" in data:
            data["comune"] = data["comune"].title()
        if "zona" in data:
            data["zona"] = data["zona"].title()

        # Categoria comune — Sessione 42: stesso lookup deterministico dell'endpoint Base.
        _record_comune = comuni_lookup.trova_comune(data.get("comune", ""), data.get("provincia"))
        data["categoria"] = _record_comune["categoria"] if _record_comune else "comune_minore"
        data["sottocategoria"] = territorio_gps.classifica_sottocategoria(data.get("lat"), data.get("long"))
        data["_wikipedia_estratto"] = _estratto_wikipedia(
            _record_comune.get("wikipedia") if _record_comune else None,
            categoria=data["categoria"],
            sottocategoria=data["sottocategoria"],
        )

        # Formatta indirizzo
        if "indirizzo" in data:
            import re as _re2
            addr = data["indirizzo"].strip()
            addr = _re2.sub(r'\s*(\d{5})\s*', r', \1, ', addr)
            addr = _re2.sub(r',\s*,', ',', addr)
            addr = _re2.sub(r'\s+', ' ', addr).strip().strip(',').strip()
            data["indirizzo"] = addr.title()
            # Fix deterministico sigla provincia (stesso fix di generate_pdf_direct)
            data["indirizzo"] = _re2.sub(r'\(([A-Za-z]{2})\)', lambda m: f"({m.group(1).upper()})", data["indirizzo"])

        if "occupazione" in data:
            data["occupazione"] = [list(row) for row in data["occupazione"]]
        if "poi" in data:
            data["poi"] = [list(row) for row in data["poi"]]
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

        # Ricalcolo mutuo se attivo
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

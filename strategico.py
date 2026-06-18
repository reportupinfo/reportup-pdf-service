"""
ReportUp — Strategico PDF pages
Importato da app.py come modulo separato.
Tutte le funzioni di pagina ricevono (c, data) come parametri.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors
import io
import math

#!/usr/bin/env python3
"""
ReportUp — Report Strategico · Fac-simile PDF
Grafica identica al Base · Dizionario DATI separato per fill-up automatico
"""


# ═══════════════════════════════════════════════════════════════════════════
# COLORI BRAND — identici al Base
# ═══════════════════════════════════════════════════════════════════════════
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

# ═══════════════════════════════════════════════════════════════════════════
# DIZIONARIO DATI — popolato da Make.com al momento del fill-up automatico
# ═══════════════════════════════════════════════════════════════════════════

def draw_header(c, data):
    header_h = 16*mm
    c.setFillColor(BLUE_NIGHT)
    c.rect(0, H - header_h, W, header_h, fill=1, stroke=0)
    lx = 14*mm
    ly = H - 10.5*mm
    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(WHITE)
    c.drawString(lx, ly, "Report")
    tw_report = c.stringWidth("Report", "Helvetica-Bold", 13)
    c.setFillColor(BLUE_PRIMARY)
    c.drawString(lx + tw_report, ly, "Up")
    c.setFont("Helvetica", 8)
    c.setFillColor(WHITE)
    c.drawRightString(W - 14*mm, H - 8*mm, "Analisi di mercato B&B \u00b7 Report Strategico")
    c.setFont("Helvetica", 7)
    c.setFillColor(HexColor("#A8BCC8"))
    c.drawRightString(W - 14*mm, H - 13*mm,
        f"Generato: {data['data_generazione']}  \u00b7  Valido 90 giorni")

def draw_footer(c, data, page_num, total=13):
    footer_h = 9*mm
    c.setFillColor(BLUE_NIGHT)
    c.rect(0, 0, W, footer_h, fill=1, stroke=0)
    c.setFont("Helvetica", 6.5)
    c.setFillColor(HexColor("#A8BCC8"))
    c.drawString(14*mm, 3.5*mm,
        "(c) 2025 ReportUp \u00b7 reportup.it  |  Documento orientativo - non costituisce consulenza professionale")
    c.drawRightString(W - 14*mm, 3.5*mm, f"Pag. {page_num} / {total}")

def draw_section_header(c, x, y, w, text):
    h = 7*mm
    c.setFillColor(BLUE_PRIMARY)
    c.rect(x, y - h, w, h, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(WHITE)
    c.drawString(x + 3*mm, y - h + 2.2*mm, text)
    return y - h

def draw_section_subtitle(c, x, y, text):
    c.setFont("Helvetica-Oblique", 7.5)
    c.setFillColor(MUTED)
    c.drawString(x, y, text)

def fmt_eur(val):
    return f"EUR {val:,}".replace(",", ".")

def fmt_eu(val):
    """Versione con simbolo € per prezzi in tabelle"""
    return f"\u20ac {val:,}".replace(",", ".")

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
        if pre: segments.append((pre, False))
        segments.append((bold_text, True))
    if remaining: segments.append((remaining, False))
    tokens = []
    for seg_text, is_bold in segments:
        for w in seg_text.split(" "):
            if w: tokens.append((w, is_bold))
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

def wrap_simple(c, text, x, y, max_w, font, size, line_h, color=None):
    if color: c.setFillColor(color)
    words = text.split()
    line = ""
    for w in words:
        test = line + (" " if line else "") + w
        if c.stringWidth(test, font, size) > max_w:
            c.setFont(font, size)
            if color: c.setFillColor(color)
            c.drawString(x, y, line)
            y -= line_h
            line = w
        else:
            line = test
    if line:
        c.setFont(font, size)
        if color: c.setFillColor(color)
        c.drawString(x, y, line)
        y -= line_h
    return y

# ═══════════════════════════════════════════════════════════════════════════
# PAG 1 — Scheda immobile + placeholder mappa + dotazioni + situazione
# ═══════════════════════════════════════════════════════════════════════════
def page1(c, data):
    draw_header(c, data)
    draw_footer(c, data, 1, 13)
    y = H - 22*mm

    # Pill REPORT STRATEGICO
    pill_label = "REPORT STRATEGICO"
    c.setFont("Helvetica-Bold", 10)
    pl_w = c.stringWidth(pill_label, "Helvetica-Bold", 10) + 12*mm
    pl_h = 8*mm
    c.setFillColor(BLUE_PRIMARY)
    c.roundRect(W/2 - pl_w/2, y - pl_h, pl_w, pl_h, 2*mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.drawCentredString(W/2, y - pl_h + 2.5*mm, pill_label)
    y -= pl_h + 4*mm

    # Pill IL TUO INVESTIMENTO
    sub_label = "IL TUO INVESTIMENTO STRATEGICO"
    c.setFont("Helvetica", 8)
    sl_w = c.stringWidth(sub_label, "Helvetica", 8) + 10*mm
    sl_h = 6*mm
    c.setFillColor(BLUE_NIGHT)
    c.roundRect(W/2 - sl_w/2, y - sl_h, sl_w, sl_h, 1.5*mm, fill=1, stroke=0)
    c.setFillColor(HexColor("#A8BCC8"))
    c.drawCentredString(W/2, y - sl_h + 1.8*mm, sub_label)
    y -= sl_h + 5*mm

    # Box indirizzo
    box_h = 16*mm
    c.setFillColor(BLUE_NIGHT)
    c.rect(14*mm, y - box_h, W - 28*mm, box_h, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(WHITE)
    c.drawCentredString(W/2, y - box_h/2 - 3.5*mm, data["indirizzo"])
    y -= box_h + 5*mm

    # Placeholder mappa
    map_h = 55*mm
    c.setFillColor(HexColor("#E3F2FA"))
    c.roundRect(14*mm, y - map_h, W - 28*mm, map_h, 3*mm, fill=1, stroke=0)
    c.setStrokeColor(BLUE_PRIMARY)
    c.setLineWidth(0.8)
    c.roundRect(14*mm, y - map_h, W - 28*mm, map_h, 3*mm, fill=0, stroke=1)
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(BLUE_PRIMARY)
    c.drawCentredString(W/2, y - map_h/2 + 3*mm, "\U0001f4cd  Posizione geografica immobile")
    c.setFont("Helvetica", 7.5)
    c.setFillColor(MUTED)
    c.drawCentredString(W/2, y - map_h/2 - 3*mm, f"{data['indirizzo']}  \u00b7  {data['zona']}")
    c.setFont("Helvetica-Oblique", 7)
    c.drawCentredString(W/2, y - map_h/2 - 8*mm, "La mappa interattiva sar\u00e0 integrata nella versione finale")
    y -= map_h + 5*mm

    # Scheda immobile
    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Scheda immobile")
    y -= 2*mm

    col_w = (W - 28*mm) / 2
    label_col_w = 28*mm
    fields_l = [
        ("Tipologia",  data["tipologia"]),
        ("Superficie", data["superficie"]),
        ("Piano",      data["piano"]),
        ("Stato",      data["stato"]),
        ("Camere",     data["camere"]),
    ]
    fields_r = [
        ("Comune",      data["comune"]),
        ("Zona",        data["zona"]),
        ("Epoca",       data["epoca"]),
        ("Bagni",       data["bagni"]),
        ("Posti letto", data["posti_letto"]),
    ]

    row_h = 7.5*mm
    for i, ((ll, lv), (rl, rv)) in enumerate(zip(fields_l, fields_r)):
        ry = y - i * row_h
        c.setFillColor(WHITE if i % 2 == 0 else CREAM)
        c.rect(14*mm, ry - row_h, W - 28*mm, row_h, fill=1, stroke=0)
        c.setFillColor(HexColor("#E3F2FA"))
        c.rect(14*mm, ry - row_h, label_col_w, row_h, fill=1, stroke=0)
        c.setFillColor(HexColor("#E3F2FA"))
        c.rect(14*mm + col_w, ry - row_h, label_col_w, row_h, fill=1, stroke=0)
        c.setStrokeColor(BORDER)
        c.setLineWidth(0.3)
        c.line(14*mm, ry - row_h, W - 14*mm, ry - row_h)
        c.setFont("Helvetica-Bold", 7.5)
        c.setFillColor(BLUE_PRIMARY)
        c.drawString(17*mm, ry - row_h + 2.5*mm, ll)
        c.setFont("Helvetica", 7.5)
        c.setFillColor(DARK_TEXT)
        c.drawString(14*mm + label_col_w + 2*mm, ry - row_h + 2.5*mm, lv)
        c.setStrokeColor(BORDER)
        c.line(14*mm + col_w, ry, 14*mm + col_w, ry - row_h)
        c.setFont("Helvetica-Bold", 7.5)
        c.setFillColor(BLUE_PRIMARY)
        c.drawString(14*mm + col_w + 3*mm, ry - row_h + 2.5*mm, rl)
        c.setFont("Helvetica", 7.5)
        c.setFillColor(DARK_TEXT)
        c.drawString(14*mm + col_w + label_col_w + 2*mm, ry - row_h + 2.5*mm, rv)

    y -= len(fields_l) * row_h + 4*mm

    # Dotazioni
    c.setFont("Helvetica", 7)
    c.setFillColor(TEAL)
    c.drawString(14*mm, y, "Dotazioni presenti")
    y -= 5*mm
    px = 14*mm
    pill_h = 5.5*mm
    for d in data["dotazioni_presenti"] + data["dotazioni_assenti"]:
        presente = d in data["dotazioni_presenti"]
        c.setFont("Helvetica-Bold" if presente else "Helvetica", 7)
        tw = c.stringWidth(d, "Helvetica-Bold" if presente else "Helvetica", 7)
        pw = tw + 6*mm
        if px + pw > W - 14*mm:
            px = 14*mm
            y -= pill_h + 1.5*mm
        c.setFillColor(TEAL if presente else LIGHT_GRAY)
        c.roundRect(px, y - pill_h + 1*mm, pw, pill_h, 2*mm, fill=1, stroke=0)
        c.setFillColor(WHITE if presente else MUTED)
        c.drawString(px + 3*mm, y - pill_h + 2.8*mm, d)
        px += pw + 2*mm
    y -= pill_h + 5*mm

    # Situazione attuale
    c.setFont("Helvetica", 7)
    c.setFillColor(TEAL)
    c.drawString(14*mm, y, "Situazione attuale dichiarata")
    y -= 5*mm
    situazioni = [
        (f"Immobile vuoto: {'SI' if data['situazione_vuoto'] else 'NO'}",      data["situazione_vuoto"]),
        (f"Inquilini attivi: {'SI' if data['situazione_inquilini'] else 'NO'}", data["situazione_inquilini"]),
        (f"B&B gi\u00e0 attivo: {'SI' if data['situazione_bnb'] else 'NO'}",   data["situazione_bnb"]),
        (f"Mutuo attivo: {'SI' if data['situazione_mutuo'] else 'NO'}",         data["situazione_mutuo"]),
    ]
    px = 14*mm
    for label, attivo in situazioni:
        c.setFont("Helvetica-Bold" if attivo else "Helvetica", 7)
        tw = c.stringWidth(label, "Helvetica-Bold" if attivo else "Helvetica", 7)
        pw = tw + 6*mm
        c.setFillColor(TEAL if attivo else LIGHT_GRAY)
        c.roundRect(px, y - pill_h + 1*mm, pw, pill_h, 2*mm, fill=1, stroke=0)
        c.setFillColor(WHITE if attivo else MUTED)
        c.drawString(px + 3*mm, y - pill_h + 2.8*mm, label)
        px += pw + 2*mm

# ═══════════════════════════════════════════════════════════════════════════
# PAG 2 — Descrizione + POI
# ═══════════════════════════════════════════════════════════════════════════
def page2(c, data):
    draw_header(c, data)
    draw_footer(c, data, 2, 13)
    y = H - 22*mm

    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Descrizione immobile")
    y -= 5*mm
    y = wrap_text(c, data["descrizione"], 14*mm, y, W - 28*mm, "Helvetica", 8, 5.5*mm)
    y -= 8*mm

    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Posizione e punti di interesse")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y, "Distanze e impatto sulla domanda di prenotazioni")
    y -= 6*mm

    poi_data = [["Punto di interesse", "A piedi", "Mezzo pubblico", "Impatto"]]
    for row in data["poi"]:
        poi_data.append(list(row))
    col_w_poi = [(W-28*mm)*0.35, (W-28*mm)*0.13, (W-28*mm)*0.33, (W-28*mm)*0.19]
    tbl_poi = Table(poi_data, colWidths=col_w_poi)
    tbl_poi.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), BLUE_NIGHT),
        ("TEXTCOLOR",     (0,0), (-1,0), WHITE),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,-1), 8),
        ("FONTNAME",      (0,1), (-1,-1), "Helvetica"),
        ("TEXTCOLOR",     (0,1), (-1,-1), BLUE_NIGHT),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, CREAM]),
        ("GRID",          (0,0), (-1,-1), 0.25, BORDER),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 5),
    ]))
    tbl_poi.wrapOn(c, W-28*mm, 200)
    tbl_poi.drawOn(c, 14*mm, y - tbl_poi._height)

# ═══════════════════════════════════════════════════════════════════════════
# PAG 3 — Occupazione stagionale
# ═══════════════════════════════════════════════════════════════════════════
def page3(c, data):
    draw_header(c, data)
    draw_footer(c, data, 3, 13)
    y = H - 22*mm

    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Occupazione stagionale")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y, "Andamento mensile stimato - prezzi e tassi di riempimento")
    y -= 6*mm

    occ = data["occupazione"]
    header_half = ["Mese", "Occup.", "EUR/notte", "Stage"]
    data_sx, data_dx = [], []
    for i in range(6):
        l, r = occ[i], occ[i+6]
        data_sx.append([l[0], f"{l[1]}%", f"EUR {l[2]}", l[3]])
        data_dx.append([r[0], f"{r[1]}%", f"EUR {r[2]}", r[3]])

    gap = 5*mm
    half = (W - 28*mm - gap) / 2
    col_w_half = [half*0.20, half*0.24, half*0.32, half*0.24]

    def make_half_style(data_rows):
        style = [
            ("BACKGROUND",    (0,0), (-1,0), BLUE_NIGHT),
            ("TEXTCOLOR",     (0,0), (-1,0), WHITE),
            ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",      (0,0), (-1,-1), 7.5),
            ("FONTNAME",      (0,1), (-1,-1), "Helvetica"),
            ("TEXTCOLOR",     (0,1), (-1,-1), BLUE_NIGHT),
            ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, CREAM]),
            ("GRID",          (0,0), (-1,-1), 0.25, BORDER),
            ("TOPPADDING",    (0,0), (-1,-1), 3.5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 3.5),
            ("LEFTPADDING",   (0,0), (-1,-1), 4),
            ("ALIGN",         (1,0), (-1,-1), "CENTER"),
            ("BACKGROUND",    (0,1), (0,-1),  HexColor("#E3F2FA")),
            ("TEXTCOLOR",     (0,1), (0,-1),  BLUE_PRIMARY),
            ("FONTNAME",      (0,1), (0,-1),  "Helvetica-Bold"),
        ]
        for ri, row in enumerate(data_rows):
            sc = stage_color(row[3])
            style.append(("TEXTCOLOR", (3, ri+1), (3, ri+1), sc))
            style.append(("FONTNAME",  (3, ri+1), (3, ri+1), "Helvetica-Bold"))
            if row[3] in ("Peak", "Alta"):
                style.append(("TEXTCOLOR", (1, ri+1), (1, ri+1), sc))
                style.append(("FONTNAME",  (1, ri+1), (1, ri+1), "Helvetica-Bold"))
        return style

    tbl_sx = Table([header_half] + data_sx, colWidths=col_w_half)
    tbl_sx.setStyle(TableStyle(make_half_style(data_sx)))
    tbl_sx.wrapOn(c, half, 300)
    tbl_dx = Table([header_half] + data_dx, colWidths=col_w_half)
    tbl_dx.setStyle(TableStyle(make_half_style(data_dx)))
    tbl_dx.wrapOn(c, half, 300)
    tbl_h = max(tbl_sx._height, tbl_dx._height)
    tbl_sx.drawOn(c, 14*mm, y - tbl_h)
    tbl_dx.drawOn(c, 14*mm + half + gap, y - tbl_h)
    y -= tbl_h + 5*mm

    # Grafico
    graph_h = 62*mm
    graph_w = W - 28*mm
    gx, gy = 14*mm, y - graph_h
    c.setFillColor(WHITE)
    c.rect(gx, gy, graph_w, graph_h, fill=1, stroke=0)
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.3)
    c.rect(gx, gy, graph_w, graph_h, fill=0, stroke=1)

    legend_items = [("Bassa", MUTED), ("Media", BLUE_PRIMARY), ("Alta stagione", TEAL), ("Peak", GOLD)]
    lx = gx + 3*mm
    for lbl, col in legend_items:
        c.setFillColor(col)
        c.circle(lx + 1.5*mm, gy + graph_h - 4*mm, 1.5*mm, fill=1, stroke=0)
        c.setFont("Helvetica", 6.5)
        c.setFillColor(MUTED)
        c.drawString(lx + 4*mm, gy + graph_h - 5*mm, lbl)
        lx += c.stringWidth(lbl, "Helvetica", 6.5) + 10*mm

    rates = [o[1] for o in occ]
    min_r, max_r = 45, 95
    for pct in [50, 60, 70, 80, 90]:
        py_line = gy + 8*mm + ((pct - min_r) / (max_r - min_r)) * (graph_h - 18*mm)
        c.setStrokeColor(BORDER)
        c.setLineWidth(0.25)
        c.line(gx + 4*mm, py_line, gx + graph_w - 2*mm, py_line)
        c.setFont("Helvetica", 5.5)
        c.setFillColor(MUTED)
        c.drawString(gx + 0.5*mm, py_line - 1.5*mm, f"{pct}%")

    step = (graph_w - 8*mm) / 11
    points = []
    for i, (mese, occ_rate, eur, stage) in enumerate(occ):
        px_dot = gx + 4*mm + i * step
        py_dot = gy + 8*mm + ((occ_rate - min_r) / (max_r - min_r)) * (graph_h - 18*mm)
        points.append((px_dot, py_dot, stage, occ_rate, eur, mese))

    c.setStrokeColor(TEAL)
    c.setLineWidth(1.5)
    p = c.beginPath()
    p.moveTo(points[0][0], points[0][1])
    for pt in points[1:]:
        p.lineTo(pt[0], pt[1])
    c.drawPath(p, stroke=1, fill=0)

    for px_dot, py_dot, stage, rate, eur, mese in points:
        col = stage_color(stage)
        c.setFillColor(col)
        r = 2.5*mm if stage == "Peak" else 1.8*mm
        c.circle(px_dot, py_dot, r, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 6)
        c.setFillColor(BLUE_NIGHT)
        c.drawCentredString(px_dot, py_dot + 3*mm, f"{rate}%")
        c.setFont("Helvetica", 6)
        c.setFillColor(BLUE_NIGHT)
        c.drawCentredString(px_dot, gy + 4*mm, mese)
        c.setFont("Helvetica", 5.5)
        c.setFillColor(MUTED)
        c.drawCentredString(px_dot, gy + 1*mm, f"EUR {eur}")

# ═══════════════════════════════════════════════════════════════════════════
# PAG 4 — Analisi economica
# ═══════════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════
# PAG 4 — Manutenzione / Ristrutturazione
# ═══════════════════════════════════════════════════════════════════════════
def page4_manutenzione(c, data):
    draw_header(c, data)
    draw_footer(c, data, 5, 13)
    y = H - 22*mm

    tipo = data["intervento_tipo"]
    importo = data["intervento_importo"]
    mesi = data["intervento_mesi"]
    mensile = data["intervento_mensile"]

    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Interventi sull’immobile — impatto su costi e valore")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y, "Costi di manutenzione o ristrutturazione dichiarati · impatto mensile sul profitto netto")
    y -= 8*mm

    if tipo == "nessuno":
        # Box verde: nessun intervento
        box_h = 16*mm
        c.setFillColor(TEAL_LIGHT)
        c.roundRect(14*mm, y - box_h, W - 28*mm, box_h, 3*mm, fill=1, stroke=0)
        c.setStrokeColor(TEAL)
        c.setLineWidth(0.8)
        c.roundRect(14*mm, y - box_h, W - 28*mm, box_h, 3*mm, fill=0, stroke=1)
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(TEAL)
        c.drawCentredString(W/2, y - 7*mm, "✓  Nessun intervento dichiarato — immobile pronto all’uso")
        c.setFont("Helvetica", 8)
        c.setFillColor(MUTED)
        c.drawCentredString(W/2, y - 12*mm, "Questa sezione non impatta il calcolo del profitto netto né il valore dell’immobile")
        y -= box_h + 8*mm
    else:
        # Determina colori e label per tipo intervento
        if tipo == "manutenzione":
            col = BLUE_PRIMARY
            bg = HexColor("#E3F2FA")
            label_tipo = "🛋️  Manutenzione"
            range_label = "€ 100 – € 5.000"
            anni_max = "3 anni"
        else:
            col = GOLD
            bg = GOLD_LIGHT
            label_tipo = "🏗️  Ristrutturazione"
            range_label = "€ 5.000 – € 50.000"
            anni_max = "10 anni"

        # 3 card affiancate: tipo, importo, impatto mensile
        cw = (W - 34*mm) / 3
        ch = 20*mm
        cards = [
            ("Tipo di intervento", label_tipo, col, bg),
            ("Importo totale", f"€ {importo:,}".replace(",","."), BLUE_NIGHT, CREAM),
            ("Impatto mensile sul profitto", f"- € {mensile:,}".replace(",","."), RED, RED_LIGHT),
        ]
        cx = 14*mm
        for lbl, val, tc, cbg in cards:
            c.setFillColor(cbg)
            c.roundRect(cx, y - ch, cw, ch, 2*mm, fill=1, stroke=0)
            c.setStrokeColor(tc)
            c.setLineWidth(0.8)
            c.roundRect(cx, y - ch, cw, ch, 2*mm, fill=0, stroke=1)
            c.setFont("Helvetica", 7)
            c.setFillColor(MUTED)
            c.drawCentredString(cx + cw/2, y - 5*mm, lbl)
            c.setFont("Helvetica-Bold", 11)
            c.setFillColor(tc)
            c.drawCentredString(cx + cw/2, y - 13*mm, val)
            cx += cw + 3*mm
        y -= ch + 8*mm

        # Tabella dettaglio diluizione
        y = draw_section_header(c, 14*mm, y, W - 28*mm, "Dettaglio diluizione nel tempo")
        y -= 5*mm

        anni = mesi / 12
        int_data = [
            ["Voce", "Dettaglio", "Valore"],
            ["Tipo di intervento", label_tipo, ""],
            ["Importo totale dichiarato",
             f"Costo stimato per l’intervento sull’immobile · Range: {range_label}",
             f"€ {importo:,}".replace(",",".")],
            ["Periodo di ammortamento",
             f"Diluito su {mesi} mesi ({anni:.1f} anni) · Max previsto: {anni_max}",
             f"{mesi} mesi"],
            ["Costo mensile da sottrarre",
             f"€ {importo:,} / {mesi} mesi = € {mensile:,}/mese".replace(",","."),
             f"- € {mensile:,}".replace(",",".")],
            ["Impatto annuale sul profitto",
             f"€ {mensile:,}/mese × 12 mesi".replace(",","."),
             f"- € {mensile*12:,}".replace(",",".")],
            ["Profitto netto DOPO intervento",
             f"€ {data['profitto_netto']:,} - € {mensile*12:,} = nel periodo di diluizione".replace(",","."),
             f"€ {data['profitto_netto'] - mensile*12:,}".replace(",",".")],
        ]

        col_w_int = [(W-28*mm)*0.30, (W-28*mm)*0.50, (W-28*mm)*0.20]
        tbl_int = Table(int_data, colWidths=col_w_int)
        style_int = [
            ("BACKGROUND",    (0,0),  (-1,0),  BLUE_NIGHT),
            ("TEXTCOLOR",     (0,0),  (-1,0),  WHITE),
            ("FONTNAME",      (0,0),  (-1,0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0,0),  (-1,-1), 7.5),
            ("FONTNAME",      (0,1),  (-1,-1), "Helvetica"),
            ("TEXTCOLOR",     (0,1),  (-1,-1), BLUE_NIGHT),
            ("ROWBACKGROUNDS",(0,1),  (-1,-1), [WHITE, CREAM]),
            ("GRID",          (0,0),  (-1,-1), 0.25, BORDER),
            ("TOPPADDING",    (0,0),  (-1,-1), 4),
            ("BOTTOMPADDING", (0,0),  (-1,-1), 4),
            ("LEFTPADDING",   (0,0),  (-1,-1), 5),
            ("ALIGN",         (2,0),  (2,-1),  "RIGHT"),
            ("BACKGROUND",    (0,1),  (0,-1),  HexColor("#E3F2FA")),
            ("TEXTCOLOR",     (0,1),  (0,-1),  BLUE_PRIMARY),
            ("FONTNAME",      (0,1),  (0,-1),  "Helvetica-Bold"),
            ("TEXTCOLOR",     (2,3),  (2,3),   RED),
            ("TEXTCOLOR",     (2,4),  (2,4),   RED),
            ("FONTNAME",      (2,3),  (2,4),   "Helvetica-Bold"),
            ("BACKGROUND",    (0,6),  (-1,6),  TEAL_LIGHT),
            ("TEXTCOLOR",     (0,6),  (-1,6),  TEAL),
            ("FONTNAME",      (0,6),  (-1,6),  "Helvetica-Bold"),
            ("TEXTCOLOR",     (2,5),  (2,5),   RED),
            ("FONTNAME",      (2,5),  (2,5),   "Helvetica-Bold"),
        ]
        tbl_int.setStyle(TableStyle(style_int))
        tbl_int.wrapOn(c, W-28*mm, 300)
        tbl_int.drawOn(c, 14*mm, y - tbl_int._height)
        y -= tbl_int._height + 8*mm

        # Nota impatto su valore asset
        y = draw_section_header(c, 14*mm, y, W - 28*mm, "Impatto sul valore dell’immobile come asset")
        y -= 5*mm

        if tipo == "ristrutturazione":
            nota_asset = (
                f"Una ristrutturazione di € {importo:,} impatta il valore dell’immobile in due modi opposti: ".replace(",",".") +
                "nel breve termine riduce il profitto netto disponibile durante il periodo di ammortamento; "
                "nel medio-lungo termine aumenta il valore di mercato dell’immobile e il potenziale di reddito B&B "
                "grazie a prezzi per notte più alti e maggiore attrattività per gli ospiti. "
                "Il valore asset calcolato nelle pagine successive tiene conto del capex come voce separata."
            )
        else:
            nota_asset = (
                f"Un intervento di manutenzione di € {importo:,} ha impatto limitato sul valore di mercato dell’immobile ".replace(",",".") +
                "ma migliora la qualità percepita dagli ospiti, contribuendo a mantenere o aumentare il rating sulle piattaforme. "
                "L’impatto economico è principalmente sul profitto netto nel periodo di diluizione dichiarato."
            )

        wrap_simple(c, nota_asset, 14*mm, y, W-28*mm, "Helvetica", 8, 5.5*mm, BLUE_NIGHT)
        y -= 18*mm

    # ── COSTI OPZIONALI ──
    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Costi opzionali — impatto sul profitto netto")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y, "Non obbligatori \u00b7 si sottraggono al profitto netto se presenti")
    y -= 6*mm

    profitto  = data["profitto_netto"]
    ricavo_lordo = data["ricavo_lordo"]
    pm_bassa  = data["pm_perc_bassa"]
    pm_alta   = data["pm_perc_alta"]
    has_pm    = data["property_manager"]
    has_int   = data["intervento_tipo"] != "nessuno"
    mens      = data["intervento_mensile"]
    costo_int_anno = mens * 12 if has_int else 0
    costo_pm_medio = int(ricavo_lordo * (pm_bassa + pm_alta) / 2 / 100) if has_pm else 0

    def opt_val(presente, val_str, zero_str="€ 0  (non previsto)"):
        return val_str if presente else zero_str

    pm_det = opt_val(has_pm,
        f"\u20ac {ricavo_lordo:,} x {pm_bassa}-{pm_alta}% = \u20ac {int(ricavo_lordo*pm_bassa/100):,} \u2013 \u20ac {int(ricavo_lordo*pm_alta/100):,} / anno *".replace(",","."))
    pm_val = opt_val(has_pm,
        f"- \u20ac {int(ricavo_lordo*pm_bassa/100):,} / {int(ricavo_lordo*pm_alta/100):,}".replace(",","."))
    int_det = opt_val(has_int,
        f"\u20ac {mens:,}/mese x 12 = \u20ac {costo_int_anno:,} / anno".replace(",","."))
    int_val = opt_val(has_int,
        f"- \u20ac {costo_int_anno:,}".replace(",","."))

    prof_basso = profitto - (int(ricavo_lordo*pm_bassa/100) if has_pm else 0) - costo_int_anno
    prof_alto  = profitto - (int(ricavo_lordo*pm_alta/100)  if has_pm else 0) - costo_int_anno

    opt_data = [
        ["Voce opzionale", "Dettaglio calcolo", "Costo annuale"],
        ["Property Manager * (15%-20% ricavi)", pm_det, pm_val],
        ["Manutenzione / Ristrutturazione",     int_det, int_val],
        ["PROFITTO con tutti gli opzionali (scenario basso)",
         f"Profitto \u20ac {profitto:,} - PM {pm_bassa}% - intervento".replace(",","."),
         f"\u20ac {prof_basso:,}".replace(",",".")],
        ["PROFITTO con tutti gli opzionali (scenario alto)",
         f"Profitto \u20ac {profitto:,} - PM {pm_alta}% - intervento".replace(",","."),
         f"\u20ac {prof_alto:,}".replace(",",".")],
    ]

    col_w_opt = [(W-28*mm)*0.42, (W-28*mm)*0.40, (W-28*mm)*0.18]
    tbl_opt = Table(opt_data, colWidths=col_w_opt)
    style_opt = [
        ("BACKGROUND",    (0,0),  (-1,0),  BLUE_NIGHT),
        ("TEXTCOLOR",     (0,0),  (-1,0),  WHITE),
        ("FONTNAME",      (0,0),  (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),  (-1,-1), 7.5),
        ("FONTNAME",      (0,1),  (-1,-1), "Helvetica"),
        ("TEXTCOLOR",     (0,1),  (-1,-1), BLUE_NIGHT),
        ("ROWBACKGROUNDS",(0,1),  (-1,2),  [WHITE, CREAM]),
        ("GRID",          (0,0),  (-1,-1), 0.25, BORDER),
        ("TOPPADDING",    (0,0),  (-1,-1), 4),
        ("BOTTOMPADDING", (0,0),  (-1,-1), 4),
        ("LEFTPADDING",   (0,0),  (-1,-1), 5),
        ("ALIGN",         (2,0),  (2,-1),  "RIGHT"),
        ("BACKGROUND",    (0,1),  (0,-1),  HexColor("#E3F2FA")),
        ("TEXTCOLOR",     (0,1),  (0,-1),  BLUE_PRIMARY),
        ("FONTNAME",      (0,1),  (0,-1),  "Helvetica-Bold"),
        ("TEXTCOLOR",     (2,1),  (2,2),   RED if has_pm or has_int else MUTED),
        ("FONTNAME",      (2,1),  (2,2),   "Helvetica-Bold"),
        ("BACKGROUND",    (0,3),  (-1,3),  HexColor("#E3F2FA")),
        ("TEXTCOLOR",     (0,3),  (-1,3),  BLUE_NIGHT),
        ("FONTNAME",      (0,3),  (-1,3),  "Helvetica-Bold"),
        ("BACKGROUND",    (0,4),  (-1,4),  HexColor("#E3F2FA")),
        ("TEXTCOLOR",     (0,4),  (-1,4),  BLUE_NIGHT),
        ("FONTNAME",      (0,4),  (-1,4),  "Helvetica-Bold"),
    ]
    tbl_opt.setStyle(TableStyle(style_opt))
    tbl_opt.wrapOn(c, W-28*mm, 300)
    tbl_opt.drawOn(c, 14*mm, y - tbl_opt._height)
    y -= tbl_opt._height + 4*mm

    # Asterisco PM
    c.setFont("Helvetica-Oblique", 7)
    c.setFillColor(MUTED)
    c.drawString(14*mm, y, "* Property Manager: professionista o agenzia che gestisce l'immobile per conto del proprietario (check-in, pulizie, comunicazioni ospiti, pricing).")
    y -= 4.5*mm
    c.drawString(14*mm, y, "  Il costo standard di mercato varia tra il 15% e il 20% dei ricavi lordi. \u00c8 una scelta opzionale: molti host gestiscono in autonomia.")

# ═══════════════════════════════════════════════════════════════════════════
# PAG 4 — Analisi economica annuale
# ═══════════════════════════════════════════════════════════════════════════
def page4(c, data):
    draw_header(c, data)
    draw_footer(c, data, 4, 13)
    y = H - 22*mm

    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Analisi economica annuale")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y, "Proiezione costi e ricavi basata sulla situazione dichiarata")
    y -= 6*mm

    p = data["prezzo_notte_stimato"]
    occ_pct = data["occupazione_percent"]
    notti = data["notti_anno"]
    comm_pct = data["costi_commissioni_pct"]
    pulizia_unit = data["costi_pulizie_unit"]
    rata_mutuo = data["rata_mutuo_mensile"]
    mutuo_annuo = rata_mutuo * 12
    adr = data["adr"]
    revpar = data["revpar"]
    ffe = data["ffe_reserve"]

    # 4 card dati principali situazione dichiarata
    sit_label = "Immobile vuoto" if data["situazione_vuoto"] else ("B&B attivo" if data["situazione_bnb"] else "Con inquilini")
    sit_cards = [
        ("Situazione",           sit_label,  BLUE_PRIMARY, HexColor("#E3F2FA")),
        ("Prezzo stimato/notte", f"\u20ac {p}",  TEAL,         TEAL_LIGHT),
        ("Occupazione stimata",  f"{occ_pct}%",  GOLD,         GOLD_LIGHT),
        ("Notti/anno stimate",   f"{notti}",     BLUE_NIGHT,   CREAM),
    ]
    card_h = 16*mm
    card_w = (W - 34*mm) / 4
    cx = 14*mm
    for lbl, val, tc, bg in sit_cards:
        c.setFillColor(bg)
        c.roundRect(cx, y - card_h, card_w, card_h, 2*mm, fill=1, stroke=0)
        c.setStrokeColor(tc)
        c.setLineWidth(0.8)
        c.roundRect(cx, y - card_h, card_w, card_h, 2*mm, fill=0, stroke=1)
        c.setFont("Helvetica", 6.5)
        c.setFillColor(MUTED)
        c.drawCentredString(cx + card_w/2, y - 4.5*mm, lbl)
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(tc)
        c.drawCentredString(cx + card_w/2, y - 11*mm, val)
        cx += card_w + 2*mm
    y -= card_h + 5*mm

    eco_data = [
        ["Voce", "Come viene calcolato", "Valore"],
        ["RICAVI", "", ""],
        ["Ricavo lordo annuo stimato",
         f"€ {p}/notte  x  {occ_pct}% occ.  x  365gg  =  € {p}  x  {notti} notti",
         fmt_eu(data["ricavo_lordo"])],
        ["Bonus prenotazioni dirette",
         f"€ {data['ricavo_lordo']:,}  x  {data['bonus_dirette_pct']}  =  € {data['bonus_dirette']:,}".replace(",","."),
         fmt_eu(data["bonus_dirette"])],
        ["TOTALE RICAVI",
         f"{fmt_eu(data['ricavo_lordo'])}  +  {fmt_eu(data['bonus_dirette'])}",
         fmt_eu(data["totale_ricavi"])],
        ["COSTI VARIABILI", "", ""],
        ["Commissioni piattaforma Airbnb",
         f"€ {data['ricavo_lordo']:,}  x  {comm_pct}%  =  € {data['costi_commissioni']:,}".replace(",","."),
         f"- {fmt_eu(data['costi_commissioni'])}"],
        ["Pulizie per cambio ospite",
         f"€ {pulizia_unit}/cambio  x  {notti} notti  =  € {data['costi_pulizie']:,}".replace(",","."),
         f"- {fmt_eu(data['costi_pulizie'])}"],
        ["Biancheria e consumabili",
         f"Range € 300-700/anno  |  conv. adottata: € {data['costi_biancheria']:,}".replace(",","."),
         f"- {fmt_eu(data['costi_biancheria'])}"],
        ["Utenze aggiuntive stimate",
         f"Range € 500-1.000/anno  |  conv. adottata: € {data['costi_utenze']:,}".replace(",","."),
         f"- {fmt_eu(data['costi_utenze'])}"],
        ["Manutenzione ordinaria",
         f"Range € 200-600/anno  |  conv. adottata: € {data['costi_manutenzione']:,}".replace(",","."),
         f"- {fmt_eu(data['costi_manutenzione'])}"],
        ["FF&E Reserve (manutenzione straord.)",
         f"Fondo manutenzione straordinaria  |  conv. adottata: € {ffe:,}".replace(",","."),
         f"- {fmt_eu(ffe)}"],
        ["Rata mutuo (se presente)",
         "Nessun mutuo dichiarato" if not data["mutuo_attivo"] else f"€ {rata_mutuo}/mese  x  12 mesi",
         "€ 0" if not data["mutuo_attivo"] else f"- {fmt_eu(mutuo_annuo)}"],
        ["TOTALE COSTI VARIABILI",
         f"{fmt_eu(data['costi_commissioni'])} + {fmt_eu(data['costi_pulizie'])} + {fmt_eu(data['costi_biancheria'])} + {fmt_eu(data['costi_utenze'])} + {fmt_eu(data['costi_manutenzione'])} + {fmt_eu(ffe)}",
         f"- {fmt_eu(data['totale_costi'])}"],
        ["PROFITTO NETTO STIMATO",
         f"{fmt_eu(data['totale_ricavi'])}  -  {fmt_eu(data['totale_costi'])}",
         fmt_eu(data["profitto_netto"])],
        ["Margine netto su ricavi lordi",
         f"{fmt_eu(data['profitto_netto'])}  /  {fmt_eu(data['totale_ricavi'])}  x  100",
         f"{data['margine_percent']}%"],
        ["KPI — ADR (Average Daily Rate)",
         f"Ricavo lordo  /  Notti occupate  =  € {data['ricavo_lordo']:,}  /  {notti}".replace(",","."),
         f"€ {adr}"],
        ["KPI — RevPAR",
         f"ADR  x  Occupazione%  =  \u20ac {adr}  x  {occ_pct}%",
         f"\u20ac {revpar}"],
    ]


    col_w_eco = [(W-28*mm)*0.30, (W-28*mm)*0.50, (W-28*mm)*0.20]
    tbl_eco = Table(eco_data, colWidths=col_w_eco)
    style_eco = [
        ("BACKGROUND",    (0,0),  (-1,0),  BLUE_NIGHT),
        ("TEXTCOLOR",     (0,0),  (-1,0),  WHITE),
        ("FONTNAME",      (0,0),  (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),  (-1,-1), 7.5),
        ("FONTNAME",      (0,1),  (-1,-1), "Helvetica"),
        ("TEXTCOLOR",     (0,1),  (-1,-1), BLUE_NIGHT),
        ("ROWBACKGROUNDS",(0,2),  (-1,4),  [WHITE, CREAM]),
        ("ROWBACKGROUNDS",(0,6),  (-1,13), [WHITE, CREAM]),
        ("GRID",          (0,0),  (-1,-1), 0.25, BORDER),
        ("TOPPADDING",    (0,0),  (-1,-1), 3),
        ("BOTTOMPADDING", (0,0),  (-1,-1), 3),
        ("LEFTPADDING",   (0,0),  (-1,-1), 5),
        ("ALIGN",         (2,0),  (2,-1),  "RIGHT"),
        ("BACKGROUND",    (0,1),  (-1,1),  TEAL_LIGHT),
        ("TEXTCOLOR",     (0,1),  (0,1),   TEAL),
        ("FONTNAME",      (0,1),  (0,1),   "Helvetica-Bold"),
        ("BACKGROUND",    (0,4),  (-1,4),  TEAL_LIGHT),
        ("TEXTCOLOR",     (0,4),  (-1,4),  TEAL),
        ("FONTNAME",      (0,4),  (-1,4),  "Helvetica-Bold"),
        ("BACKGROUND",    (0,5),  (-1,5),  RED_LIGHT),
        ("TEXTCOLOR",     (0,5),  (0,5),   RED),
        ("FONTNAME",      (0,5),  (0,5),   "Helvetica-Bold"),
        ("TEXTCOLOR",     (2,6),  (2,13),  RED),
        ("TEXTCOLOR",     (2,13), (2,13),  MUTED if not data["mutuo_attivo"] else RED),
        ("BACKGROUND",    (0,13), (-1,13), RED_LIGHT),
        ("TEXTCOLOR",     (0,13), (-1,13), RED),
        ("FONTNAME",      (0,13), (-1,13), "Helvetica-Bold"),
        ("BACKGROUND",    (0,14), (-1,14), TEAL_LIGHT),
        ("TEXTCOLOR",     (0,14), (-1,14), TEAL),
        ("FONTNAME",      (0,14), (-1,14), "Helvetica-Bold"),
        ("BACKGROUND",    (0,15), (-1,15), TEAL_LIGHT),
        ("TEXTCOLOR",     (0,15), (-1,15), TEAL),
        ("FONTNAME",      (0,15), (-1,15), "Helvetica-Bold"),
        ("BACKGROUND",    (0,16), (-1,16), GOLD_LIGHT),
        ("TEXTCOLOR",     (0,16), (-1,16), GOLD),
        ("FONTNAME",      (0,16), (-1,16), "Helvetica-Bold"),
        ("BACKGROUND",    (0,17), (-1,17), GOLD_LIGHT),
        ("TEXTCOLOR",     (0,17), (-1,17), GOLD),
        ("FONTNAME",      (0,17), (-1,17), "Helvetica-Bold"),
    ]
    tbl_eco.setStyle(TableStyle(style_eco))
    tbl_eco.wrapOn(c, W-28*mm, 600)
    tbl_eco.drawOn(c, 14*mm, y - tbl_eco._height)
    y -= tbl_eco._height + 5*mm

    # 4 card: margine grigio, ricavo verde, costi rosso, guadagno gold (più grande)
    total_w = W - 28*mm
    small_w = (total_w - 6*mm) * 0.26
    big_w   = total_w - 3*small_w - 6*mm
    small_h = 18*mm
    big_h   = 24*mm

    cards4 = [
        ("Margine netto",          f"{data['margine_percent']}%",          WHITE,      BLUE_NIGHT, small_w, small_h),
        ("Ricavo lordo stimato",   fmt_eur(data["ricavo_lordo"]),           TEAL_LIGHT, TEAL,       small_w, small_h),
        ("Costi variabili totali", f"- {fmt_eur(data['totale_costi'])}",   RED_LIGHT,  RED,        small_w, small_h),
        ("Il tuo guadagno stimato",fmt_eur(data["profitto_netto"]),         GOLD_LIGHT, GOLD,       big_w,   big_h),
    ]
    cx = 14*mm
    for lbl, val, bg, tc, cw, ch in cards4:
        is_gold = (tc == GOLD)
        cy = y - big_h + (big_h - ch) / 2
        if is_gold:
            cy = y - big_h
        c.setFillColor(bg)
        c.roundRect(cx, cy, cw, ch, 2*mm, fill=1, stroke=0)
        c.setStrokeColor(GOLD if is_gold else HexColor("#C8C8C8"))
        c.setLineWidth(1.5 if is_gold else 0.5)
        c.roundRect(cx, cy, cw, ch, 2*mm, fill=0, stroke=1)
        lbl_size = 8 if is_gold else 7
        c.setFont("Helvetica-Bold" if is_gold else "Helvetica", lbl_size)
        c.setFillColor(GOLD if is_gold else MUTED)
        c.drawCentredString(cx + cw/2, cy + ch - 5*mm, lbl)
        val_y = y - big_h + (big_h - small_h)/2 + small_h/2 - 4*mm
        c.setFont("Helvetica-Bold", 14 if is_gold else 12)
        c.setFillColor(tc)
        c.drawCentredString(cx + cw/2, val_y, val)
        cx += cw + 2*mm
    y -= big_h

# ═══════════════════════════════════════════════════════════════════════════
# PAG 5 — Pricing mese per mese
# ═══════════════════════════════════════════════════════════════════════════
def page5(c, data):
    draw_header(c, data)
    draw_footer(c, data, 6, 13)
    y = H - 22*mm

    # ── CONFRONTO AFFITTO TRADIZIONALE ──
    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Confronto con affitto tradizionale")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y, "Proiezione annuale · affitto tradizionale vs B&B short rent")
    y -= 6*mm

    conf_data = [
        ["", "Affitto tradizionale", "B&B / Short rent", "Differenza"],
        ["Ricavo annuo lordo",
         fmt_eu(data["affitto_ricavo"]), fmt_eu(data["ricavo_lordo"]),
         f"+{fmt_eu(data['ricavo_lordo'] - data['affitto_ricavo'])}"],
        ["Costi di gestione",
         fmt_eu(data["affitto_costi"]), fmt_eu(data["totale_costi"]), "--"],
        ["Profitto netto",
         fmt_eu(data["affitto_profitto"]), fmt_eu(data["profitto_netto"]),
         f"+{fmt_eu(data['profitto_netto'] - data['affitto_profitto'])}"],
        ["Flessibilit\u00e0 utilizzo", "Bassa", "Alta", "Molto alta"],
        ["Rischio morosit\u00e0",       "Alto",  "Nullo", "Eliminato"],
    ]
    col_w_conf = [(W-28*mm)*0.28, (W-28*mm)*0.22, (W-28*mm)*0.22, (W-28*mm)*0.28]
    tbl_conf = Table(conf_data, colWidths=col_w_conf)
    tbl_conf.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),  (-1,0),  BLUE_NIGHT),
        ("TEXTCOLOR",     (0,0),  (-1,0),  WHITE),
        ("FONTNAME",      (0,0),  (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),  (-1,-1), 8),
        ("FONTNAME",      (0,1),  (-1,-1), "Helvetica"),
        ("TEXTCOLOR",     (0,1),  (-1,-1), BLUE_NIGHT),
        ("ROWBACKGROUNDS",(0,1),  (-1,-1), [WHITE, CREAM]),
        ("GRID",          (0,0),  (-1,-1), 0.25, BORDER),
        ("TOPPADDING",    (0,0),  (-1,-1), 4),
        ("BOTTOMPADDING", (0,0),  (-1,-1), 4),
        ("LEFTPADDING",   (0,0),  (-1,-1), 5),
        ("TEXTCOLOR",     (3,1),  (3,1),   TEAL), ("FONTNAME", (3,1), (3,1), "Helvetica-Bold"),
        ("TEXTCOLOR",     (3,3),  (3,3),   TEAL), ("FONTNAME", (3,3), (3,3), "Helvetica-Bold"),
        ("TEXTCOLOR",     (3,4),  (3,4),   TEAL), ("FONTNAME", (3,4), (3,4), "Helvetica-Bold"),
        ("TEXTCOLOR",     (3,5),  (3,5),   TEAL), ("FONTNAME", (3,5), (3,5), "Helvetica-Bold"),
    ]))
    tbl_conf.wrapOn(c, W-28*mm, 300)
    tbl_conf.drawOn(c, 14*mm, y - tbl_conf._height)
    y -= tbl_conf._height + 8*mm

    # ── PRICING STAGIONALE ──
    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Piano di pricing stagionale — mese per mese")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y, "Prezzi consigliati per notte · aggiornati su dati mercato zona · in italiano e inglese")
    y -= 6*mm

    pr_data = [["Mese / Month", "Prezzo notte", "Occup.", "Ricavo stimato", "Evento / Note"]]
    for mese_it, mese_en, prezzo, occ_p, ricavo, evento in data["pricing_mensile"]:
        pr_data.append([
            f"{mese_it} / {mese_en}",
            f"\u20ac {prezzo}",
            f"{occ_p}%",
            f"\u20ac {ricavo:,}".replace(",","."),
            evento,
        ])

    # Totali
    tot_ricavo = sum(r[4] for r in data["pricing_mensile"])
    pr_data.append(["TOTALE ANNUO", "", "", f"\u20ac {tot_ricavo:,}".replace(",","."), "Scenario ottimistico"])

    col_w_pr = [(W-28*mm)*0.20, (W-28*mm)*0.13, (W-28*mm)*0.09, (W-28*mm)*0.15, (W-28*mm)*0.43]
    tbl_pr = Table(pr_data, colWidths=col_w_pr)

    style_pr = [
        ("BACKGROUND",    (0,0),  (-1,0),  BLUE_NIGHT),
        ("TEXTCOLOR",     (0,0),  (-1,0),  WHITE),
        ("FONTNAME",      (0,0),  (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),  (-1,-1), 7.5),
        ("FONTNAME",      (0,1),  (-1,-2), "Helvetica"),
        ("TEXTCOLOR",     (0,1),  (-1,-2), BLUE_NIGHT),
        ("ROWBACKGROUNDS",(0,1),  (-1,-2), [WHITE, CREAM]),
        ("GRID",          (0,0),  (-1,-1), 0.25, BORDER),
        ("TOPPADDING",    (0,0),  (-1,-1), 3.5),
        ("BOTTOMPADDING", (0,0),  (-1,-1), 3.5),
        ("LEFTPADDING",   (0,0),  (-1,-1), 4),
        ("ALIGN",         (1,0),  (3,-1),  "CENTER"),
        # Mese in azzurro
        ("BACKGROUND",    (0,1),  (0,-2),  HexColor("#E3F2FA")),
        ("TEXTCOLOR",     (0,1),  (0,-2),  BLUE_PRIMARY),
        ("FONTNAME",      (0,1),  (0,-2),  "Helvetica-Bold"),
        # Riga totale
        ("BACKGROUND",    (0,-1), (-1,-1), BLUE_NIGHT),
        ("TEXTCOLOR",     (0,-1), (-1,-1), WHITE),
        ("FONTNAME",      (0,-1), (-1,-1), "Helvetica-Bold"),
    ]

    # Colori Peak e Alta sulla colonna occupazione
    for ri, row in enumerate(data["pricing_mensile"]):
        occ_p = row[3]
        if occ_p >= 80:
            style_pr.append(("TEXTCOLOR", (2, ri+1), (2, ri+1), GOLD if occ_p >= 85 else TEAL))
            style_pr.append(("FONTNAME",  (2, ri+1), (2, ri+1), "Helvetica-Bold"))

    tbl_pr.setStyle(TableStyle(style_pr))
    tbl_pr.wrapOn(c, W-28*mm, 500)
    tbl_pr.drawOn(c, 14*mm, y - tbl_pr._height)
    y -= tbl_pr._height + 8*mm

    # Nota ADR
    c.setFont("Helvetica-Oblique", 7.5)
    c.setFillColor(MUTED)
    adr = data["adr"]
    revpar = data["revpar"]
    nota_pr = f"ADR (Average Daily Rate) ponderato annuo: \u20ac {adr}  \u00b7  RevPAR: \u20ac {revpar}  \u00b7  I prezzi si aggiornano automaticamente in base ai dati di mercato della zona al momento della generazione del report."
    wrap_simple(c, nota_pr, 14*mm, y, W-28*mm, "Helvetica-Oblique", 7, 4.5*mm, MUTED)

# ═══════════════════════════════════════════════════════════════════════════
# PAG 6 — Normativa affitti brevi
# ═══════════════════════════════════════════════════════════════════════════
def page6(c, data):
    draw_header(c, data)
    draw_footer(c, data, 9, 13)
    y = H - 22*mm

    y = draw_section_header(c, 14*mm, y, W - 28*mm,
        f"Normativa affitti brevi — {data['comune_normativa']} / {data['regione_normativa']} \u00b7 2025")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y, "Obblighi normativi vigenti alla data di generazione del report")
    y -= 6*mm

    norm_data = [["Obbligo / Voce", "Dettaglio", "Stato"]]
    for voce, dettaglio, stato in data["normativa_extra"]:
        norm_data.append([voce, dettaglio, stato])

    col_w_norm = [(W-28*mm)*0.28, (W-28*mm)*0.52, (W-28*mm)*0.20]
    tbl_norm = Table(norm_data, colWidths=col_w_norm)
    tbl_norm.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), BLUE_NIGHT),
        ("TEXTCOLOR",     (0,0), (-1,0), WHITE),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,-1), 7),
        ("FONTNAME",      (0,1), (-1,-1), "Helvetica"),
        ("TEXTCOLOR",     (0,1), (-1,-1), BLUE_NIGHT),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, CREAM]),
        ("GRID",          (0,0), (-1,-1), 0.25, BORDER),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 5),
        ("WORDWRAP",      (0,0), (-1,-1), True),
        ("BACKGROUND",    (0,1), (0,-1), HexColor("#E3F2FA")),
        ("TEXTCOLOR",     (0,1), (0,-1), BLUE_PRIMARY),
        ("FONTNAME",      (0,1), (0,-1), "Helvetica-Bold"),
    ]))
    tbl_norm.wrapOn(c, W-28*mm, 300)
    tbl_norm.drawOn(c, 14*mm, y - tbl_norm._height)
    y -= tbl_norm._height + 10*mm

    # Box disclaimer normativa
    disc_h = 18*mm
    c.setFillColor(GOLD_LIGHT)
    c.roundRect(14*mm, y - disc_h, W - 28*mm, disc_h, 2*mm, fill=1, stroke=0)
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.8)
    c.roundRect(14*mm, y - disc_h, W - 28*mm, disc_h, 2*mm, fill=0, stroke=1)
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(GOLD)
    c.drawString(18*mm, y - 6*mm, "\u26a0\ufe0f  Nota legale importante")
    c.setFont("Helvetica", 7.5)
    c.setFillColor(BLUE_NIGHT)
    nota_norm = ("Le informazioni normative riportate sono aggiornate alla data di generazione del report e hanno carattere orientativo. "
                 "La normativa sugli affitti brevi \u00e8 in continua evoluzione. Si raccomanda di verificare sempre con un professionista legale "
                 "o fiscale prima di avviare l\u2019attivit\u00e0.")
    wrap_simple(c, nota_norm, 18*mm, y - 11*mm, W - 40*mm, "Helvetica", 7.5, 4.5*mm, BLUE_NIGHT)

# ═══════════════════════════════════════════════════════════════════════════
# PAG 7 — Valore immobile come asset
# ═══════════════════════════════════════════════════════════════════════════
def page7(c, data):
    draw_header(c, data)
    draw_footer(c, data, 10, 13)
    y = H - 22*mm

    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Valore immobile come asset B&B — Analisi professionale")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y, "Metodologia da modello di valutazione bancaria professionale")
    y -= 7*mm

    saggio = data["saggio_capitalizzazione"]
    ebitda = data["ebitda_stimato"]
    valore = data["valore_mercato"]
    v_stimato = data["valore_immobile_stimato"]

    asset_data = [
        ["Indicatore", "Come viene calcolato", "Valore"],
        ["Profitto netto operativo (EBITDA proxy)",
         "Ricavi totali  -  Costi totali operativi",
         fmt_eu(ebitda)],
        ["Saggio di capitalizzazione",
         f"Rendimento atteso per immobili ricettivi  |  Valore applicato: {saggio}%",
         f"{saggio}%"],
        ["VALORE DI MERCATO come asset B&B",
         f"EBITDA  /  Saggio cap.  =  \u20ac {ebitda:,}  /  {saggio}%  =".replace(",","."),
         fmt_eu(valore)],
        ["Valore immobile stimato (mercato)",
         "Stima da banche dati OMI per zona e tipologia",
         fmt_eu(v_stimato)],
        ["Differenza valore asset vs mercato",
         f"{fmt_eu(valore)}  -  {fmt_eu(v_stimato)}",
         fmt_eu(valore - v_stimato) if valore > v_stimato else f"- {fmt_eu(v_stimato - valore)}"],
        ["Cap Rate effettivo",
         f"EBITDA  /  Valore mercato  x  100  =  \u20ac {ebitda:,}  /  \u20ac {v_stimato:,}  x  100".replace(",","."),
         f"{round(ebitda/v_stimato*100, 2)}%"],
        ["Rendita mensile netta stimata",
         f"Profitto netto annuo  /  12 mesi  =  \u20ac {ebitda:,}  /  12".replace(",","."),
         fmt_eu(round(ebitda/12))],
    ]

    col_w_asset = [(W-28*mm)*0.32, (W-28*mm)*0.50, (W-28*mm)*0.18]
    tbl_asset = Table(asset_data, colWidths=col_w_asset)
    style_asset = [
        ("BACKGROUND",    (0,0),  (-1,0),  BLUE_NIGHT),
        ("TEXTCOLOR",     (0,0),  (-1,0),  WHITE),
        ("FONTNAME",      (0,0),  (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),  (-1,-1), 7.5),
        ("FONTNAME",      (0,1),  (-1,-1), "Helvetica"),
        ("TEXTCOLOR",     (0,1),  (-1,-1), BLUE_NIGHT),
        ("ROWBACKGROUNDS",(0,1),  (-1,-1), [WHITE, CREAM]),
        ("GRID",          (0,0),  (-1,-1), 0.25, BORDER),
        ("TOPPADDING",    (0,0),  (-1,-1), 4),
        ("BOTTOMPADDING", (0,0),  (-1,-1), 4),
        ("LEFTPADDING",   (0,0),  (-1,-1), 5),
        ("ALIGN",         (2,0),  (2,-1),  "RIGHT"),
        ("BACKGROUND",    (0,1),  (0,-1),  HexColor("#E3F2FA")),
        ("TEXTCOLOR",     (0,1),  (0,-1),  BLUE_PRIMARY),
        ("FONTNAME",      (0,1),  (0,-1),  "Helvetica-Bold"),
        # Riga valore di mercato in evidenza
        ("BACKGROUND",    (0,3),  (-1,3),  GOLD_LIGHT),
        ("TEXTCOLOR",     (0,3),  (-1,3),  GOLD),
        ("FONTNAME",      (0,3),  (-1,3),  "Helvetica-Bold"),
        ("TEXTCOLOR",     (2,1),  (2,1),   TEAL),
        ("FONTNAME",      (2,1),  (2,1),   "Helvetica-Bold"),
    ]
    # Aggiungo WORDWRAP allo stile
    style_asset.append(("WORDWRAP", (0,0), (-1,-1), True))
    style_asset.append(("FONTSIZE", (0,0), (-1,-1), 7))
    tbl_asset.setStyle(TableStyle(style_asset))
    tbl_asset.wrapOn(c, W-28*mm, 300)
    tbl_asset.drawOn(c, 14*mm, y - tbl_asset._height)
    y -= tbl_asset._height + 6*mm

    # Glossario tecnico
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(BLUE_NIGHT)
    c.drawString(14*mm, y, "Glossario e note metodologiche")
    y -= 5*mm

    glossario = [
        ("* Saggio di capitalizzazione",
         f"Tasso percentuale ({saggio}%) che esprime il rendimento atteso dal mercato per un immobile a destinazione ricettiva. "
         "Varia in base al rischio della zona: pi\u00f9 centrale e liquido \u00e8 il mercato, pi\u00f9 basso \u00e8 il saggio. "
         "Range indicativo: 5,5%-6,5% zone prime (centri storici), 7%-9% zone periferiche o mercati meno liquidi. "
         "Pi\u00f9 basso \u00e8 il saggio, pi\u00f9 alto \u00e8 il valore dell\u2019immobile."),
        ("* Cap Rate (Capitalization Rate)",
         "Rapporto percentuale tra il reddito netto operativo annuo e il valore di mercato dell\u2019immobile. "
         "Indica la redditivit\u00e0 dell\u2019investimento: un Cap Rate del 3-5% \u00e8 nella norma per immobili residenziali "
         "in zone centrali delle grandi citt\u00e0 italiane."),
        ("* RevPAR (Revenue Per Available Room)",
         "Ricavo per unit\u00e0 disponibile: ADR moltiplicato per il tasso di occupazione. "
         "\u00c8 l\u2019indicatore chiave per confrontare la performance tra strutture ricettive diverse."),
        ("* ADR (Average Daily Rate)",
         "Prezzo medio per notte effettivamente incassato, calcolato dividendo i ricavi lordi per le notti vendute. "
         "Differisce dal prezzo di listino perch\u00e9 tiene conto di sconti, promozioni e variazioni stagionali."),
        ("* FF&E Reserve",
         "Fondo accantonamento per la manutenzione e sostituzione straordinaria di arredi, attrezzature e dotazioni "
         "(Furniture, Fixtures & Equipment). Standard del settore ricettivo professionale."),
        ("Nota privacy",
         "I valori di superficie e valore al metro quadro non sono calcolati in quanto la superficie non \u00e8 "
         "sempre disponibile al momento dell\u2019analisi. Il valore di mercato \u00e8 orientativo e non sostituisce "
         "una perizia immobiliare formale."),
    ]

    for termine, spieg in glossario:
        c.setFont("Helvetica-Bold", 7)
        c.setFillColor(BLUE_PRIMARY)
        c.drawString(14*mm, y, termine)
        y -= 4.5*mm
        y = wrap_simple(c, spieg, 18*mm, y, W-32*mm, "Helvetica", 7, 4.5*mm, MUTED)
        y -= 2*mm

# ═══════════════════════════════════════════════════════════════════════════
# PAG 8 — 3 Scenari economici
# ═══════════════════════════════════════════════════════════════════════════
def page8(c, data):
    draw_header(c, data)
    draw_footer(c, data, 7, 13)
    y = H - 22*mm

    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Tre scenari economici — proiezione annuale")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y, "Basati sui dati reali dell\u2019analisi economica · Lo scenario realistico \u00e8 il riferimento principale")
    y -= 7*mm

    scenari = [data["scenario_pess"], data["scenario_real"], data["scenario_ott"]]
    colori  = [RED, BLUE_PRIMARY, GOLD]
    bg_col  = [RED_LIGHT, HexColor("#E3F4FC"), GOLD_LIGHT]

    box_w = (W - 34*mm) / 3
    box_h = 90*mm

    for i, (sc, col, bg) in enumerate(zip(scenari, colori, bg_col)):
        bx = 14*mm + i*(box_w + 3*mm)
        by = y - box_h
        c.setFillColor(bg)
        c.roundRect(bx, by, box_w, box_h, 3*mm, fill=1, stroke=0)
        c.setStrokeColor(col)
        c.setLineWidth(1.5)
        c.roundRect(bx, by, box_w, box_h, 3*mm, fill=0, stroke=1)

        # Header
        c.setFillColor(col)
        c.roundRect(bx, by+box_h-13*mm, box_w, 13*mm, 3*mm, fill=1, stroke=0)
        c.rect(bx, by+box_h-13*mm, box_w, 6*mm, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(WHITE)
        c.drawCentredString(bx+box_w/2, by+box_h-7*mm, sc["label"])
        c.setFont("Helvetica", 7)
        c.drawCentredString(bx+box_w/2, by+box_h-11.5*mm, sc["subtitle"])

        # Dati
        righe = [
            ("Occupazione media", f"{sc['occupazione']}%"),
            ("Notti vendute",     f"{sc['notti']} / anno"),
            ("Prezzo medio notte",f"EUR {sc['prezzo_medio']}"),
            ("Ricavi lordi",      fmt_eur(sc["ricavi_lordi"])),
            ("Costi totali",      fmt_eur(sc["costi_totali"])),
            ("Profitto netto",    fmt_eur(sc["profitto_netto"])),
        ]
        dy = by + box_h - 18*mm
        for lbl, val in righe:
            c.setFont("Helvetica", 7)
            c.setFillColor(MUTED)
            c.drawString(bx+4*mm, dy, lbl)
            c.setFont("Helvetica-Bold", 8)
            c.setFillColor(col if lbl == "Profitto netto" else BLUE_NIGHT)
            c.drawRightString(bx+box_w-4*mm, dy, val)
            c.setStrokeColor(BORDER)
            c.setLineWidth(0.3)
            c.line(bx+4*mm, dy-2*mm, bx+box_w-4*mm, dy-2*mm)
            dy -= 10*mm

        # Nota
        words = sc["note"].split()
        line, ny = "", by + 8*mm
        for w in words:
            test = line + (" " if line else "") + w
            if c.stringWidth(test, "Helvetica-Oblique", 6) > box_w - 8*mm:
                c.setFont("Helvetica-Oblique", 6)
                c.setFillColor(MUTED)
                c.drawString(bx+4*mm, ny, line)
                ny -= 3.5*mm
                line = w
            else:
                line = test
        if line:
            c.setFont("Helvetica-Oblique", 6)
            c.setFillColor(MUTED)
            c.drawString(bx+4*mm, ny, line)

    y -= box_h + 8*mm

    # Confronto tabella
    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Confronto scenari — tabella riassuntiva")
    y -= 5*mm

    pess = data["scenario_pess"]
    real = data["scenario_real"]
    ott  = data["scenario_ott"]

    conf_data = [
        ["Voce", "Pessimistico", "Realistico", "Ottimistico"],
        ["Occupazione media",  f"{pess['occupazione']}%", f"{real['occupazione']}%", f"{ott['occupazione']}%"],
        ["Notti vendute/anno", str(pess["notti"]),        str(real["notti"]),         str(ott["notti"])],
        ["Prezzo medio/notte", f"EUR {pess['prezzo_medio']}", f"EUR {real['prezzo_medio']}", f"EUR {ott['prezzo_medio']}"],
        ["Ricavi lordi",       fmt_eur(pess["ricavi_lordi"]),  fmt_eur(real["ricavi_lordi"]),  fmt_eur(ott["ricavi_lordi"])],
        ["Costi totali",       fmt_eur(pess["costi_totali"]),  fmt_eur(real["costi_totali"]),  fmt_eur(ott["costi_totali"])],
        ["Profitto netto",     fmt_eur(pess["profitto_netto"]),fmt_eur(real["profitto_netto"]),fmt_eur(ott["profitto_netto"])],
    ]
    col_w_conf = [(W-28*mm)*0.28,(W-28*mm)*0.24,(W-28*mm)*0.24,(W-28*mm)*0.24]
    tbl_conf = Table(conf_data, colWidths=col_w_conf)
    tbl_conf.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),  (-1,0),  BLUE_NIGHT),
        ("TEXTCOLOR",     (0,0),  (-1,0),  WHITE),
        ("FONTNAME",      (0,0),  (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),  (-1,-1), 7.5),
        ("FONTNAME",      (0,1),  (-1,-1), "Helvetica"),
        ("TEXTCOLOR",     (0,1),  (-1,-1), BLUE_NIGHT),
        ("ROWBACKGROUNDS",(0,1),  (-1,-1), [WHITE, CREAM]),
        ("GRID",          (0,0),  (-1,-1), 0.25, BORDER),
        ("TOPPADDING",    (0,0),  (-1,-1), 3.5),
        ("BOTTOMPADDING", (0,0),  (-1,-1), 3.5),
        ("LEFTPADDING",   (0,0),  (-1,-1), 5),
        ("ALIGN",         (1,0),  (-1,-1), "CENTER"),
        ("TEXTCOLOR",     (1,-1), (1,-1),  RED),
        ("TEXTCOLOR",     (2,-1), (2,-1),  TEAL),
        ("TEXTCOLOR",     (3,-1), (3,-1),  GOLD),
        ("FONTNAME",      (1,-1), (-1,-1), "Helvetica-Bold"),
    ]))
    tbl_conf.wrapOn(c, W-28*mm, 200)
    tbl_conf.drawOn(c, 14*mm, y - tbl_conf._height)

# ═══════════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════
# PAG 9 — Piano d'azione 90 giorni
# ═══════════════════════════════════════════════════════════════════════════
def page9(c, data):
    draw_header(c, data)
    draw_footer(c, data, 8, 13)
    y = H - 22*mm

    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Piano d’azione — primi 90 giorni")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y, "Roadmap operativa per massimizzare le performance nella fase di lancio")
    y -= 9*mm

    # ── Timeline visiva orizzontale — design premium ──
    tl_h       = 32*mm   # altezza box timeline
    tl_y_top   = y - 2*mm
    tl_y_bot   = tl_y_top - tl_h
    tl_x_start = 14*mm
    tl_x_end   = W - 14*mm
    tl_cx      = (tl_x_start + tl_x_end) / 2
    tl_line_y  = tl_y_top - tl_h/2  # linea a metà box

    # Sfondo box timeline con gradiente simulato (rettangoli sovrapposti)
    steps = 12
    for si in range(steps):
        ratio = si / steps
        alpha_r = int(227 + (240-227)*ratio)
        alpha_g = int(242 + (248-242)*ratio)
        alpha_b = int(250 + (252-250)*ratio)
        c.setFillColor(HexColor(f"#{alpha_r:02x}{alpha_g:02x}{alpha_b:02x}"))
        strip_h = tl_h / steps
        c.rect(tl_x_start, tl_y_bot + si*strip_h, tl_x_end - tl_x_start, strip_h+0.5, fill=1, stroke=0)

    # Bordo box
    c.setStrokeColor(BLUE_PRIMARY)
    c.setLineWidth(0.8)
    c.roundRect(tl_x_start, tl_y_bot, tl_x_end - tl_x_start, tl_h, 3*mm, fill=0, stroke=1)

    # Etichetta "TIMELINE"
    c.setFont("Helvetica-Bold", 6)
    c.setFillColor(MUTED)
    c.drawString(tl_x_start + 3*mm, tl_y_top - 4*mm, "ROADMAP  90  GIORNI")

    # Nodi posizioni
    nodi = [
        (tl_x_start + (tl_x_end - tl_x_start)*0.18, "MESE 1", "Avvio e registrazioni",  "Gg 1-30",  BLUE_PRIMARY),
        (tl_x_start + (tl_x_end - tl_x_start)*0.50, "MESE 2", "Prime recensioni",        "Gg 31-60", TEAL),
        (tl_x_start + (tl_x_end - tl_x_start)*0.82, "MESE 3", "Ottimizzazione",          "Gg 61-90", GOLD),
    ]

    # Linea centrale continua
    c.setStrokeColor(BORDER)
    c.setLineWidth(2)
    c.line(nodi[0][0], tl_line_y, nodi[-1][0], tl_line_y)

    # Segmento colorato tra nodi con gradiente a blocchi
    for i in range(len(nodi)-1):
        nx1, nx2 = nodi[i][0], nodi[i+1][0]
        col1, col2 = nodi[i][4], nodi[i+1][4]
        seg_steps = 8
        seg_w = (nx2 - nx1) / seg_steps
        for si in range(seg_steps):
            c.setStrokeColor(col1 if si < seg_steps//2 else col2)
            c.setLineWidth(2)
            c.line(nx1 + si*seg_w, tl_line_y, nx1 + (si+1)*seg_w, tl_line_y)

    for i, (nx, label, subtitle, giorni, col) in enumerate(nodi):
        # Cerchio esterno (alone)
        c.setFillColor(HexColor("#FFFFFF"))
        c.setStrokeColor(col)
        c.setLineWidth(2)
        c.circle(nx, tl_line_y, 6.5*mm, fill=1, stroke=1)
        # Cerchio interno colorato
        c.setFillColor(col)
        c.setStrokeColor(WHITE)
        c.setLineWidth(1)
        c.circle(nx, tl_line_y, 4.5*mm, fill=1, stroke=1)
        # Testo nel nodo
        c.setFont("Helvetica-Bold", 6.5)
        c.setFillColor(WHITE)
        c.drawCentredString(nx, tl_line_y + 0.8*mm, label.split()[0])   # "MESE"
        c.drawCentredString(nx, tl_line_y - 1.8*mm, label.split()[1])   # "1" / "2" / "3"
        # Testo sopra il nodo
        c.setFont("Helvetica-Bold", 7)
        c.setFillColor(col)
        c.drawCentredString(nx, tl_line_y + 9*mm, subtitle)
        # Giorni sotto il nodo
        c.setFont("Helvetica", 6.5)
        c.setFillColor(MUTED)
        c.drawCentredString(nx, tl_line_y - 9*mm, giorni)

        # Pallino grigio a metà tra i nodi
        if i < len(nodi) - 1:
            nx_next = nodi[i+1][0]
            mid_x = (nx + nx_next) / 2
            c.setFillColor(BORDER)
            c.setStrokeColor(WHITE)
            c.setLineWidth(0.5)
            c.circle(mid_x, tl_line_y, 2.2*mm, fill=1, stroke=1)

    y = tl_y_bot - 6*mm


    for fase_label, col, items in data["piano_90"]:
        c.setFillColor(col)
        c.roundRect(14*mm, y - 6.5*mm, W - 28*mm, 6.5*mm, 2*mm, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(WHITE)
        c.drawString(18*mm, y - 4.5*mm, fase_label)
        y -= 7.5*mm

        for item in items:
            c.setFillColor(col)
            c.circle(17*mm, y - 1.5*mm, 1.2*mm, fill=1, stroke=0)
            c.setFont("Helvetica", 7.5)
            c.setFillColor(BLUE_NIGHT)
            c.drawString(20*mm, y - 2.5*mm, item)
            y -= 6*mm

        y -= 4*mm

# ═══════════════════════════════════════════════════════════════════════════
# PAG 10 — Analisi personale Arch. Sica
# ═══════════════════════════════════════════════════════════════════════════
def page10(c, data):
    draw_header(c, data)
    draw_footer(c, data, 11, 13)
    y = H - 22*mm

    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Analisi personale — Arch. Salvatore Junior Sica")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y, "Valutazione professionale in 4 aree tematiche · 30.000+ valutazioni immobiliari")
    y -= 7*mm

    aree = [
        ("📍  Posizione e contesto di mercato", data["analisi_posizione"],   BLUE_PRIMARY),
        ("🏠  Condizione e caratteristiche immobile", data["analisi_condizione"],  TEAL),
        ("📈  Potenzialit\u00e0 e proiezioni", data["analisi_potenzialita"], GOLD),
        ("✅  Raccomandazione operativa", data["analisi_raccomandazione"], BLUE_NIGHT),
    ]

    for titolo, testo, col in aree:
        # Header area
        c.setFillColor(col)
        c.roundRect(14*mm, y - 7*mm, W - 28*mm, 7*mm, 2*mm, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(WHITE)
        c.drawString(18*mm, y - 5*mm, titolo)
        y -= 8*mm

        # Testo area
        c.setFillColor(CREAM)
        # Calcola altezza approssimativa
        words = testo.split()
        line, lines_count = "", 0
        for w in words:
            test = line + (" " if line else "") + w
            if c.stringWidth(test, "Helvetica", 8) > W - 40*mm:
                lines_count += 1
                line = w
            else:
                line = test
        if line: lines_count += 1
        box_h = lines_count * 5.5*mm + 8*mm

        c.setFillColor(HexColor("#F8FAFC"))
        c.roundRect(14*mm, y - box_h, W - 28*mm, box_h, 2*mm, fill=1, stroke=0)
        c.setStrokeColor(BORDER)
        c.setLineWidth(0.5)
        c.roundRect(14*mm, y - box_h, W - 28*mm, box_h, 2*mm, fill=0, stroke=1)

        ty = y - 5*mm
        ty = wrap_simple(c, testo, 18*mm, ty, W - 40*mm, "Helvetica", 8, 5.5*mm, BLUE_NIGHT)
        y = ty - 5*mm

    # Firma
    y -= 4*mm
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(BLUE_NIGHT)
    c.drawRightString(W - 14*mm, y, "Arch. Salvatore Junior Sica")
    c.setFont("Helvetica", 8)
    c.setFillColor(MUTED)
    c.drawRightString(W - 14*mm, y - 5*mm, "Fondatore ReportUp \u00b7 30.000+ valutazioni immobiliari \u00b7 reportup.it")

# ═══════════════════════════════════════════════════════════════════════════
# PAG 11 — Fonti + Ringraziamento
# ═══════════════════════════════════════════════════════════════════════════
def page11(c, data):
    draw_header(c, data)
    draw_footer(c, data, 13, 13)
    y = H - 22*mm

    y -= 5*mm
    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Fonti e riferimenti")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y, "Dati e metodologia alla base di questa analisi")
    y -= 6*mm

    fonti = [
        ("Prezzi e tasso occupazione",
         "Elaborazione su dati aggregati Airbnb, Booking.com, VRBO. Medie di mercato per tipologia e zona alla data di generazione."),
        ("Canoni affitto tradizionale",
         "OMI — Osservatorio Mercato Immobiliare, Agenzia delle Entrate. Aggiornamento semestrale."),
        ("Dati demografici e turistici",
         "ISTAT — Istituto Nazionale di Statistica. Movimento turistico, arrivi e presenze per comune."),
        ("Normativa affitti brevi",
         f"Regione {data['regione_normativa']} \u00b7 Comune di {data['comune_normativa']} \u00b7 Ministero del Turismo \u00b7 Fonti ufficiali aggiornate 2025."),
        ("Valutazione asset immobiliare",
         "Modello professionale di valutazione bancaria alberghiera \u00b7 Arch. Salvatore Junior Sica \u00b7 30.000+ perizie."),
        ("Saggio di capitalizzazione",
         "Parametro derivato da modello bancario professionale \u00b7 Range mercato ricettivo italiano 5,5%-8%."),
        ("Punti di interesse e distanze",
         "Google Maps Platform \u00b7 percorrenza pedonale e trasporto pubblico \u00b7 stime indicative."),
    ]

    for fonte, desc in fonti:
        c.setFillColor(BLUE_PRIMARY)
        c.circle(17*mm, y - 1.5*mm, 1.2*mm, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 7.5)
        c.setFillColor(BLUE_NIGHT)
        c.drawString(20*mm, y - 2*mm, fonte)
        c.setFont("Helvetica", 7)
        c.setFillColor(MUTED)
        c.drawString(20*mm, y - 6.5*mm, desc)
        c.setStrokeColor(BORDER)
        c.setLineWidth(0.3)
        c.line(14*mm, y - 9*mm, W - 14*mm, y - 9*mm)
        y -= 13*mm

    y -= 6*mm

    # Box ringraziamento
    box_h = 72*mm
    c.setFillColor(CREAM)
    c.roundRect(14*mm, y - box_h, W - 28*mm, box_h, 3*mm, fill=1, stroke=0)
    c.setStrokeColor(BLUE_PRIMARY)
    c.setLineWidth(1)
    c.roundRect(14*mm, y - box_h, W - 28*mm, box_h, 3*mm, fill=0, stroke=1)

    # Badge logo
    bfs = 16
    c.setFont("Helvetica-Bold", bfs)
    tw_r = c.stringWidth("Report", "Helvetica-Bold", bfs)
    tw_u = c.stringWidth("Up",     "Helvetica-Bold", bfs)
    bw = tw_r + tw_u + 10*mm
    bh = 9*mm
    bx = W/2 - bw/2
    by2 = y - bh - 4*mm
    c.setFillColor(BLUE_NIGHT)
    c.roundRect(bx, by2, bw, bh, 2*mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.drawString(bx + 5*mm, by2 + 2.2*mm, "Report")
    c.setFillColor(BLUE_PRIMARY)
    c.drawString(bx + 5*mm + tw_r, by2 + 2.2*mm, "Up")
    iy = by2 - 7*mm

    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(BLUE_NIGHT)
    c.drawCentredString(W/2, iy, "Grazie per aver scelto ReportUp.")
    iy -= 9*mm

    paragrafi = [
        ("Sono l\u2019Arch. Salvatore Junior Sica, e questo report porta con s\u00e9 oltre un decennio di esperienza "
         "nel settore immobiliare italiano e pi\u00f9 di 30.000 valutazioni effettuate sul territorio nazionale.", False),
        ("Siamo una piccola realt\u00e0 che sta crescendo, e lo facciamo con calma, con seriet\u00e0 e senza "
         "scorciatoie. Ogni report che esce porta il nostro nome, e questo per noi non \u00e8 mai un dettaglio.", True),
        ("Spero che questa analisi ti sia utile e ti aiuti a prendere la decisione giusta per il tuo immobile.", False),
    ]
    for testo, corsivo in paragrafi:
        fn = "Helvetica-Oblique" if corsivo else "Helvetica"
        col = TEAL if corsivo else BLUE_NIGHT
        words = testo.split()
        line = ""
        for w in words:
            test = line + (" " if line else "") + w
            if c.stringWidth(test, fn, 8) > W - 50*mm:
                c.setFont(fn, 8)
                c.setFillColor(col)
                c.drawCentredString(W/2, iy, line)
                iy -= 5*mm
                line = w
            else:
                line = test
        if line:
            c.setFont(fn, 8)
            c.setFillColor(col)
            c.drawCentredString(W/2, iy, line)
            iy -= 5*mm
        iy -= 2*mm

    iy -= 2*mm
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(BLUE_NIGHT)
    c.drawCentredString(W/2, iy, "Arch. Salvatore Junior Sica")
    iy -= 6*mm
    c.setFont("Helvetica", 8)
    c.setFillColor(MUTED)
    c.drawCentredString(W/2, iy, "Fondatore \u2014 ReportUp | reportup.it")

# ═══════════════════════════════════════════════════════════════════════════
# PAG 12 — Riepilogo obiettivi e guida alla lettura
# ═══════════════════════════════════════════════════════════════════════════
def page_obiettivi(c, data):
    draw_header(c, data)
    draw_footer(c, data, 12, 13)
    y = H - 22*mm

    y = draw_section_header(c, 14*mm, y, W - 28*mm, "I tuoi obiettivi — dove trovare le risposte")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y, "Riepilogo di ci\u00f2 che hai dichiarato \u00b7 le sezioni del report pi\u00f9 rilevanti per te")
    y -= 8*mm

    obiettivi = data["obiettivi_selezionati"]
    pagine_map = data["obiettivi_pagine"]

    for emoji_label, titolo, desc in obiettivi:
        # Lookup pagine
        form_key = [k for k in pagine_map if k in emoji_label.lower().replace(" ","_").replace("\u2019","'")]
        if not form_key:
            form_key = [k for k in pagine_map if k in titolo.lower().replace(" ","_")]
        pag_label, pag_desc = pagine_map.get(form_key[0], ("\u2014", "")) if form_key else ("\u2014", "")

        # Box obiettivo — più alto
        box_h = 32*mm
        pill_w = 44*mm
        pill_h = 10*mm
        pill_x = W - 14*mm - pill_w - 4*mm

        c.setFillColor(GOLD_LIGHT)
        c.roundRect(14*mm, y - box_h, W - 28*mm, box_h, 3*mm, fill=1, stroke=0)
        c.setStrokeColor(GOLD)
        c.setLineWidth(1.0)
        c.roundRect(14*mm, y - box_h, W - 28*mm, box_h, 3*mm, fill=0, stroke=1)

        # Striscia sinistra colorata
        c.setFillColor(GOLD)
        c.roundRect(14*mm, y - box_h, 3*mm, box_h, 1.5*mm, fill=1, stroke=0)

        # Titolo obiettivo
        c.setFont("Helvetica-Bold", 13)
        c.setFillColor(BLUE_NIGHT)
        c.drawString(20*mm, y - 9*mm, titolo)

        # Descrizione
        c.setFont("Helvetica", 10)
        c.setFillColor(MUTED)
        c.drawString(20*mm, y - 16*mm, desc)

        # Pill "→ Pag. X" — centrata verticalmente
        pill_txt_line1 = "\u2192  Vai a"
        pill_txt_line2 = pag_label
        pill_cy = y - box_h/2  # centro verticale del box
        pill_top = pill_cy + (pill_h + 4*mm)/2
        c.setFillColor(GOLD)
        c.roundRect(pill_x, pill_top - (pill_h + 4*mm), pill_w, pill_h + 4*mm, 2*mm, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont("Helvetica", 8)
        c.drawCentredString(pill_x + pill_w/2, pill_top - 5.5*mm, pill_txt_line1)
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(pill_x + pill_w/2, pill_top - 10.5*mm, pill_txt_line2)

        # Descrizione sezioni — sotto il box con spazio
        c.setFont("Helvetica-Oblique", 7.5)
        c.setFillColor(MUTED)
        c.drawRightString(W - 16*mm, y - box_h - 3*mm, pag_desc)

        y -= box_h + 10*mm

    y -= 4*mm

    # Box nota finale
    nota_h = 28*mm
    c.setFillColor(HexColor("#E3F2FA"))
    c.roundRect(14*mm, y - nota_h, W - 28*mm, nota_h, 2*mm, fill=1, stroke=0)
    c.setStrokeColor(BLUE_PRIMARY)
    c.setLineWidth(0.8)
    c.roundRect(14*mm, y - nota_h, W - 28*mm, nota_h, 2*mm, fill=0, stroke=1)

    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(BLUE_NIGHT)
    c.drawString(18*mm, y - 6*mm, "Hai domande sul report?")
    c.setFont("Helvetica", 8)
    c.setFillColor(BLUE_NIGHT)
    note_lines = [
        "Questo report \u00e8 stato generato sulla base delle informazioni che hai fornito al momento dell\u2019acquisto.",
        "Se hai dubbi sui numeri, vuoi approfondire un\u2019area specifica o hai bisogno di chiarimenti,",
        "scrivici a reportup.info@gmail.com \u2014 rispondiamo entro 48 ore.",
    ]
    ny = y - 12*mm
    for line in note_lines:
        c.setFont("Helvetica", 7.5)
        c.setFillColor(BLUE_NIGHT)
        c.drawString(18*mm, ny, line)
        ny -= 5*mm

# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def build_strategico_pdf_bytes(data):
    """Genera il PDF Strategico in memoria e restituisce bytes."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle("ReportUp — Report Strategico")
    c.setAuthor("Arch. Salvatore Junior Sica · ReportUp")
    for page_fn in [page1, page2, page3, page4, page4_manutenzione, page5, page8, page9, page6, page7, page10, page_obiettivi, page11]:
        page_fn(c, data)
        c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()

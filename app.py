"""
ReportUp PDF Service
Riceve JSON con i dati del report, genera il PDF branded, restituisce base64.
Deploy su Render.com (piano free).
"""

import os
import io
import base64
import math
from flask import Flask, request, jsonify
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

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

    # Box indirizzo
    box_h = 16 * mm
    c.setFillColor(BLUE_NIGHT)
    c.rect(14 * mm, y - box_h, W - 28 * mm, box_h, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(WHITE)
    c.drawCentredString(W / 2, y - box_h / 2 - 3.5 * mm, D.get("indirizzo", ""))
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
    presenti = D.get("dotazioni_presenti", [])
    assenti = D.get("dotazioni_assenti", [])
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
    wrap_text(c, D.get("descrizione", ""), 14 * mm, y, W - 28 * mm, "Helvetica", 8, 5.5 * mm)


def page2(c, D):
    draw_header(c, D)
    draw_footer(c, 2)
    y = H - 22 * mm

    # POI
    y = draw_section_header(c, 14 * mm, y, W - 28 * mm, "Posizione e punti di interesse")
    y -= 3 * mm
    draw_section_subtitle(c, 14 * mm, y, "Distanze e impatto sulla domanda di prenotazioni")
    y -= 6 * mm
    poi_data = [["Punto di interesse", "A piedi", "Mezzo pubblico", "Impatto"]]
    for row in D.get("poi", []):
        poi_data.append(list(row))
    col_w_poi = [(W - 28 * mm) * 0.35, (W - 28 * mm) * 0.13, (W - 28 * mm) * 0.33, (W - 28 * mm) * 0.19]
    tbl = Table(poi_data, colWidths=col_w_poi)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLUE_NIGHT), ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"), ("TEXTCOLOR", (0, 1), (-1, -1), BLUE_NIGHT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, CREAM]),
        ("GRID", (0, 0), (-1, -1), 0.25, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
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

    sit_label = "Immobile vuoto" if D.get("situazione_vuoto") else ("B&B attivo" if D.get("situazione_bnb") else "Con inquilini")
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
        "kpi_occ_range", "kpi_potenziale", "data_generazione"
    ]:
        val = data.get(field, report.get(field, imm.get(field)))
        if val is not None:
            flat[field] = val

    return flat


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

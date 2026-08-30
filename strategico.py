"""
ReportUp — Strategico PDF pages
Importato da app.py come modulo separato.
Tutte le funzioni di pagina ricevono (c, data) come parametri.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
import datetime
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
        f"Generato: {data.get('data_generazione', '')}  \u00b7  Valido 90 giorni")

TOTALE_PAGINE = 17


def draw_footer(c, data, page_num, total=TOTALE_PAGINE):
    footer_h = 9*mm
    c.setFillColor(BLUE_NIGHT)
    c.rect(0, 0, W, footer_h, fill=1, stroke=0)
    c.setFont("Helvetica", 6.5)
    c.setFillColor(HexColor("#A8BCC8"))
    # Stessa riga del Base: simbolo \u00a9 e anno corrente (prima era fisso
    # "(c) 2025", quindi un Base e uno Strategico generati lo stesso giorno
    # mostravano copyright diversi).
    c.drawString(14*mm, 3.5*mm,
        f"\u00a9 {datetime.date.today().year} ReportUp \u00b7 reportup.it  |  "
        "Documento orientativo - non costituisce consulenza professionale")
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

def draw_competitor(c, data, y):
    """Tabella competitor identica a quella del Base (page4 in app.py): stesse
    colonne, stessi stili, stessa riga finale evidenziata con la stima del tuo
    immobile. I dati arrivano dallo stesso campo `competitor`, calcolato in
    modo deterministico dal motore condiviso, quindi i due PDF mostrano gli
    stessi prezzi per le stesse tipologie."""
    _zona_comp = str(data.get("competitor_zona") or data.get("zona") or "").strip()
    _suffisso_comp = f" - {_zona_comp}" if _zona_comp and _zona_comp != "—" else ""

    y = draw_section_header(c, 14*mm, y, W - 28*mm, f"Analisi competitor{_suffisso_comp}")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y, "Confronto diretto con gli annunci attivi nella zona")
    y -= 6*mm

    comp_data = [[f"Tipologia annunci{_suffisso_comp}", "Prezzo med."]]
    for row in data.get("competitor", []):
        comp_data.append(list(row))
    comp_data.append(["IL TUO IMMOBILE (stima)", f"€ {data.get('kpi_prezzo', data.get('prezzo_notte_stimato', 0))}"])

    col_w_comp = [(W - 28*mm) * 0.65, (W - 28*mm) * 0.35]
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
    tbl_comp.wrapOn(c, W - 28*mm, 200)
    tbl_comp.drawOn(c, 14*mm, y - tbl_comp._height)
    return y - tbl_comp._height - 7*mm


def fmt_num(val):
    """Solo il numero col separatore delle migliaia. Serve per non applicare
    .replace(",", ".") a intere frasi: dove la nota conteneva una virgola
    (biancheria, FF&E) usciva un punto al suo posto — "per la tipologia.
    soggiorno medio 2 notti"."""
    return f"{val:,}".replace(",", ".")


def fmt_eur(val):
    """Il Base stampa ovunque il simbolo €; qui usciva la sigla "EUR", quindi
    la stessa cifra si leggeva "EUR 34.063" nello Strategico e "€ 34.063" nel
    Base. Unificato sul simbolo."""
    return f"€ {val:,}".replace(",", ".")

def fmt_eu(val):
    """Versione con simbolo € per prezzi in tabelle"""
    return f"\u20ac {val:,}".replace(",", ".")

def draw_centred_fit(c, cx, y, testo, max_w, font, size, line_h=None, min_size=5.5):
    """Testo centrato che non esce mai dal riquadro: prima rimpicciolisce il
    corpo, poi va a capo. Serve ai sottotitoli delle card scenario, che a
    corpo fisso sbordavano sia a sinistra sia a destra della card colorata."""
    line_h = line_h or size + 1.5
    corpo = size
    while corpo > min_size and c.stringWidth(testo, font, corpo) > max_w:
        corpo -= 0.5
    if c.stringWidth(testo, font, corpo) <= max_w:
        c.setFont(font, corpo)
        c.drawCentredString(cx, y, testo)
        return y - line_h
    righe, linea = [], ""
    for parola in testo.split():
        prova = f"{linea} {parola}".strip()
        if c.stringWidth(prova, font, corpo) > max_w and linea:
            righe.append(linea)
            linea = parola
        else:
            linea = prova
    if linea:
        righe.append(linea)
    c.setFont(font, corpo)
    for riga in righe:
        c.drawCentredString(cx, y, riga)
        y -= line_h
    return y


def _righe_nota(c, testo, max_w, size):
    righe, linea = [], ""
    for parola in str(testo).split():
        prova = f"{linea} {parola}".strip()
        if c.stringWidth(prova, "Helvetica", size) > max_w and linea:
            righe.append(linea)
            linea = parola
        else:
            linea = prova
    if linea:
        righe.append(linea)
    return righe


def altezza_nota(c, testi, box_w, size=7, massimo=42*mm):
    """Altezza da riservare in fondo alle card perché la nota più lunga delle
    tre ci stia tutta. Le card vanno allineate, quindi si dimensiona sul caso
    peggiore invece di lasciare una fascia fissa: con note corte non resta un
    buco, con note lunghe non serve rimpicciolire il testo."""
    max_w = box_w - 8*mm
    n = max((len(_righe_nota(c, t, max_w, size)) for t in testi if t), default=0)
    return min(massimo, n * (size + 2.2) + 3*mm) if n else 0


def draw_nota_card(c, testo, bx, by, box_w, altezza, colore=None, size=7, min_size=5):
    """Nota in fondo a una card scenario. Il testo è scritto dall'AI e può
    essere lungo quanto vuole: prima si cerca il corpo più grande che ci sta
    nella fascia riservata, poi si scrive dall'alto verso il basso. Il ciclo
    precedente partiva da una quota fissa e andava giù senza limite, quindi le
    note lunghe finivano sotto il riquadro colorato.
    Colore pieno e non corsivo: sono suggerimenti operativi, non note a piè di
    pagina."""
    if not testo:
        return
    colore = colore or BLUE_NIGHT
    max_w = box_w - 8*mm
    corpo = size
    righe = []
    while True:
        interlinea = corpo + 2.2
        righe, linea = [], ""
        for parola in testo.split():
            prova = f"{linea} {parola}".strip()
            if c.stringWidth(prova, "Helvetica", corpo) > max_w and linea:
                righe.append(linea)
                linea = parola
            else:
                linea = prova
        if linea:
            righe.append(linea)
        if len(righe) * interlinea <= altezza or corpo <= min_size:
            break
        corpo -= 0.5

    interlinea = corpo + 2.2
    # Se anche al corpo minimo non ci sta, si tengono le righe che entrano:
    # meglio una nota troncata che una che sfonda la card.
    massimo = max(1, int(altezza // interlinea))
    righe = righe[:massimo]

    c.setFont("Helvetica", corpo)
    c.setFillColor(colore)
    ny = by + altezza - interlinea + 1.5
    for riga in righe:
        c.drawString(bx + 4*mm, ny, riga)
        ny -= interlinea


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
    draw_footer(c, data, 1)
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
    c.setFillColor(WHITE)
    # Stessa scaletta di corpi del Base: l'indirizzo si rimpicciolisce finché
    # entra nel riquadro invece di sbordare a 20pt fissi.
    indirizzo_txt = data.get('indirizzo', '')
    max_w_ind = W - 36*mm
    for font_size in [18, 16, 14, 12, 10]:
        c.setFont("Helvetica-Bold", font_size)
        if c.stringWidth(indirizzo_txt, "Helvetica-Bold", font_size) <= max_w_ind:
            break
    c.drawCentredString(W/2, y - box_h/2 - font_size*0.18*mm, indirizzo_txt)
    y -= box_h + 5*mm

    # Mappa stradale (Google Static Maps, vedi _fetch_static_map_png in
    # app.py \u2014 roadmap, non satellite: Google blocca satellite/hybrid per
    # account/regione EEA). Stessa GOOGLE_MAPS_API_KEY di geocode/AirROI,
    # nessuna chiamata aggiuntiva oltre quella gi\u00e0 fatta per lat/long. Se
    # manca (chiave assente, timeout, coordinate mancanti) ricade sul
    # placeholder di sempre.
    # 100mm, non 55: sotto le pillole "Situazione attuale" restavano ~80mm di
    # pagina bianca. Alzando il riquadro tutto il resto scende di 45mm e ne
    # avanzano ~35mm come margine inferiore, che è respiro voluto e non buco.
    # Il rapporto 182x100mm deve restare allineato al `size` richiesto in
    # _fetch_static_map_png (640x352): qui si disegna con
    # preserveAspectRatio=False, quindi un rapporto diverso stira l'immagine.
    map_h = 100*mm
    map_png = data.get('_mappa_png')
    map_ok = False
    if map_png:
        try:
            img = ImageReader(io.BytesIO(map_png))
            c.saveState()
            clip = c.beginPath()
            clip.roundRect(14*mm, y - map_h, W - 28*mm, map_h, 3*mm)
            c.clipPath(clip, stroke=0, fill=0)
            c.drawImage(img, 14*mm, y - map_h, width=W - 28*mm, height=map_h,
                        preserveAspectRatio=False, mask='auto')
            c.restoreState()
            c.setStrokeColor(BLUE_PRIMARY)
            c.setLineWidth(0.8)
            c.roundRect(14*mm, y - map_h, W - 28*mm, map_h, 3*mm, fill=0, stroke=1)
            # Banda scura in basso: indirizzo leggibile sopra la foto satellitare.
            label_h = 9*mm
            c.saveState()
            c.setFillColor(BLUE_NIGHT)
            c.setFillAlpha(0.72)
            c.rect(14*mm, y - map_h, W - 28*mm, label_h, fill=1, stroke=0)
            c.restoreState()
            c.setFont("Helvetica-Bold", 8)
            c.setFillColor(WHITE)
            c.drawCentredString(W/2, y - map_h + label_h/2 - 1*mm,
                                 f"{data.get('indirizzo', '')}  \u00b7  {data.get('zona', '')}")
            map_ok = True
        except Exception:
            map_ok = False

    if not map_ok:
        # Placeholder: chiave assente/timeout/coordinate mancanti.
        c.setFillColor(HexColor("#E3F2FA"))
        c.roundRect(14*mm, y - map_h, W - 28*mm, map_h, 3*mm, fill=1, stroke=0)
        c.setStrokeColor(BLUE_PRIMARY)
        c.setLineWidth(0.8)
        c.roundRect(14*mm, y - map_h, W - 28*mm, map_h, 3*mm, fill=0, stroke=1)
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(BLUE_PRIMARY)
        # Niente emoji: i font standard del PDF non le hanno e ReportLab ripiega
        # su ZapfDingbats, che le rendeva come quadratini neri.
        c.drawCentredString(W/2, y - map_h/2 + 3*mm, "Posizione geografica immobile")
        c.setFont("Helvetica", 7.5)
        c.setFillColor(MUTED)
        c.drawCentredString(W/2, y - map_h/2 - 3*mm, f"{data.get('indirizzo', '')}  \u00b7  {data.get('zona', '')}")
        c.setFont("Helvetica-Oblique", 7)
        c.drawCentredString(W/2, y - map_h/2 - 8*mm, "La mappa non \u00e8 disponibile per questo indirizzo")
    y -= map_h + 5*mm

    # Scheda immobile
    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Scheda immobile")
    y -= 2*mm

    col_w = (W - 28*mm) / 2
    label_col_w = 28*mm
    # Chiavi `scheda_*` (_prepara_etichette_scheda in app.py): stesse etichette
    # leggibili del Base. Prima qui finivano i codici grezzi del form
    # ("bilocale", "1-3", "anni70", "base") mentre il Base mostrava già
    # "Bilocale", "1° – 3° piano", "Anni '70", "Arredi base, funzionale".
    fields_l = [
        ("Tipologia",  data.get('scheda_tipologia')  or data.get('tipologia', '')),
        ("Superficie", data.get('scheda_superficie') or data.get('superficie', '')),
        ("Piano",      data.get('scheda_piano')      or data.get('piano', '')),
        ("Stato",      data.get('scheda_stato')      or data.get('stato', '')),
        ("Camere",     data.get('scheda_camere')     or data.get('camere', '')),
    ]
    fields_r = [
        ("Comune",      data.get('comune', '')),
        ("Zona",        data.get('zona', '')),
        ("Epoca",       data.get('scheda_epoca')       or data.get('epoca', '')),
        ("Bagni",       data.get('scheda_bagni')       or data.get('bagni', '')),
        ("Posti letto", data.get('scheda_posti_letto') or data.get('posti_letto', '')),
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
    for d in data.get('dotazioni_presenti', []) + data.get('dotazioni_assenti', []):
        presente = d in data.get('dotazioni_presenti', [])
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
        (f"Immobile vuoto: {'SI' if data.get('situazione_vuoto', False) else 'NO'}",      data.get('situazione_vuoto', False)),
        (f"Inquilini attivi: {'SI' if data.get('situazione_inquilini', False) else 'NO'}", data.get('situazione_inquilini', False)),
        (f"B&B gi\u00e0 attivo: {'SI' if data.get('situazione_bnb', False) else 'NO'}",   data.get('situazione_bnb', False)),
        (f"Mutuo attivo: {'SI' if data.get('situazione_mutuo', False) else 'NO'}",         data.get('situazione_mutuo', False)),
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
    draw_footer(c, data, 2)
    y = H - 22*mm

    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Descrizione immobile")
    y -= 5*mm
    y = wrap_text(c, data.get('descrizione', ''), 14*mm, y, W - 28*mm, "Helvetica", 8, 5.5*mm)
    y -= 8*mm

    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Posizione e punti di interesse")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y, "Distanze e impatto sulla domanda di prenotazioni")
    y -= 6*mm

    # Stessa tabella del Base: 5 slot fissi di categoria e colonne identiche.
    # Prima lo Strategico usava colonne sue ("Punto di interesse / A piedi /
    # Mezzo pubblico / Impatto"): le righe arrivano già convertite nello schema
    # del Base da _poi_strategico_in_formato_base in app.py.
    SLOT_LABELS = [
        "Trasporto pubblico",
        "Comune di riferimento",
        "Elemento caratteristico",
        "Servizi essenziali",
        "Aeroporto",
    ]

    poi_rows_raw = [list(row) for row in data.get('poi', [])]
    while len(poi_rows_raw) < 5:
        poi_rows_raw.append(["—", "—", "—"])
    poi_rows_raw = poi_rows_raw[:5]

    style_cell_bold = ParagraphStyle("poiCellBold", fontName="Helvetica-Bold", fontSize=8, textColor=BLUE_NIGHT, leading=10)
    style_cell_reg  = ParagraphStyle("poiCellReg",  fontName="Helvetica",      fontSize=8, textColor=BLUE_NIGHT, leading=10)
    style_header    = ParagraphStyle("poiHeader",   fontName="Helvetica-Bold", fontSize=8, textColor=WHITE,      leading=10)

    header_labels = ["Categoria", "Distanza", "Punto di riferimento", "Impatto"]
    poi_data = [[Paragraph(h, style_header) for h in header_labels]]
    for label, row in zip(SLOT_LABELS, poi_rows_raw):
        mezzo_distanza, nome, impatto = (row + ["—", "—", "—"])[:3]
        poi_data.append([
            Paragraph(label, style_cell_bold),
            Paragraph(str(mezzo_distanza), style_cell_reg),
            Paragraph(str(nome), style_cell_reg),
            Paragraph(str(impatto), style_cell_reg),
        ])

    col_w_poi = [(W - 28*mm) * 0.20, (W - 28*mm) * 0.22, (W - 28*mm) * 0.42, (W - 28*mm) * 0.16]
    tbl_poi = Table(poi_data, colWidths=col_w_poi)
    tbl_poi.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), BLUE_NIGHT),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, CREAM]),
        ("GRID",          (0,0), (-1,-1), 0.25, BORDER),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 5), ("RIGHTPADDING",  (0,0), (-1,-1), 5),
    ]))
    tbl_poi.wrapOn(c, W-28*mm, 200)
    tbl_poi.drawOn(c, 14*mm, y - tbl_poi._height)

# ═══════════════════════════════════════════════════════════════════════════
# PAG 3 — Occupazione stagionale
# ═══════════════════════════════════════════════════════════════════════════
def page3(c, data):
    draw_header(c, data)
    draw_footer(c, data, 3)
    y = H - 22*mm

    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Occupazione stagionale")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y, "Andamento mensile stimato - prezzi e tassi di riempimento")
    y -= 6*mm

    occ = data.get('occupazione', [])
    # Stessi tre mesi che il Base evidenzia in verde (dato AirROI più
    # affidabile): prima lo Strategico li ignorava del tutto, quindi la stessa
    # tabella usciva con evidenziazioni diverse sui due PDF.
    mesi_affidabili_idx = set(data.get("mesi_affidabili_idx", []))
    VERDE_AFFIDABILE = HexColor("#D4F1DE")
    VERDE_DATO_REALE = HexColor("#2E9E4F")

    header_half = ["Mese", "Occup.", "€/notte", "Stage"]
    data_sx = [[o[0], f"{o[1]}%", f"€ {o[2]}", o[3]] for o in occ[:6]]
    data_dx = [[o[0], f"{o[1]}%", f"€ {o[2]}", o[3]] for o in occ[6:]]

    gap = 5*mm
    half = (W - 28*mm - gap) / 2
    col_w_half = [half*0.20, half*0.24, half*0.32, half*0.24]

    def make_half_style(data_rows, idx_offset):
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
            if (ri + idx_offset) in mesi_affidabili_idx:
                style.append(("BACKGROUND", (0, ri+1), (2, ri+1), VERDE_AFFIDABILE))
                style.append(("BOX",        (0, ri+1), (2, ri+1), 1.3, VERDE_DATO_REALE))
                style.append(("FONTSIZE",   (0, ri+1), (2, ri+1), 9))
                style.append(("FONTNAME",   (0, ri+1), (2, ri+1), "Helvetica-Bold"))
                style.append(("TEXTCOLOR",  (1, ri+1), (1, ri+1), BLUE_NIGHT))
                style.append(("TOPPADDING",    (0, ri+1), (2, ri+1), 5))
                style.append(("BOTTOMPADDING", (0, ri+1), (2, ri+1), 5))
        return style

    tbl_sx = Table([header_half] + data_sx, colWidths=col_w_half)
    tbl_sx.setStyle(TableStyle(make_half_style(data_sx, 0)))
    tbl_sx.wrapOn(c, half, 300)
    tbl_dx = Table([header_half] + data_dx, colWidths=col_w_half)
    tbl_dx.setStyle(TableStyle(make_half_style(data_dx, 6)))
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

    # Grafico allineato al Base: stessa legenda (compresa la voce "Dato reale
    # attuale"), stessa scala 30-95 con clamp, stessi cerchi ingranditi con
    # anello e badge verde sui mesi affidabili, stesso disclaimer sotto.
    legend_items = [("Bassa", MUTED), ("Media", BLUE_PRIMARY), ("Alta stagione", TEAL),
                    ("Peak", GOLD), ("Dato reale attuale", VERDE_DATO_REALE)]
    lx = gx + 3*mm
    for lbl, col in legend_items:
        c.setFillColor(col)
        c.circle(lx + 1.5*mm, gy + graph_h - 4*mm, 1.5*mm, fill=1, stroke=0)
        c.setFont("Helvetica", 6.5)
        c.setFillColor(MUTED)
        c.drawString(lx + 4*mm, gy + graph_h - 5*mm, lbl)
        lx += c.stringWidth(lbl, "Helvetica", 6.5) + 10*mm

    bottom_margin = 17*mm
    top_margin = 10*mm
    plot_h = graph_h - bottom_margin - top_margin
    side_margin = 16*mm
    min_r, max_r = 30, 95
    for pct in [30, 40, 50, 60, 70, 80, 90]:
        py_line = gy + bottom_margin + ((pct - min_r) / (max_r - min_r)) * plot_h
        c.setStrokeColor(BORDER)
        c.setLineWidth(0.25)
        c.line(gx + side_margin, py_line, gx + graph_w - side_margin, py_line)
        c.setFont("Helvetica", 5.5)
        c.setFillColor(MUTED)
        c.drawString(gx + 0.5*mm, py_line - 1.5*mm, f"{pct}%")

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
    if not points:
        return
    p = c.beginPath()
    p.moveTo(points[0][0], points[0][1])
    for pt in points[1:]:
        p.lineTo(pt[0], pt[1])
    c.drawPath(p, stroke=1, fill=0)

    for i, (px_dot, py_dot, stage, rate) in enumerate(points):
        col = stage_color(stage)
        affidabile = i in mesi_affidabili_idx
        r = 2.5*mm if stage == "Peak" else 1.8*mm
        if affidabile:
            r += 0.7*mm
        c.setFillColor(col)
        c.circle(px_dot, py_dot, r, fill=1, stroke=0)
        if affidabile:
            c.setStrokeColor(VERDE_DATO_REALE)
            c.setLineWidth(1.2)
            c.circle(px_dot, py_dot, r + 1*mm, fill=0, stroke=1)
            badge_w, badge_h = 8.5*mm, 4.2*mm
            bx, by = px_dot - badge_w / 2, py_dot + 2.2*mm
            c.setFillColor(HexColor("#B9C7BE"))
            c.roundRect(bx + 0.3*mm, by - 0.3*mm, badge_w, badge_h, 1.2*mm, fill=1, stroke=0)
            c.setFillColor(VERDE_DATO_REALE)
            c.roundRect(bx, by, badge_w, badge_h, 1.2*mm, fill=1, stroke=0)
            c.setFont("Helvetica-Bold", 6.5)
            c.setFillColor(WHITE)
            c.drawCentredString(px_dot, by + 1.3*mm, f"{rate}%")
        else:
            c.setFont("Helvetica-Bold", 6)
            c.setFillColor(BLUE_NIGHT)
            c.drawCentredString(px_dot, py_dot + 3*mm, f"{rate}%")

    for i, row in enumerate(occ):
        px_dot = gx + side_margin + i * step
        affidabile = i in mesi_affidabili_idx
        c.setFont("Helvetica-Bold" if affidabile else "Helvetica", 7 if affidabile else 6)
        c.setFillColor(VERDE_DATO_REALE if affidabile else BLUE_NIGHT)
        c.drawCentredString(px_dot, gy + 8*mm, row[0])
        c.setFont("Helvetica-Bold" if affidabile else "Helvetica", 6 if affidabile else 5.5)
        c.setFillColor(BLUE_NIGHT if affidabile else MUTED)
        c.drawCentredString(px_dot, gy + 4*mm, f"€ {row[2]}")

    disclaimer_prezzi = (
        "I mesi in evidenza (i 3 piu' vicini alla data del report) mostrano il prezzo attualmente piu' affidabile, "
        "rilevato oggi sul mercato reale. Gli altri mesi sono affidabili alla data odierna, ma possono variare "
        "(tipicamente al rialzo) avvicinandosi al periodo di riferimento."
    )
    style_disclaimer = ParagraphStyle(
        "disclaimerPrezzi", fontName="Helvetica-Oblique", fontSize=6,
        textColor=MUTED, leading=7.5, alignment=TA_CENTER,
    )
    p_disclaimer = Paragraph(disclaimer_prezzi, style_disclaimer)
    _, h_disclaimer = p_disclaimer.wrap(W - 28*mm, 20*mm)
    p_disclaimer.drawOn(c, 14*mm, gy - 4*mm - h_disclaimer)

    # Media prossimo trimestre (ToDo Sessione 65) — si affianca alla curva a
    # 12 mesi sopra, non la sostituisce. Calcolata dal backend sugli stessi
    # 3 mesi già evidenziati in verde nel grafico (dato AirROI più
    # affidabile, non stima annua diluita) — vedi _calcola_trimestre_
    # affidabile in app.py. Se il backend non l'ha calcolata (dato mancante
    # o malformato), la sezione viene omessa invece di mostrare zeri.
    if "trimestre_ricavo_atteso" in data:
        # Sotto il disclaimer prezzi appena aggiunto, non più a quota fissa:
        # altrimenti l'intestazione di sezione ci finirebbe sopra.
        y = gy - 4*mm - h_disclaimer - 6*mm
        y = draw_section_header(c, 14*mm, y, W - 28*mm,
            f"Prossimi 3 mesi ({data.get('trimestre_mesi_label', '')}) — dato più affidabile")
        y -= 3*mm
        draw_section_subtitle(c, 14*mm, y, "Media calcolata solo sul trimestre in arrivo, non sull'anno intero")
        y -= 7*mm

        card_gap = 4*mm
        card_w = (W - 28*mm - 2*card_gap) / 3
        card_h = 20*mm
        trimestre_cards = [
            ("Prezzo medio/notte",   f"€ {data.get('trimestre_prezzo_medio', 0)}",   TEAL_LIGHT, TEAL),
            ("Occupazione media",    f"{data.get('trimestre_occupazione_media', 0)}%", HexColor("#E3F4FC"), BLUE_PRIMARY),
            ("Ricavo atteso trimestre", fmt_eur(data.get('trimestre_ricavo_atteso', 0)), GOLD_LIGHT, GOLD),
        ]
        cx = 14*mm
        for lbl, val, bg, tc in trimestre_cards:
            c.setFillColor(bg)
            c.roundRect(cx, y - card_h, card_w, card_h, 2*mm, fill=1, stroke=0)
            c.setStrokeColor(tc)
            c.setLineWidth(0.8)
            c.roundRect(cx, y - card_h, card_w, card_h, 2*mm, fill=0, stroke=1)
            c.setFont("Helvetica", 7)
            c.setFillColor(MUTED)
            c.drawCentredString(cx + card_w/2, y - 6*mm, lbl)
            c.setFont("Helvetica-Bold", 12)
            c.setFillColor(tc)
            c.drawCentredString(cx + card_w/2, y - 14*mm, val)
            cx += card_w + card_gap

# ═══════════════════════════════════════════════════════════════════════════
# PAG 4 — Analisi economica
# ═══════════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════
# PAG 4 — Manutenzione / Ristrutturazione
# ═══════════════════════════════════════════════════════════════════════════
def page4_manutenzione(c, data):
    draw_header(c, data)
    draw_footer(c, data, 5)
    y = H - 22*mm

    tipo = data.get('intervento_tipo', "nessuno")
    importo = data.get('intervento_importo', 0)
    mesi = data.get('intervento_mesi', 0)
    mensile = data.get('intervento_mensile', 0)

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
        c.drawCentredString(W/2, y - 7*mm, "Nessun intervento dichiarato — immobile pronto all’uso")
        c.setFont("Helvetica", 8)
        c.setFillColor(MUTED)
        c.drawCentredString(W/2, y - 12*mm, "Questa sezione non impatta il calcolo del profitto netto né il valore dell’immobile")
        y -= box_h + 8*mm
    else:
        # Determina colori e label per tipo intervento
        if tipo == "manutenzione":
            col = BLUE_PRIMARY
            bg = HexColor("#E3F2FA")
            label_tipo = "Manutenzione"
            range_label = "€ 100 – € 5.000"
            anni_max = "3 anni"
        else:
            col = GOLD
            bg = GOLD_LIGHT
            label_tipo = "Ristrutturazione"
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
        # Sessione 29/8: mensile*12 in float dava resti tipo 6875.039999999999
        # (classico errore di rappresentazione binaria, es. 572.92*12). Il
        # resto del report mostra sempre euro interi (mai centesimi sparsi),
        # quindi si arrotonda una volta sola qui e si riusa ovunque sotto.
        impatto_annuo = round(mensile * 12)
        profitto_dopo = round(data.get('profitto_netto', 0) - mensile * 12)
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
             f"- € {impatto_annuo:,}".replace(",",".")],
            ["Profitto netto DOPO intervento",
             f"€ {data.get('profitto_netto', 0):,} - € {impatto_annuo:,} = nel periodo di diluizione".replace(",","."),
             f"€ {profitto_dopo:,}".replace(",",".")],
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

    profitto  = data.get('profitto_netto', 0)
    ricavo_lordo = data.get('ricavo_lordo', 0)
    pm_bassa  = data.get('pm_perc_bassa', 15)
    pm_alta   = data.get('pm_perc_alta', 20)
    has_pm    = data.get('property_manager', False)
    has_int   = data.get('intervento_tipo', "nessuno") != "nessuno"
    mens      = data.get('intervento_mensile', 0)
    # round() qui invece che sul risultato finale: stesso bug float di sopra
    # (mens*12 tipo 6875.039999999999) si propagherebbe a prof_basso/prof_alto.
    costo_int_anno = round(mens * 12) if has_int else 0
    # round() e non int(): il troncamento faceva uscire il 20% di 31.828 come
    # 6.365 invece di 6.366, e la riga del profitto ereditava l'euro perso.
    _pm_costo_basso = round(ricavo_lordo * pm_bassa / 100)
    _pm_costo_alto = round(ricavo_lordo * pm_alta / 100)
    costo_pm_medio = round(ricavo_lordo * (pm_bassa + pm_alta) / 2 / 100) if has_pm else 0

    def opt_val(presente, val_str, zero_str="€ 0  (non previsto)"):
        return val_str if presente else zero_str

    pm_det = opt_val(has_pm,
        f"\u20ac {ricavo_lordo:,} x {pm_bassa}-{pm_alta}% = \u20ac {_pm_costo_basso:,} \u2013 \u20ac {_pm_costo_alto:,} / anno *".replace(",","."))
    pm_val = opt_val(has_pm,
        f"- \u20ac {_pm_costo_basso:,} / {_pm_costo_alto:,}".replace(",","."))
    int_det = opt_val(has_int,
        f"\u20ac {mens:,}/mese x 12 = \u20ac {costo_int_anno:,} / anno".replace(",","."))
    int_val = opt_val(has_int,
        f"- \u20ac {costo_int_anno:,}".replace(",","."))

    prof_basso = profitto - (_pm_costo_basso if has_pm else 0) - costo_int_anno
    prof_alto  = profitto - (_pm_costo_alto  if has_pm else 0) - costo_int_anno

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


def page4b_moltiplicatori(c, data):
    """Solo Strategico (CORE parlava di 'TABELLA MOLTIPLICATORI STRATEGICO').
    Usa SOLO il modello di incremento gia' applicato al calcolo
    deterministico del prezzo/notte reale (INCREMENTO_PREZZO_PER_DOTAZIONE
    in app.py, la stessa tabella che ha gia' corretto il prezzo mostrato nel
    resto del report) - nessun coefficiente nuovo o inventato per stato o
    posti letto, perche' nel motore deterministico attuale (AirROI) non
    esiste un modello validato per quelli: aggiungerne uno qui sarebbe lo
    stesso problema appena tolto al resto del report (numeri inventati)."""
    draw_header(c, data)
    draw_footer(c, data, 6)
    y = H - 22*mm

    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Moltiplicatori di valore - dotazioni")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y, "Quanto guadagneresti aggiungendo le dotazioni che il mercato di zona premia di piu'")
    y -= 7*mm

    righe = data.get('moltiplicatori_dotazioni') or []

    if not righe:
        box_h = 22*mm
        c.setFillColor(TEAL_LIGHT)
        c.roundRect(14*mm, y - box_h, W - 28*mm, box_h, 3*mm, fill=1, stroke=0)
        c.setStrokeColor(TEAL)
        c.setLineWidth(1)
        c.roundRect(14*mm, y - box_h, W - 28*mm, box_h, 3*mm, fill=0, stroke=1)
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(TEAL)
        c.drawString(18*mm, y - 8*mm, "Il tuo immobile ha gia' le dotazioni che il mercato premia di piu'")
        c.setFont("Helvetica", 8)
        c.setFillColor(BLUE_NIGHT)
        wrap_simple(c, "Nessun margine residuo su questo fronte: il prezzo/notte gia' mostrato nel report include per intero il bonus dotazioni calcolato per il tuo immobile.", 18*mm, y - 14*mm, W - 40*mm, "Helvetica", 8, 4.5*mm, BLUE_NIGHT)
        return

    tbl_data = [["Dotazione da aggiungere", "Incremento stimato", "Impatto su prezzo/notte", "Impatto su ricavo annuo"]]
    for nome, pct_label, delta_prezzo, delta_ricavo in righe:
        tbl_data.append([nome, pct_label, f"+€ {delta_prezzo}", f"+{fmt_eur(delta_ricavo)}"])

    col_w = [(W-28*mm)*0.34, (W-28*mm)*0.20, (W-28*mm)*0.23, (W-28*mm)*0.23]
    tbl = Table(tbl_data, colWidths=col_w)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), BLUE_NIGHT),
        ("TEXTCOLOR",     (0,0), (-1,0), WHITE),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,-1), 8),
        ("FONTNAME",      (0,1), (-1,-1), "Helvetica"),
        ("TEXTCOLOR",     (0,1), (-1,-1), BLUE_NIGHT),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, CREAM]),
        ("GRID",          (0,0), (-1,-1), 0.25, BORDER),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 5),
        ("ALIGN",         (1,0), (-1,-1), "CENTER"),
        ("TEXTCOLOR",     (2,1), (3,-1), TEAL),
        ("FONTNAME",      (2,1), (3,-1), "Helvetica-Bold"),
    ]))
    tbl.wrapOn(c, W-28*mm, 300)
    tbl.drawOn(c, 14*mm, y - tbl._height)
    y -= tbl._height + 8*mm

    disc_h = 16*mm
    c.setFillColor(GOLD_LIGHT)
    c.roundRect(14*mm, y - disc_h, W - 28*mm, disc_h, 2*mm, fill=1, stroke=0)
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.8)
    c.roundRect(14*mm, y - disc_h, W - 28*mm, disc_h, 2*mm, fill=0, stroke=1)
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(GOLD)
    c.drawString(18*mm, y - 6*mm, "Come leggere questa tabella")
    c.setFont("Helvetica", 7.5)
    c.setFillColor(BLUE_NIGHT)
    wrap_simple(c, "Impatti calcolati sullo stesso modello gia' usato per correggere il prezzo/notte reale del tuo immobile (non stime generiche): riflettono l'aumento medio di mercato osservato per ciascuna dotazione, cumulabile se ne aggiungi piu' di una.", 18*mm, y - 11*mm, W - 40*mm, "Helvetica", 7.5, 4.5*mm, BLUE_NIGHT)

# ═══════════════════════════════════════════════════════════════════════════
# PAG 4 — Analisi economica annuale
# ═══════════════════════════════════════════════════════════════════════════
def page4(c, data):
    draw_header(c, data)
    draw_footer(c, data, 4)
    y = H - 22*mm

    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Analisi economica annuale")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y, "Proiezione costi e ricavi basata sulla situazione dichiarata")
    y -= 6*mm

    p = data.get('prezzo_notte_stimato', 0)
    occ_pct = data.get('occupazione_percent', 0)
    notti = data.get('notti_anno', 0)
    comm_pct = data.get('costi_commissioni_pct', 15)
    pulizia_unit = data.get('costi_pulizie_unit', 0)
    rata_mutuo = data.get('rata_mutuo_mensile', 0)
    mutuo_annuo = rata_mutuo * 12
    # ADR/RevPAR: ricalcolati qui se il campo non arriva già corretto da
    # _ricalcola_kpi_strategico, così il numero in colonna Valore torna sempre
    # con la formula stampata di fianco (prima erano stime AI scollegate).
    _ricavo_lordo = data.get('ricavo_lordo', 0)
    adr = data.get('adr') or (round(_ricavo_lordo / notti) if notti else 0)
    revpar = data.get('revpar') or round(adr * occ_pct / 100)
    ffe = data.get('ffe_reserve', 0)
    # Il form manda la situazione mutuo in `situazione_mutuo` (come nel Base):
    # leggerla solo da `mutuo_attivo` faceva sparire la rata dalla tabella.
    mutuo_attivo = bool(data.get('mutuo_attivo', data.get('situazione_mutuo', False))) and rata_mutuo > 0

    # Sessione 68: la formula pulizie qui era rimasta "x notti", mai
    # allineata al fix Sessione 67 (pulizie per CAMBIO, non per notte) gia'
    # attivo nel Base — i valori in data.get('costi_pulizie', 0) erano gia' corretti
    # (calcolati a monte in app.py), ma il testo mostrato al cliente era
    # sbagliato/non coerente col totale. Stesso schema del Base.
    _cambi = data.get("cambi_anno")
    _sm = data.get("soggiorno_medio_notti")
    _pulizie_tot = f"{data.get('costi_pulizie', 0):,}".replace(",", ".")
    if _cambi and _sm:
        _sm_txt = f"{_sm:g}".replace(".", ",")
        _formula_pulizie = (f"€ {pulizia_unit}/cambio  x  {_cambi} cambi "
                            f"(soggiorno medio {_sm_txt} notti)  =  € {_pulizie_tot}")
    else:
        _formula_pulizie = f"€ {pulizia_unit}/cambio  x  {notti} notti  =  € {_pulizie_tot}"
    _sm_biancheria = (
        (f", soggiorno medio {_sm:g} notti".replace(".", ",") if _sm else "")
        + ", stima in scenario di gestione mista (propria/appalto a terzi)"
    )

    # 4 card dati principali situazione dichiarata
    # `situazione_inquilini` va letto esplicitamente: usarlo come ramo di default
    # faceva stampare "Con inquilini" anche con tutti e tre i flag a False (caso
    # raggiungibile dal form — i toggle vuoto/inquilini/B&B non si escludono a
    # vicenda), in contraddizione con la riga "Situazione attuale dichiarata" di
    # pagina 1 che nello stesso report diceva NO a tutti e tre. Stessa cascata e
    # stessa etichetta neutra del Base (vedi app.py).
    if data.get('situazione_vuoto', False):
        sit_label = "Immobile vuoto"
    elif data.get('situazione_bnb', False):
        sit_label = "B&B attivo"
    elif data.get('situazione_inquilini', False):
        sit_label = "Con inquilini"
    else:
        sit_label = "Non dichiarata"
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

    # Addendi effettivi di `totale_costi` (vedi app.py): l'FF&E è un
    # accantonamento mostrato a parte e NON entra nel totale.
    _addendi_costi = [
        fmt_eu(data.get('costi_commissioni', 0)),
        fmt_eu(data.get('costi_pulizie', 0)),
        fmt_eu(data.get('costi_biancheria', 0)),
        fmt_eu(data.get('costi_utenze', 0)),
        fmt_eu(data.get('costi_manutenzione', 0)),
    ]
    if mutuo_attivo:
        _addendi_costi.append(fmt_eu(mutuo_annuo))

    eco_data = [
        ["Voce", "Come viene calcolato", "Valore"],
        ["RICAVI", "", ""],
        ["Ricavo lordo annuo stimato",
         f"€ {p}/notte  x  {occ_pct}% occ.  x  365gg  =  € {p}  x  {notti} notti",
         fmt_eu(data.get('ricavo_lordo', 0))],
        ["Bonus prenotazioni dirette",
         f"€ {data.get('ricavo_lordo', 0):,}  x  {data.get('bonus_dirette_pct') or '5-10%'}  =  € {data.get('bonus_dirette', 0):,}".replace(",","."),
         fmt_eu(data.get('bonus_dirette', 0))],
        ["TOTALE RICAVI",
         f"{fmt_eu(data.get('ricavo_lordo', 0))}  +  {fmt_eu(data.get('bonus_dirette', 0))}",
         fmt_eu(data.get('totale_ricavi', 0))],
        ["COSTI DI GESTIONE", f"Media di mercato per tipologia: {data.get('scheda_tipologia') or data.get('tipologia', 'immobile')}", ""],
        ["Commissioni piattaforma Airbnb",
         f"€ {data.get('ricavo_lordo', 0):,}  x  {comm_pct}%  =  € {data.get('costi_commissioni', 0):,}".replace(",","."),
         f"- {fmt_eu(data.get('costi_commissioni', 0))}"],
        ["Pulizie per cambio ospite", _formula_pulizie,
         f"- {fmt_eu(data.get('costi_pulizie', 0))}"],
        ["Biancheria e consumabili",
         f"€ {fmt_num(data.get('costi_biancheria', 0))}/anno (media di mercato per la tipologia)",
         f"- {fmt_eu(data.get('costi_biancheria', 0))}"],
        # Stessa formulazione del Base: le "convenzioni adottate" e i range
        # sono stati tolti da entrambi i prodotti, resta la voce come media di
        # mercato per la tipologia.
        ["Utenze aggiuntive stimate",
         f"€ {data.get('costi_utenze', 0):,}/anno (media di mercato per la tipologia)".replace(",","."),
         f"- {fmt_eu(data.get('costi_utenze', 0))}"],
        ["Manutenzione ordinaria",
         f"€ {data.get('costi_manutenzione', 0):,}/anno (media di mercato per la tipologia)".replace(",","."),
         f"- {fmt_eu(data.get('costi_manutenzione', 0))}"],
        # Accantonamento consigliato, non sottratto dal totale sotto: il
        # segno "-" faceva sembrare che fosse già conteggiato.
        ["FF&E Reserve (manutenzione straord.)",
         f"€ {fmt_num(ffe)}/anno per arredi e dotazioni (non incluso nel totale)",
         fmt_eu(ffe)],
        ["Rata mutuo (se presente)",
         "Nessun mutuo dichiarato" if not mutuo_attivo else f"€ {rata_mutuo}/mese  x  12 mesi",
         "€ 0" if not mutuo_attivo else f"- {fmt_eu(mutuo_annuo)}"],
        # La formula elencava anche l'FF&E e ometteva il mutuo, mentre il
        # totale calcolato dal backend fa l'opposto: sommando le voci a video
        # non tornava il numero stampato di fianco. Ora la stringa elenca
        # esattamente gli addendi che compongono `totale_costi`.
        ["TOTALE COSTI DI GESTIONE",
         "  +  ".join(_addendi_costi),
         f"- {fmt_eu(data.get('totale_costi', 0))}"],
        ["PROFITTO NETTO STIMATO",
         f"{fmt_eu(data.get('totale_ricavi', 0))}  -  {fmt_eu(data.get('totale_costi', 0))}",
         fmt_eu(data.get('profitto_netto', 0))],
        # La formula divide per i ricavi TOTALI (lordi + bonus dirette), non
        # per i soli lordi: l'etichetta diceva il contrario ed era l'unica
        # riga della tabella in cui testo e calcolo non coincidevano.
        ["Margine netto su ricavi totali",
         f"{fmt_eu(data.get('profitto_netto', 0))}  /  {fmt_eu(data.get('totale_ricavi', 0))}  x  100",
         f"{data.get('margine_percent', 0)}%"],
        ["KPI — ADR (Average Daily Rate)",
         f"Ricavo lordo  /  Notti occupate  =  € {data.get('ricavo_lordo', 0):,}  /  {notti}".replace(",","."),
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
        # Riga 11 = FF&E: è un accantonamento consigliato, non entra nel totale
        # sotto. In rosso come le altre voci sembrava un costo già sottratto.
        ("TEXTCOLOR",     (2,11), (2,11),  MUTED),
        ("FONTNAME",      (0,11), (-1,11), "Helvetica-Oblique"),
        # Riga 12 = rata mutuo (l'indice qui diceva 13, che è il TOTALE).
        ("TEXTCOLOR",     (2,12), (2,12),  MUTED if not mutuo_attivo else RED),
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

    # Il dettaglio "soggiorno medio + gestione mista" era dentro la cella
    # biancheria e la mandava fuori tabella (riga singola, ReportLab non
    # avvolge le celle stringa). Il dato resta ma come nota sotto la
    # tabella; la cella torna alla stessa lunghezza di Utenze/Manutenzione.
    _nota_biancheria = "Biancheria e consumabili" + _sm_biancheria + "."
    y = wrap_simple(c, _nota_biancheria, 14*mm, y, W - 28*mm,
                     "Helvetica-Oblique", 6.5, 3.2*mm, color=MUTED)
    y -= 3*mm

    # 4 card: margine grigio, ricavo verde, costi rosso, guadagno gold (più grande)
    total_w = W - 28*mm
    small_w = (total_w - 6*mm) * 0.26
    big_w   = total_w - 3*small_w - 6*mm
    small_h = 18*mm
    big_h   = 24*mm

    cards4 = [
        ("Margine netto",          f"{data.get('margine_percent', 0)}%",          WHITE,      BLUE_NIGHT, small_w, small_h),
        ("Totale ricavi",          fmt_eur(data.get('totale_ricavi', 0)),          TEAL_LIGHT, TEAL,       small_w, small_h),
        ("Costi di gestione totali", f"- {fmt_eur(data.get('totale_costi', 0))}",   RED_LIGHT,  RED,        small_w, small_h),
        ("Il tuo guadagno stimato",fmt_eur(data.get('profitto_netto', 0)),         GOLD_LIGHT, GOLD,       big_w,   big_h),
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
    draw_footer(c, data, 7)
    y = H - 22*mm

    # ── CONFRONTO AFFITTO TRADIZIONALE ──
    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Confronto con affitto tradizionale")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y, "Proiezione annuale · affitto tradizionale vs B&B short rent")
    y -= 6*mm

    # Stesso criterio del Base: la colonna "Affitto tradizionale" mostra un
    # range +-10% invece del numero secco, la Differenza resta calcolata sul
    # valore preciso (altrimenti il conto non tornerebbe).
    def _fmt_range_eu(valore):
        basso = round(valore * 0.9)
        alto = round(valore * 1.1)
        return f"{fmt_eu(basso)} - {fmt_eu(alto)}"

    def _fmt_diff_range_eu(esatto, valore_affitto):
        # Il B&B è un valore secco, l'affitto tradizionale è un range +-10%:
        # la differenza eredita lo stesso range (estremo alto dell'affitto
        # -> differenza minima, estremo basso -> differenza massima).
        basso = esatto - round(valore_affitto * 1.1)
        alto = esatto - round(valore_affitto * 0.9)
        segno_b = "+" if basso >= 0 else "-"
        segno_a = "+" if alto >= 0 else "-"
        return f"{segno_b}{fmt_eu(abs(int(basso)))} - {segno_a}{fmt_eu(abs(int(alto)))}"

    conf_data = [
        ["", "Affitto tradizionale", "B&B / Short rent", "Differenza"],
        ["Ricavo annuo lordo",
         _fmt_range_eu(data.get('affitto_ricavo', 0)), fmt_eu(data.get('ricavo_lordo', 0)),
         _fmt_diff_range_eu(data.get('ricavo_lordo', 0), data.get('affitto_ricavo', 0))],
        ["Costi di gestione",
         _fmt_range_eu(data.get('affitto_costi', 0)), fmt_eu(data.get('totale_costi', 0)),
         _fmt_diff_range_eu(data.get('totale_costi', 0), data.get('affitto_costi', 0))],
        ["Profitto netto",
         _fmt_range_eu(data.get('affitto_profitto', 0)), fmt_eu(data.get('profitto_netto', 0)),
         _fmt_diff_range_eu(data.get('profitto_netto', 0), data.get('affitto_profitto', 0))],
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
        ("TEXTCOLOR",     (3,2),  (3,2),   TEAL), ("FONTNAME", (3,2), (3,2), "Helvetica-Bold"),
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
    for mese_it, mese_en, prezzo, occ_p, ricavo, evento in data.get('pricing_mensile', []):
        pr_data.append([
            f"{mese_it} / {mese_en}",
            f"\u20ac {prezzo}",
            f"{occ_p}%",
            f"\u20ac {ricavo:,}".replace(",","."),
            evento,
        ])

    # Totali
    tot_ricavo = sum(r[4] for r in data.get('pricing_mensile', []))
    # Etichetta "Scenario ottimistico" rimossa: il totale \u00e8 la somma dei 12
    # mesi calcolati sugli stessi prezzi e occupazioni dell'analisi economica,
    # quindi \u00e8 il ricavo lordo di riferimento, non uno scenario a parte.
    pr_data.append(["TOTALE ANNUO", "", "", f"\u20ac {tot_ricavo:,}".replace(",","."), "Ricavo lordo annuo stimato"])

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
    for ri, row in enumerate(data.get('pricing_mensile', [])):
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
    adr = data.get('adr', 0)
    revpar = data.get('revpar', 0)
    nota_pr = f"ADR (Average Daily Rate) ponderato annuo: \u20ac {adr}  \u00b7  RevPAR: \u20ac {revpar}  \u00b7  I prezzi si aggiornano automaticamente in base ai dati di mercato della zona al momento della generazione del report."
    wrap_simple(c, nota_pr, 14*mm, y, W-28*mm, "Helvetica-Oblique", 7, 4.5*mm, MUTED)

# ═══════════════════════════════════════════════════════════════════════════
# PAG 6 — Normativa affitti brevi
# ═══════════════════════════════════════════════════════════════════════════
def page6(c, data):
    draw_header(c, data)
    draw_footer(c, data, 12)
    y = H - 22*mm

    y = draw_section_header(c, 14*mm, y, W - 28*mm,
        f"Normativa affitti brevi — {data.get('comune_normativa', '')} / {data.get('regione_normativa', '')} "
        f"\u00b7 {datetime.date.today().year}")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y, "Obblighi normativi vigenti alla data di generazione del report")
    y -= 6*mm

    # Celle come Paragraph: prima erano stringhe semplici, che in ReportLab non
    # vanno mai a capo ("WORDWRAP" non è un comando di TableStyle e veniva
    # ignorato). I testi normativi sono lunghi e finivano uno sopra l'altro,
    # sconfinando nelle colonne accanto e fuori pagina.
    stile_voce  = ParagraphStyle("normVoce",  fontName="Helvetica-Bold", fontSize=7, textColor=BLUE_PRIMARY, leading=9)
    stile_dett  = ParagraphStyle("normDett",  fontName="Helvetica",      fontSize=7, textColor=BLUE_NIGHT,   leading=9)
    stile_stato = ParagraphStyle("normStato", fontName="Helvetica",      fontSize=7, textColor=BLUE_NIGHT,   leading=9)
    stile_head  = ParagraphStyle("normHead",  fontName="Helvetica-Bold", fontSize=7, textColor=WHITE,        leading=9)

    norm_data = [[Paragraph(h, stile_head) for h in ("Obbligo / Voce", "Dettaglio", "Stato")]]
    for riga in data.get('normativa_extra', []):
        voce, dettaglio, stato = (list(riga) + ["", "", ""])[:3]
        norm_data.append([
            Paragraph(str(voce), stile_voce),
            Paragraph(str(dettaglio), stile_dett),
            Paragraph(str(stato), stile_stato),
        ])

    col_w_norm = [(W-28*mm)*0.26, (W-28*mm)*0.56, (W-28*mm)*0.18]
    tbl_norm = Table(norm_data, colWidths=col_w_norm)
    tbl_norm.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), BLUE_NIGHT),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, CREAM]),
        ("GRID",          (0,0), (-1,-1), 0.25, BORDER),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 5),
        ("RIGHTPADDING",  (0,0), (-1,-1), 5),
        ("BACKGROUND",    (0,1), (0,-1), HexColor("#E3F2FA")),
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
    c.drawString(18*mm, y - 6*mm, "Nota legale importante")
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
    draw_footer(c, data, 13)
    y = H - 22*mm

    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Valore immobile come asset B&B — Analisi professionale")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y, "Metodologia da modello di valutazione bancaria professionale")
    y -= 7*mm

    saggio = data.get('saggio_capitalizzazione', 0)
    ebitda = data.get('ebitda_stimato', 0)
    valore = data.get('valore_mercato', 0)
    v_stimato = data.get('valore_immobile_stimato', 0)

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
        # A zero si scriveva "€ 0", che davanti a un cliente si legge come
        # "il tuo immobile non vale niente". Le due righe sotto già dicono n/d
        # per lo stesso motivo: qui mancava.
        ["Valore immobile stimato (mercato)",
         "Stima da banche dati OMI per zona e tipologia"
         if v_stimato else "Non disponibile per questa zona: nessuna stima OMI di compravendita",
         fmt_eu(v_stimato) if v_stimato else "n/d"],
        # v_stimato arriva dall'AI e nel template del prompt vale 0: il backend
        # non lo calcola (nessuna stima OMI di compravendita oggi). Senza
        # guardia il Cap Rate divideva per zero e faceva fallire con 500
        # l'INTERO PDF, non solo questa riga \u2014 nessun report Strategico veniva
        # mai consegnato. Quando il dato manca si dichiara n/d, non si inventa.
        ["Differenza valore asset vs mercato",
         f"{fmt_eu(valore)}  -  {fmt_eu(v_stimato)}" if v_stimato else
         "Richiede la stima di mercato dell'immobile, non disponibile per questa zona",
         (fmt_eu(valore - v_stimato) if valore > v_stimato else f"- {fmt_eu(v_stimato - valore)}")
         if v_stimato else "n/d"],
        ["Cap Rate effettivo",
         f"EBITDA  /  Valore mercato  x  100  =  \u20ac {ebitda:,}  /  \u20ac {v_stimato:,}  x  100".replace(",",".")
         if v_stimato else "Richiede la stima di mercato dell'immobile, non disponibile per questa zona",
         f"{round(ebitda/v_stimato*100, 2)}%" if v_stimato else "n/d"],
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
    draw_footer(c, data, 8)
    y = H - 22*mm

    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Tre scenari economici — proiezione annuale")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y, "Basati sui dati reali dell\u2019analisi economica · Lo scenario realistico \u00e8 il riferimento principale")
    y -= 7*mm

    scenari = [data.get('scenario_pess', {}), data.get('scenario_real', {}), data.get('scenario_ott', {})]
    colori  = [RED, BLUE_PRIMARY, GOLD]
    bg_col  = [RED_LIGHT, HexColor("#E3F4FC"), GOLD_LIGHT]

    # Card più alta e passo righe più stretto per liberare in fondo una fascia
    # dedicata alla nota, che prima usciva sotto il riquadro colorato.
    box_w = (W - 34*mm) / 3
    passo_riga = 9*mm
    nota_h = altezza_nota(c, [s.get("note", "") for s in scenari], box_w)
    box_h = 13*mm + 5*mm + 6*passo_riga + nota_h

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
        # Il sottotitolo dello scenario è testo libero dell'AI: a corpo fisso
        # usciva dai bordi della card colorata su entrambi i lati.
        draw_centred_fit(c, bx+box_w/2, by+box_h-11.5*mm, sc.get("subtitle", ""),
                         box_w - 4*mm, "Helvetica", 7, line_h=3.2*mm, min_size=5)

        # Dati
        righe = [
            ("Occupazione media", f"{sc['occupazione']}%"),
            ("Notti vendute",     f"{sc['notti']} / anno"),
            ("Prezzo medio notte",f"€ {sc['prezzo_medio']}"),
            ("Ricavi totali",     fmt_eur(sc["ricavi_lordi"])),
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
            dy -= passo_riga

        # Nota: fascia dedicata in fondo alla card, testo pieno nel colore
        # dello scenario — è un suggerimento operativo, va letto.
        draw_nota_card(c, sc.get("note", ""), bx, by + 3*mm, box_w, nota_h - 3*mm, colore=col)

    y -= box_h + 8*mm

    # Confronto tabella
    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Confronto scenari — tabella riassuntiva")
    y -= 5*mm

    pess = data.get('scenario_pess', {})
    real = data.get('scenario_real', {})
    ott  = data.get('scenario_ott', {})

    conf_data = [
        ["Voce", "Pessimistico", "Realistico", "Ottimistico"],
        ["Occupazione media",  f"{pess['occupazione']}%", f"{real['occupazione']}%", f"{ott['occupazione']}%"],
        ["Notti vendute/anno", str(pess["notti"]),        str(real["notti"]),         str(ott["notti"])],
        ["Prezzo medio/notte", f"€ {pess['prezzo_medio']}", f"€ {real['prezzo_medio']}", f"€ {ott['prezzo_medio']}"],
        ["Ricavi totali",      fmt_eur(pess["ricavi_lordi"]),  fmt_eur(real["ricavi_lordi"]),  fmt_eur(ott["ricavi_lordi"])],
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
# PAG 8B — 3 scenari per durata soggiorno (B7)
# ═══════════════════════════════════════════════════════════════════════════
def page8b_durata(c, data):
    """Solo Strategico (B7). Stesso ricavo lordo (occupazione/prezzo sono un
    dato di mercato, non una scelta dell'host) nei 3 scenari — cambia solo
    il numero di cambi ospite/anno e quindi i costi di pulizia, a seconda
    del min-stay che l'host imposta su Airbnb/Booking. Dati precalcolati da
    _calcola_scenari_durata_soggiorno in app.py."""
    draw_header(c, data)
    draw_footer(c, data, 9)
    y = H - 22*mm

    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Quanto costa il turnover — 3 scenari per durata soggiorno")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y, "Stesso ricavo lordo · costi di pulizia molto diversi a seconda del min-stay che scegli")
    y -= 7*mm

    scenari = data.get('scenari_durata') or []
    if not scenari:
        box_h = 22*mm
        c.setFillColor(CREAM)
        c.roundRect(14*mm, y - box_h, W - 28*mm, box_h, 3*mm, fill=1, stroke=0)
        c.setFont("Helvetica", 8.5)
        c.setFillColor(MUTED)
        wrap_simple(c, "Dati insufficienti per calcolare gli scenari per durata soggiorno di questo immobile.", 18*mm, y - 12*mm, W - 40*mm, "Helvetica", 8.5, 4.5*mm, MUTED)
        return

    ricavi_lordi = data.get('totale_ricavi', 0)
    colori = [GOLD, BLUE_PRIMARY, TEAL]
    bg_col = [GOLD_LIGHT, HexColor("#E3F4FC"), TEAL_LIGHT]

    box_w = (W - 34*mm) / 3
    passo_riga = 9*mm
    nota_h = altezza_nota(c, [s.get("nota", "") for s in scenari], box_w)
    box_h = 13*mm + 5*mm + 6*passo_riga + nota_h

    for i, (sc, col, bg) in enumerate(zip(scenari, colori, bg_col)):
        bx = 14*mm + i*(box_w + 3*mm)
        by = y - box_h
        c.setFillColor(bg)
        c.roundRect(bx, by, box_w, box_h, 3*mm, fill=1, stroke=0)
        c.setStrokeColor(col)
        c.setLineWidth(1.5)
        c.roundRect(bx, by, box_w, box_h, 3*mm, fill=0, stroke=1)

        c.setFillColor(col)
        c.roundRect(bx, by+box_h-13*mm, box_w, 13*mm, 3*mm, fill=1, stroke=0)
        c.rect(bx, by+box_h-13*mm, box_w, 6*mm, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(WHITE)
        c.drawCentredString(bx+box_w/2, by+box_h-7*mm, sc["label"])
        c.setFont("Helvetica", 7)
        c.drawCentredString(bx+box_w/2, by+box_h-11.5*mm, f"{sc['durata']:g} notti/soggiorno")

        righe = [
            ("Cambi ospite/anno",  str(sc["cambi"])),
            ("Ricavi totali",      fmt_eur(ricavi_lordi)),
            ("Costi pulizia",      fmt_eur(sc["costi_pulizie"])),
            ("Costi totali",       fmt_eur(sc["costi_totali"])),
            ("Profitto netto",     fmt_eur(sc["profitto_netto"])),
            ("Margine",            f"{sc['margine']}%"),
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
            dy -= passo_riga

        draw_nota_card(c, sc.get("nota", ""), bx, by + 3*mm, box_w, nota_h - 3*mm, colore=col)

    y -= box_h + 8*mm

    disc_h = 16*mm
    c.setFillColor(GOLD_LIGHT)
    c.roundRect(14*mm, y - disc_h, W - 28*mm, disc_h, 2*mm, fill=1, stroke=0)
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.8)
    c.roundRect(14*mm, y - disc_h, W - 28*mm, disc_h, 2*mm, fill=0, stroke=1)
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(GOLD)
    c.drawString(18*mm, y - 6*mm, "Come leggere questa pagina")
    c.setFont("Helvetica", 7.5)
    c.setFillColor(BLUE_NIGHT)
    wrap_simple(c, "Il ricavo lordo non cambia: occupazione e prezzo/notte sono un dato di mercato, non una scelta dell'host. A cambiare e' solo il numero di cambi ospite/anno (e quindi i costi di pulizia) in base al min-stay che imposti su Airbnb/Booking: piu' soggiorni brevi accetti, piu' pulizie paghi.", 18*mm, y - 11*mm, W - 40*mm, "Helvetica", 7.5, 4.5*mm, BLUE_NIGHT)

# ═══════════════════════════════════════════════════════════════════════════
# PAG 8C — Dati di mercato extra (B9)
# ═══════════════════════════════════════════════════════════════════════════
def _posiziona_percentile(valore, perc):
    p25, p50, p75, p90 = perc.get('p25', 0), perc.get('p50', 0), perc.get('p75', 0), perc.get('p90', 0)
    if valore < p25:   return "sotto il 25° percentile di zona"
    if valore < p50:   return "tra il 25° e il 50° percentile di zona"
    if valore < p75:   return "tra il 50° e il 75° percentile di zona"
    if valore < p90:   return "tra il 75° e il 90° percentile di zona"
    return "sopra il 90° percentile di zona"

def page8c_mercato(c, data):
    """Solo Strategico (B9). Percentili prezzo/occupazione, split gestione
    professionale/privata e posizionamento stagionale (ultimi 90gg vs media
    12 mesi) sui comparabili reali AirROI della zona — dati sempre esistiti
    nella risposta API ma mai letti fino a quando una chiamata reale via
    /debug-airroi-raw non ne ha confermato la struttura (RU_Log_Sessione_
    2026-08-27, 'Punto 0'). Ogni sezione si nasconde da sola se il dato non
    e' disponibile per questa zona (AirROI non copre tutti i comuni)."""
    draw_header(c, data)
    draw_footer(c, data, 10)
    y = H - 22*mm

    # La fascia "Dati di mercato extra" che apriva la pagina è stata rimossa:
    # era un'intestazione senza contenuto proprio, subito seguita da quella dei
    # percentili. Al suo posto apre la pagina la tabella competitor, identica a
    # quella del Base (pag. 4) — stesso tema, comparabili reali della zona.
    y = draw_competitor(c, data, y)

    perc_p = data.get('percentili_prezzo')
    perc_o = data.get('percentili_occupazione')
    pct_gest = data.get('pct_gestione_professionale')
    n_gest = data.get('n_comparabili_gestione') or 0
    trend = data.get('trend_stagionale')

    if not (perc_p or perc_o or pct_gest is not None or trend):
        box_h = 26*mm
        c.setFillColor(CREAM)
        c.roundRect(14*mm, y - box_h, W - 28*mm, box_h, 3*mm, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColor(MUTED)
        c.drawString(18*mm, y - 8*mm, "Dati di mercato extra non disponibili per questa zona")
        c.setFont("Helvetica", 8)
        wrap_simple(c, "AirROI non ha comparabili sufficienti su questo comune per calcolare percentili, tipo di gestione o posizionamento stagionale. Il resto del report (prezzo, occupazione, scenari) resta affidabile: usa gli stessi dati di zona a livello aggregato, dove disponibili.", 18*mm, y - 14*mm, W - 40*mm, "Helvetica", 8, 4.5*mm, BLUE_NIGHT)
        return

    # ── Sezione A: percentili prezzo/occupazione ──
    if perc_p or perc_o:
        y = draw_section_header(c, 14*mm, y, W - 28*mm, "Percentili reali di zona — prezzo e occupazione")
        y -= 5*mm
        tbl_data = [["", "Prezzo/notte", "Occupazione"]]
        for label, key in [("P25 (fascia bassa)", 'p25'), ("Mediana (P50)", 'p50'),
                            ("P75 (fascia alta)", 'p75'), ("P90 (top di zona)", 'p90')]:
            riga_prezzo = f"€ {perc_p[key]}" if perc_p else "n/d"
            riga_occ = f"{perc_o[key]}%" if perc_o else "n/d"
            tbl_data.append([label, riga_prezzo, riga_occ])
        col_w = [(W-28*mm)*0.42, (W-28*mm)*0.29, (W-28*mm)*0.29]
        tbl = Table(tbl_data, colWidths=col_w)
        tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0), BLUE_NIGHT),
            ("TEXTCOLOR",     (0,0), (-1,0), WHITE),
            ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",      (0,0), (-1,-1), 8),
            ("FONTNAME",      (0,1), (-1,-1), "Helvetica"),
            ("TEXTCOLOR",     (0,1), (-1,-1), BLUE_NIGHT),
            ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, CREAM]),
            ("GRID",          (0,0), (-1,-1), 0.25, BORDER),
            ("TOPPADDING",    (0,0), (-1,-1), 4.5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4.5),
            ("LEFTPADDING",   (0,0), (-1,-1), 5),
            ("ALIGN",         (1,0), (-1,-1), "CENTER"),
        ]))
        tbl.wrapOn(c, W-28*mm, 200)
        tbl.drawOn(c, 14*mm, y - tbl._height)
        y -= tbl._height + 3*mm

        note_bits = []
        if perc_p and data.get('prezzo_notte_stimato'):
            note_bits.append(f"Il tuo prezzo/notte (€ {data['prezzo_notte_stimato']}) e' {_posiziona_percentile(data['prezzo_notte_stimato'], perc_p)}.")
        if perc_o and data.get('occupazione_percent') is not None:
            note_bits.append(f"La tua occupazione ({data['occupazione_percent']}%) e' {_posiziona_percentile(data['occupazione_percent'], perc_o)}.")
        if note_bits:
            c.setFont("Helvetica-Oblique", 7.5)
            c.setFillColor(MUTED)
            y = wrap_simple(c, " ".join(note_bits), 14*mm, y - 2*mm, W - 28*mm, "Helvetica-Oblique", 7.5, 4*mm, MUTED)
        y -= 5*mm

    # ── Sezione B: gestione professionale vs privata ──
    if pct_gest is not None:
        y = draw_section_header(c, 14*mm, y, W - 28*mm, "Chi gestisce gli annunci in questa zona")
        y -= 3*mm
        draw_section_subtitle(c, 14*mm, y, f"Campione: {n_gest} annunci comparabili reali")
        y -= 7*mm

        card_w = (W - 32*mm) / 2
        card_h = 22*mm
        cards = [("Gestione professionale", f"{pct_gest}%", GOLD, GOLD_LIGHT),
                 ("Host privati", f"{100 - pct_gest}%", TEAL, TEAL_LIGHT)]
        for i, (lbl, val, col, bg) in enumerate(cards):
            cx = 14*mm + i*(card_w + 4*mm)
            c.setFillColor(bg)
            c.roundRect(cx, y - card_h, card_w, card_h, 3*mm, fill=1, stroke=0)
            c.setStrokeColor(col)
            c.setLineWidth(1)
            c.roundRect(cx, y - card_h, card_w, card_h, 3*mm, fill=0, stroke=1)
            c.setFont("Helvetica-Bold", 15)
            c.setFillColor(col)
            c.drawCentredString(cx + card_w/2, y - 10*mm, val)
            c.setFont("Helvetica", 8)
            c.setFillColor(BLUE_NIGHT)
            c.drawCentredString(cx + card_w/2, y - 17*mm, lbl)
        y -= card_h + 8*mm

    # ── Sezione C: posizionamento stagionale ──
    if trend:
        y = draw_section_header(c, 14*mm, y, W - 28*mm, "Posizionamento stagionale — ultimi 90 giorni vs media 12 mesi")
        y -= 3*mm
        draw_section_subtitle(c, 14*mm, y, "Non e' un trend pluriennale: confronta la stagione corrente con la media dell'intero anno")
        y -= 6*mm

        trend_data = [
            ["Indicatore", "Ultimi 90 giorni", "Media 12 mesi (TTM)"],
            ["Occupazione media", f"{trend['occupazione_l90d']}%", f"{trend['occupazione_ttm']}%"],
            ["Prezzo medio/notte", f"€ {trend['prezzo_l90d']}", f"€ {trend['prezzo_ttm']}"],
            ["RevPAR", f"€ {trend['revpar_l90d']}", f"€ {trend['revpar_ttm']}"],
        ]
        col_w_t = [(W-28*mm)*0.34, (W-28*mm)*0.33, (W-28*mm)*0.33]
        tbl_t = Table(trend_data, colWidths=col_w_t)
        tbl_t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0), BLUE_NIGHT),
            ("TEXTCOLOR",     (0,0), (-1,0), WHITE),
            ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",      (0,0), (-1,-1), 8),
            ("FONTNAME",      (0,1), (-1,-1), "Helvetica"),
            ("TEXTCOLOR",     (0,1), (-1,-1), BLUE_NIGHT),
            ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, CREAM]),
            ("GRID",          (0,0), (-1,-1), 0.25, BORDER),
            ("TOPPADDING",    (0,0), (-1,-1), 4.5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4.5),
            ("LEFTPADDING",   (0,0), (-1,-1), 5),
            ("ALIGN",         (1,0), (-1,-1), "CENTER"),
        ]))
        tbl_t.wrapOn(c, W-28*mm, 200)
        tbl_t.drawOn(c, 14*mm, y - tbl_t._height)
        y -= tbl_t._height + 8*mm

    disc_h = 14*mm
    c.setFillColor(GOLD_LIGHT)
    c.roundRect(14*mm, y - disc_h, W - 28*mm, disc_h, 2*mm, fill=1, stroke=0)
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.8)
    c.roundRect(14*mm, y - disc_h, W - 28*mm, disc_h, 2*mm, fill=0, stroke=1)
    c.setFont("Helvetica", 7.5)
    c.setFillColor(BLUE_NIGHT)
    wrap_simple(c, "Dati aggregati sui comparabili reali restituiti da AirROI per questa zona (stesso motore che calcola prezzo/occupazione del tuo immobile) — non stime AI.", 18*mm, y - 6*mm, W - 40*mm, "Helvetica", 7.5, 4.5*mm, BLUE_NIGHT)

# ═══════════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════
# PAG 9 — Piano d'azione 90 giorni
# ═══════════════════════════════════════════════════════════════════════════
def page9(c, data):
    draw_header(c, data)
    draw_footer(c, data, 11)
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


    # Bug fix (riapertura cantiere Strategico): il JSON reale (prompt +
    # route /generate-strategico) descrive piano_90 come lista di DICT
    # {"titolo","colore":"BLU/VERDE/GOLD","azioni":[...]} — la stringa
    # "colore" va tradotta nell'oggetto Color di ReportLab, non passata
    # direttamente a setFillColor(). Prima questo ciclo si aspettava tuple
    # (titolo, ColorObject, azioni) come nel fac-simile locale hardcoded
    # (PDF/genera_strategico_reportup.py, dati finti): su un JSON reale
    # avrebbe spacchettato le CHIAVI del dict come se fossero i tre valori.
    _colore_piano90 = {"BLU": BLUE_PRIMARY, "VERDE": TEAL, "GOLD": GOLD}
    fasi = []
    for fase in (data.get("piano_90") or []):
        fasi.append((
            fase.get("titolo", "") if isinstance(fase, dict) else fase[0],
            _colore_piano90.get(fase.get("colore", "BLU"), BLUE_PRIMARY) if isinstance(fase, dict) else fase[1],
            (fase.get("azioni") or []) if isinstance(fase, dict) else fase[2],
        ))

    # Quante azioni scrive l'AI non è prevedibile: con tre fasi piene l'ultima
    # riga finiva sotto il footer. Si misura prima l'ingombro e si stringe
    # progressivamente corpo e spaziature finché il piano sta tutto in pagina,
    # invece di scriverlo a passo fisso e sperare che basti.
    larghezza_testo = W - 34*mm
    spazio = y - 13*mm  # fondo pagina utile, sopra la fascia del footer

    def _righe(testo, size):
        n, linea = 0, ""
        for parola in str(testo).split():
            prova = f"{linea} {parola}".strip()
            if c.stringWidth(prova, "Helvetica", size) > larghezza_testo and linea:
                n += 1
                linea = parola
            else:
                linea = prova
        return n + 1 if linea else max(n, 1)

    # Ogni azione consuma anche lo scarto fra la quota corrente e la prima
    # riga di testo (offset del pallino): con 18 azioni sono ~45 mm, ignorarli
    # faceva scegliere un passo troppo largo e l'ultima riga finiva comunque
    # sotto il footer.
    offset_item = 2.5*mm

    def _ingombro(size, line_h, gap_item, gap_fase, header_h):
        totale = 0
        for _, _, items in fasi:
            totale += header_h
            for item in items:
                totale += offset_item + _righe(item, size) * line_h + gap_item
            totale += gap_fase
        return totale

    # Dal passo comodo a quello più compatto ancora leggibile.
    livelli = [
        (7.5, 4.2*mm, 1.8*mm, 4.0*mm, 7.5*mm),
        (7.2, 4.0*mm, 1.5*mm, 3.6*mm, 7.5*mm),
        (7.0, 3.9*mm, 1.2*mm, 3.2*mm, 7.0*mm),
        (6.7, 3.7*mm, 1.0*mm, 2.8*mm, 7.0*mm),
        (6.4, 3.5*mm, 0.8*mm, 2.4*mm, 6.5*mm),
        (6.0, 3.3*mm, 0.6*mm, 2.0*mm, 6.5*mm),
        (5.6, 3.1*mm, 0.5*mm, 1.6*mm, 6.0*mm),
    ]
    size, line_h, gap_item, gap_fase, header_h = livelli[-1]
    for livello in livelli:
        if _ingombro(*livello) <= spazio:
            size, line_h, gap_item, gap_fase, header_h = livello
            break

    barra_h = header_h - 1*mm
    for fase_label, col, items in fasi:
        c.setFillColor(col)
        c.roundRect(14*mm, y - barra_h, W - 28*mm, barra_h, 2*mm, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", min(8, size + 1))
        c.setFillColor(WHITE)
        c.drawString(18*mm, y - barra_h + 1.9*mm, fase_label)
        y -= header_h

        for item in items:
            c.setFillColor(col)
            c.circle(17*mm, y - 1.5*mm, 1.2*mm, fill=1, stroke=0)
            # Le azioni sono frasi lunghe scritte dall'AI: senza a capo
            # uscivano ben oltre il margine destro della pagina.
            y_dopo = wrap_simple(c, item, 20*mm, y - offset_item, larghezza_testo,
                                 "Helvetica", size, line_h, color=BLUE_NIGHT)
            y = y_dopo - gap_item

        y -= gap_fase

# ═══════════════════════════════════════════════════════════════════════════
# PAG 10 — Analisi personale Arch. Sica
# ═══════════════════════════════════════════════════════════════════════════
def page10(c, data):
    draw_header(c, data)
    draw_footer(c, data, 14)
    y = H - 22*mm

    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Analisi personale — Arch. Salvatore Junior Sica")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y, "Valutazione professionale in 4 aree tematiche · 30.000+ valutazioni immobiliari")
    y -= 7*mm

    aree = [
        ("Posizione e contesto di mercato", data.get('analisi_posizione', ''),   BLUE_PRIMARY),
        ("Condizione e caratteristiche immobile", data.get('analisi_condizione', ''),  TEAL),
        ("Potenzialit\u00e0 e proiezioni", data.get('analisi_potenzialita', ''), GOLD),
        ("Raccomandazione operativa", data.get('analisi_raccomandazione', ''), BLUE_NIGHT),
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
    draw_footer(c, data, 17)
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
         f"Stima comparativa: prezzo/notte medio (fonte AirROI) x 30 giorni, scontato del "
         f"{data.get('sconto_affitto_tradizionale_pct', 40)}% per riflettere il differenziale tipico "
         f"tra locazione tradizionale e affitto breve sulla stessa unità e zona."),
        ("Dati demografici e turistici",
         "ISTAT — Istituto Nazionale di Statistica. Movimento turistico, arrivi e presenze per comune."),
        ("Normativa affitti brevi",
         f"Regione {data.get('regione_normativa', '')} \u00b7 Comune di {data.get('comune_normativa', '')} \u00b7 Ministero del Turismo \u00b7 Fonti ufficiali aggiornate 2025."),
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
        # Le descrizioni più lunghe (canoni affitto tradizionale) uscivano
        # oltre il margine destro: ora vanno a capo dentro la colonna.
        y_desc = wrap_simple(c, desc, 20*mm, y - 6.5*mm, W - 34*mm,
                             "Helvetica", 7, 4*mm, color=MUTED)
        c.setStrokeColor(BORDER)
        c.setLineWidth(0.3)
        riga_y = min(y - 9*mm, y_desc - 1*mm)
        c.line(14*mm, riga_y, W - 14*mm, riga_y)
        y = riga_y - 4*mm

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
    draw_footer(c, data, 15)
    y = H - 22*mm

    y = draw_section_header(c, 14*mm, y, W - 28*mm, "I tuoi obiettivi — dove trovare le risposte")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y, "Riepilogo di ci\u00f2 che hai dichiarato \u00b7 le sezioni del report pi\u00f9 rilevanti per te")
    y -= 8*mm

    obiettivi = data.get('obiettivi_selezionati', [])
    pagine_map = data.get('obiettivi_pagine', {})

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

        # Titolo e descrizione si fermano prima del bottone: a piena larghezza
        # la descrizione ci finiva sotto.
        testo_max_w = pill_x - 20*mm - 4*mm

        c.setFont("Helvetica-Bold", 13)
        c.setFillColor(BLUE_NIGHT)
        c.drawString(20*mm, y - 9*mm, titolo)

        wrap_simple(c, desc, 20*mm, y - 16*mm, testo_max_w,
                    "Helvetica", 9, 4.6*mm, color=MUTED)

        # Bottone "Vai a Pag. X" — centrato verticalmente nel box
        # Tolta la freccia: non esiste nei font standard del PDF e ReportLab
        # la sostituiva con un glifo ZapfDingbats.
        pill_txt_line1 = "Vai a"
        pill_txt_line2 = pag_label
        pill_cy = y - box_h/2  # centro verticale del box
        pill_top = pill_cy + (pill_h + 4*mm)/2 + 2*mm
        c.setFillColor(GOLD)
        c.roundRect(pill_x, pill_top - (pill_h + 4*mm), pill_w, pill_h + 4*mm, 2*mm, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont("Helvetica", 8)
        c.drawCentredString(pill_x + pill_w/2, pill_top - 5.5*mm, pill_txt_line1)
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(pill_x + pill_w/2, pill_top - 10.5*mm, pill_txt_line2)

        # Didascalia della sezione: dentro il riquadro, sotto il bottone e
        # allineata a esso. Prima cadeva fuori dal box, staccata, e sembrava
        # una scritta finita sotto al bottone per sbaglio.
        c.setFillColor(MUTED)
        draw_centred_fit(c, pill_x + pill_w/2, pill_top - (pill_h + 4*mm) - 4*mm,
                         pag_desc, pill_w + 10*mm, "Helvetica-Oblique", 7.5,
                         line_h=3.4*mm, min_size=6)

        y -= box_h + 8*mm

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

def page_riepilogo(c, data):
    """Riepilogo finale in stile Base (stesse card oro), ma con i valori
    significativi dello Strategico. Dove il report presenta più scenari si
    prende sempre quello centrale/realistico, come da indicazione: è il
    riferimento dichiarato in tutto il resto del documento."""
    draw_header(c, data)
    draw_footer(c, data, 16)
    y = H - 22*mm

    y = draw_section_header(c, 14*mm, y, W - 28*mm, "Riepilogo indicatori chiave")
    y -= 3*mm
    draw_section_subtitle(c, 14*mm, y,
        "Sintesi conclusiva dei valori calcolati per il tuo immobile · dove ci sono più scenari vale il realistico")
    y -= 7*mm

    real = data.get('scenario_real') or {}
    occ_pct = data.get('occupazione_percent', 0)

    def card_row(kpis, y):
        kw = (W - 28*mm - 6*mm) / 4
        kh = 24*mm
        for i, (lbl, val, sub, nota) in enumerate(kpis):
            cx = 14*mm + i * (kw + 2*mm)
            c.setFillColor(GOLD_LIGHT)
            c.roundRect(cx, y - kh, kw, kh, 2*mm, fill=1, stroke=0)
            c.setStrokeColor(GOLD)
            c.setLineWidth(1)
            c.roundRect(cx, y - kh, kw, kh, 2*mm, fill=0, stroke=1)
            c.setFillColor(GOLD)
            draw_centred_fit(c, cx + kw/2, y - 4.5*mm, lbl, kw - 3*mm, "Helvetica-Bold", 6.5, min_size=5)
            c.setFillColor(BLUE_NIGHT)
            draw_centred_fit(c, cx + kw/2, y - 13*mm, val, kw - 3*mm, "Helvetica-Bold", 13, min_size=8)
            c.setFillColor(MUTED)
            draw_centred_fit(c, cx + kw/2, y - 17*mm, sub, kw - 3*mm, "Helvetica", 6.5, min_size=5)
            c.setFillColor(MUTED)
            draw_centred_fit(c, cx + kw/2, y - 21*mm, nota, kw - 3*mm, "Helvetica", 6, min_size=5)
        return y - kh - 6*mm

    # Riga 1 — il cuore economico annuale (scenario realistico).
    y = card_row([
        ("PREZZO MEDIO / NOTTE", f"€ {data.get('prezzo_notte_stimato', 0)}", "per notte",
         f"ADR ponderato € {data.get('adr', 0)}"),
        ("TASSO DI OCCUPAZIONE", f"{occ_pct}%", "stimato",
         f"{data.get('notti_anno', 0)} notti/anno"),
        ("RICAVI TOTALI ANNUI", fmt_eur(data.get('totale_ricavi', 0)), "lordi",
         f"Con occupazione al {occ_pct}%"),
        ("PROFITTO NETTO STIMATO", fmt_eur(data.get('profitto_netto', 0)), "netto stimato",
         f"Margine {data.get('margine_percent', 0)}% sui ricavi"),
    ], y)

    # Riga 2 — gli indicatori esclusivi dello Strategico.
    _valore_asset = data.get('valore_mercato') or 0
    y = card_row([
        ("RENDITA MENSILE NETTA",
         fmt_eur(round((data.get('profitto_netto', 0)) / 12)), "al mese",
         "Profitto netto / 12 mesi"),
        ("VALORE COME ASSET B&B",
         fmt_eur(_valore_asset) if _valore_asset else "n/d", "valore di mercato",
         f"Saggio cap. {data.get('saggio_capitalizzazione', 7.0)}%"),
        ("RevPAR", f"€ {data.get('revpar', 0)}", "per unità disponibile",
         "ADR x occupazione"),
        ("SCENARIO REALISTICO",
         fmt_eur(real.get('profitto_netto', data.get('profitto_netto', 0))), "profitto netto",
         f"{real.get('occupazione', occ_pct)}% occ. · € {real.get('prezzo_medio', data.get('prezzo_notte_stimato', 0))}/notte"),
    ], y)

    # Riga 3 — il trimestre affidabile e il confronto con l'affitto classico.
    _trim = "trimestre_ricavo_atteso" in data
    y = card_row([
        ("PROSSIMI 3 MESI",
         fmt_eur(data.get('trimestre_ricavo_atteso', 0)) if _trim else "n/d", "ricavo atteso",
         data.get('trimestre_mesi_label', '') if _trim else "dato non disponibile"),
        ("PREZZO TRIMESTRE",
         f"€ {data.get('trimestre_prezzo_medio', 0)}" if _trim else "n/d", "medio/notte",
         "Dato di mercato più affidabile"),
        ("AFFITTO TRADIZIONALE",
         fmt_eur(data.get('affitto_profitto', 0)), "profitto netto",
         "Stessa unità, locazione classica"),
        ("DIFFERENZA A FAVORE B&B",
         f"+{fmt_eur(max(0, data.get('profitto_netto', 0) - data.get('affitto_profitto', 0)))}", "in più all'anno",
         "Rispetto all'affitto tradizionale"),
    ], y)

    c.setFont("Helvetica-Oblique", 6.5)
    c.setFillColor(MUTED)
    c.drawString(14*mm, y,
                 "Valori orientativi calcolati sui dati inseriti e sulle medie di mercato della zona. "
                 "Dove il report presenta tre scenari, qui è riportato sempre quello realistico.")


def build_strategico_pdf_bytes(data):
    """Genera il PDF Strategico in memoria e restituisce bytes."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle("ReportUp — Report Strategico")
    c.setAuthor("Arch. Salvatore Junior Sica · ReportUp")
    # page_riepilogo entra come pagina 16, subito prima di fonti/ringraziamenti
    # (page11, ora pagina 17): stesso posto che il riepilogo occupa nel Base.
    for page_fn in [page1, page2, page3, page4, page4_manutenzione, page4b_moltiplicatori, page5, page8, page8b_durata, page8c_mercato, page9, page6, page7, page10, page_obiettivi, page_riepilogo, page11]:
        page_fn(c, data)
        c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()

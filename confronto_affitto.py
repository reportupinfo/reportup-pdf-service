# ── Tabella "Confronto con affitto tradizionale" — UNICA per Base e Strategico ─
# Una sola costruzione dati + stile, così le due pagine non possono divergere.
# Chi disegna (app.py / strategico.py) chiama solo `tabella_confronto` e poi,
# se `disclaimer_mercato(D)` non è None, lo stampa sotto la tabella.

from reportlab.lib.colors import HexColor
from reportlab.lib.units import mm
from reportlab.platypus import Table, TableStyle

import affitti_mercato

_BLUE_NIGHT = HexColor("#0D1F2D")
_TEAL = HexColor("#0D9E5C")
_RED = HexColor("#C0392B")
_CREAM = HexColor("#FAF8F4")
_BORDER = HexColor("#DDD4C8")
_WHITE = HexColor("#FFFFFF")


def _eur(v):
    return f"€ {int(round(v)):,}".replace(",", ".")


def _eur_segno(v):
    return ("+" if v >= 0 else "-") + _eur(abs(v))


def _estremi(D, chiave, chiave_min=None, chiave_max=None, reale=False):
    """(basso, alto) dell'affitto tradizionale: range reale se il comune è
    coperto da affitti_mercato, altrimenti il +-10% generico."""
    v = D.get(chiave, 0) or 0
    if reale and chiave_min and D.get(chiave_min) is not None and D.get(chiave_max) is not None:
        return D[chiave_min], D[chiave_max]
    if reale:  # costi: un solo valore
        return v, v
    return round(v * 0.9), round(v * 1.1)


def _testo_range(basso, alto):
    if round(basso) == round(alto):
        return _eur(basso)
    return f"{_eur(basso)} - {_eur(alto)}"


def _riga(D, label, esatto_bnb, chiave, chiave_min=None, chiave_max=None, reale=False):
    basso, alto = _estremi(D, chiave, chiave_min, chiave_max, reale)
    d_basso, d_alto = esatto_bnb - alto, esatto_bnb - basso   # differenza min / max
    if round(d_basso) == round(d_alto):
        diff = _eur_segno(d_basso)
    else:
        diff = f"{_eur_segno(d_basso)} - {_eur_segno(d_alto)}"
    ok = (d_basso + d_alto) / 2 >= 0
    return [label, _testo_range(basso, alto), _eur(esatto_bnb), diff], ok


def tabella_confronto(D, larghezza):
    """Ritorna la Table già stilizzata, identica in Base e Strategico."""
    reale = D.get("fonte_affitto_tradizionale") == "mercato_reale"
    r_ric, ok_ric = _riga(D, "Ricavo annuo lordo", D.get("ricavo_lordo", 0), "affitto_ricavo",
                          "affitto_ricavo_min", "affitto_ricavo_max", reale)
    r_cos, _ = _riga(D, "Costi di gestione", D.get("totale_costi", 0), "affitto_costi", reale=reale)
    r_pro, ok_pro = _riga(D, "Profitto netto", D.get("profitto_netto", 0), "affitto_profitto",
                          "affitto_profitto_min", "affitto_profitto_max", reale)
    # Costi: la "differenza" non è un guadagno/perdita colorabile, resta neutra.
    rows = [
        ["", "Affitto tradizionale", "B&B / Short rent", "Differenza"],
        r_ric, r_cos, r_pro,
        ["Flessibilità utilizzo", "Bassa", "Alta", "Molto alta"],
        ["Rischio morosità", "Alto", "Nullo", "Eliminato"],
    ]
    tbl = Table(rows, colWidths=[larghezza * 0.28, larghezza * 0.22, larghezza * 0.22, larghezza * 0.28])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _BLUE_NIGHT), ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"), ("TEXTCOLOR", (0, 1), (-1, -1), _BLUE_NIGHT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _CREAM]),
        ("GRID", (0, 0), (-1, -1), 0.25, _BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("TEXTCOLOR", (3, 1), (3, 1), _TEAL if ok_ric else _RED), ("FONTNAME", (3, 1), (3, 1), "Helvetica-Bold"),
        ("FONTNAME", (3, 2), (3, 2), "Helvetica-Bold"),
        ("TEXTCOLOR", (3, 3), (3, 3), _TEAL if ok_pro else _RED), ("FONTNAME", (3, 3), (3, 3), "Helvetica-Bold"),
        ("TEXTCOLOR", (3, 4), (3, 5), _TEAL), ("FONTNAME", (3, 4), (3, 5), "Helvetica-Bold"),
    ]))
    return tbl


def disclaimer_mercato(D):
    """Testo da stampare sotto la tabella, solo per comuni da affitti_mercato."""
    if D.get("fonte_affitto_tradizionale") == "mercato_reale":
        return affitti_mercato.DISCLAIMER
    return None

"""Verifica aritmetica indipendente di un PDF ReportUp (Base o Strategico) dal solo testo stampato.
Uso: python dump_pdf_testo.py report.pdf report.txt  poi  python verifica_pdf_aritmetica.py report.txt
Creato il 28/10/2026 per il test Base/Strategico di Sorrento: ricalcola ricavi, costi, scenari, durate
di soggiorno, asset, FF&E, moltiplicatori e intervento dalle formule stampate e segnala ogni scarto.
Pensato per il test con trilocale + mutuo + manutenzione (altre configurazioni: alcuni controlli saltano)."""
import io, re, sys

txt = io.open(sys.argv[1], encoding="utf-8").read()
flat = re.sub(r"\s+", " ", txt)
strategico = "Report Strategico" in txt[:400]
esiti = []


def n(s):
    return int(s.replace(".", ""))


def ok(nome, atteso, trovato, tol=0):
    good = abs(atteso - trovato) <= tol
    esiti.append((good, nome, atteso, trovato))


def cerca(pat, cosa, gruppo=1, flags=0):
    m = re.search(pat, flat, flags)
    if not m:
        esiti.append((False, f"NON TROVATO: {cosa}", "-", "-"))
        return None
    return m.group(gruppo)


# ── analisi economica ─────────────────────────────────────────────────────────
m = re.search(r"€ (\d+)/notte x (\d+)% occ\. x 365gg = (\d+) notti x € (\d+) = € ([\d.]+)", flat)
prezzo, occ, notti, prezzo2, ricavo = int(m[1]), int(m[2]), int(m[3]), int(m[4]), n(m[5])
ok("notti = round(365*occ/100)", round(365 * occ / 100), notti)
ok("prezzo coerente nella formula", prezzo, prezzo2)
ok("ricavo lordo = prezzo*notti", prezzo * notti, ricavo)
m = re.search(r"€ ([\d.]+) x 7% \(stima nel range 5-10%\) = € ([\d.]+)", flat)
bonus = n(m[2]); ok("bonus = round(ricavo*7%)", round(ricavo * 0.07), bonus)
m = re.search(r"€ ([\d.]+) \+ € ([\d.]+) = € ([\d.]+)", flat)
totale_ricavi = n(m[3]); ok("totale ricavi", ricavo + bonus, totale_ricavi)
m = re.search(r"€ ([\d.]+) x 15,5% = € ([\d.]+)", flat); comm = n(m[2])
ok("commissioni = round(ricavo*15,5%)", round(ricavo * 0.155), comm)
m = re.search(r"€ (\d+)/cambio x (\d+) cambi \(soggiorno medio ([\d,]+) notti\) = € ([\d.]+)", flat)
unit, cambi, sm, pul = int(m[1]), int(m[2]), float(m[3].replace(",", ".")), n(m[4])
ok("cambi = max(1,round(notti/soggiorno))", max(1, round(notti / sm)), cambi)
ok("pulizie = unit*cambi", unit * cambi, pul)
bianc = n(cerca(r"Biancheria e consumabili (?:- )?€ ([\d.]+)/anno", "biancheria"))
ut = n(cerca(r"Utenze aggiuntive stimate (?:- )?€ ([\d.]+)/anno", "utenze"))
man = n(cerca(r"Manutenzione ordinaria (?:- )?€ ([\d.]+)/anno", "manutenzione"))
mm = re.search(r"€ ([\d.]+)/mese x 12 = € ([\d.]+)", flat)
mutuo = n(mm[2]) if mm else 0
if mm:
    ok("mutuo = rata*12", n(mm[1]) * 12, mutuo)
_mc = re.search(r"Totale costi di gestione - € ([\d.]+)", flat, re.I) or re.search(r"TOTALE COSTI DI GESTIONE (?:€ [\d.]+ \+ )+€ [\d.]+ - € ([\d.]+)", flat)
tot_costi = n(_mc.group(1))
ok("totale costi = somma voci", comm + pul + bianc + ut + man + mutuo, tot_costi)
_mp = re.search(r"PROFITTO NETTO STIMATO € ([0-9.]+) Margine", flat) or re.search(r"PROFITTO NETTO STIMATO (?:€ [0-9.]+ - € [0-9.]+ )?€ ([0-9.]+)", flat)
profitto = n(_mp.group(1))
ok("profitto = ricavi - costi", totale_ricavi - tot_costi, profitto)
marg = int(cerca(r"Margine netto su ricavi totali (?:€ [\d.]+ / € [\d.]+ x 100 )?(\d+)%", "margine"))
ok("margine = round(profitto/ricavi)", round(profitto / totale_ricavi * 100), marg)

# ── riepilogo / range ─────────────────────────────────────────────────────────
# Dal 28/10/2026 le fasce sotto le card sono i percentili reali P25-P75 di AirROI
# ("Range zona", gli stessi della pag. 10 dello Strategico); senza percentili
# restano il +-20% del nostro valore, ma si chiamano "Intervallo stimato".
_p25 = re.search(r"P25 \(fascia bassa\) € (\d+) (\d+)%", flat)
_p75 = re.search(r"P75 \(fascia alta\) € (\d+) (\d+)%", flat)
m = re.search(r"Range zona: € (\d+)-(\d+)", flat)
mi = re.search(r"Intervallo stimato: € (\d+)-(\d+)", flat)
if m:
    if _p25 and _p75:
        ok("range zona prezzo = P25 pag. 10", int(_p25[1]), int(m[1])); ok("range zona prezzo = P75 pag. 10", int(_p75[1]), int(m[2]))
    else:
        ok("range zona prezzo ordinato (P25 < P75)", 1, 1 if int(m[1]) < int(m[2]) else 0)
elif mi:
    ok("intervallo prezzo -20%", max(1, round(prezzo * 0.8)), int(mi[1])); ok("intervallo prezzo +20%", round(prezzo * 1.2), int(mi[2]))
else:
    esiti.append((False, "riepilogo: 'Range zona' / 'Intervallo stimato' prezzo non presente", "-", "-"))
m = re.search(r"Range zona: (\d+)-(\d+)%", flat)
mi = re.search(r"Intervallo stimato: (\d+)-(\d+)%", flat)
if m:
    if _p25 and _p75:
        ok("range zona occ = P25 pag. 10", int(_p25[2]), int(m[1])); ok("range zona occ = P75 pag. 10", int(_p75[2]), int(m[2]))
    else:
        ok("range zona occ ordinato (P25 < P75)", 1, 1 if int(m[1]) < int(m[2]) else 0)
elif mi:
    ok("intervallo occ -20%", max(5, round(occ * 0.8)), int(mi[1])); ok("intervallo occ +20% (tetto)", round(occ * 1.2), int(mi[2]), tol=0)
else:
    esiti.append((False, "riepilogo: 'Range zona' / 'Intervallo stimato' occupazione non presente", "-", "-"))
_pm = re.search(r"POTENZIALE LORDO ANNUO € ([\d.]+) all'anno Con occupazione al (\d+)%", flat)
if _pm:
    ok("potenziale lordo = ricavo lordo", ricavo, n(_pm.group(1)))
else:
    esiti.append((False, "riepilogo: 'POTENZIALE LORDO ANNUO' non presente", "-", "-"))

# ── confronto con affitto tradizionale ───────────────────────────────────────
m = re.search(r"Ricavo annuo lordo\* € ([\d.]+) - € ([\d.]+) € ([\d.]+) \+€ ([\d.]+) - \+€ ([\d.]+) Costi di gestione € ([\d.]+) € ([\d.]+) \+€ ([\d.]+) Profitto netto € ([\d.]+) - € ([\d.]+) € ([\d.]+) \+€ ([\d.]+) - \+€ ([\d.]+)", flat)
r_min, r_max, bb_r, d1, d2, c_trad, bb_c, dc, p_min, p_max, bb_p, dp1, dp2 = (n(g) for g in m.groups())
ok("confronto: ricavo B&B = totale ricavi", totale_ricavi, bb_r)
ok("confronto: diff ricavo max", bb_r - r_min, d2); ok("confronto: diff ricavo min", bb_r - r_max, d1)
ok("confronto: costi B&B = totale costi", tot_costi, bb_c)
ok("confronto: diff costi", bb_c - c_trad, dc)
ok("confronto: profitto trad min = ricavo min - costi", r_min - c_trad, p_min)
ok("confronto: profitto trad max = ricavo max - costi", r_max - c_trad, p_max)
ok("confronto: profitto B&B", profitto, bb_p)
ok("confronto: diff profitto max", bb_p - p_min, dp2); ok("confronto: diff profitto min", bb_p - p_max, dp1)
medio = (r_min + r_max) / 2
ok("confronto: costi trad = 10% canone medio (500-2000) + mutuo", min(2000, max(500, round(medio * 0.10))) + mutuo, c_trad, tol=1)

# ── tabella mensile ───────────────────────────────────────────────────────────
mesi = re.findall(r"(Gen|Feb|Mar|Apr|Mag|Giu|Lug|Ago|Set|Ott|Nov|Dic) (\d+)% € (\d+) (?:Bassa|Media|Alta|Peak)", flat)
if len(mesi) >= 12:
    giorni = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    ric_m = sum(int(o) / 100 * g * int(p) for (_, o, p), g in zip(mesi[:12], giorni))
    nott_m = sum(int(o) / 100 * g for (_, o, p), g in zip(mesi[:12], giorni))
    ok("tabella mensile: somma ricavi = ricavo lordo (arrotondamenti ≤0,3%)", ricavo, round(ric_m), tol=ricavo * 0.003)
    ok("tabella mensile: notti = notti/anno (±2)", notti, round(nott_m), tol=2)
else:
    esiti.append((False, "tabella mensile non trovata", "-", len(mesi)))

# ── competitor ───────────────────────────────────────────────────────────────
m = re.search(r"Monolocali € (\d+) Bilocali € (\d+) Trilocali € (\d+) B&B e camere € (\d+) IL TUO IMMOBILE \(stima\) € (\d+)", flat)
if m:
    ok("competitor: il tuo immobile = prezzo", prezzo, int(m[5]))
    ok("competitor: trilocali = prezzo", prezzo, int(m[3]))

if strategico:
    # scenari
    m = re.search(r"Occupazione media (\d+)% (\d+)% (\d+)% Notti vendute/anno (\d+) (\d+) (\d+) Prezzo medio/notte € (\d+) € (\d+) € (\d+) Ricavi totali € ([\d.]+) € ([\d.]+) € ([\d.]+) Costi totali € ([\d.]+) € ([\d.]+) € ([\d.]+) Profitto netto € ([\d.]+) € ([\d.]+) € ([\d.]+)", flat)
    if m:
        g = [n(x) for x in m.groups()]
        occs, nott, prz, ric, cos, pro = g[0:3], g[3:6], g[6:9], g[9:12], g[12:15], g[15:18]
        ok("scenario real = analisi economica (occ)", occ, occs[1]); ok("scenario real (prezzo)", prezzo, prz[1])
        ok("scenario real (ricavi)", totale_ricavi, ric[1]); ok("scenario real (costi)", tot_costi, cos[1]); ok("scenario real (profitto)", profitto, pro[1])
        ratio = (tot_costi - mutuo) / totale_ricavi
        for i, par in enumerate(((0.65, 0.80, 0.0), None, (1.20, 1.18, 0.10))):
            if par is None: continue
            om, pm, bn = par
            o = min(90, round(occ * om)); p = round(prezzo * pm); nt = round(365 * o / 100); rl = p * nt; rt = round(rl * (1 + bn))
            c_ = round(rt * ratio) + mutuo
            nome = "pess" if i == 0 else "ott"
            ok(f"scenario {nome}: occ", o, occs[i]); ok(f"scenario {nome}: notti", nt, nott[i]); ok(f"scenario {nome}: prezzo", p, prz[i])
            ok(f"scenario {nome}: ricavi", rt, ric[i]); ok(f"scenario {nome}: costi", c_, cos[i], tol=1); ok(f"scenario {nome}: profitto", rt - c_, pro[i], tol=1)
    # durata soggiorno
    for dur in (2, 7, 14):
        m = re.search(rf"{dur} notti/soggiorno Cambi ospite/anno (\d+) Ricavi totali € ([\d.]+) Costi pulizia € ([\d.]+) Costi totali € ([\d.]+) Profitto netto € ([\d.]+) Margine (\d+)%", flat)
        if m:
            cb = max(1, round(notti / dur)); pl = unit * cb; ct = comm + bianc + ut + man + mutuo + pl; pf = totale_ricavi - ct
            ok(f"durata {dur}: cambi", cb, int(m[1])); ok(f"durata {dur}: pulizia", pl, n(m[3])); ok(f"durata {dur}: costi", ct, n(m[4]))
            ok(f"durata {dur}: profitto", pf, n(m[5])); ok(f"durata {dur}: margine", round(pf / totale_ricavi * 100), int(m[6]))
    # asset
    m = re.search(r"EBITDA / Saggio cap\. = € ([\d.]+) / ([\d.]+)% = € ([\d.]+)", flat)
    if m:
        eb = n(m[1]); sag = float(m[2]); val = n(m[3])
        ok("EBITDA = ricavi - costi senza mutuo", totale_ricavi - (tot_costi - mutuo), eb)
        ok("valore asset = EBITDA/saggio", round(eb / (sag / 100)), val, tol=1)
        mr = re.search(r"EBITDA / 12 mesi = € [\d.]+ / 12 € ([\d.]+)", flat)
        if mr: ok("rendita mensile EBITDA", round(eb / 12), n(mr[1]), tol=1)
    # FF&E
    m = re.search(r"FF&E Reserve \(manutenzione straord\.\) (\d+)% x € ([\d.]+) = € ([\d.]+)/anno per arredi e dotazioni \(non incluso nel totale\) € ([\d.]+)", flat)
    if m:
        ok("FF&E = 2% ricavo lordo", round(ricavo * 0.02), n(m[3])); ok("FF&E colonna valore", n(m[3]), n(m[4]))
        ok("FF&E base = ricavo lordo", ricavo, n(m[2]))
    else:
        esiti.append((False, "FF&E con formula non trovata", "-", "-"))
    # pricing mensile
    m = re.search(r"TOTALE ANNUO € ([\d.]+)", flat)
    if m: ok("pricing mensile: totale ~ ricavo lordo (≤0,3%)", ricavo, n(m[1]), tol=ricavo * 0.003)
    # riepilogo
    m = re.search(r"RENDITA MENSILE NETTA € ([\d.]+)", flat)
    if m: ok("rendita mensile netta = profitto/12", round(profitto / 12), n(m[1]), tol=1)
    m = re.search(r"AFFITTO TRADIZIONALE € ([\d.]+) profitto netto", flat)
    if m: ok("affitto trad = media profitti min/max", round((p_min + p_max) / 2), n(m[1]), tol=1)
    m = re.search(r"DIFFERENZA A FAVORE B&B \+€ ([\d.]+)", flat)
    if m: ok("differenza B&B - trad", profitto - n(re.search(r"AFFITTO TRADIZIONALE € ([\d.]+)", flat)[1]), n(m[1]), tol=1)
    # moltiplicatori
    for nome, pct in (("Piscina", 7), ("Parcheggio", 5), ("Giardino", 3), ("Lavatrice", 3), ("Ascensore", 2)):
        m = re.search(rf"{nome} \+{pct}% \+€ (\d+) \+€ ([\d.]+)", flat)
        if m:
            ok(f"moltiplicatore {nome}: ricavo = delta*notti", int(m[1]) * notti, n(m[2]))
    # intervento
    m = re.search(r"Costo mensile da sottrarre € ([\d.]+) / (\d+) mesi = € ([\d.]+)/mese - € [\d.]+ Impatto sul profitto del primo anno € ([\d.]+)/mese × (\d+) mesi - € ([\d.]+) Profitto netto DOPO intervento € [\d.]+ - € ([\d.]+) = profitto netto del primo anno € ([\d.]+)", flat)
    if m:
        imp, mesi_i, mens, _, mesi_a, imp_a, _, prof_dopo = (n(x) if i != 1 else int(x) for i, x in enumerate(m.groups()))
        ok("intervento: mensile = round(importo/mesi)", round(imp / mesi_i), mens)
        ok("intervento: mesi primo anno = min(12, mesi)", min(12, mesi_i), mesi_a)
        ok("intervento: impatto anno = mensile*mesi", mens * mesi_a, imp_a); ok("intervento: profitto dopo", profitto - imp_a, prof_dopo)
    else:
        esiti.append((False, "blocco intervento non trovato (o formato diverso)", "-", "-"))

# ── stampa ────────────────────────────────────────────────────────────────────
bad = [e for e in esiti if not e[0]]
print(f"{sys.argv[1]}: {len(esiti) - len(bad)}/{len(esiti)} controlli OK")
for g, nome, a, t in bad:
    print(f"   ✗ {nome}: atteso {a}  trovato {t}")

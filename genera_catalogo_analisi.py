"""Scrive il catalogo leggibile di tutte le frasi dell'analisi personale (pag. 14
dello Strategico), tratto direttamente da analisi_personale.py: serve a
rileggerle e approvarle una per una. Rilanciare dopo ogni modifica alle frasi.
Uso: python genera_catalogo_analisi.py [percorso_output.md]"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analisi_personale as A

USCITA_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Da rivedere - Strategico",
                              "Catalogo_frasi_analisi_personale.md")

righe = []


def titolo(t, livello=2):
    righe.append("")
    righe.append("#" * livello + " " + t)
    righe.append("")


def voce(codice, condizione, testo, prima_persona=False):
    marca = " ✍️ *prima persona*" if prima_persona else ""
    righe.append(f"**{codice}** · *{condizione}*{marca}  ")
    righe.append(f"> {testo}")
    righe.append("")


righe.append("# Catalogo frasi — Analisi personale (pag. 14 Report Strategico)")
righe.append("")
righe.append("Ogni frase ha un codice: rispondi con \"ok tutto\" oppure con i codici da cambiare "
             "(es. \"B3 più breve, D2 togli\"). Le parti tra {graffe} sono compilate dal codice con dati "
             "veri del report; le frasi con ✍️ sono in prima persona e portano la tua firma.")
righe.append("")
righe.append("Come lavora: per ogni blocco il codice sceglie le frasi dai fatti misurati (distanze Google, "
             "quota, stato dichiarato, dotazioni, percentili AirROI, mutuo, gestione, obiettivi). Se una "
             "condizione non è verificata, la frase non esce. Se il blocco supera il tetto di lunghezza si "
             "tolgono prima le frasi meno importanti (le ultime di ogni elenco).")

# ── A. Posizione ─────────────────────────────────────────────────────────────
titolo("A. Posizione e contesto di mercato (tetto 750 caratteri; massimo 3 frasi: ambiente + centralità + collegamenti)")
righe.append("**Come si sceglie l'ambiente** (in quest'ordine): montagna (quota da 600 m o zona montana) · "
             "città (capoluogo o grande città) · mare (costa entro 1,5 km, o spiaggia a pochi minuti / non lontana, "
             "o costa entro 5 km) · lago (lago vicino / non lontano) · isolata (comune minore fuori dal centro) · "
             "borgo (tutto il resto). Se la zona (quartiere) è nota e diversa dal comune, si antepone «Comune, zona X.». "
             "{mesi} = «; nelle stime i mesi più forti sono …» dai mesi Alta + Peak della curva del report.")
righe.append("")
for i, (k, t) in enumerate(A.FRASI_AMBIENTE.items(), 1):
    voce(f"A{i}", f"ambiente: {k}", t)
righe.append("**Centralità** (minuti reali di Google verso il centro del comune; non esce per l'ambiente «isolata», che la contiene già):")
righe.append("")
nomi_c = {"nel_centro": "nel centro", "centrale": "centro a ≤15 min a piedi", "breve_distanza": "centro a ≤25 min a piedi o ≤10 in auto",
          "fuori": "oltre"}
for i, (k, t) in enumerate(A.FRASI_CENTRALITA.items(), 1):
    voce(f"B{i}", nomi_c[k], t)
righe.append("**Collegamenti** (casello vicino = ≤10 min in auto; stazione vicina = ≤15 min a piedi):")
righe.append("")
nomi_k = {"casello_e_stazione": "casello e stazione vicini", "casello": "solo casello vicino", "stazione": "solo stazione vicina",
          "nessuno": "nessuno dei due vicino e posizione fuori dal centro"}
for i, (k, t) in enumerate(A.FRASI_COLLEGAMENTI.items(), 1):
    voce(f"C{i}", nomi_k[k], t)

# ── B. Condizione ────────────────────────────────────────────────────────────
titolo("B. Condizione e caratteristiche immobile (tetto 1.100 caratteri)")
righe.append("**Stato dichiarato nel form** (sempre una frase):")
righe.append("")
for i, (k, t) in enumerate(A.FRASI_STATO.items(), 1):
    voce(f"D{i}", f"stato: {k}", t)
righe.append("**Epoca** (ante 1990 → controllo impianti; dal 2010 → costruzione recente; anni '90-2000 nessuna frase):")
righe.append("")
voce("E1", "epoca prima del 1990", A.FRASE_EPOCA_VECCHIA)
voce("E2", "epoca dal 2010", A.FRASE_EPOCA_RECENTE)
righe.append("**Intervento dichiarato** (importo e mesi dal form, scritti dal codice; «nessuno» = nessuna frase):")
righe.append("")
voce("F1", "manutenzione", A.FRASI_INTERVENTO["manutenzione"])
voce("F2", "ristrutturazione", A.FRASI_INTERVENTO["ristrutturazione"])
righe.append("**Dotazioni mancanti** (solo quelle assenti nel form):")
righe.append("")
voce("G1", "mancano WiFi / aria condizionata / riscaldamento (una frase unica, elenco dei nomi; «manca» se una sola)",
     A.FRASE_DOTAZIONI_BASE)
for i, (k, t) in enumerate(A.FRASI_DOTAZIONE_MANCANTE.items(), 2):
    extra = " — solo se il piano non è terra" if k == "Ascensore" else ""
    voce(f"G{i}", f"manca: {k}{extra} (si scelgono le 2 con più peso sul prezzo, tabella pag. 6)",
         t + " (+X% sul prezzo per notte, pag. 6).")
voce("G9", "nessuna dotazione mancante", A.FRASE_TUTTE_DOTAZIONI)

# ── C. Potenzialità ──────────────────────────────────────────────────────────
titolo("C. Potenzialità e proiezioni (tetto 950 caratteri)")
voce("H1", "prezzo e occupazione stimati nella stessa fascia di percentile", A.FRASE_PERCENTILI_UGUALI)
voce("H2", "fasce diverse", A.FRASE_PERCENTILI_DIVERSI)
voce("H3", "gestione professionale ≥60% degli annunci comparabili", A.FRASI_CONCORRENZA["alta"])
voce("H4", "gestione professionale 30-59%", A.FRASI_CONCORRENZA["mista"])
voce("H5", "gestione professionale <30%", A.FRASI_CONCORRENZA["bassa"])
righe.append("**Leve** (massimo tre, in quest'ordine di priorità; la frase di apertura è «Le leve con più effetto sui tuoi dati sono: (1) …; (2) …»):")
righe.append("")
nomi_l = {"dotazioni": "mancano wifi / aria / riscaldamento / lavatrice / cucina", "prezzo": "prezzo stimato sotto la mediana di zona",
          "visibilita": "occupazione stimata sotto la mediana di zona", "esistente": "B&B già attivo",
          "recensioni": "attività nuova", "dirette": "sempre (ultima)"}
for i, (k, t) in enumerate(A.LEVE.items(), 1):
    voce(f"I{i}", nomi_l[k], t)
voce("I7", "sempre (chiusura)", A.FRASE_SCENARIO_OTTIMISTICO)

# ── D. Raccomandazione ───────────────────────────────────────────────────────
titolo("D. Raccomandazione operativa (tetto 1.450 caratteri)")
righe.append("**Gestione** (una sola frase): se il cliente ha previsto il property manager → L1; altrimenti con oltre "
             "100 cambi ospite/anno o 3+ camere → L2; altrimenti → L3. Se B&B già attivo si aggiunge L4.")
righe.append("")
voce("L1", "property manager previsto (compenso calcolato sui ricavi lordi)", A.FRASE_GESTIONE_PM, True)
voce("L2", "oltre 100 cambi ospite/anno o 3+ camere", A.FRASE_GESTIONE_PM_CONSIGLIATO, True)
voce("L3", "gestione sostenibile in autonomia", A.FRASE_GESTIONE_DIRETTA, True)
voce("L3b", "come L3 ma senza dato dei cambi ospite", A.FRASE_GESTIONE_DIRETTA_SENZA_CAMBI, True)
voce("L4", "B&B già attivo", A.FRASE_GIA_ATTIVO)
righe.append("**Rischi** (priorità: normativa sempre; poi UN solo secondo rischio, il primo che scatta):")
righe.append("")
voce("M1", "sempre", A.FRASE_RISCHIO_NORMATIVO)
voce("M2", "la rata del mutuo supera il 50% del reddito operativo (profitto + rata)", A.FRASE_RISCHIO_MUTUO)
voce("M3", "manca una dotazione che vale ≥5% sul prezzo (piscina, parcheggio)", A.FRASE_RISCHIO_DOTAZIONE)
voce("M4", "gestione professionale ≥60% degli annunci comparabili", A.FRASE_RISCHIO_CONCORRENZA)
righe.append("**Da dove partire e opportunità:**")
righe.append("")
voce("N1", "attività nuova", A.FRASE_PARTENZA_NUOVO)
voce("N2", "B&B già attivo", A.FRASE_PARTENZA_ATTIVO)
voce("N3", "sempre: ripete la prima leva", A.FRASE_OPPORTUNITA)
righe.append("**Obiettivi dichiarati nel form** (massimo i primi due; il confronto con l'affitto confronta il profitto B&B "
             "con la fascia del profitto da affitto tradizionale):")
righe.append("")
nomi_o = {"massimizzare_guadagno": "obiettivo: massimizzare il guadagno", "confronto_affitto_meglio": "confronto affitto: B&B sopra la fascia",
          "confronto_affitto_peggio": "confronto affitto: B&B sotto la fascia", "confronto_affitto_pari": "confronto affitto: B&B dentro la fascia",
          "primo_avvio": "obiettivo: avviare da zero", "ottimizzare_esistente": "obiettivo: ottimizzare l'esistente",
          "valutazione_investimento": "obiettivo: valutare come investimento", "pianificazione_normativa": "obiettivo: pianificare la normativa"}
for i, (k, t) in enumerate(A.FRASI_OBIETTIVO.items(), 1):
    voce(f"O{i}", nomi_o[k], t)

# ── Esempio completo ─────────────────────────────────────────────────────────
titolo("Esempio completo (Sorrento, trilocale, stato «ben tenuto», manutenzione 2.400 in 6 mesi)")
try:
    import test_analisi_personale as T
    esempio = A.genera_analisi(T.SORRENTO)
    for etichetta, chiave in (("Posizione e contesto di mercato", "analisi_posizione"),
                              ("Condizione e caratteristiche immobile", "analisi_condizione"),
                              ("Potenzialità e proiezioni", "analisi_potenzialita"),
                              ("Raccomandazione operativa", "analisi_raccomandazione")):
        righe.append(f"**{etichetta}**")
        righe.append("")
        righe.append(esempio[chiave])
        righe.append("")
except Exception as e:                                   # il catalogo resta valido anche senza esempio
    righe.append(f"(esempio non generato: {type(e).__name__})")

uscita = sys.argv[1] if len(sys.argv) > 1 else USCITA_DEFAULT
os.makedirs(os.path.dirname(os.path.abspath(uscita)), exist_ok=True)
io.open(uscita, "w", encoding="utf-8", newline="\n").write("\n".join(righe) + "\n")
print("scritto", os.path.abspath(uscita))

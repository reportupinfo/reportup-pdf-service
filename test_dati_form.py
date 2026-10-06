"""Self-test del parse del prompt Make. Lanciare dopo ogni modifica alle
etichette degli scenari Make: python test_dati_form.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dati_form

PROMPT = """Dati cliente
Via e numero civico (come scritto): Via Mazzini 20
CAP: 37121
Comune: Verona
Provincia: Verona
Tipologia: Bilocale
Superficie: 60m2
Piano: 2
Stato conservativo: Ottimo
Numero bagni: 1
Posti letto: 4
Epoca costruzione: 1980
Dotazioni presenti: Wi-Fi, Aria condizionata
INDIRIZZO VERIFICATO GOOGLE: Via Giuseppe Mazzini, 20, 37121 Verona VR, Italia
QUARTIERE VERIFICATO GOOGLE (se presente): Centro storico
Restituisci ESATTAMENTE questo oggetto JSON
{"lat":45.4384,"long":10.9916,"situazione_mutuo":true,"rata_mutuo_mensile":650,
"intervento_tipo":"ristrutturazione","intervento_importo":12000,"intervento_mesi":3}"""

d = dati_form.parse_prompt(PROMPT)
assert dati_form.campi_mancanti(d) == [], dati_form.campi_mancanti(d)
assert d["mq"] == 60 and d["comune"] == "Verona" and d["rata_mutuo_mensile"] == 650
assert d["intervento_importo"] == 12000 and d["intervento_mesi"] == 3

# etichetta cambiata: deve emergere, e la rata non deve essere azzerata
rotto = PROMPT.replace("Superficie:", "Metri quadri:").replace('"rata_mutuo_mensile":650,', "")
d2 = dati_form.parse_prompt(rotto)
assert "Superficie" in dati_form.campi_mancanti(d2)
ai = {"rata_mutuo_mensile": 650}
dati_form.applica_dati_utente(ai, d2)
assert ai["rata_mutuo_mensile"] == 650, "rata azzerata in silenzio"
print("OK")

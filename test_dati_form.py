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
# dotazioni dichiarate (piscina/giardino alimentano il sovrapprezzo manutenzione):
# sovrascrivono quelle dell'IA, anche se l'IA le ha omesse o inventate
AMMESSE = ["WiFi", "Parcheggio", "Aria condizionata", "Lavatrice", "Cucina attrezzata",
           "Terrazzo", "Giardino", "Riscaldamento", "Ascensore", "Piscina"]
SINONIMI = {"wi-fi": "WiFi", "wifi": "WiFi", "aria condizionata": "Aria condizionata",
            "piscina": "Piscina", "giardino": "Giardino"}
norm = lambda v: SINONIMI.get(str(v or "").strip().lower(), str(v or "").strip())
d3 = dati_form.parse_prompt(PROMPT.replace("Wi-Fi, Aria condizionata", "wi-fi, piscina, Giardino"))
ai3 = {"dotazioni_presenti": ["WiFi"], "dotazioni_assenti": ["Piscina", "Giardino"]}
dati_form.applica_dotazioni_dichiarate(ai3, d3, norm, AMMESSE)
assert ai3["dotazioni_presenti"] == ["WiFi", "Piscina", "Giardino"], ai3
assert "Piscina" not in ai3["dotazioni_assenti"] and "Giardino" not in ai3["dotazioni_assenti"]
ai4 = {"dotazioni_presenti": ["Piscina"]}
dati_form.applica_dotazioni_dichiarate(ai4, dati_form.parse_prompt(PROMPT.replace("Dotazioni presenti:", "Altro:")), norm, AMMESSE)
assert ai4["dotazioni_presenti"] == ["Piscina"], "riga assente: non deve cancellare"
print("OK")

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
# indirizzo: Google trova solo il centro del comune (caso Maratea 26/10/2026, CAP a 4 cifre)
assert dati_form.google_solo_comune("85046 Maratea PZ, Italia", "Maratea")
assert dati_form.google_solo_comune("Maratea, Italia", "Maratea")
assert not dati_form.google_solo_comune("Via Giuseppe Mazzini, 20, 37121 Verona VR, Italia", "Verona")
assert dati_form.cap_valido("8546", "85046 Maratea PZ, Italia") == "85046"
assert dati_form.cap_valido("8546", "") == ""
assert dati_form.cap_valido("37121", "x") == "37121"
d_mar = dati_form.parse_prompt(PROMPT.replace("Via Mazzini 20", "via curzo").replace("CAP: 37121", "CAP: 8546")
                               .replace("Comune: Verona", "Comune: Maratea")
                               .replace("Via Giuseppe Mazzini, 20, 37121 Verona VR, Italia", "85046 Maratea PZ, Italia"))
ind, approx = dati_form.indirizzo_da_form(d_mar)
assert ind == "via curzo, 85046, Maratea (PZ)" and approx, (ind, approx)
ind_v, approx_v = dati_form.indirizzo_da_form(d)
assert ind_v == "Via Giuseppe Mazzini 20, 37121, Verona (VR)" and not approx_v, (ind_v, approx_v)
# il rigeocoding del backend (solo_comune) ha la precedenza sull'euristica sul testo
assert dati_form.indirizzo_da_form(d, solo_comune=True)[1] is True
print("OK")

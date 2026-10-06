"""Collaudo dei punti di interesse (_applica_poi_stabili) su un campione di comuni
italiani, tramite l'endpoint /debug-poi del servizio live.

Uso (PowerShell, dalla cartella reportup-pdf-service-repo):
    $env:PDF_SECRET = "<il segreto X-Internal-Secret di Render>"
    C:\\pytmp\\py312\\python.exe collaudo_poi_nazionale.py

Il segreto resta nella tua shell: lo script lo legge dall'ambiente e non lo
scrive da nessuna parte. Output: collaudo_poi_risultati.json (nessun segreto
dentro) + riepilogo a video.

Campione: ~80 comuni stratificati per categoria (grande citta', capoluogo,
comune minore) e per regione, piu' un blocco fisso di destinazioni turistiche
note (costa, lago, montagna, isole, borghi).
"""
import csv, json, os, random, sys, time
import requests

URL = "https://reportup-pdf-service.onrender.com/debug-poi"
SECRET = os.environ.get("PDF_SECRET", "")
if not SECRET:
    sys.exit("Imposta prima $env:PDF_SECRET")

QUI = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(QUI, "..", "reportup_comuni_lookup.csv")

FISSI = ["Lecce", "Firenze", "Napoli", "Roma", "Milano", "Venezia", "Palermo", "Cagliari", "Bari", "Genova",
         "Positano", "Bellagio", "Cortina d'Ampezzo", "Taormina", "Sorrento", "Alghero", "Matera", "Siena",
         "Pescasseroli", "Roccaraso", "Riva del Garda", "Lipari", "Cefalù", "Polignano a Mare", "Otranto",
         "Gubbio", "Orvieto", "Bormio", "Sirmione", "Portofino"]

random.seed(7)
righe = list(csv.DictReader(open(CSV, encoding="utf-8")))
per_nome = {}
for r in righe:
    per_nome.setdefault(r["comune"], r)
campione = [per_nome[n] for n in FISSI if n in per_nome]
visti = {r["comune"] for r in campione}

strati = {}
for r in righe:
    if r["comune"] in visti or not r.get("lat"):
        continue
    chiave = (r["categoria"], r["regione"])
    strati.setdefault(chiave, []).append(r)
chiavi = list(strati)
random.shuffle(chiavi)
for k in chiavi:
    if len(campione) >= 80:
        break
    campione.append(random.choice(strati[k]))
    visti.add(campione[-1]["comune"])

def centro(r):
    """Centro abitato via Nominatim (non il centroide amministrativo del CSV,
    che per molti comuni cade in campagna). Fallback: coordinate del CSV."""
    try:
        q = requests.get("https://nominatim.openstreetmap.org/search",
                         params={"q": f"{r['comune']}, {r['provincia']}, Italia", "format": "json", "limit": 1},
                         headers={"User-Agent": "ReportUp-collaudo/1.0 (reportup.info@gmail.com)"}, timeout=15).json()
        time.sleep(1.1)
        if q:
            return q[0]["lat"], q[0]["lon"]
    except Exception:
        pass
    return r["lat"], r["long"]


out = []
for i, r in enumerate(campione, 1):
    r["lat"], r["long"] = centro(r)
    try:
        resp = requests.post(URL, json={"lat": r["lat"], "long": r["long"], "categoria": r["categoria"]},
                             headers={"X-Internal-Secret": SECRET}, timeout=90)
        j = resp.json() if resp.status_code == 200 else {"errore": resp.status_code}
    except Exception as e:
        j = {"errore": str(e)}
    out.append({"comune": r["comune"], "prov": r["sigla_provincia"], "categoria": r["categoria"],
                "regione": r["regione"], "pop": r["popolazione"], **j})
    riga = (j.get("poi") or [[], [], [], [], []])
    print(f"{i:>2} {r['comune'][:22]:<22} {r['categoria'][:12]:<12} "
          f"T={riga[0][1] if len(riga) > 0 and len(riga[0]) > 1 else '-'} | "
          f"C={riga[2][1] if len(riga) > 2 and len(riga[2]) > 1 else '-'} | "
          f"S={riga[3][1] if len(riga) > 3 and len(riga[3]) > 1 else '-'}")
    time.sleep(0.3)

json.dump(out, open(os.path.join(QUI, "collaudo_poi_risultati.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\nScritto collaudo_poi_risultati.json con", len(out), "comuni")

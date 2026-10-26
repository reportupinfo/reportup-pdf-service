# ── Punti di interesse territoriali: mare, lago, montagna ────────────────────
#
# Problema (Maratea, 26/10/2026): il report turistico di una casa vicino al mare
# non diceva mai dov'e' la spiaggia. I POI standard (fermata, supermercato,
# attrazione, aeroporto) sono validi ovunque ma non rispondono alla domanda che
# fa chi compra una casa di vacanza: "quanto dista il mare / il lago / la
# montagna?". Qui si aggiungono righe alla tabella "Posizione e punti di
# interesse", solo quando il territorio lo giustifica e solo con dati verificati:
#
#   - spiaggia: Google Places (parola chiave, per distanza), poi distanza reale a
#     piedi o in auto dalla Distance Matrix. Si cerca solo se la costa (dati
#     offline Natural Earth) e' entro 12 km.
#   - lago: il lago noto piu' vicino (lista curata in territorio_gps) + il punto
#     di accesso piu' vicino trovato da Google (lungolago, lido, spiaggia).
#   - montagna: solo sopra i 500 m di quota; la cima piu' nota nel raggio, da
#     Wikidata (numero di voci Wikipedia = notorieta'), distanza in linea d'aria.
#
# Regola del progetto: nessun dato inventato. Se Google/Wikidata non rispondono
# o non c'e' un candidato credibile, la riga non compare. Le distanze sono
# arrotondate ai 10 m e dichiarano da dove vengono (a piedi, in auto, linea d'aria).

import math
import os
import re
import requests

import territorio_gps

GOOGLE_PLACES_NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
GOOGLE_DISTANCE_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"
WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"

MAX_KM_COSTA = 12.0        # sotto questa distanza dalla costa si cerca la spiaggia
MAX_KM_SPIAGGIA = 12.0     # spiaggia piu' lontana citabile (linea d'aria)
MAX_KM_LAGO = 8.0          # lago noto piu' lontano considerato
MAX_KM_ACCESSO_LAGO = 6.0  # punto di accesso al lago piu' lontano citabile
QUOTA_MIN_MONTAGNA = 500   # sotto questa quota non si cerca la montagna
RAGGIO_MONTE_KM = 20

_haversine_km = territorio_gps._haversine_km


# ── Utilita' ─────────────────────────────────────────────────────────────────

def _chiave():
    return os.environ.get("GOOGLE_MAPS_API_KEY")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fmt_metri(metri):
    """350 -> "350 m" (arrotondato a 10 m); 1380 -> "1,4 km"; 14200 -> "14 km"."""
    metri = float(metri)
    if metri < 1000:
        return f"{max(10, int(round(metri / 10.0)) * 10)} m"
    km = metri / 1000.0
    if km < 10:
        return f"{km:.1f}".replace(".", ",") + " km"
    return f"{int(round(km))} km"


def _titolo(nome):
    """Maiuscola iniziale parola per parola, preposizioni minuscole."""
    minuscole = {"di", "del", "della", "dei", "delle", "dello", "da", "dal", "dalla", "de", "e", "ed", "o", "la",
                 "le", "lo", "il", "i", "gli", "a", "al", "alla", "in", "degli", "sul", "sulla", "sui"}
    out = []
    for i, w in enumerate(str(nome or "").strip().split(" ")):
        if any(ch.isupper() for ch in w):
            out.append(w)
        elif i > 0 and w.lower() in minuscole:
            out.append(w)
        else:
            out.append(w.capitalize())
    return " ".join(out)


# ── Google: ricerca luoghi e percorsi ────────────────────────────────────────

_PLACES_CACHE = {}


def _luoghi(lat, lon, keyword, raggio_m=None, timeout=5):
    """Nearby Search per parola chiave. Senza raggio: ordinato per distanza
    (rankby=distance, max 20). Con raggio: ordinato per notorieta' (il default
    di Google), utile per "la spiaggia piu' importante". Ritorna
    [{nome, lat, lon, rec, types, _dist_km}] oppure [] se Google non risponde."""
    key = _chiave()
    lat, lon = _num(lat), _num(lon)
    if not key or lat is None or lon is None:
        return []
    ck = (round(lat, 3), round(lon, 3), keyword, raggio_m)
    if ck in _PLACES_CACHE:
        return _PLACES_CACHE[ck]
    params = {"location": f"{lat},{lon}", "keyword": keyword, "language": "it", "key": key}
    if raggio_m:
        params["radius"] = int(raggio_m)
    else:
        params["rankby"] = "distance"
    try:
        resp = requests.get(GOOGLE_PLACES_NEARBY_URL, params=params, timeout=timeout)
        if resp.status_code != 200:
            return []
        dati = resp.json()
        if dati.get("status") not in ("OK", "ZERO_RESULTS"):
            print(f"[POI-TERRITORIO] Places status {dati.get('status')} per {keyword!r}")
            return []
        out = []
        for r in dati.get("results", []):
            loc = (r.get("geometry") or {}).get("location") or {}
            if r.get("name") and loc.get("lat") is not None and loc.get("lng") is not None:
                out.append({"nome": r["name"], "lat": loc["lat"], "lon": loc["lng"],
                            "rec": r.get("user_ratings_total") or 0,
                            "types": r.get("types") or [],
                            "_dist_km": _haversine_km(lat, lon, loc["lat"], loc["lng"])})
        out.sort(key=lambda x: x["_dist_km"])
        _PLACES_CACHE[ck] = out
        return out
    except Exception as e:
        print(f"[POI-TERRITORIO] eccezione Places {keyword!r}: {type(e).__name__}: {e}")
        return []


_PERCORSO_CACHE = {}


def percorso(lat1, lon1, lat2, lon2, modo, timeout=4):
    """(metri, minuti) del percorso reale (Distance Matrix) o None. modo:
    "walking" / "driving". Si cachea solo il successo."""
    key = _chiave()
    try:
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
    except (TypeError, ValueError):
        return None
    if not key:
        return None
    ck = (round(lat1, 4), round(lon1, 4), round(lat2, 4), round(lon2, 4), modo)
    if ck in _PERCORSO_CACHE:
        return _PERCORSO_CACHE[ck]
    risultato = None
    try:
        resp = requests.get(GOOGLE_DISTANCE_URL,
                            params={"origins": f"{lat1},{lon1}", "destinations": f"{lat2},{lon2}",
                                    "mode": modo, "key": key}, timeout=timeout)
        if resp.status_code == 200:
            d = resp.json()
            if d.get("status") == "OK":
                el = d["rows"][0]["elements"][0]
                if el.get("status") == "OK":
                    risultato = (int(el["distance"]["value"]),
                                 max(1, int(round(el["duration"]["value"] / 60.0))))
    except Exception:
        risultato = None
    if risultato is not None:
        _PERCORSO_CACHE[ck] = risultato
    return risultato


def distanza_testo(lat, lon, dlat, dlon):
    """(testo, impatto). A piedi se il percorso e' entro 25 minuti, altrimenti in
    auto; se la Distance Matrix non risponde, linea d'aria dichiarata come tale.
    Un percorso a piedi molto piu' lungo di quello in auto (Maratea: 3,3 km a
    piedi contro 200 m in auto, il punto di partenza cade in un'area pedonale)
    e' un'anomalia di Google: non si stampa."""
    linea_km = _haversine_km(float(lat), float(lon), float(dlat), float(dlon))
    p = percorso(lat, lon, dlat, dlon, "walking")
    a = None
    if p is None or p[1] > 12:
        a = percorso(lat, lon, dlat, dlon, "driving")
        if p and a and p[0] > max(1.5 * a[0], a[0] + 300):
            p = None
    if p and p[1] <= 25:
        impatto = "Alto" if p[1] <= 15 else "Medio"
        return f"{fmt_metri(p[0])} · {p[1]} min a piedi", impatto
    if a and a[0] > 1500:
        impatto = "Medio" if a[1] <= 10 else "Basso"
        return f"{fmt_metri(a[0])} · {a[1]} min in auto", impatto
    impatto = "Alto" if linea_km <= 1.2 else "Medio" if linea_km <= 4 else "Basso"
    return f"{fmt_metri(linea_km * 1000)} (linea d'aria)", impatto


# ── Mare ─────────────────────────────────────────────────────────────────────

_RE_SPIAGGIA = re.compile(r"^(spiaggia|spiaggetta|spiagge|cala|baia|arenile|lido)\b|\bspiaggia\b", re.IGNORECASE)
_RE_NON_SPIAGGIA = re.compile(
    r"hotel|resort|ristorant|trattoria|pizzeri|\bbar\b|camping|villaggio|b&b|appartament|residence|"
    r"affittacamere|casa vacanz|hostel|agriturism|parcheggio|accesso|sentiero|scuola|diving|noleggio|kayak|"
    r"escursion|sdraio|ombrellon|\bclub\b|ristoro|chiosco|stabiliment|\bbagni\b|\blidi\b|villa\b|"
    r"\bsrl\b|\bsnc\b|\bsas\b|gelateria|negozio|market", re.IGNORECASE)
_TIPI_NON_SPIAGGIA = {"lodging", "food", "restaurant", "bar", "cafe", "store", "real_estate_agency",
                      "travel_agency", "parking", "campground", "gym", "spa", "night_club", "meal_takeaway",
                      "bakery", "supermarket", "car_rental", "bicycle_store"}


_NOMI_GENERICI = {"spiaggia", "spiaggia libera", "spiaggia pubblica", "spiaggia attrezzata", "spiaggia comunale",
                  "lido", "lido comunale", "cala", "baia", "spiaggia di sabbia", "spiaggia privata"}


def _e_spiaggia(luogo):
    nome = luogo["nome"]
    if nome.strip().lower() in _NOMI_GENERICI:
        return False   # "Spiaggia Libera" da sola non dice quale spiaggia sia
    if not _RE_SPIAGGIA.search(nome) or _RE_NON_SPIAGGIA.search(nome):
        return False
    return not (set(luogo.get("types") or []) & _TIPI_NON_SPIAGGIA)


def _scegli_spiagge(candidati):
    """Da una lista Places (qualunque ordine) ritorna (piu_vicina, principale).
    piu_vicina: la spiaggia vera piu' vicina (i "Lido ..." solo se non ce ne sono
    altre). principale: la piu' recensita entro 5 km se ha almeno 300
    recensioni e almeno 5 volte la piu' vicina, altrimenti None."""
    visti, validi = set(), []
    for l in candidati:
        k = (l["nome"].lower(), round(l["lat"], 4), round(l["lon"], 4))
        if k in visti or not _e_spiaggia(l) or l["_dist_km"] > MAX_KM_SPIAGGIA:
            continue
        visti.add(k)
        validi.append(l)
    if not validi:
        return None, None
    non_lido = [l for l in validi if not l["nome"].lower().startswith("lido")]
    pool = non_lido or validi
    vicina = min(pool, key=lambda l: l["_dist_km"])
    entro5 = [l for l in pool if l["_dist_km"] <= 5]
    principale = max(entro5, key=lambda l: l["rec"]) if entro5 else None
    if (not principale or principale is vicina or principale["rec"] < 300
            or principale["rec"] < 5 * max(vicina["rec"], 1)):
        principale = None
    return vicina, principale


def righe_spiaggia(lat, lon):
    """[[etichetta, distanza, nome, impatto], ...] (0-2 righe)."""
    d_costa = territorio_gps.distanza_costa_km(lat, lon)
    if d_costa is None or d_costa > MAX_KM_COSTA:
        return []
    candidati = (_luoghi(lat, lon, "spiaggia") + _luoghi(lat, lon, "spiaggia", raggio_m=8000)
                 + _luoghi(lat, lon, "cala baia"))
    vicina, principale = _scegli_spiagge(candidati)
    if not vicina:
        return []
    righe = []
    for etichetta, luogo in (("Spiaggia più vicina", vicina), ("Spiaggia principale", principale)):
        if not luogo:
            continue
        testo, impatto = distanza_testo(lat, lon, luogo["lat"], luogo["lon"])
        righe.append([etichetta, testo, _titolo(luogo["nome"]), impatto])
    return righe


# ── Lago ─────────────────────────────────────────────────────────────────────

_RE_ACCESSO_LAGO = re.compile(
    r"^(lungolago|lido|spiaggia|spiaggetta|imbarcadero|darsena|molo|pontile|approdo|passeggiata)\b|lungolago",
    re.IGNORECASE)


def lago_piu_vicino(lat, lon, max_km=MAX_KM_LAGO):
    """(nome, km) del lago noto piu' vicino ai punti di sponda della lista
    curata, oppure (None, None). La lista e' fatta di punti di sponda, non di
    poligoni: la distanza e' indicativa, non "al metro"."""
    lat, lon = _num(lat), _num(lon)
    if lat is None or lon is None:
        return None, None
    migliore = (None, None)
    for nome, punti, _soglia in territorio_gps.LAGHI_ITALIA:
        for plat, plon in punti:
            d = _haversine_km(lat, lon, plat, plon)
            if d <= max_km and (migliore[1] is None or d < migliore[1]):
                migliore = (nome, d)
    return migliore


def righe_lago(lat, lon):
    nome_lago, dkm = lago_piu_vicino(lat, lon)
    if not nome_lago:
        return []
    accessi = []
    for kw in ("lungolago", "spiaggia", "lido"):
        accessi += [l for l in _luoghi(lat, lon, kw)
                    if _RE_ACCESSO_LAGO.search(l["nome"]) and not _RE_NON_SPIAGGIA.search(l["nome"])
                    and not (set(l.get("types") or []) & _TIPI_NON_SPIAGGIA)
                    and l["_dist_km"] <= MAX_KM_ACCESSO_LAGO]
    if accessi:
        acc = min(accessi, key=lambda l: l["_dist_km"])
        testo, impatto = distanza_testo(lat, lon, acc["lat"], acc["lon"])
        nome_acc = _titolo(acc["nome"])
        etichetta_nome = nome_lago if nome_lago.lower() in nome_acc.lower() else f"{nome_lago} ({nome_acc})"
        return [["Lago", testo, etichetta_nome, impatto]]
    # Nessun punto di accesso: distanza dalla sponda della lista curata, dichiarata
    # come indicativa (arrotondata a 0,5 km), mai "al metro".
    km = max(0.5, round(dkm * 2) / 2.0)
    impatto = "Alto" if km <= 1.5 else "Medio" if km <= 5 else "Basso"
    return [["Lago", f"circa {fmt_metri(km * 1000)} (linea d'aria)", nome_lago, impatto]]


# ── Montagna ─────────────────────────────────────────────────────────────────

def _cime_wikidata(lat, lon, raggio_km=RAGGIO_MONTE_KM, timeout=6):
    sparql = f"""
SELECT ?itemLabel ?ele ?coord ?links WHERE {{
  SERVICE wikibase:around {{
    ?item wdt:P625 ?coord .
    bd:serviceParam wikibase:center "Point({lon} {lat})"^^geo:wktLiteral .
    bd:serviceParam wikibase:radius "{raggio_km}" .
  }}
  ?item wdt:P31/wdt:P279* wd:Q8502 .
  ?item wdt:P2044 ?ele .
  FILTER(?ele >= 1000)
  ?item wikibase:sitelinks ?links .
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "it,en". }}
}} ORDER BY DESC(?links) LIMIT 12"""
    try:
        r = requests.get(WIKIDATA_SPARQL_URL, params={"query": sparql, "format": "json"},
                         headers={"User-Agent": "ReportUp/1.0 (reportup.info@gmail.com)"}, timeout=timeout)
        if r.status_code != 200:
            return []
        out = []
        for b in r.json()["results"]["bindings"]:
            m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", b["coord"]["value"])
            if not m:
                continue
            clon, clat = float(m.group(1)), float(m.group(2))
            nome = b["itemLabel"]["value"]
            if re.match(r"^Q\d+$", nome):   # senza etichetta italiana/inglese
                continue
            out.append({"nome": nome, "ele": float(b["ele"]["value"]), "links": int(b["links"]["value"]),
                        "lat": clat, "lon": clon, "_dist_km": _haversine_km(lat, lon, clat, clon)})
        return out
    except Exception as e:
        print(f"[POI-TERRITORIO] eccezione Wikidata: {type(e).__name__}: {e}")
        return []


def riga_montagna(lat, lon, quota):
    """La cima piu' nota (voci Wikipedia) entro 12 km, altrimenti entro 20."""
    if quota is None or quota < QUOTA_MIN_MONTAGNA:
        return []
    lat, lon = _num(lat), _num(lon)
    if lat is None or lon is None:
        return []
    cime = _cime_wikidata(lat, lon)
    if not cime:
        return []
    vicine = [c for c in cime if c["_dist_km"] <= 12]
    # Notorieta' (voci Wikipedia) per quota: tra due cime ugualmente note vince la piu' alta.
    cima = max(vicine or cime, key=lambda c: (c["links"] * c["ele"], -c["_dist_km"]))
    nome = cima["nome"]
    quota_txt = f"{int(round(cima['ele'])):,}".replace(",", ".")
    km = cima["_dist_km"]
    impatto = "Alto" if km <= 10 else "Medio" if km <= 25 else "Basso"
    return [["Montagna di riferimento", f"{fmt_metri(km * 1000)} (linea d'aria)",
             f"{_titolo(nome)} ({quota_txt} m)", impatto]]


# ── Ingresso unico ───────────────────────────────────────────────────────────

def poi_territoriali(lat, lon):
    """Righe extra [[etichetta, distanza, nome, impatto], ...] + contesto
    {"vicino_mare": bool, "vicino_lago": bool}. Qualunque errore: niente righe."""
    righe, ctx = [], {"vicino_mare": False, "vicino_lago": False}
    try:
        if _num(lat) is None or _num(lon) is None:
            return righe, ctx
        mare = righe_spiaggia(lat, lon)
        lago = righe_lago(lat, lon)
        quota = territorio_gps.elevazione_metri(lat, lon)
        monte = riga_montagna(lat, lon, quota)
        righe = mare + lago + monte
        ctx["vicino_mare"] = bool(mare) and (territorio_gps.distanza_costa_km(lat, lon) or 99) <= 3.0
        ctx["vicino_lago"] = bool(lago) and (lago_piu_vicino(lat, lon, 3.0)[0] is not None)
    except Exception as e:
        print(f"[POI-TERRITORIO] saltato: {type(e).__name__}: {e}")
        return [], {"vicino_mare": False, "vicino_lago": False}
    return righe, ctx

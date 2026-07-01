# ── Classificazione territoriale via GPS — sostituisce la sottocategoria statica per comune ──
#
# Problema che risolve: prima la sottocategoria (costiero/lacuale/montano) era una proprietà
# fissa del COMUNE intero. Un comune esteso come Giugliano in Campania ha sia un centro
# interno che una frazione costiera (Varcaturo): la vecchia logica li trattava allo stesso
# modo. Qui si classifica il PUNTO ESATTO dell'indirizzo (lat/long già disponibili da
# Geocode), non il comune.
#
# Costiero e lacuale: calcolo offline, zero chiamate esterne, zero costo per ordine.
#   Dati costa: Natural Earth 10m coastline, ritagliati su bbox Italia (vedi
#   territorio_costa_data.py — rigenerabile se serve più precisione).
#   Dati laghi: lista curata a mano dei laghi italiani principali (facile da estendere,
#   stesso pattern del dizionario ALIAS in comuni_lookup.py).
#
# Montano: richiede la quota reale del punto, non deducibile da geometria — un'unica
# chiamata alla Google Elevation API (stessa chiave Google già in uso, va solo abilitata
# l'API "Elevation API" sul progetto Google Cloud). Cache in memoria, fallback silenzioso.

import math
import os
import requests

from territorio_costa_data import SEGMENTI_COSTA

# ── Laghi italiani principali ────────────────────────────────────────────────
# Ogni lago: alcuni punti lungo la sponda (non solo il centro, per non essere troppo
# larghi sui laghi allungati come Garda) + soglia in km da quei punti.
# Per aggiungere un lago mancante: aggiungere una voce con 2-4 punti sponda e soglia_km.
LAGHI_ITALIA = [
    ("Lago di Garda", [
        (45.4386, 10.6892),  # Peschiera del Garda
        (45.4667, 10.5333),  # Desenzano del Garda
        (45.4947, 10.6069),  # Sirmione
        (45.6083, 10.5233),  # Salò
        (45.6236, 10.5678),  # Gardone Riviera
        (45.5497, 10.7194),  # Bardolino
        (45.6167, 10.6833),  # Torri del Benaco
        (45.7669, 10.8078),  # Malcesine
        (45.8850, 10.8419),  # Riva del Garda
    ], 2.5),
    ("Lago Maggiore", [
        (45.7597, 8.5597),   # Arona
        (45.7667, 8.5833),   # Angera
        (45.8850, 8.5325),   # Stresa
        (45.9227, 8.5514),   # Verbania
        (45.9167, 8.6167),   # Laveno-Mombello
        (46.1667, 8.8000),   # Locarno (confine)
    ], 2.5),
    ("Lago di Como", [
        (45.9664, 9.2564),   # Lecco
        (45.9664, 8.6545),   # Griante/Bellagio zona
        (45.8567, 9.0850),   # Bellagio
        (46.1500, 9.3167),   # Colico
        (45.8100, 9.0850),   # Como città
    ], 2.5),
    ("Lago d'Iseo", [
        (45.6667, 10.0500),  # Iseo
        (45.7333, 10.0667),  # Sarnico/Predore zona
    ], 2.0),
    ("Lago d'Orta", [(45.8000, 8.4000)], 1.5),
    ("Lago Trasimeno", [
        (43.1836, 12.1444),  # Passignano sul Trasimeno
        (43.1231, 12.0409),  # Castiglione del Lago
        (43.2144, 12.0644),  # Tuoro sul Trasimeno
        (43.1167, 12.1667),  # San Feliciano
    ], 2.0),
    ("Lago di Bolsena",    [(42.6389, 11.9906), (42.5667, 11.9333)], 2.0),
    ("Lago di Bracciano",  [(42.1042, 12.1856), (42.0714, 12.2364)], 1.5),
    ("Lago di Vico",       [(42.3236, 12.1611)], 1.5),
    ("Lago di Nemi",       [(41.7167, 12.7167)], 1.0),
    ("Lago Albano",        [(41.7500, 12.6833)], 1.0),
    ("Lago d'Idro",        [(45.7667, 10.5000)], 1.5),
    ("Lago di Ledro",      [(45.8700, 10.7300)], 1.0),
    ("Lago di Molveno",    [(46.1500, 10.9500)], 1.0),
    ("Laghi di Levico e Caldonazzo", [(46.0000, 11.3000), (46.0200, 11.2500)], 1.5),
    ("Lago di Piediluco",  [(42.5300, 12.7500)], 1.0),
    ("Lago di Massaciuccoli", [(43.8300, 10.3300)], 1.5),
    ("Lago di Varano",     [(41.8800, 15.7200)], 2.0),
    ("Lago di Lesina",     [(41.8800, 15.4000)], 2.0),
    ("Lago di Scanno",     [(41.9000, 13.9000)], 1.0),
]

_R_TERRA_KM = 6371.0


def _haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * _R_TERRA_KM * math.asin(math.sqrt(a))


def _to_xy_km(lat, lon, ref_lat):
    """Proiezione locale approssimata in km (equirettangolare), sufficiente su scala <50km."""
    x = math.radians(lon) * _R_TERRA_KM * math.cos(math.radians(ref_lat))
    y = math.radians(lat) * _R_TERRA_KM
    return x, y


def _dist_punto_segmento_km(lat, lon, lat1, lon1, lat2, lon2):
    px, py = _to_xy_km(lat, lon, lat)
    ax, ay = _to_xy_km(lat1, lon1, lat)
    bx, by = _to_xy_km(lat2, lon2, lat)
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    proj_x, proj_y = ax + t * dx, ay + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def distanza_costa_km(lat, lon):
    """Distanza minima (km) dal punto alla costa italiana. None se coordinate assenti."""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    migliore = None
    for lat1, lon1, lat2, lon2 in SEGMENTI_COSTA:
        d = _dist_punto_segmento_km(lat, lon, lat1, lon1, lat2, lon2)
        if migliore is None or d < migliore:
            migliore = d
    return migliore


def lago_vicino(lat, lon):
    """Nome del lago se il punto è entro soglia da un lago noto, altrimenti None."""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    for nome, punti, soglia_km in LAGHI_ITALIA:
        for plat, plon in punti:
            if _haversine_km(lat, lon, plat, plon) <= soglia_km:
                return nome
    return None


_ELEVATION_CACHE = {}


def elevazione_metri(lat, lon, timeout=3):
    """Quota del punto in metri via Google Elevation API. None se chiave assente o errore.
    Richiede la variabile d'ambiente GOOGLE_MAPS_API_KEY su Render (stessa chiave usata
    per Geocode/Places, con l'API 'Elevation API' abilitata sul progetto Google Cloud)."""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None

    cache_key = f"{round(lat, 4)},{round(lon, 4)}"
    if cache_key in _ELEVATION_CACHE:
        return _ELEVATION_CACHE[cache_key]

    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return None

    quota = None
    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/elevation/json",
            params={"locations": f"{lat},{lon}", "key": api_key},
            timeout=timeout,
        )
        if resp.status_code == 200:
            dati = resp.json()
            if dati.get("status") == "OK" and dati.get("results"):
                quota = dati["results"][0].get("elevation")
    except Exception:
        quota = None

    _ELEVATION_CACHE[cache_key] = quota
    return quota


_DISTANCE_MATRIX_CACHE = {}


def distanza_e_tempo_auto(lat1, lon1, lat2, lon2, timeout=4):
    """
    Distanza e tempo di percorrenza IN AUTO tra due punti, via Google Distance
    Matrix API (stessa chiave GOOGLE_MAPS_API_KEY già in uso per l'elevazione).
    Ritorna (km_auto, minuti_auto) oppure None se la chiave manca, l'API non
    risponde, o la rotta non è disponibile (es. isole senza collegamento auto) —
    in quel caso chi chiama ricade sulla distanza in linea d'aria.
    """
    try:
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
    except (TypeError, ValueError):
        return None

    cache_key = f"{round(lat1,4)},{round(lon1,4)}|{round(lat2,4)},{round(lon2,4)}"
    if cache_key in _DISTANCE_MATRIX_CACHE:
        return _DISTANCE_MATRIX_CACHE[cache_key]

    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return None

    risultato = None
    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/distancematrix/json",
            params={
                "origins": f"{lat1},{lon1}",
                "destinations": f"{lat2},{lon2}",
                "mode": "driving",
                "key": api_key,
            },
            timeout=timeout,
        )
        if resp.status_code == 200:
            dati = resp.json()
            if dati.get("status") == "OK":
                elemento = dati["rows"][0]["elements"][0]
                if elemento.get("status") == "OK":
                    km = round(elemento["distance"]["value"] / 1000)
                    minuti = round(elemento["duration"]["value"] / 60)
                    risultato = (km, minuti)
    except Exception:
        risultato = None

    _DISTANCE_MATRIX_CACHE[cache_key] = risultato
    return risultato


def classifica_sottocategoria(lat, lon):
    """
    Ritorna 'costiero' / 'lacuale' / 'montano' / None in base al punto GPS esatto
    dell'indirizzo — non più al comune. Priorità: costa, poi lago, poi quota.
    Un indirizzo può teoricamente essere sia costiero che in quota (es. costiera
    amalfitana): la costa vince perché più rilevante per il posizionamento B&B.
    """
    if lat in (None, "", "\u2014") or lon in (None, "", "\u2014"):
        return None

    d_costa = distanza_costa_km(lat, lon)
    if d_costa is not None and d_costa <= 3.0:
        return "costiero"

    if lago_vicino(lat, lon):
        return "lacuale"

    quota = elevazione_metri(lat, lon)
    if quota is not None and quota >= SOGLIA_MONTANO_METRI:
        return "montano"

    return None

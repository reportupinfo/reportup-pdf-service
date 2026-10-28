"""Self-test (senza rete) delle funzioni pure di territorio_poi.
Lanciare dopo ogni modifica: python test_territorio_poi.py"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import territorio_poi as tp

assert tp.fmt_metri(354) == "350 m", tp.fmt_metri(354)
assert tp.fmt_metri(4) == "10 m"
assert tp.fmt_metri(1380) == "1,4 km"
assert tp.fmt_metri(14200) == "14 km"
assert tp._titolo("Spiaggia Nera o Cala Jannita") == "Spiaggia Nera o Cala Jannita"


def L(nome, dist, rec=10, types=None):
    return {"nome": nome, "lat": 40.0 + dist / 111.0, "lon": 15.0, "rec": rec,
            "types": types or ["establishment", "point_of_interest"], "_dist_km": dist}


# stabilimenti, bar, hotel e nomi generici non sono "la spiaggia"
assert not tp._e_spiaggia(L("Spiaggia Libera", 0.3))
assert not tp._e_spiaggia(L("Baia Stanca Beach Bar", 0.3, types=["bar", "establishment"]))
assert not tp._e_spiaggia(L("Hotel Spiaggia d'Oro", 0.3))
assert not tp._e_spiaggia(L("Bagno 23 Sirena Beach", 0.3))
assert tp._e_spiaggia(L("Spiaggia di Fiumicello", 0.3, 1600))

vicina, principale = tp._scegli_spiagge([
    L("Spiaggia Del Crivo", 0.3, 5),
    L("Spiaggia di Fiumicello", 1.6, 1614),
    L("Lido l'Approdo Fiumicello", 1.7, 185),
    L("Spiaggia Remota", 20.0, 9000),          # oltre 12 km: ignorata
])
assert vicina["nome"] == "Spiaggia Del Crivo", vicina
assert principale and principale["nome"] == "Spiaggia di Fiumicello", principale

# principale solo se molto piu' recensita; i "Lido" solo in mancanza di spiagge
v2, p2 = tp._scegli_spiagge([L("Spiaggia A", 0.5, 100), L("Spiaggia B", 1.0, 200)])
assert v2["nome"] == "Spiaggia A" and p2 is None
v3, _ = tp._scegli_spiagge([L("Lido Azzurro", 0.2, 50), L("Spiaggia Grande", 1.0, 80)])
assert v3["nome"] == "Spiaggia Grande"
v4, _ = tp._scegli_spiagge([L("Lido Azzurro", 0.2, 50)])
assert v4["nome"] == "Lido Azzurro"
assert tp._scegli_spiagge([]) == (None, None)

# lago: la lista curata trova Garda a Torri del Benaco e niente a Piacenza
assert tp.lago_piu_vicino(45.6180, 10.6820)[0] == "Lago di Garda"
assert tp.lago_piu_vicino(45.0522, 9.6930) == (None, None)

# viabilita': casello vero (non localita' omonime, aziende, attrazioni) e stazione ferroviaria vera
assert tp._scegli_casello([
    L("Casello", 0.5, types=["locality", "political"]),                           # localita' omonima
    L("Autostrada Brescia Verona Vicenza Padova Spa", 1.0),                       # azienda, non un casello
    L("Uscita Costa di Maratea", 2.0, types=["tourist_attraction", "establishment"]),
    L("Svincolo Padula", 3.0, types=["gas_station", "establishment"]),
    L("Casello di Piacenza Sud", 4.6),
    L("Casello di Piacenza Ovest", 2.8),
])["nome"] == "Casello di Piacenza Ovest"
assert tp._scegli_casello([L("Casello di Polla", 55.0)]) is None                  # oltre 40 km
assert tp._scegli_casello([]) is None
T = ["train_station", "transit_station", "point_of_interest"]
assert tp._scegli_stazione([L("Bivio/PC S. Lucia", 1.0, types=T), L("Verona Porta Nuova", 1.4, types=T)])["nome"] == "Verona Porta Nuova"
assert tp._scegli_stazione([L("Fermata Bus 12", 0.2, types=["bus_station", "transit_station"])]) is None   # non e' ferrovia
assert tp._scegli_stazione([L("Lioni", 20.0, types=T)]) is None                   # oltre 15 km
# la stazione gia' mostrata come "Trasporto pubblico" non si ripete
assert tp._scegli_stazione([L("Scalea", 1.1, types=T)], escludi_nomi=["Stazione di Scalea"]) is None
assert tp._scegli_stazione([L("Scalea", 1.1, types=T)], escludi_nomi=["Fermata Via Roma"])["nome"] == "Scalea"
assert tp._scegli_stazione([L("Scalea", 1.1, types=T)], escludi_nomi=["Fermata Scalea Ss 18 - Baiatour"])["nome"] == "Scalea"   # fermata bus != stazione
assert tp._nome_stazione("Scalea") == "Stazione di Scalea"
assert tp._nome_stazione("Stazione Ancona Stadio") == "Stazione Ancona Stadio"

# senza chiave Google nessuna riga e nessuna eccezione
os.environ.pop("GOOGLE_MAPS_API_KEY", None)
assert tp.righe_spiaggia(39.99, 15.71) == []   # costa vicina ma niente chiave: nessuna riga, nessuna eccezione
righe, ctx = tp.poi_territoriali(None, None)
assert righe == [] and ctx == {"vicino_mare": False, "vicino_lago": False}
print("OK")

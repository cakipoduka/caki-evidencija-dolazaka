"""
CAKI — profesor_danas.py  (12.10.2026.)
Logika kartice "🏠 Danas" u portalu za profesore. Čiste funkcije (bez Streamlita i bez pisanja u Sheet),
da se mogu testirati: testovi/test_profesor_danas.py.

Prikazuje se SAMO ono što profesor već smije vidjeti: njegove grupe, njegove instrukcije, njegov izvještaj.
Nikad cijene, iznose ni kontakte.
"""
from datetime import date, timedelta

import pandas as pd

from pipeline_upisi import (
    DANI_U_TJEDNU,
    ROK_PROFESOR_DANA,
    blok_aktivan_na_datum,
    blokovi_nastavnika,
    program_ima_blokove,
    lijepo_vrijeme,
    matura_kante,
    razdoblje_grupe_upisa,
    razdoblje_kante_mature,
    u_datum,
    vrijeme_u_minute,
)


def _tekst(v) -> str:
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip()


def _termin_zabiljezen(df_termini: pd.DataFrame, grupa_id: str, d: date) -> bool:
    """Postoji li u tabu Termini redak za (grupa_id, datum)."""
    if df_termini is None or df_termini.empty or "grupa_id" not in df_termini.columns:
        return False
    t = df_termini[(df_termini["grupa_id"].astype(str) == str(grupa_id))
                   & (df_termini["datum"].astype(str).str[:10] == d.isoformat())]
    return not t.empty


def moji_blokovi(df_grupe, df_raspored_matura, razdoblja: dict, praznici: dict, nastavnik: str,
                 df_blokovi=None) -> list:
    """Tjedni blokovi (Upisi grupe + Matura kante) u kojima je profesor upisan kao redovni, PLUS
    pojedini blokovi višepredmetnih termina (PRELOG) koje drži (18.10.2026.).
    [{izvor, grupa_id, dan, vrijeme, minute, naziv, ucionica, od, do}]

    Kod višepredmetnog programa jedan profesor ne drži cijeli termin nego pojedini blok na
    pojedini datum, pa se tjedni zapis grupe PRESKAČE kad za nju postoje upisani blokovi —
    inače bi se isti datum pojavio dvaput, i to s pogrešnim predmetom."""
    out = []
    s_blokovima = {b["grupa_id"] for b in blokovi_nastavnika(df_blokovi, nastavnik)} if nastavnik else set()
    if df_grupe is not None and not df_grupe.empty and "dan" in df_grupe.columns:
        for _, g in df_grupe.iterrows():
            if _tekst(g.get("aktivna")).lower() != "da":
                continue
            if program_ima_blokove(g.get("program")) and _tekst(g.get("grupa_id")) in s_blokovima:
                continue          # taj termin je opisan blokovima, niže
            if _tekst(g.get("redovni_nastavnik")) != nastavnik:
                continue
            od, do, _ = razdoblje_grupe_upisa(g, razdoblja, praznici)
            out.append({"izvor": "Upisi", "grupa_id": _tekst(g.get("grupa_id")), "dan": _tekst(g.get("dan")),
                        "vrijeme": lijepo_vrijeme(g.get("vrijeme")), "minute": vrijeme_u_minute(g.get("vrijeme")) or (0, 0),
                        "naziv": _tekst(g.get("program")), "ucionica": _tekst(g.get("ucionica")), "od": od, "do": do})
    for k in matura_kante(df_raspored_matura):
        if k["profesor"] != nastavnik:
            continue
        od, do = razdoblje_kante_mature(k, razdoblja, praznici)
        out.append({"izvor": "Matura", "grupa_id": k["grupa_id"], "dan": k["dan"],
                    "vrijeme": lijepo_vrijeme(k["vrijeme"]), "minute": vrijeme_u_minute(k["vrijeme"]) or (0, 0),
                    "naziv": " + ".join(k["predmeti"]) or "Matura", "ucionica": k["ucionica"], "od": od, "do": do})
    # Blokovi višepredmetnih termina: razdoblje je točno taj jedan datum, pa ih sati_na_datum()
    # pokaže samo tada, bez ikakve nove logike.
    grupe_po_id = {}
    if df_grupe is not None and not df_grupe.empty and "grupa_id" in df_grupe.columns:
        grupe_po_id = {_tekst(g.get("grupa_id")): g for _, g in df_grupe.iterrows()}
    for b in blokovi_nastavnika(df_blokovi, nastavnik):
        if not b["datum"]:
            continue
        g = grupe_po_id.get(b["grupa_id"], {})
        naziv = (_tekst(g.get("program")) + " " + b["predmet"]).strip() if len(g) else b["predmet"]
        out.append({"izvor": "Upisi", "grupa_id": b["grupa_id"],
                    "dan": DANI_U_TJEDNU[b["datum"].weekday()], "vrijeme": b["vrijeme"],
                    "minute": vrijeme_u_minute(b["vrijeme"]) or (0, 0), "naziv": naziv,
                    "ucionica": _tekst(g.get("ucionica")) if len(g) else "",
                    "od": b["datum"], "do": b["datum"]})
    return out


def sati_na_datum(blokovi: list, d: date, praznici: dict) -> list:
    """Blokovi koji se taj datum stvarno održavaju (dan u tjednu, razdoblje, ne praznik), po vremenu."""
    if d in (praznici or {}):
        return []
    dan = DANI_U_TJEDNU[d.weekday()]
    res = [b for b in blokovi if b["dan"] == dan and blok_aktivan_na_datum({"datum_od": b["od"], "datum_do": b["do"]}, d)]
    return sorted(res, key=lambda b: (b["minute"], b["naziv"]))


def danasnji_sati(blokovi: list, df_termini: pd.DataFrame, danas: date, praznici: dict) -> list:
    """Sati za danas, svaki s oznakom `zabiljezen`."""
    return [dict(b, zabiljezen=_termin_zabiljezen(df_termini, b["grupa_id"], danas))
            for b in sati_na_datum(blokovi, danas, praznici)]


def nezabiljezeni_sati(blokovi: list, df_termini: pd.DataFrame, danas: date, praznici: dict,
                       rok: int = ROK_PROFESOR_DANA) -> list:
    """Prošli sati (zadnjih `rok` dana, bez današnjeg) koji nisu zabilježeni. Najhitniji (najmanje preostalih
    dana) prvi. [{...blok, datum, zadnji_dan, preostalo_dana}]; preostalo_dana 0 = zadnji dan za upis je danas."""
    out = []
    for i in range(1, rok + 1):
        d = danas - timedelta(days=i)
        for b in sati_na_datum(blokovi, d, praznici):
            if not _termin_zabiljezen(df_termini, b["grupa_id"], d):
                zadnji = d + timedelta(days=rok)
                out.append(dict(b, datum=d, zadnji_dan=zadnji, preostalo_dana=(zadnji - danas).days))
    return sorted(out, key=lambda x: (x["preostalo_dana"], x["minute"]))


def pregled_instrukcija(df_instr: pd.DataFrame, nastavnik: str, danas: date, unaprijed: int = 7) -> dict:
    """{'danas': [...], 'cekaju_status': [...], 'nadolazece': [...]} — redci kao dict-ovi s ključem `d` (date).
    cekaju_status = termini koji su još 'Zakazan', a datum im je prošao (profesor mora označiti Održan/Otkazan).
    Ako tab nema stupac status_termina, svi se tretiraju kao evidentirani (nema zakazanih)."""
    prazno = {"danas": [], "cekaju_status": [], "nadolazece": []}
    if df_instr is None or df_instr.empty or "nastavnik" not in df_instr.columns:
        return prazno
    t = df_instr[df_instr["nastavnik"].astype(str).str.strip() == nastavnik]
    res = {"danas": [], "cekaju_status": [], "nadolazece": []}
    for _, r in t.iterrows():
        d = u_datum(_tekst(r.get("datum"))[:10])
        if not d:
            continue
        status = _tekst(r.get("status_termina")) if "status_termina" in t.columns else ""
        red = {"d": d, "termin_id": _tekst(r.get("termin_id")), "ucenik": _tekst(r.get("ime_djeteta")),
               "predmet": _tekst(r.get("predmet")), "min": _tekst(r.get("duljina_min")),
               "oblik": _tekst(r.get("oblik")), "status": status or "Održan"}
        if d == danas:
            res["danas"].append(red)
        elif d < danas and status == "Zakazan":
            res["cekaju_status"].append(red)
        elif danas < d <= danas + timedelta(days=unaprijed) and status == "Zakazan":
            res["nadolazece"].append(red)
    for k in res:
        res[k].sort(key=lambda x: x["d"])
    return res


def prosli_mjesec(danas: date) -> tuple:
    return (danas.year, danas.month - 1) if danas.month > 1 else (danas.year - 1, 12)


def status_izvjestaja(df_izv: pd.DataFrame, nastavnik: str, danas: date) -> dict:
    """Izvještaj za prošli mjesec: {'mjesec': '2026-09', 'status': 'Nije poslan' | stvarni status, 'napomena_admin': str}."""
    g, m = prosli_mjesec(danas)
    kljuc = f"{g}-{m:02d}"
    if df_izv is not None and not df_izv.empty and {"nastavnik", "mjesec", "status"} <= set(df_izv.columns):
        r = df_izv[(df_izv["nastavnik"] == nastavnik) & (df_izv["mjesec"].astype(str) == kljuc)]
        if not r.empty:
            x = r.iloc[0]
            return {"mjesec": kljuc, "status": _tekst(x["status"]) or "Poslano",
                    "napomena_admin": _tekst(x.get("napomena_admin"))}
    return {"mjesec": kljuc, "status": "Nije poslan", "napomena_admin": ""}

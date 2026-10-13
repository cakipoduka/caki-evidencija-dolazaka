"""
CAKI — dostupnost_profesora.py  (13.10.2026.)
Tjedna dostupnost profesora za NOVE instrukcije. Profesor je unosi u portalu (kartica 🗓️ Dostupnost), admin je vidi u CRM-u
(📝 Instrukcije → 🗓️ Dostupnost profesora i uz upite) da zna kome može dodijeliti novog učenika bez telefoniranja.

Tab Dostupnost_profesora (nastaje sam pri prvom spremanju): dostupnost_id, profesor, vrsta (Termin / Postavke), dan, od, do,
oblik (Uživo / Online / Oboje), napomena, pauza (Da/Ne, samo vrsta Postavke), aktivno (Da/Ne), azurirano.
Spremanje NE briše ništa: stari redovi profesora dobiju aktivno = Ne, novi se dodaju (povijest ostaje, nema utrka).

Ova datoteka je ISTA u caki-upisi-crm-main (admin) i caki-evidencija-dolazaka (portal). Ne dira pipeline_upisi.py.
Dostupnost je informacija za admina; ništa se ne dodjeljuje i ne šalje automatski.
"""
import re
from datetime import date

import pandas as pd

from pipeline_upisi import (
    DANI_U_TJEDNU,
    _dodaj_red_po_nazivu,
    _id,
    _load_opcionalno,
    _load_worksheet_df,
    _osiguraj_tab_stupce,
    sada_zagreb,
    u_datum,
)

DOSTUPNOST_TAB = "Dostupnost_profesora"
DOSTUPNOST_HEADERS = ["dostupnost_id", "profesor", "vrsta", "dan", "od", "do", "oblik", "napomena", "pauza", "aktivno",
                      "azurirano"]
VRSTA_TERMIN, VRSTA_POSTAVKE = "Termin", "Postavke"
OBLICI = ["Uživo", "Online", "Oboje"]
NAJVISE_PROZORA_DNEVNO = 2
ZASTARJELO_DANA = 60          # dostupnost starija od ovoga traži se ponovno potvrditi
VREMENA = [f"{h:02d}:{m:02d}" for h in range(7, 23) for m in (0, 30)] + ["23:00"]


def _t(v) -> str:
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip()


def u_minute(tekst) -> int | None:
    """'17:30' / '17.30' / '17:30:00' → 1050; neispravno → None."""
    m = re.match(r"^\s*(\d{1,2})[:.](\d{2})(?::\d{2})?\s*$", _t(tekst))
    if not m or int(m[1]) > 23 or int(m[2]) > 59:
        return None
    return int(m[1]) * 60 + int(m[2])


def u_tekst_vremena(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def provjeri_redove(redovi: list) -> list:
    """Validira i normalizira prozore [{dan, od, do, oblik}] (od ≤ do, najviše 2 po danu, bez preklapanja unutar dana).
    Vraća čistu listu poredanu po danu i vremenu; baca ValueError s razumljivom porukom."""
    ciste = []
    for r in redovi:
        dan = _t(r.get("dan"))
        if dan not in DANI_U_TJEDNU:
            raise ValueError(f"Nepoznat dan: {dan or '—'}.")
        od, do = u_minute(r.get("od")), u_minute(r.get("do"))
        if od is None or do is None:
            raise ValueError(f"{dan}: odaberite početak i kraj.")
        if do <= od:
            raise ValueError(f"{dan}: kraj ({u_tekst_vremena(do)}) mora biti iza početka ({u_tekst_vremena(od)}).")
        oblik = _t(r.get("oblik")) or "Oboje"
        if oblik not in OBLICI:
            raise ValueError(f"{dan}: nepoznat oblik '{oblik}'.")
        ciste.append({"dan": dan, "od": od, "do": do, "oblik": oblik})
    ciste.sort(key=lambda x: (DANI_U_TJEDNU.index(x["dan"]), x["od"]))
    for dan in DANI_U_TJEDNU:
        d = [x for x in ciste if x["dan"] == dan]
        if len(d) > NAJVISE_PROZORA_DNEVNO:
            raise ValueError(f"{dan}: najviše {NAJVISE_PROZORA_DNEVNO} vremenska okvira dnevno.")
        for a, b in zip(d, d[1:]):
            if b["od"] < a["do"]:
                raise ValueError(f"{dan}: okviri {u_tekst_vremena(a['od'])}–{u_tekst_vremena(a['do'])} i "
                                 f"{u_tekst_vremena(b['od'])}–{u_tekst_vremena(b['do'])} se preklapaju.")
    return [dict(x, od=u_tekst_vremena(x["od"]), do=u_tekst_vremena(x["do"])) for x in ciste]


def aktivni_redovi(df: pd.DataFrame, profesor: str = "") -> pd.DataFrame:
    if df is None or df.empty or "profesor" not in df.columns:
        return pd.DataFrame(columns=DOSTUPNOST_HEADERS)
    akt = df["aktivno"].astype(str).str.strip() if "aktivno" in df.columns else pd.Series("Da", index=df.index)
    out = df[akt != "Ne"]
    if profesor:
        out = out[out["profesor"].astype(str).str.strip() == profesor]
    return out


def dostupnost_profesora(df: pd.DataFrame, profesor: str) -> dict:
    """{'prozori': [{dan, od, do, oblik}], 'pauza': bool, 'napomena': str, 'azurirano': 'YYYY-MM-DD HH:MM' | ''}"""
    a = aktivni_redovi(df, profesor)
    prozori, pauza, napomena, azurirano = [], False, "", ""
    for _, r in a.iterrows():
        azurirano = max(azurirano, _t(r.get("azurirano")))
        if _t(r.get("vrsta")) == VRSTA_POSTAVKE:
            pauza, napomena = _t(r.get("pauza")) == "Da", _t(r.get("napomena"))
        elif _t(r.get("dan")) in DANI_U_TJEDNU and u_minute(r.get("od")) is not None and u_minute(r.get("do")) is not None:
            prozori.append({"dan": _t(r["dan"]), "od": u_tekst_vremena(u_minute(r["od"])),
                            "do": u_tekst_vremena(u_minute(r["do"])), "oblik": _t(r.get("oblik")) or "Oboje"})
    prozori.sort(key=lambda x: (DANI_U_TJEDNU.index(x["dan"]), x["od"]))
    return {"prozori": prozori, "pauza": pauza, "napomena": napomena, "azurirano": azurirano}


def spremi_dostupnost(sheet, profesor: str, redovi: list, pauza: bool = False, napomena: str = "") -> int:
    """Zamijeni dostupnost profesora. Validira PRIJE ikakvog pisanja. Vraća broj spremljenih prozora."""
    if not _t(profesor):
        raise ValueError("Nepoznat profesor.")
    ciste = provjeri_redove(redovi)
    _osiguraj_tab_stupce(sheet, DOSTUPNOST_TAB, DOSTUPNOST_HEADERS)
    ws = sheet.worksheet(DOSTUPNOST_TAB)
    headers = ws.row_values(1)
    df = _load_worksheet_df(ws)
    if not df.empty and "profesor" in df.columns:
        stari = aktivni_redovi(df, profesor)
        if not stari.empty:
            kol = headers.index("aktivno") + 1
            ws.batch_update([{"range": _a1(int(r["_row"]), kol), "values": [["Ne"]]} for _, r in stari.iterrows()],
                            raw=True)
    sada = sada_zagreb().strftime("%Y-%m-%d %H:%M")
    for r in ciste:
        _dodaj_red_po_nazivu(ws, {"dostupnost_id": _id("DS-"), "profesor": profesor, "vrsta": VRSTA_TERMIN, "dan": r["dan"],
                                  "od": r["od"], "do": r["do"], "oblik": r["oblik"], "aktivno": "Da", "azurirano": sada},
                             headers)
    _dodaj_red_po_nazivu(ws, {"dostupnost_id": _id("DS-"), "profesor": profesor, "vrsta": VRSTA_POSTAVKE,
                              "napomena": _t(napomena)[:300], "pauza": "Da" if pauza else "Ne", "aktivno": "Da",
                              "azurirano": sada}, headers)
    return len(ciste)


def _a1(red: int, kolona: int) -> str:
    slova = ""
    while kolona:
        kolona, ostatak = divmod(kolona - 1, 26)
        slova = chr(65 + ostatak) + slova
    return f"{slova}{red}"


def sazetak(d: dict) -> str:
    """'Pon 17:00–20:00 (Uživo) · Sri 16:00–19:00' ili '⏸️ ne prima nove učenike' / 'nije unijeo/la dostupnost'."""
    if d["pauza"]:
        return "⏸️ ne prima nove učenike" + (f" — {d['napomena']}" if d["napomena"] else "")
    if not d["prozori"]:
        return "nije unijeo/la dostupnost"
    dijelovi = [f"{p['dan'][:3]} {p['od']}–{p['do']}" + ("" if p["oblik"] == "Oboje" else f" ({p['oblik']})")
                for p in d["prozori"]]
    return " · ".join(dijelovi) + (f" — {d['napomena']}" if d["napomena"] else "")


def zastarjelo(d: dict, danas: date | None = None) -> bool:
    """Nema nikakvog unosa ili je zadnje ažuriranje starije od ZASTARJELO_DANA."""
    zadnje = u_datum(d["azurirano"][:10]) if d["azurirano"] else None
    return zadnje is None or ((danas or sada_zagreb().date()) - zadnje).days > ZASTARJELO_DANA


def slobodni_u(df: pd.DataFrame, profesori: list, dan: str, od: str, do: str, oblik: str = "Svejedno") -> list:
    """Profesori koji u zadanom danu i vremenu imaju prozor koji POKRIVA cijeli traženi termin i nisu na pauzi.
    oblik 'Svejedno' ne filtrira; 'Uživo'/'Online' prihvaća prozore tog oblika ili 'Oboje'."""
    a, b = u_minute(od), u_minute(do)
    if a is None or b is None or b <= a or dan not in DANI_U_TJEDNU:
        return []
    out = []
    for prof in profesori:
        d = dostupnost_profesora(df, prof)
        if d["pauza"]:
            continue
        for p in d["prozori"]:
            if p["dan"] == dan and u_minute(p["od"]) <= a and u_minute(p["do"]) >= b \
                    and (oblik == "Svejedno" or p["oblik"] in (oblik, "Oboje")):
                out.append(prof)
                break
    return out


def preklapanja_s_grupama(redovi: list, blokovi: list) -> list:
    """Upozorenja: prozori koji se preklapaju s profesorovim vlastitim grupnim satima.
    blokovi = profesor_danas.moji_blokovi(...) ({dan, vrijeme, minute (od, do), naziv})."""
    out = []
    for r in redovi:
        a, b = u_minute(r.get("od")), u_minute(r.get("do"))
        if a is None or b is None:
            continue
        for bl in blokovi:
            if bl["dan"] == r.get("dan") and bl.get("minute") and a < bl["minute"][1] and bl["minute"][0] < b:
                out.append(f"{r['dan']} {r['od']}–{r['do']} preklapa se s vašim grupnim satom "
                           f"({bl['naziv']}, {bl['vrijeme']}).")
    return out


def load_dostupnost(sheet) -> pd.DataFrame:
    return _load_opcionalno(sheet, DOSTUPNOST_TAB)

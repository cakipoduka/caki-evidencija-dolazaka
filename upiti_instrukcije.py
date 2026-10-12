"""
CAKI — upiti_instrukcije.py  (13.10.2026.)
Raspodjela NOVIH UPITA za instrukcije profesorima.

Tok: učenik se prijavi na formu "Instrukcije za školu / studente" → u tabu Prijave nastane redak
(program_tip = Instrukcije, jedan redak po predmetu). Profesor u portalu vidi OTVORENE upite (bez imena i kontakta)
i klikne "Preuzimam" ili "Ne mogu". VIŠE profesora može preuzeti isti upit. Admin u CRM-u vidi tko je preuzeo i
jednim klikom DODIJELI odabranog (→ postojeći tab Dodjele). Upit je tada zatvoren za sve.

Tab Upiti_instrukcije (nastaje sam pri prvom odgovoru): odgovor_id, redak_id, ucenik_id, predmet, profesor,
odgovor (Preuzimam / Ne mogu / Dodijeljeno / Nije odabran), napomena, kreirano, azurirano.

Ova datoteka je ISTA u caki-upisi-crm-main (admin) i caki-evidencija-dolazaka (portal za profesore).
Ne dira pipeline_upisi.py — koristi samo njegove postojeće pomoćne funkcije.
Privatnost: profesor NIKAD ne dobiva ime, kontakt, školu ni napomenu iz prijave — samo predmet, stupanj, oblik, starost upita.
"""
from datetime import date

import pandas as pd

from pipeline_upisi import (
    _azuriraj_polja,
    _datum,
    _dodaj_red_po_nazivu,
    _id,
    _load_opcionalno,
    _load_worksheet_df,
    _osiguraj_tab_stupce,
    aktivne_dodjele,
    dodaj_dodjelu,
    sada_zagreb,
)

UPITI_TAB = "Upiti_instrukcije"
UPITI_HEADERS = ["odgovor_id", "redak_id", "ucenik_id", "predmet", "profesor", "odgovor", "napomena",
                 "kreirano", "azurirano"]
ODGOVOR_PREUZIMAM, ODGOVOR_NE_MOGU = "Preuzimam", "Ne mogu"
ODGOVOR_DODIJELJENO, ODGOVOR_NIJE_ODABRAN = "Dodijeljeno", "Nije odabran"
ODGOVORI_PROFESORA = (ODGOVOR_PREUZIMAM, ODGOVOR_NE_MOGU)
ZATVORENI_STATUSI_POZIVA = ("Odustao", "Otkazano")

# Nastavnici.predmeti sadrži oznake poput MAT-A, FIZ, KEM; upit ima slobodan naziv (Matematika, Fizika…)
PREFIKSI_PREDMETA = {"MAT": "matemat", "FIZ": "fiz", "KEM": "kemij", "BIO": "biolog", "HRV": "hrvat",
                     "ENG": "engle", "INF": "informat"}


def _t(v) -> str:
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip()


def predmet_odgovara(predmeti_prof: list, predmet: str) -> bool:
    """Prazan popis predmeta profesora = vidi sve. Inače: oznaka (MAT-A → 'matemat') mora biti u nazivu predmeta."""
    if not predmeti_prof:
        return True
    p = _t(predmet).lower()
    for o in predmeti_prof:
        baza = _t(o).upper().split("-")[0]
        if PREFIKSI_PREDMETA.get(baza, baza.lower()) in p:
            return True
    return False


def otvoreni_upiti(df_prijave: pd.DataFrame, df_dodjele: pd.DataFrame, danas: date, sezona: str = "") -> list:
    """Upiti za instrukcije koje još nitko nije preuzeo u dodjelu. [{redak_id, ucenik_id, ime_djeteta, predmet,
    stupanj, oblik, napomena, stiglo (date|None), dana}] — najstariji prvi.
    Otvoren = program_tip Instrukcije, poziv nije Odustao/Otkazano, nema aktivne dodjele za isti predmet
    (dodjela bez predmeta pokriva sve predmete učenika)."""
    if df_prijave is None or df_prijave.empty or "program_tip" not in df_prijave.columns:
        return []
    dodjele = aktivne_dodjele(df_dodjele, danas)
    pokriveno = set()
    for _, d in dodjele.iterrows():
        pokriveno.add((_t(d.get("ucenik_id")), _t(d.get("predmet")).lower()))
    out = []
    for _, r in df_prijave.iterrows():
        if _t(r.get("program_tip")) != "Instrukcije" or _t(r.get("status_kontakta")) in ZATVORENI_STATUSI_POZIVA:
            continue
        if sezona and _t(r.get("sezona")) and _t(r.get("sezona")) != sezona:
            continue
        uid, predmet = _t(r.get("ucenik_id")), _t(r.get("predmet"))
        if not _t(r.get("redak_id")) or not uid:
            continue
        if (uid, predmet.lower()) in pokriveno or (uid, "") in pokriveno:
            continue
        stiglo = _datum(r.get("timestamp_prijave"))
        out.append({"redak_id": _t(r.get("redak_id")), "ucenik_id": uid, "ime_djeteta": _t(r.get("ime_djeteta")),
                    "predmet": predmet, "stupanj": _t(r.get("stupanj_skolovanja")), "oblik": _t(r.get("oblik_instrukcija")),
                    "napomena": _t(r.get("napomena")), "stiglo": stiglo,
                    "dana": (danas - stiglo).days if stiglo else None})
    return sorted(out, key=lambda x: (x["stiglo"] or date.max, x["redak_id"]))


def odgovori_upita(df_upiti: pd.DataFrame) -> dict:
    """{redak_id: [{profesor, odgovor, napomena, azurirano, _row}]}"""
    out = {}
    if df_upiti is None or df_upiti.empty or "redak_id" not in df_upiti.columns:
        return out
    for _, r in df_upiti.iterrows():
        out.setdefault(_t(r["redak_id"]), []).append(
            {"profesor": _t(r.get("profesor")), "odgovor": _t(r.get("odgovor")), "napomena": _t(r.get("napomena")),
             "azurirano": _t(r.get("azurirano")), "_row": r.get("_row")})
    return out


def upiti_za_profesora(otvoreni: list, df_upiti: pd.DataFrame, profesor: str, predmeti_prof: list,
                       samo_moji_predmeti: bool = True) -> list:
    """Što profesor smije vidjeti: samo sigurna polja + njegov odgovor. Neodgovoreni prvi."""
    odg = odgovori_upita(df_upiti)
    out = []
    for u in otvoreni:
        if samo_moji_predmeti and not predmet_odgovara(predmeti_prof, u["predmet"]):
            continue
        moj = next((o for o in odg.get(u["redak_id"], []) if o["profesor"] == profesor), None)
        out.append({"redak_id": u["redak_id"], "ucenik_id": u["ucenik_id"], "predmet": u["predmet"],
                    "stupanj": u["stupanj"], "oblik": u["oblik"], "dana": u["dana"],
                    "moj_odgovor": moj["odgovor"] if moj else "", "moja_napomena": moj["napomena"] if moj else ""})
    return sorted(out, key=lambda x: (x["moj_odgovor"] != "", -(x["dana"] or 0)))


def broj_neodgovorenih(otvoreni: list, df_upiti: pd.DataFrame, profesor: str, predmeti_prof: list) -> int:
    return sum(1 for u in upiti_za_profesora(otvoreni, df_upiti, profesor, predmeti_prof) if not u["moj_odgovor"])


def postavi_odgovor(sheet, upit: dict, profesor: str, odgovor: str, napomena: str = "") -> str:
    """Profesor: Preuzimam / Ne mogu (može se predomisliti dok admin ne dodijeli). Jedan redak po (upit, profesor)."""
    if odgovor not in ODGOVORI_PROFESORA:
        raise ValueError("Nepoznat odgovor.")
    if not _t(profesor):
        raise ValueError("Nepoznat profesor.")
    _osiguraj_tab_stupce(sheet, UPITI_TAB, UPITI_HEADERS)
    ws = sheet.worksheet(UPITI_TAB)
    df = _load_worksheet_df(ws)
    sada = sada_zagreb().strftime("%Y-%m-%d %H:%M")
    postojeci = pd.DataFrame()
    if not df.empty and "redak_id" in df.columns:
        postojeci = df[(df["redak_id"].astype(str) == upit["redak_id"]) & (df["profesor"].astype(str) == profesor)]
    if not postojeci.empty:
        r = postojeci.iloc[0]
        if _t(r["odgovor"]) in (ODGOVOR_DODIJELJENO, ODGOVOR_NIJE_ODABRAN):
            raise ValueError("Admin je već odlučio o ovom upitu.")
        _azuriraj_polja(ws, int(r["_row"]), {"odgovor": odgovor, "napomena": _t(napomena)[:500], "azurirano": sada})
        return _t(r["odgovor_id"])
    odgovor_id = _id("UP-")
    _dodaj_red_po_nazivu(ws, {"odgovor_id": odgovor_id, "redak_id": upit["redak_id"], "ucenik_id": upit["ucenik_id"],
                              "predmet": upit["predmet"], "profesor": profesor, "odgovor": odgovor,
                              "napomena": _t(napomena)[:500], "kreirano": sada, "azurirano": sada})
    return odgovor_id


def dodijeli_upit(sheet, upit: dict, profesor: str, kontakt_dopusten: bool = False, napomena: str = "",
                  admin: str = "admin") -> str:
    """Admin: odabrani profesor dobiva učenika (red u Dodjele). Svi koji su preuzeli → 'Nije odabran'.
    Dodjela se prvo upisuje (greška = ništa se ne mijenja u Upiti_instrukcije)."""
    dodjela_id = dodaj_dodjelu(sheet, upit["ucenik_id"], upit.get("ime_djeteta", ""), profesor, upit["predmet"],
                               kontakt_dopusten=kontakt_dopusten, napomena_za_profesora=napomena, dodijelio=admin)
    _osiguraj_tab_stupce(sheet, UPITI_TAB, UPITI_HEADERS)
    ws = sheet.worksheet(UPITI_TAB)
    df = _load_worksheet_df(ws)
    sada = sada_zagreb().strftime("%Y-%m-%d %H:%M")
    imao_red = False
    if not df.empty and "redak_id" in df.columns:
        for _, r in df[df["redak_id"].astype(str) == upit["redak_id"]].iterrows():
            if _t(r["profesor"]) == profesor:
                imao_red = True
                _azuriraj_polja(ws, int(r["_row"]), {"odgovor": ODGOVOR_DODIJELJENO, "azurirano": sada})
            elif _t(r["odgovor"]) == ODGOVOR_PREUZIMAM:
                _azuriraj_polja(ws, int(r["_row"]), {"odgovor": ODGOVOR_NIJE_ODABRAN, "azurirano": sada})
    if not imao_red:
        _dodaj_red_po_nazivu(ws, {"odgovor_id": _id("UP-"), "redak_id": upit["redak_id"], "ucenik_id": upit["ucenik_id"],
                                  "predmet": upit["predmet"], "profesor": profesor, "odgovor": ODGOVOR_DODIJELJENO,
                                  "napomena": "dodijelio admin", "kreirano": sada, "azurirano": sada})
    return dodjela_id


def load_upiti(sheet) -> pd.DataFrame:
    return _load_opcionalno(sheet, UPITI_TAB)

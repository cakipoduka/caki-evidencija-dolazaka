"""
CAKI — dolasci_tablica.py (12.11.2026.)
ISTA TABLICA DOLAZAKA KAO U ADMIN CRM-u — za portal profesora.

Cakijev zahtjev: „Primjeni izmjene i na profesorskom portalu isto. Neka sučelje izgleda isto kao na
CRM-u. Bit će profesorima lakše i preglednije.”

KOPIJA čistih funkcija iz `caki-upisi-crm-main/dolasci_matura.py` (blok-po-grupi, svoji datumi,
gost, brisanje uz potvrdu). Kad se ta logika mijenja, mijenjati u OBA repoa — inače se CRM i portal
razidu. Admin-only dijelovi (šifra-link, PDF, popunjenost, izostanci) ovdje NISU.

Profesor smije ispravljati samo satove unutar `ROK_PROFESOR_DANA` (14) dana — starije kolone su
zaključane, a brisanje zapisa radi admin.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from urllib.parse import quote

import pandas as pd

from pipeline_upisi import (
    DANI_U_TJEDNU,
    labela_kante,
    labela_matura_grupe,
    otkazi_termin,
    razdoblje_kante_mature,
    sada_zagreb,
    spremi_cijeli_termin,
    zadnji_datum_dana,
)

BEZ_ZAPISA_DANA = 14
KOLIKO_TERMINA = 8
OZNAKE = {"u": "\u2705", "o": "\U0001F4BB", "x": "\u274C"}
IZ_OZNAKE = {v: k for k, v in OZNAKE.items()}
IZ_OZNAKE["—"] = ""            # prazna ćelija
OPCIJE_CELIJE = ["", "\u2705", "\U0001F4BB", "\u274C"]
OPCIJE_GOSTA = ["", "\u2705", "\U0001F4BB"]
STATUS_IZ_BROJA = {"1": "u", "2": "o", "0": "x"}


def u_datum(v):
    """'2026-10-07' / date -> date (ili None)."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None

def kratki(d) -> str:
    return d.strftime("%d.%m.")

def mapa_gostovanja(df_gostovanja) -> dict:
    """{(datum_iso, ucenik_id, grupa_gostovanja): maticna_grupa} — iz taba Gostovanja."""
    out = {}
    if df_gostovanja is None or getattr(df_gostovanja, "empty", True):
        return out
    for _, r in df_gostovanja.iterrows():
        d = u_datum(r.get("datum"))
        if not d:
            continue
        out[(d.isoformat(), str(r.get("ucenik_id", "")).strip(), str(r.get("grupa_gostovanja", "")).strip())] = \
            str(r.get("maticna_grupa", "") or "").strip()
    return out

def kratka_grupa(grupa_id: str) -> str:
    """'MATURA|Subota|1|A' -> 'Subota T1 · Uč. A' (za „gost iz …”)."""
    if not grupa_id:
        return "druga grupa"
    return labela_matura_grupe(grupa_id).replace("Matura · ", "")

def datumi_bloka(kanta: dict, razdoblja=None, praznici=None, danas=None,
                 koliko: int = KOLIKO_TERMINA, zapisani=None, pomak: int = 0,
                 otkazani=None) -> list:
    """Prozor od `koliko` datuma te grupe: planirani (iz Razdoblja_termina, praznici preskočeni) +
    svi datumi koji imaju zapis. `pomak` = koliko prozora unatrag (0 = zadnjih 8).

    Ako grupa nema upisano razdoblje i nema zapisa, zadaje se zadnji datum njezina dana u tjednu —
    tako se i bez rasporeda može upisati sat (isto što je prije radio tab Prozivka)."""
    danas = danas or sada_zagreb().date()
    praznici = praznici or {}
    datumi = []
    od, do = razdoblje_kante_mature(kanta, razdoblja or {}, praznici)
    if od and kanta.get("dan") in DANI_U_TJEDNU:
        d = od + timedelta(days=(DANI_U_TJEDNU.index(kanta["dan"]) - od.weekday()) % 7)
        kraj = min(do or danas, danas)
        while d <= kraj and len(datumi) < 400:
            if d not in praznici and (kanta["grupa_id"], d) not in (otkazani or {}) \
                    and (kanta["grupa_id"], d.isoformat()) not in (otkazani or {}):
                datumi.append(d)
            d += timedelta(days=7)
    for z in zapisani or []:
        zd = u_datum(z)
        if zd and zd <= danas and zd not in datumi:
            datumi.append(zd)
    svi = sorted(set(datumi))
    if not svi and kanta.get("dan") in DANI_U_TJEDNU:
        svi = [zadnji_datum_dana(kanta["dan"], danas)]
    if not svi:
        return []
    if int(pomak or 0) <= 0:
        return svi[-koliko:]
    kraj = max(len(svi) - int(pomak) * koliko, 0)
    return svi[max(kraj - koliko, 0):kraj]

def _zapisi_kante(d_matura: pd.DataFrame, grupa_id: str) -> dict:
    """{ucenik_id: {'ime': str, 'statusi': {date: 'u'|'o'|'x'}, 'svi': {(date): status}}}"""
    out = {}
    if d_matura is None or getattr(d_matura, "empty", True):
        return out
    redci = d_matura[d_matura["grupa_id"].astype(str) == str(grupa_id)]
    for _, r in redci.iterrows():
        uid = str(r.get("ucenik_id", "")).strip()
        d = u_datum(r.get("datum"))
        if not uid or not d:
            continue
        z = out.setdefault(uid, {"ime": str(r.get("ime_djeteta", "") or uid), "statusi": {}})
        z["statusi"][d] = STATUS_IZ_BROJA.get(str(r.get("status", "")).strip(), "")
    return out

def redci_bloka(kanta: dict, datumi: list, d_matura: pd.DataFrame, gost_map=None) -> tuple:
    """(redci učenika, gosti) za jedan blok.
    redak = {ucenik_id, ime, statusi {date: oznaka-jednoslovka}, ukupno, evidentirano, postotak}."""
    zapisi = _zapisi_kante(d_matura, kanta["grupa_id"])
    gost_map = gost_map or {}

    def _redak(uid, ime, statusi):
        svi = [s for s in zapisi.get(uid, {}).get("statusi", {}).values() if s]
        ukupno = sum(1 for s in svi if s in ("u", "o"))
        return {"ucenik_id": uid, "ime": ime, "statusi": statusi, "ukupno": ukupno,
                "evidentirano": len(svi),
                "postotak": f"{round(100 * ukupno / len(svi))} %" if svi else "—"}

    redci, clanovi = [], set()
    for u in kanta["ucenici"]:
        uid = u["ucenik_id"]
        clanovi.add(uid)
        statusi = {d: zapisi.get(uid, {}).get("statusi", {}).get(d, "") for d in datumi}
        redci.append(_redak(uid, u["ime_djeteta"], statusi))

    gosti = []
    for uid, zapis in zapisi.items():
        if uid in clanovi:
            continue
        statusi = {d: zapis["statusi"].get(d, "") for d in datumi}
        if not any(statusi.values()):
            continue                                # nema zapisa u prikazanom prozoru
        maticna = ""
        for d, s in statusi.items():
            if s:
                maticna = gost_map.get((d.isoformat(), uid, kanta["grupa_id"]), "") or maticna
        r = _redak(uid, zapis["ime"], statusi)
        r["maticna"] = kratka_grupa(maticna) if maticna else "nije u grupi"
        gosti.append(r)
    return redci, gosti

def tablica_bloka(redci: list, datumi: list, prikazi_sifru: bool = True, portal_url: str = "",
                 gostovanja: dict | None = None) -> pd.DataFrame:
    """DataFrame za st.data_editor: Učenik · (Šifra) · datumi · Ukupno · %  (index = ucenik_id)."""
    podaci = {}
    for r in redci:
        red = {"Učenik": r["ime"]}
        if prikazi_sifru:
            red["Šifra"] = (f"{str(portal_url).rstrip('/')}/?ucenik_id={quote(str(r['ucenik_id']))}"
                            if portal_url else str(r["ucenik_id"]))
        for d in datumi:
            red[kratki(d)] = OZNAKE.get(r["statusi"].get(d, ""), "—")
        red["Ukupno"] = r["ukupno"]
        red["%"] = r["postotak"]
        if gostovanja is not None:
            red["Gostovanja"] = (gostovanja or {}).get(r["ucenik_id"], "")
        podaci[r["ucenik_id"]] = red
    stupci = (["Učenik"] + (["Šifra"] if prikazi_sifru else []) + [kratki(d) for d in datumi]
              + ["Ukupno", "%"] + (["Gostovanja"] if gostovanja is not None else []))
    df = pd.DataFrame(list(podaci.values()), index=list(podaci), columns=stupci)
    return df

def tablica_gostiju(gosti: list, datumi: list) -> pd.DataFrame:
    podaci = {}
    for r in gosti:
        red = {"Učenik": r["ime"], "Gost iz": r.get("maticna", "") or "druga grupa"}
        for d in datumi:
            red[kratki(d)] = OZNAKE.get(r["statusi"].get(d, ""), "—")
        podaci[r["ucenik_id"]] = red
    stupci = ["Učenik", "Gost iz"] + [kratki(d) for d in datumi]
    return pd.DataFrame(list(podaci.values()), index=list(podaci), columns=stupci)

def izmjene_bloka(izvorno: pd.DataFrame, izmijenjeno: pd.DataFrame, grupa_id: str,
                  datumi: list, gosti_info: dict | None = None) -> list:
    """Usporedi dvije tablice i vrati popis promjena (samo datumi-stupci)."""
    gosti_info = gosti_info or {}
    izmjene = []
    if izmijenjeno is None or izvorno is None:
        return izmjene
    stupci = [kratki(d) for d in datumi if kratki(d) in izmijenjeno.columns]
    for uid in izvorno.index:
        if uid not in izmijenjeno.index:
            continue
        for kol in stupci:
            staro = str(izvorno.at[uid, kol] if kol in izvorno.columns else "")
            novo = str(izmijenjeno.at[uid, kol])
            if staro == novo:
                continue
            izmjene.append({
                "grupa_id": grupa_id,
                "datum": next(d for d in datumi if kratki(d) == kol),
                "ucenik_id": str(uid),
                "ime": str(izmijenjeno.at[uid, "Učenik"]),
                "status": IZ_OZNAKE.get(novo, ""),
                "staro": IZ_OZNAKE.get(staro, ""),
                "gost": uid in gosti_info,
                "maticna": gosti_info.get(uid, ""),
            })
    return izmjene

def grupiraj_izmjene(izmjene: list) -> dict:
    """{(grupa_id, datum): [izmjena, ...]}"""
    out = {}
    for z in izmjene:
        out.setdefault((z["grupa_id"], z["datum"]), []).append(z)
    return out

def obrisi_dolazak(sheet, grupa_id: str, datum, ucenik_id: str) -> int:
    """Briše zapis dolaska (i eventualno gostovanje) za taj termin. Vraća broj obrisanih redaka."""
    datum_iso = (u_datum(datum) or datum).isoformat() if not isinstance(datum, str) else str(datum)[:10]
    obrisano = 0
    try:
        ws_t = sheet.worksheet("Termini")
        termini = ws_t.get_all_records()
    except Exception:                                              # noqa: BLE001 — tab ne postoji
        return 0
    termin_id = next((str(r.get("termin_id")) for r in termini
                      if str(r.get("grupa_id")) == str(grupa_id)
                      and str(r.get("datum"))[:10] == datum_iso), None)
    if termin_id:
        try:
            ws_d = sheet.worksheet("Dolasci")
            for i, red in enumerate(ws_d.get_all_records(), start=2):
                if str(red.get("termin_id")) == termin_id and str(red.get("ucenik_id")) == str(ucenik_id):
                    ws_d.delete_rows(i)
                    obrisano += 1
                    break
        except Exception:                                          # noqa: BLE001
            pass
    try:
        ws_g = sheet.worksheet("Gostovanja")
        for i, red in enumerate(ws_g.get_all_records(), start=2):
            if (str(red.get("datum"))[:10] == datum_iso and str(red.get("ucenik_id")) == str(ucenik_id)
                    and str(red.get("grupa_gostovanja")) == str(grupa_id)):
                ws_g.delete_rows(i)
                obrisano += 1
                break
    except Exception:                                              # noqa: BLE001
        pass
    return obrisano

def primijeni_izmjene(sheet, izmjene: list, kante: list, nastavnik_po_terminu: dict) -> dict:
    """Sprema izmjene: briše ispražnjene ćelije, ostalo šalje spremi_cijeli_termin (jedan poziv po terminu)."""
    rez = {"spremljeno": 0, "obrisano": 0, "greske": []}
    for (grupa_id, datum), zapisi in grupiraj_izmjene(izmjene).items():
        kanta = next((k for k in kante if k["grupa_id"] == grupa_id), {})
        redovni = str(kanta.get("profesor", "") or "")
        odrzao = nastavnik_po_terminu.get((grupa_id, datum.isoformat())) or redovni
        roster, gosti = [], []
        for z in zapisi:
            if not z["status"]:
                if z["staro"]:
                    rez["obrisano"] += obrisi_dolazak(sheet, grupa_id, datum.isoformat(), z["ucenik_id"])
                continue
            if z["gost"]:
                gosti.append({"ucenik_id": z["ucenik_id"], "ime_djeteta": z["ime"],
                              "status": z["status"], "maticna_grupa": z["maticna"] or redovni})
            else:
                roster.append({"ucenik_id": z["ucenik_id"], "ime_djeteta": z["ime"], "status": z["status"]})
        if not roster and not gosti:
            continue
        try:
            spremi_cijeli_termin(sheet, grupa_id, datum.isoformat(), odrzao, redovni, roster, gosti)
            rez["spremljeno"] += len(roster) + len(gosti)
        except Exception as e:                                     # noqa: BLE001 — poruka mora doći Cakiju
            rez["greske"].append(f"{labela_kante(kanta) if kanta else grupa_id} · "
                                 f"{datum.strftime('%d.%m.%Y.')}: {e}")
    return rez

# ------------------------------------------------------------------ profesorsko sučelje

def _upisi(st, sheet, kanta, datum, df_termini, nastavnik, roster=None, gosti=None):
    """Jedan upis u Sheet („Svi prisutni” / dodavanje gosta)."""
    gid = kanta["grupa_id"]
    redovni = str(kanta.get("profesor", "") or nastavnik)
    odrzao = nastavnik or redovni
    if df_termini is not None and not getattr(df_termini, "empty", True):
        red = df_termini[(df_termini["grupa_id"].astype(str) == gid)
                         & (df_termini["datum"].astype(str).str[:10] == datum.isoformat())]
        if not red.empty:
            odrzao = str(red.iloc[0].get("nastavnik_odrzao", "") or odrzao)
    try:
        spremi_cijeli_termin(sheet, gid, datum.isoformat(), odrzao, redovni,
                             list(roster or []), list(gosti or []))
    except Exception as e:                                        # noqa: BLE001
        st.error(f"❌ Nije spremljeno: {e}")
        return
    st.session_state["mat_poruka"] = "✅ Spremljeno."
    st.cache_data.clear()
    st.rerun()


def prikazi_grupu(st, sheet, kanta, d_matura, danas, razdoblja=None, praznici=None,
                  df_termini=None, ucenici=None, nastavnik="", rok_dana=14, key_prefix="mat",
                  otkazani=None):
    """Tablica jedne grupe: učenici × datumi, padajući izbor, gost, spremanje jednim gumbom."""
    gid = kanta["grupa_id"]
    datumi = datumi_bloka(kanta, razdoblja, praznici, danas, otkazani=otkazani)
    if not datumi:
        st.info("Za ovu grupu još nema termina.")
        return
    redci, gosti = redci_bloka(kanta, datumi, d_matura)
    if not redci:
        st.info("U ovoj grupi još nema učenika.")
        return
    if st.session_state.get("mat_poruka"):
        st.success(st.session_state.pop("mat_poruka"))
    rok_od = danas - timedelta(days=int(rok_dana or 0))
    st.caption(f"{labela_kante(kanta)}  ·  {len(kanta['ucenici'])} učenika  ·  možeš ispravljati satove "
               f"od {rok_od.strftime('%d.%m.%Y.')} (starije upisuje admin).")

    zadnji_u_roku = max((dt for dt in datumi if dt >= rok_od), default=None)
    lab_d = {kratki(x): x for x in datumi}
    b1, b2, b3, b4 = st.columns([2, 2, 3, 2])
    odabrani = b1.selectbox("Termin", list(lab_d), index=len(lab_d) - 1,
                            key=f"{key_prefix}_bulk_{gid}", label_visibility="collapsed",
                            help="Termin na koji se odnose gumbi desno")
    datum_bulk = lab_d[odabrani]
    if b2.button("✅ Svi prisutni", key=f"{key_prefix}_svi_{gid}",
                 disabled=zadnji_u_roku is None,
                 help=f"Odmah upiše sve učenike kao prisutne za {odabrani}"):
        _upisi(st, sheet, kanta, datum_bulk, df_termini, nastavnik,
               roster=[{"ucenik_id": u["ucenik_id"], "ime_djeteta": u["ime_djeteta"], "status": "1"}
                       for u in kanta["ucenici"]])
    with b3.popover("➕ Gost (učenik iz druge grupe)"):
        _gost(st, sheet, kanta, datum_bulk, df_termini, ucenici, nastavnik, key_prefix)
    with b4.popover("🚫 Ne održava se"):
        st.caption(f"Grupa: {labela_kante(kanta)}")
        predlozeni = _naredni_datum(kanta, danas)
        datum_otk = st.date_input("Datum koji se NE održava", value=predlozeni,
                                  min_value=danas - timedelta(days=60),
                                  max_value=danas + timedelta(days=180),
                                  format="DD.MM.YYYY", key=f"{key_prefix}_otk_d_{gid}")
        razlog = st.text_input("Razlog (npr. praznik)", key=f"{key_prefix}_otk_r_{gid}")
        if st.button("🚫 Otkaži termin", key=f"{key_prefix}_otk_b_{gid}"):
            try:
                otkazi_termin(sheet, gid, datum_otk, razlog.strip() or "ne održava se", False, nastavnik)
            except Exception as e:                                # noqa: BLE001
                st.error(f"❌ Nije otkazano: {e}")
            else:
                st.cache_data.clear()
                st.rerun()
        st.caption("Otkazani datum više ne ulazi u tablicu ni u obračun.")


    izvorno = tablica_bloka(redci, datumi, prikazi_sifru=False)
    konfig = {"Učenik": st.column_config.TextColumn(width="medium", disabled=True)}
    for dt in datumi:
        if dt >= rok_od:
            konfig[kratki(dt)] = st.column_config.SelectboxColumn(
                kratki(dt), options=OPCIJE_CELIJE, width="small", required=False)
        else:
            konfig[kratki(dt)] = st.column_config.TextColumn(
                kratki(dt), width="small", disabled=True, help="Starije od roka — upisuje admin")
    konfig["Ukupno"] = st.column_config.NumberColumn("Ukupno", width="small", disabled=True,
                                                    help="Dolasci u cijeloj sezoni")
    konfig["%"] = st.column_config.TextColumn("%", width="small", disabled=True,
                                             help="Postotak na cijelu sezonu")
    izmijenjeno = st.data_editor(izvorno, key=f"{key_prefix}_tab_{gid}", hide_index=True,
                                 column_config=konfig, width="stretch",
                                 disabled=["Učenik", "Ukupno", "%"])
    izmjene = izmjene_bloka(izvorno, izmijenjeno, gid, datumi)
    brisanja = [z for z in izmjene if not z["status"] and z["staro"]]
    if brisanja:
        st.warning(f"⚠️ {len(brisanja)} praznih ćelija — brisanje zapisa radi admin. "
                   f"Ostavi ćeliju kako je bila ili upiši ❌/✅/💻.")
        izmjene = [z for z in izmjene if z["status"]]
    if izmjene:
        st.caption(f"✏️ {len(izmjene)} promjena nije spremljeno.")
    if st.button("💾 Spremi izmjene", type="primary", key=f"{key_prefix}_spremi_{gid}",
                 disabled=not izmjene):
        nast = {}
        if df_termini is not None and not getattr(df_termini, "empty", True):
            for _, r in df_termini.iterrows():
                nast[(str(r["grupa_id"]), str(r["datum"])[:10])] = str(r.get("nastavnik_odrzao", "") or "")
        for dt in datumi:
            nast.setdefault((gid, dt.isoformat()), nastavnik)
        rez = primijeni_izmjene(sheet, izmjene, [kanta], nast)
        if rez["greske"]:
            st.error("❌ " + " · ".join(rez["greske"]))
        elif rez["brisano"] or rez["spremljeno"]:
            st.success(f"✅ Spremljeno: {rez['spremljeno']} zapisa.")
            st.cache_data.clear()
            st.rerun()


def _naredni_datum(kanta, danas):
    """Predloženi datum za otkazivanje: prvi sljedeći termin te grupe (ili danas)."""
    if kanta.get("dan") not in DANI_U_TJEDNU:
        return danas
    d = zadnji_datum_dana(kanta["dan"], danas)
    return d if d >= danas else d + timedelta(days=7)


def _gost(st, sheet, kanta, datum, df_termini, ucenici, nastavnik, key_prefix):
    """➕ Gost iz druge grupe — traži po imenu/šifri, upisuje odmah."""
    gid = kanta["grupa_id"]
    st.caption(f"Upiši učenika u: **{labela_kante(kanta)} · {datum.strftime('%d.%m.%Y.')}**")
    upit = st.text_input("Ime ili šifra (min. 2 znaka)", key=f"{key_prefix}_gq_{gid}_{datum.isoformat()}")
    if not upit or len(upit.strip()) < 2:
        return
    if ucenici is None or getattr(ucenici, "empty", True):
        st.caption("Nema podataka o učenicima.")
        return
    vec = {u["ucenik_id"] for u in kanta["ucenici"]}
    maska = (ucenici["ime_djeteta"].astype(str).str.contains(upit, case=False, na=False)
             | ucenici["ucenik_id"].astype(str).str.contains(upit, case=False, na=False))
    nadjeni = ucenici[maska & ~ucenici["ucenik_id"].astype(str).isin(vec)].head(6)
    if nadjeni.empty:
        st.caption("Nema takvog učenika (ili je već u ovoj grupi).")
        return
    for _, u in nadjeni.iterrows():
        uid = str(u["ucenik_id"])
        a, b, c = st.columns([3, 1, 1])
        a.write(f"{u['ime_djeteta']} · {uid}")
        for col, status, ikona in ((b, "1", "✅"), (c, "2", "💻")):
            if col.button(ikona, key=f"{key_prefix}_gadd_{gid}_{datum.isoformat()}_{uid}_{status}"):
                _upisi(st, sheet, kanta, datum, df_termini, nastavnik, gosti=[
                    {"ucenik_id": uid, "ime_djeteta": str(u["ime_djeteta"]), "status": status,
                     "maticna_grupa": ""}])

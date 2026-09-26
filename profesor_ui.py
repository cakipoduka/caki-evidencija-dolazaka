"""
CAKI — profesor_ui.py  (26.9.2026.)
Portal za profesore / instruktore: JEDNA prijava (ime + osobna lozinka iz taba Nastavnici),
u karticama: ✅ Dolasci (grupni termini) · 📝 Instrukcije · 📄 Mjesečni izvještaj.

Koriste ga caki-evidencija-dolazaka.py (glavna adresa) i pages/2_Instrukcije.py (stari link).

Privatnost: profesor NIKAD ne vidi cijene, iznose ni ponude. Vidi samo svoje instrukcije i je li
termin plaćen (✅). Naplatu gotovinom smije evidentirati samo profesor s ovlaštenjem
(Nastavnici.naplata_gotovinom = Da, postavlja admin).
"""
import json
from datetime import date

import pandas as pd
import streamlit as st

from pipeline_upisi import (
    DANI_U_TJEDNU,
    INSTRUKCIJE_OBLICI,
    INSTRUKCIJE_PREDMETI,
    INSTRUKCIJE_TRAJANJA,
    MJESECI_HR,
    PLACENO_GOTOVINOM,
    STATUSI_ZA_OBRACUN,
    STUPNJEVI_SKOLOVANJA_INSTR,
    _load_opcionalno,
    dodaj_instrukciju_termin,
    get_gspread_client,
    izvjestaj_instruktora,
    load_izvjestaji,
    nastavnici_aktivni,
    oznaci_naplatu_gotovinom,
    pdf_izvjestaja_instruktora,
    posalji_izvjestaj_instruktora,
    pretrazi_ucenike,
    provjeri_lozinku_instruktora,
    roster_grupe,
    sada_zagreb,
    smije_naplatu_gotovinom,
    spremi_cijeli_termin,
)


@st.cache_resource
def _init_sheet():
    sa_info = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    return get_gspread_client(sa_info).open_by_key(st.secrets["SHEET_ID"])


@st.cache_data(ttl=20)
def _ucitaj(naziv: str) -> pd.DataFrame:
    return _load_opcionalno(_init_sheet(), naziv)


def _poruka(vrsta, tekst):
    st.session_state["_prof_poruka"] = (vrsta, tekst)


# ------------------------------------------------------------------ prijava

def _prijava():
    if st.session_state.get("instruktor_prijavljen"):
        return st.session_state["instruktor_prijavljen"]
    st.title("🎓 CAKI — portal za profesore")
    df_n = _ucitaj("Nastavnici")
    if df_n.empty:
        st.error("Tab 'Nastavnici' još nije postavljen u Sheetu — javite adminu.")
        st.stop()
    with st.form("prijava"):
        ime = st.selectbox("Tko ste vi?", options=nastavnici_aktivni(df_n))
        lozinka = st.text_input("Vaša lozinka", type="password")
        if st.form_submit_button("Prijava", type="primary"):
            if provjeri_lozinku_instruktora(df_n, ime, lozinka):
                st.session_state["instruktor_prijavljen"] = ime
                st.rerun()
            st.error("Pogrešna lozinka.")
    st.stop()


# ------------------------------------------------------------------ ✅ dolasci

def _kartica_dolasci(sheet, nastavnik):
    odabrani_datum = st.date_input("Datum termina", value=date.today(), format="DD.MM.YYYY")
    dan_naziv = DANI_U_TJEDNU[odabrani_datum.weekday()]
    df_grupe, df_rez, df_ucenici = _ucitaj("Grupe"), _ucitaj("Rezervacije"), _ucitaj("Učenici")
    if df_grupe.empty:
        st.info("Grupe još nisu postavljene.")
        return
    grupe_danas = df_grupe[(df_grupe["dan"] == dan_naziv) & (df_grupe["aktivna"].astype(str).str.lower() == "da")]
    if grupe_danas.empty:
        st.info(f"Nema aktivnih termina za {dan_naziv.lower()}.")
        return
    # Svoje grupe prve (redovni nastavnik), ostale ispod — za zamjene
    grupe_danas = grupe_danas.assign(_moja=grupe_danas.get("redovni_nastavnik", "") != nastavnik).sort_values(["_moja", "vrijeme"])
    opcije = {f"{'⭐ ' if not g['_moja'] else ''}{g['program']} — {g['vrijeme']} ({g['ucionica']})": g["grupa_id"]
              for _, g in grupe_danas.iterrows()}
    grupa_id = opcije[st.selectbox(f"Grupa ({dan_naziv})", options=list(opcije))]
    grupa_red = grupe_danas[grupe_danas["grupa_id"] == grupa_id].iloc[0]
    upisani_redovni = str(grupa_red.get("redovni_nastavnik", "") or "")
    redovni = upisani_redovni or nastavnik   # grupa bez redovnog nastavnika → nije zamjena
    danas_predaje = st.text_input("Danas predaje", value=nastavnik)
    if upisani_redovni and danas_predaje != upisani_redovni:
        st.warning(f"⚠ Zamjena — redovni nastavnik je {upisani_redovni}. Bilježi se automatski.")

    roster = roster_grupe(df_rez, grupa_id)
    if roster.empty:
        st.info("Nema potvrđenih učenika u ovoj grupi.")
        return
    st.markdown(f"#### Popis učenika ({len(roster)})")
    oznake = {"1": "✅ Prisutan", "0": "❌ Odsutan", "2": "💻 Online"}
    statusi = {}
    for _, r in roster.iterrows():
        c1, c2 = st.columns([2, 3])
        c1.write(r["ime_djeteta"])
        statusi[r["ucenik_id"]] = c2.radio("status", ["1", "0", "2"], format_func=oznake.get, horizontal=True,
                                           key=f"dol_{grupa_id}_{r['ucenik_id']}_{odabrani_datum}",
                                           label_visibility="collapsed")

    kljuc_g = f"gosti_{grupa_id}_{odabrani_datum}"
    gosti = st.session_state.setdefault(kljuc_g, {})
    with st.expander("➕ Dodaj gosta (učenik iz druge grupe)"):
        upit = st.text_input("Pretraži po imenu", key=f"gost_upit_{grupa_id}")
        if upit:
            vec = set(roster["ucenik_id"]) | set(gosti)
            nadjeni = df_ucenici[df_ucenici["ime_djeteta"].str.contains(upit, case=False, na=False)
                                 & ~df_ucenici["ucenik_id"].isin(vec)]
            for _, u in nadjeni.head(10).iterrows():
                if st.button(f"Dodaj: {u['ime_djeteta']} ({u['ucenik_id']})", key=f"gost_{grupa_id}_{u['ucenik_id']}"):
                    njegova = df_rez[(df_rez["ucenik_id"] == u["ucenik_id"]) & (df_rez["status"] == "Potvrđeno")]
                    gosti[u["ucenik_id"]] = {"ime": u["ime_djeteta"], "status": "1",
                                             "maticna": njegova.iloc[0]["grupa_id"] if not njegova.empty else "Nepoznato"}
                    st.rerun()
    for uid, podaci in list(gosti.items()):
        g1, g2, g3 = st.columns([2, 2, 1])
        g1.write(f"{podaci['ime']} 🔄")
        podaci["status"] = g2.radio("gost", ["1", "2"], format_func=oznake.get, horizontal=True,
                                    key=f"gost_st_{uid}_{odabrani_datum}", label_visibility="collapsed")
        if g3.button("🗑️", key=f"gost_del_{uid}_{odabrani_datum}"):
            del gosti[uid]
            st.rerun()

    if st.button("💾 Spremi dolazak", type="primary", key=f"spremi_dol_{grupa_id}"):
        spremi_cijeli_termin(
            sheet, grupa_id, str(odabrani_datum), danas_predaje, redovni,
            [{"ucenik_id": r["ucenik_id"], "ime_djeteta": r["ime_djeteta"], "status": statusi[r["ucenik_id"]]}
             for _, r in roster.iterrows()],
            [{"ucenik_id": uid, "ime_djeteta": p["ime"], "status": p["status"], "maticna_grupa": p["maticna"]}
             for uid, p in gosti.items()])
        _poruka("success", "Dolazak spremljen. Zakašnjele učenike možete dodati i spremiti ponovno.")
        st.cache_data.clear()
        st.rerun()


# ------------------------------------------------------------------ 📝 instrukcije

def _kartica_instrukcije(sheet, nastavnik, smije_gotovinu):
    df_ucenici, df_instr = _ucitaj("Učenici"), _ucitaj("Instrukcije_termini")
    st.markdown("#### Novi termin")
    upit = st.text_input("Pretraži učenika (ime ili šifra)", key="instr_upit")
    if upit:
        nadjeni = pretrazi_ucenike(df_ucenici, upit)
        if nadjeni.empty:
            st.warning("Nema rezultata.")
        else:
            opcije = {f"{r['ime_djeteta']} ({r['ucenik_id']})": r["ucenik_id"] for _, r in nadjeni.iterrows()}
            uid = opcije[st.selectbox("Učenik", options=list(opcije))]
            ime = nadjeni[nadjeni["ucenik_id"] == uid].iloc[0]["ime_djeteta"]
            with st.form("novi_termin_form", clear_on_submit=True):
                c1, c2 = st.columns(2)
                datum = c1.date_input("Datum", value=date.today(), format="DD.MM.YYYY")
                duljina = c2.selectbox("Duljina termina (min)", options=INSTRUKCIJE_TRAJANJA, index=1)
                predmet = c1.selectbox("Predmet", options=INSTRUKCIJE_PREDMETI)
                stupanj = c2.selectbox("Stupanj školovanja", options=STUPNJEVI_SKOLOVANJA_INSTR, index=1)
                oblik = st.radio("Oblik", options=INSTRUKCIJE_OBLICI, horizontal=True)
                broj = st.number_input("Broj učenika u grupi (samo za grupu)", min_value=1, max_value=10, value=1)
                gotovina = st.checkbox("💵 Naplaćeno gotovinom") if smije_gotovinu else False
                nap_int = st.text_area("Napomena (interna — vidite samo vi i admin)")
                nap_jav = st.text_area("Napomena (javna — vidi i roditelj)")
                if st.form_submit_button("💾 Spremi termin", type="primary"):
                    dodaj_instrukciju_termin(
                        sheet, ucenik_id=uid, ime_djeteta=ime, nastavnik=nastavnik, datum=str(datum),
                        duljina_min=duljina, oblik=oblik, broj_ucenika_u_grupi=broj if oblik == "Grupa" else None,
                        placeno_oznaka_prof=PLACENO_GOTOVINOM if gotovina else "Ne",
                        napomena_interna=nap_int, napomena_javna=nap_jav, predmet=predmet, stupanj_skolovanja=stupanj)
                    _poruka("success", f"Termin spremljen: {ime}, {datum.strftime('%d.%m.%Y.')}.")
                    st.cache_data.clear()
                    st.rerun()

    st.markdown("#### Moji termini")
    if df_instr.empty or "nastavnik" not in df_instr.columns:
        st.info("Još nema evidentiranih termina.")
        return
    moji = df_instr[df_instr["nastavnik"] == nastavnik].sort_values("datum", ascending=False)
    if moji.empty:
        st.info("Nemate još evidentiranih termina.")
        return
    placeno = (moji.get("placeno_oznaka_prof", "") == PLACENO_GOTOVINOM) | (moji.get("uplata_potvrdjena_admin", "") == "Da")
    st.dataframe(pd.DataFrame({
        "Datum": [str(v)[:10] for v in moji["datum"]],
        "Učenik": moji["ime_djeteta"],
        "Predmet": moji["predmet"] if "predmet" in moji.columns else "",
        "Min": moji["duljina_min"],
        "Oblik": moji["oblik"],
        "Plaćeno": ["✅" if x else "" for x in placeno],
        "Napomena": moji.get("napomena_interna", ""),
    }), hide_index=True, width="stretch")

    if smije_gotovinu and "status_obracuna" in moji.columns:
        otvoreni = moji[~placeno & moji["status_obracuna"].fillna("").isin(STATUSI_ZA_OBRACUN)].head(20)
        if not otvoreni.empty:
            with st.expander(f"💵 Evidentiraj naplatu gotovinom ({len(otvoreni)} neplaćenih)"):
                for _, t in otvoreni.iterrows():
                    c1, c2 = st.columns([3, 1])
                    c1.write(f"{str(t['datum'])[:10]} · {t['ime_djeteta']} · {t.get('predmet', '')} · {t['duljina_min']} min")
                    if c2.button("💵 Naplaćeno", key=f"got_{t['termin_id']}"):
                        try:
                            oznaci_naplatu_gotovinom(sheet, int(t["_row"]), nastavnik)
                            _poruka("success", f"Označeno kao plaćeno: {t['ime_djeteta']}, {str(t['datum'])[:10]}.")
                        except ValueError as e:
                            _poruka("error", str(e))
                        st.cache_data.clear()
                        st.rerun()


# ------------------------------------------------------------------ 📄 mjesečni izvještaj

def _kartica_izvjestaj(sheet, nastavnik):
    danas = sada_zagreb().date()
    mjeseci = []
    g, m = danas.year, danas.month
    for _ in range(6):
        mjeseci.append((g, m))
        g, m = (g, m - 1) if m > 1 else (g - 1, 12)
    # zadano: prošli mjesec (izvještaj se šalje nakon završetka mjeseca)
    g, m = st.selectbox("Mjesec", mjeseci, index=1, format_func=lambda x: f"{MJESECI_HR[x[1] - 1]} {x[0]}.")
    izv = izvjestaj_instruktora(_ucitaj("Instrukcije_termini"), _ucitaj("Termini"), _ucitaj("Grupe"), nastavnik, g, m)
    c1, c2, c3 = st.columns(3)
    c1.metric("📝 Instrukcije", izv["broj_instrukcija"])
    c2.metric("⏱️ Sati instrukcija", f"{izv['sati_instrukcija']:g}")
    c3.metric("👥 Grupni termini", izv["broj_grupnih_termina"])
    if not izv["instrukcije"].empty:
        st.dataframe(izv["instrukcije"], hide_index=True, width="stretch")
    if not izv["grupni"].empty:
        st.dataframe(izv["grupni"], hide_index=True, width="stretch")

    df_izv = load_izvjestaji(sheet)
    postojeci = df_izv[(df_izv["nastavnik"] == nastavnik) & (df_izv["mjesec"].astype(str) == izv["mjesec"])] \
        if not df_izv.empty else df_izv
    if not postojeci.empty:
        r = postojeci.iloc[0]
        tekst = f"Status izvještaja: **{r['status']}** (poslano {r['poslano']})"
        if str(r.get("napomena_admin", "") or "").strip():
            tekst += f" — napomena admina: *{r['napomena_admin']}*"
        (st.warning if r["status"] == "Vraćeno na ispravak" else st.info)(tekst)

    b1, b2 = st.columns(2)
    b1.download_button("⬇️ Preuzmi PDF", data=pdf_izvjestaja_instruktora(izv),
                       file_name=f"CAKI_izvjestaj_{nastavnik.split()[0]}_{izv['mjesec']}.pdf", mime="application/pdf")
    if b2.button("📤 Pošalji adminu na provjeru", type="primary"):
        try:
            posalji_izvjestaj_instruktora(sheet, izv)
            _poruka("success", "Izvještaj je poslan — admin ga vidi u panelu za provjeru.")
        except ValueError as e:
            _poruka("error", str(e))
        st.cache_data.clear()
        st.rerun()


# ------------------------------------------------------------------ portal

def prikazi_portal_profesora():
    sheet = _init_sheet()
    nastavnik = _prijava()
    c1, c2 = st.columns([4, 1])
    c1.title(f"🎓 {nastavnik}")
    if c2.button("🚪 Odjava"):
        st.session_state.pop("instruktor_prijavljen", None)
        st.rerun()
    if "_prof_poruka" in st.session_state:
        vrsta, tekst = st.session_state.pop("_prof_poruka")
        getattr(st, vrsta)(tekst)
    smije_gotovinu = smije_naplatu_gotovinom(_ucitaj("Nastavnici"), nastavnik)
    k_dol, k_instr, k_izv = st.tabs(["✅ Dolasci — grupe", "📝 Instrukcije", "📄 Mjesečni izvještaj"])
    with k_dol:
        _kartica_dolasci(sheet, nastavnik)
    with k_instr:
        _kartica_instrukcije(sheet, nastavnik, smije_gotovinu)
    with k_izv:
        _kartica_izvjestaj(sheet, nastavnik)

"""
CAKI — profesor_ui.py  (26.9.2026.)
Portal za profesore / instruktore: JEDNA prijava (ime + osobna lozinka iz taba Nastavnici),
u karticama: ✅ Dolasci (grupni termini) · 🎓 Matura · 📝 Instrukcije · 📄 Mjesečni izvještaj.

🎓 Matura (26.9.2026.): profesor bilježi dolaske za svoju kantu (dan × termin × učionica) iz
rasporeda koji admin složi u 🎓 Raspored Matura. Vidi samo kante svojih predmeta
(Nastavnici.predmeti). Datum slobodan, najviše ROK_PROFESOR_DANA (14) dana unatrag.
"Držim sat umjesto kolege" = zamjena (bilježi se u Zamjene log).

Koriste ga caki-evidencija-dolazaka.py (glavna adresa) i pages/2_Instrukcije.py (stari link).

2.10.2026.: ✅ Dolasci — profesor vidi samo SVOJE grupe Upisa (Grupe.redovni_nastavnik); grupe kolega tek
kad odabere "Držim sat umjesto kolege". Nova kartica 🏫 Zauzetost učionica: tjedni pregled samo s oznakom
"ZAUZETO – MATURA / UPISI" (bez programa, profesora i učenika) — da se instrukcije ne dogovaraju tada.

3.10.2026.: 📝 Instrukcije — profesor bira SAMO učenike koji su mu dodijeljeni (tab Dodjele, dodjeljuju admini);
nova kartica 👩‍🎓 Moji učenici (kontakt samo ako ga admin dopusti); status termina (📅 Zakazan, ✅ Održan,
otkazivanje, nadoknada); 📒 bilješka sa sata (vidi i roditelj) može se ispraviti do ROK_PROFESOR_DANA dana;
📄 izvještaj prikazuje i profesorov honorar (samo njegov iznos).

Privatnost: profesor NIKAD ne vidi cijene, iznose ni ponude. Vidi samo svoje instrukcije i je li
termin plaćen (✅). Naplatu gotovinom smije evidentirati samo profesor s ovlaštenjem
(Nastavnici.naplata_gotovinom = Da, postavlja admin).
"""
import json
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from pipeline_upisi import (
    DODJELE_TAB,
    HONORARI_TAB,
    OTKAZ_SATI,
    OZNAKE_STATUSA_TERMINA,
    STATUSI_TERMINA,
    aktivne_dodjele,
    centi_u_tekst,
    promijeni_status_termina,
    ucenici_profesora,
    uredi_biljesku_sata,
    whatsapp_link,
    DANI_U_TJEDNU,
    blok_aktivan_na_datum,
    blokovi_zauzetosti,
    html_tjedne_mreze,
    ponedjeljak_tjedna,
    razdoblje_grupe_upisa,
    ucitaj_praznike,
    ucitaj_razdoblja,
    INSTRUKCIJE_OBLICI,
    INSTRUKCIJE_PREDMETI,
    INSTRUKCIJE_TRAJANJA,
    MJESECI_HR,
    ROK_PROFESOR_DANA,
    SEZONA,
    datum_u_roku,
    kante_za_profesora,
    labela_kante,
    matura_kante,
    naziv_taba_rasporeda_mature,
    postojeci_dolasci,
    predmeti_nastavnika,
    zadnji_datum_dana,
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


@st.cache_data(ttl=60)
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
    # samo grupe koje taj datum traju (Razdoblja_termina: prvi termin + broj termina; prazno = cijela sezona)
    if not grupe_danas.empty:
        razdoblja, praznici = _razdoblja_i_praznici()
        traju = []
        for _, g in grupe_danas.iterrows():
            od, do, _broj = razdoblje_grupe_upisa(g, razdoblja, praznici)
            traju.append(blok_aktivan_na_datum({"datum_od": od, "datum_do": do}, odabrani_datum))
        grupe_danas = grupe_danas[traju]
    if grupe_danas.empty:
        st.info(f"Nema aktivnih termina za {dan_naziv.lower()}.")
        return
    # 2.10.2026.: profesor vidi samo SVOJE grupe; tuđe tek kad drži sat umjesto kolege
    redovni_stupac = grupe_danas.get("redovni_nastavnik", pd.Series("", index=grupe_danas.index)).astype(str)
    moje_g, ostale_g = grupe_danas[redovni_stupac == nastavnik], grupe_danas[redovni_stupac != nastavnik]
    nacin = st.radio("Sat", ["moje", "zamjena"], horizontal=True, key="dol_nacin",
                     format_func={"moje": f"⭐ Moje grupe ({len(moje_g)})",
                                  "zamjena": f"🔄 Držim sat umjesto kolege ({len(ostale_g)})"}.get)
    izbor_g = (moje_g if nacin == "moje" else ostale_g).sort_values("vrijeme")
    if izbor_g.empty:
        st.info(f"Nemate svojih grupa za {dan_naziv.lower()}. Grupe bez upisanog nastavnika su pod "
                "\"Držim sat umjesto kolege\" — javite adminu da vas upiše kao redovnog nastavnika."
                if nacin == "moje" else "Nema drugih grupa taj dan.")
        return
    opcije = {f"{g['program']} — {g['vrijeme']} ({g['ucionica']})"
              + (f" · {g.get('redovni_nastavnik', '') or 'bez nastavnika'}" if nacin == "zamjena" else ""): g["grupa_id"]
              for _, g in izbor_g.iterrows()}
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


# ------------------------------------------------------------------ 🎓 matura

def _kartica_matura(sheet, nastavnik):
    df_ras = _ucitaj(naziv_taba_rasporeda_mature(SEZONA))
    kante = matura_kante(df_ras)
    if not kante:
        st.info("Raspored Mature još nije složen/spremljen — javite adminu.")
        return
    moje, ostale = kante_za_profesora(kante, nastavnik, predmeti_nastavnika(_ucitaj("Nastavnici"), nastavnik))
    nacin = st.radio("Sat", ["moje", "zamjena"], horizontal=True, key="mat_nacin",
                     format_func={"moje": f"⭐ Moje grupe ({len(moje)})",
                                  "zamjena": f"🔄 Držim sat umjesto kolege ({len(ostale)})"}.get)
    izbor = moje if nacin == "moje" else ostale
    if not izbor:
        st.info("Nemate upisanih grupa u rasporedu Mature — javite adminu." if nacin == "moje"
                else "Nema drugih grupa vaših predmeta.")
        return
    opcije = {labela_kante(k, s_profesorom=(nacin == "zamjena")): k for k in izbor}
    kanta = opcije[st.selectbox("Grupa (kanta iz rasporeda)", list(opcije), key=f"mat_kanta_{nacin}")]
    gid = kanta["grupa_id"]

    danas = sada_zagreb().date()
    datum = st.date_input("Datum sata", value=zadnji_datum_dana(kanta["dan"], danas), format="DD.MM.YYYY",
                          min_value=danas - timedelta(days=ROK_PROFESOR_DANA), max_value=danas,
                          key=f"mat_datum_{gid}",
                          help=f"Najviše {ROK_PROFESOR_DANA} dana unatrag. Stariji sat upisuje admin.")
    if not datum_u_roku(datum, danas):
        st.error(f"Sat se može upisati najviše {ROK_PROFESOR_DANA} dana unatrag — za stariji se javite adminu.")
        return
    dan_datuma = DANI_U_TJEDNU[datum.weekday()]
    if dan_datuma != kanta["dan"]:
        st.warning(f"Odabrani datum je {dan_datuma.lower()}, a grupa je u rasporedu {kanta['dan'].lower()} — "
                   "u redu ako je sat premješten.")
    redovni = kanta["profesor"] or nastavnik
    if kanta["profesor"] and kanta["profesor"] != nastavnik:
        st.warning(f"🔄 Zamjena — u rasporedu je {kanta['profesor']}. Bilježi se automatski.")

    if not kanta["ucenici"]:
        st.info("U ovoj grupi još nema učenika.")
        return
    prije = postojeci_dolasci(_ucitaj("Termini"), _ucitaj("Dolasci"), gid, str(datum))
    if prije:
        st.info("Ovaj sat je već zabilježen — ispod su spremljeni statusi, možete ih ispraviti.")
    st.markdown(f"#### Popis učenika ({len(kanta['ucenici'])})")
    oznake = {"1": "✅ Prisutan", "0": "❌ Odsutan", "2": "💻 Online"}
    statusi = {}
    for u in kanta["ucenici"]:
        zadano = prije.get(u["ucenik_id"], "2" if u["online"] else "1")
        c1, c2 = st.columns([2, 3])
        c1.write(f"{u['ime_djeteta']} · {u['predmet']}" + (" 💻" if u["online"] else ""))
        statusi[u["ucenik_id"]] = c2.radio("status", ["1", "0", "2"], index=["1", "0", "2"].index(zadano)
                                           if zadano in ("1", "0", "2") else 0,
                                           format_func=oznake.get, horizontal=True,
                                           key=f"mat_dol_{gid}_{u['ucenik_id']}_{datum}", label_visibility="collapsed")

    # Gost: Matura učenik iz druge kante (nadoknada)
    kljuc_g = f"mat_gosti_{gid}_{datum}"
    gosti = st.session_state.setdefault(kljuc_g, {})
    u_kanti = {u["ucenik_id"] for u in kanta["ucenici"]}
    with st.expander("➕ Dodaj gosta (učenik iz druge grupe nadoknađuje sat)"):
        upit = st.text_input("Pretraži po imenu", key=f"mat_gost_upit_{gid}")
        if upit:
            nadjeni = {}
            for k in kante:
                for u in k["ucenici"]:
                    if (upit.lower() in u["ime_djeteta"].lower() and u["ucenik_id"] not in u_kanti
                            and u["ucenik_id"] not in gosti and u["ucenik_id"] not in nadjeni):
                        nadjeni[u["ucenik_id"]] = (u["ime_djeteta"], k["grupa_id"])
            for uid, (ime, maticna) in list(nadjeni.items())[:10]:
                if st.button(f"Dodaj: {ime} ({uid})", key=f"mat_gost_{gid}_{uid}"):
                    gosti[uid] = {"ime": ime, "status": "1", "maticna": maticna}
                    st.rerun()
    for uid, podaci in list(gosti.items()):
        g1, g2, g3 = st.columns([2, 2, 1])
        g1.write(f"{podaci['ime']} 🔄")
        podaci["status"] = g2.radio("gost", ["1", "2"], format_func=oznake.get, horizontal=True,
                                    key=f"mat_gost_st_{uid}_{datum}", label_visibility="collapsed")
        if g3.button("🗑️", key=f"mat_gost_del_{uid}_{datum}"):
            del gosti[uid]
            st.rerun()

    if st.button("💾 Spremi dolazak", type="primary", key=f"mat_spremi_{gid}"):
        spremi_cijeli_termin(
            sheet, gid, str(datum), nastavnik, redovni,
            [{"ucenik_id": u["ucenik_id"], "ime_djeteta": u["ime_djeteta"], "status": statusi[u["ucenik_id"]]}
             for u in kanta["ucenici"]],
            [{"ucenik_id": uid, "ime_djeteta": p["ime"], "status": p["status"], "maticna_grupa": p["maticna"]}
             for uid, p in gosti.items()])
        st.session_state.pop(kljuc_g, None)
        _poruka("success", f"Dolazak spremljen: {labela_kante(kanta)}, {datum.strftime('%d.%m.%Y.')}.")
        st.cache_data.clear()
        st.rerun()


# ------------------------------------------------------------------ 📝 instrukcije

def _moji_ucenici(nastavnik) -> pd.DataFrame:
    return ucenici_profesora(_ucitaj(DODJELE_TAB), _ucitaj("Učenici"), nastavnik, sada_zagreb().date())


def _kartica_moji_ucenici(nastavnik):
    st.caption("Učenici koje vam je dodijelio admin. Kontakt vidite samo kad je dopušten (za prvi dogovor). "
               "Podatke ne prepisujte u privatni imenik i ne dijelite ih dalje.")
    moji = _moji_ucenici(nastavnik)
    if moji.empty:
        st.info("Nemate dodijeljenih učenika — javite adminu.")
        return
    for _, u in moji.iterrows():
        with st.container(border=True):
            st.markdown(f"**{u['ime_djeteta']}** · {u['predmet'] or 'svi predmeti'}"
                        + (f" · {u['skola']}" if u["skola"] else ""))
            if u["napomena_za_profesora"]:
                st.caption(f"📌 {u['napomena_za_profesora']}")
            if u["kontakt_dopusten"] == "Da":
                c1, c2 = st.columns(2)
                if u["mobitel_roditelja"]:
                    c1.link_button(f"📲 Roditelj {u['ime_roditelja']}".strip(), whatsapp_link("", u["mobitel_roditelja"]))
                    c1.caption(f"📞 {u['mobitel_roditelja']}")
                if u["mobitel_djeteta"]:
                    c2.link_button("📲 Učenik", whatsapp_link("", u["mobitel_djeteta"]))
                    c2.caption(f"📞 {u['mobitel_djeteta']}")
            else:
                st.caption("🔒 Kontakt nije dopušten — termin dogovara admin.")


def _kartica_instrukcije(sheet, nastavnik, smije_gotovinu):
    df_instr = _ucitaj("Instrukcije_termini")
    ima_status = "status_termina" in df_instr.columns
    st.markdown("#### Novi termin")
    moji = _moji_ucenici(nastavnik)
    if moji.empty:
        st.info("Nemate dodijeljenih učenika, pa ne možete upisati termin. Admin vas povezuje s učenikom "
                "(👩‍🎓 Moji učenici). Javite se adminu.")
    else:
        opcije = {f"{r['ime_djeteta']} ({r['ucenik_id']})": r for _, r in moji.iterrows()}
        u = opcije[st.selectbox("Učenik (samo vaši)", options=list(opcije), key="instr_ucenik")]
        uid, ime = u["ucenik_id"], u["ime_djeteta"]
        zadani_predmet = (u["predmet"].split(", ")[0] if u["predmet"] else "")
        with st.form("novi_termin_form", clear_on_submit=True):
            if ima_status:
                status = st.radio("Termin", STATUSI_TERMINA, horizontal=True, format_func=OZNAKE_STATUSA_TERMINA.get,
                                  help=f"📅 Zakazan = budući termin (podsjetnik roditelju šalje admin dan prije). "
                                       f"Otkazivanje kasnije od {OTKAZ_SATI} h ili nedolazak se naplaćuje.")
            else:
                status = "Održan"
            c1, c2, c3 = st.columns(3)
            datum = c1.date_input("Datum", value=date.today(), format="DD.MM.YYYY")
            vrijeme = c2.text_input("Vrijeme (npr. 17:00)") if ima_status else ""
            duljina = c3.selectbox("Duljina termina (min)", options=INSTRUKCIJE_TRAJANJA, index=1)
            c4, c5 = st.columns(2)
            predmet = c4.selectbox("Predmet", options=INSTRUKCIJE_PREDMETI,
                                   index=INSTRUKCIJE_PREDMETI.index(zadani_predmet) if zadani_predmet in INSTRUKCIJE_PREDMETI else 0)
            stupanj = c5.selectbox("Stupanj školovanja", options=STUPNJEVI_SKOLOVANJA_INSTR, index=1)
            oblik = st.radio("Oblik", options=INSTRUKCIJE_OBLICI, horizontal=True)
            broj = st.number_input("Broj učenika u grupi (samo za grupu)", min_value=1, max_value=10, value=1)
            gotovina = st.checkbox("💵 Naplaćeno gotovinom") if smije_gotovinu else False
            nap_jav = st.text_area("📒 Bilješka sa sata — što se radilo, domaća zadaća (vidi i roditelj)")
            nap_int = st.text_area("Napomena interna (vidite samo vi i admin)")
            if st.form_submit_button("💾 Spremi termin", type="primary"):
                danas = sada_zagreb().date()
                if status not in ("Zakazan", "Otkazan na vrijeme") and datum > danas:
                    st.error("Budući termin može biti samo 📅 Zakazan.")
                elif status == "Zakazan" and datum < danas:
                    st.error("Zakazan termin mora biti danas ili kasnije.")
                elif datum < danas - timedelta(days=ROK_PROFESOR_DANA):
                    st.error(f"Termin se može upisati najviše {ROK_PROFESOR_DANA} dana unatrag — za stariji se javite adminu.")
                else:
                    dodaj_instrukciju_termin(
                        sheet, ucenik_id=uid, ime_djeteta=ime, nastavnik=nastavnik, datum=str(datum),
                        duljina_min=duljina, oblik=oblik, broj_ucenika_u_grupi=broj if oblik == "Grupa" else None,
                        placeno_oznaka_prof=PLACENO_GOTOVINOM if gotovina else "Ne",
                        napomena_interna=nap_int, napomena_javna=nap_jav, predmet=predmet, stupanj_skolovanja=stupanj,
                        status_termina=status, vrijeme=vrijeme)
                    _poruka("success", f"Termin spremljen: {ime}, {datum.strftime('%d.%m.%Y.')} ({status}).")
                    st.cache_data.clear()
                    st.rerun()

    if df_instr.empty or "nastavnik" not in df_instr.columns:
        st.info("Još nema evidentiranih termina.")
        return
    moji_t = df_instr[df_instr["nastavnik"] == nastavnik].sort_values("datum", ascending=False)
    if moji_t.empty:
        st.info("Nemate još evidentiranih termina.")
        return

    if ima_status:
        zakazani = moji_t[moji_t["status_termina"] == "Zakazan"].sort_values("datum")
        if not zakazani.empty:
            st.markdown(f"#### 📅 Zakazani termini ({len(zakazani)})")
            danas = sada_zagreb().date()
            for _, t in zakazani.iterrows():
                with st.container(border=True):
                    st.markdown(f"**{str(t['datum'])[:10]} {t.get('vrijeme', '')}** · {t['ime_djeteta']} · "
                                f"{t.get('predmet', '')} · {t['duljina_min']} min")
                    proslo = str(t["datum"])[:10] <= str(danas)
                    opcije_st = ["Održan", "Otkazan na vrijeme", "Otkazan kasno", "Nije došao"] if proslo \
                        else ["Otkazan na vrijeme"]
                    k1, k2 = st.columns([2, 3])
                    novi = k1.selectbox("Što je bilo?", opcije_st, format_func=OZNAKE_STATUSA_TERMINA.get,
                                        key=f"zak_st_{t['termin_id']}")
                    bilj = k2.text_input("📒 Bilješka sa sata (vidi roditelj)", key=f"zak_b_{t['termin_id']}") \
                        if novi == "Održan" else None
                    if st.button("💾 Spremi", key=f"zak_s_{t['termin_id']}"):
                        try:
                            promijeni_status_termina(sheet, t["termin_id"], novi, biljeska=bilj, nastavnik=nastavnik)
                            _poruka("success", f"{t['ime_djeteta']}: {OZNAKE_STATUSA_TERMINA[novi]}.")
                        except ValueError as e:
                            _poruka("error", str(e))
                        st.cache_data.clear()
                        st.rerun()

    st.markdown("#### Moji termini")
    placeno = (moji_t.get("placeno_oznaka_prof", "") == PLACENO_GOTOVINOM) | (moji_t.get("uplata_potvrdjena_admin", "") == "Da")
    tablica = pd.DataFrame({
        "Datum": [str(v)[:10] for v in moji_t["datum"]],
        "Učenik": moji_t["ime_djeteta"],
        "Predmet": moji_t["predmet"] if "predmet" in moji_t.columns else "",
        "Min": moji_t["duljina_min"],
        "Oblik": moji_t["oblik"],
        "Plaćeno": ["✅" if x else "" for x in placeno],
        "📒 Bilješka sa sata": moji_t.get("napomena_javna", ""),
        "Napomena": moji_t.get("napomena_interna", ""),
    })
    if ima_status:
        tablica.insert(1, "Termin", [OZNAKE_STATUSA_TERMINA.get(str(v or "Održan"), str(v)).split(" (")[0]
                                     for v in moji_t["status_termina"]])
    st.dataframe(tablica, hide_index=True, width="stretch")

    danas = sada_zagreb().date()
    za_uredit = moji_t[moji_t["datum"].astype(str).str[:10] >= str(danas - timedelta(days=ROK_PROFESOR_DANA))]
    if ima_status:
        za_uredit = za_uredit[za_uredit["status_termina"] != "Zakazan"]
    if not za_uredit.empty:
        with st.expander(f"📒 Uredi bilješku sa sata (zadnjih {ROK_PROFESOR_DANA} dana)"):
            opcije_t = {f"{str(t['datum'])[:10]} · {t['ime_djeteta']} · {t.get('predmet', '')}": t
                        for _, t in za_uredit.iterrows()}
            t = opcije_t[st.selectbox("Termin", list(opcije_t), key="bilj_termin")]
            jav = st.text_area("📒 Bilješka sa sata (vidi i roditelj)", value=str(t.get("napomena_javna", "") or ""),
                               key=f"bilj_j_{t['termin_id']}")
            inte = st.text_area("Napomena interna", value=str(t.get("napomena_interna", "") or ""),
                                key=f"bilj_i_{t['termin_id']}")
            if st.button("💾 Spremi bilješku", key=f"bilj_s_{t['termin_id']}"):
                try:
                    uredi_biljesku_sata(sheet, t["termin_id"], jav, inte, nastavnik=nastavnik, rok_dana=ROK_PROFESOR_DANA)
                    _poruka("success", "Bilješka spremljena.")
                except ValueError as e:
                    _poruka("error", str(e))
                st.cache_data.clear()
                st.rerun()

    if smije_gotovinu and "status_obracuna" in moji_t.columns:
        otvoreni = moji_t[~placeno & moji_t["status_obracuna"].fillna("").isin(STATUSI_ZA_OBRACUN)].head(20)
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
    df_hon = _ucitaj(HONORARI_TAB)
    izv = izvjestaj_instruktora(_ucitaj("Instrukcije_termini"), _ucitaj("Termini"), _ucitaj("Grupe"), nastavnik, g, m,
                                df_hon if not df_hon.empty else None)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📝 Instrukcije", izv["broj_instrukcija"])
    c2.metric("⏱️ Sati instrukcija", f"{izv['sati_instrukcija']:g}")
    c3.metric("👥 Grupni termini", izv["broj_grupnih_termina"])
    if izv.get("honorar_ukupno_centi") is not None:
        c4.metric("💰 Moj honorar", f"{centi_u_tekst(izv['honorar_ukupno_centi'])} €",
                  help="Po pravilima koja je postavio admin. Konačan iznos potvrđuje admin."
                  + (f" {izv['honorar_bez_pravila']} termina još nema iznos — upisuje admin." if izv.get("honorar_bez_pravila") else ""))
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

    if st.button("📤 Pošalji adminu na provjeru", type="primary"):
        try:
            posalji_izvjestaj_instruktora(sheet, izv)
            _poruka("success", "Izvještaj je poslan — admin ga vidi u panelu za provjeru.")
        except ValueError as e:
            _poruka("error", str(e))
        st.cache_data.clear()
        st.rerun()


# ------------------------------------------------------------------ portal

@st.cache_data(ttl=300)
def _razdoblja_i_praznici():
    sheet = _init_sheet()
    return ucitaj_razdoblja(sheet), ucitaj_praznike(sheet)


def _kartica_zauzetost():
    """Tjedni pregled zauzetosti učionica — samo "ZAUZETO", bez detalja (2.10.2026.)."""
    st.caption("Kad su učionice zauzete grupama (Matura, Upisi). **Grupe imaju prednost** — instrukcije u "
               "centru ne dogovarajte u tim terminima.")
    dan = st.date_input("Tjedan (odaberite bilo koji dan)", value=sada_zagreb().date(), format="DD.MM.YYYY",
                        key="zau_tjedan")
    pon = ponedjeljak_tjedna(dan)
    st.caption(f"Tjedan {pon:%d.%m.} – {pon + timedelta(days=6):%d.%m.%Y.}")
    razdoblja, praznici = _razdoblja_i_praznici()
    blokovi = blokovi_zauzetosti(_ucitaj("Grupe"), _ucitaj(naziv_taba_rasporeda_mature(SEZONA)), razdoblja, praznici)
    st.markdown(html_tjedne_mreze(blokovi, pon, javno=True, praznici=praznici), unsafe_allow_html=True)


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
    k_dol, k_mat, k_instr, k_uc, k_izv, k_zau = st.tabs(["✅ Dolasci — grupe", "🎓 Matura", "📝 Instrukcije",
                                                         "👩‍🎓 Moji učenici", "📄 Mjesečni izvještaj",
                                                         "🏫 Zauzetost učionica"])
    with k_dol:
        _kartica_dolasci(sheet, nastavnik)
    with k_mat:
        _kartica_matura(sheet, nastavnik)
    with k_instr:
        _kartica_instrukcije(sheet, nastavnik, smije_gotovinu)
    with k_uc:
        _kartica_moji_ucenici(nastavnik)
    with k_izv:
        _kartica_izvjestaj(sheet, nastavnik)
    with k_zau:
        _kartica_zauzetost()

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

13.10.2026.: nova kartica 🗓️ Dostupnost (profesor unosi tjedne slobodne termine za nove instrukcije, do 2 okvira dnevno,
oblik Uživo/Online/Oboje, "ne primam nove učenike"; admin to vidi uz upite; logika u dostupnost_profesora.py).

13.10.2026.: nova kartica 📥 Novi upiti (profesor vidi otvorene upite za instrukcije BEZ imena i kontakta, javlja
"Preuzimam" / "Ne mogu"; više profesora može preuzeti isti upit, dodjeljuje admin; logika u upiti_instrukcije.py).

17.10.2026.: nova kartica 📅 Kalendar centra (ugrađen dijeljeni Google kalendar centra, samo za
gledanje; uređivanje ostaje u Google kalendaru, mjerodavna zauzetost učionica je 🏫 Zauzetost učionica).

12.10.2026.: nova prva kartica 🏠 Danas (danasnji sati, sati koji čekaju upis i do kada, instrukcije bez
statusa, status izvještaja; logika u profesor_danas.py); cijeli portal je layout="wide".

Privatnost: profesor NIKAD ne vidi cijene, iznose ni ponude. Vidi samo svoje instrukcije i je li
termin plaćen (✅). Naplatu gotovinom smije evidentirati samo profesor s ovlaštenjem
(Nastavnici.naplata_gotovinom = Da, postavlja admin).
"""
import base64   # noqa: F401  (ostaje — koristi se u drugim dijelovima portala)
import json
import urllib.parse
from datetime import date, timedelta

import streamlit.components.v1 as _components

import pandas as pd
import streamlit as st

import profesor_danas as _danas
import dostupnost_profesora as _dost
import upiti_instrukcije as _upiti
import sat_biljeska as _sat

from pipeline_upisi import (
    DODJELE_TAB,
    HONORARI_TAB,
    IZVJESTAJI_TAB,
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
    naziv_ucionice_centra,
    oznaka_ucionice,
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
    BLOKOVI_TAB,
    blokovi_nastavnika,
    grupe_nastavnika_s_blokom,
    slobodni_blokovi,
    preuzmi_blok,
    otpusti_blok,
    NAJAM_TAB,
    PROFILI_PROFESORA_TAB,
    UCIONICE_CENTRA,
    blok_iz_unosa_grupe,
    je_ispravno_vrijeme,
    je_najmoprimac,
    najam_sazetak,
    najam_termini,
    opcija_ucionice_upisi,
    otkazi_najam,
    otkazi_termin,
    otkazani_po_kljucu,
    provjeri_grupu_upisa,
    upisi_najam,
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


# ------------------------------------------------------------------ 📚 teme, ocjena sata, zadaća (17.10.2026.)

def _kljuc_baze(predmet: str, stupanj: str) -> str:
    """Secret s ID-em Sheeta baze zadataka za taj predmet (BAZA_SHEET_ID_*), ili ''."""
    p = str(predmet or "").strip().lower()
    if p.startswith("matemat"):
        return "BAZA_SHEET_ID_MATEMATIKA_OS" if "osnov" in str(stupanj or "").lower() else "BAZA_SHEET_ID_MATEMATIKA"
    if p.startswith("fizik"):
        return "BAZA_SHEET_ID_FIZIKA"
    return ""


@st.cache_data(ttl=3600, show_spinner=False)
def _popis_tema(predmet: str, stupanj: str) -> list:
    """Teme za izbornik iz šifrarnika baze zadataka. Ako secret/pristup ne postoji → [] (slobodan unos)."""
    kljuc = _kljuc_baze(predmet, stupanj)
    try:
        if not kljuc or not str(st.secrets.get(kljuc, "")).strip():
            return []
        sa_info = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
        baza = get_gspread_client(sa_info).open_by_key(str(st.secrets[kljuc]).strip())
        return _sat.popis_tema(_sat.ucitaj_sifrarnik(baza))
    except Exception:
        return []


def _polja_sata(kljuc: str, predmet: str, stupanj: str, teme0=(), ocjena0: str = "", zadaca0: bool = False):
    """Widgeti: teme, ocjena sata, zadaća zadana. Vraća (teme_lista, ocjena, zadaca_zadana)."""
    opcije = _popis_tema(predmet, stupanj)
    spremljene = list(teme0)
    sve = list(dict.fromkeys(opcije + [t for t in spremljene if t in opcije]))
    st.markdown("**📚 Što smo radili na satu**")
    teme = st.multiselect("Teme i podcjeline", sve, default=[t for t in spremljene if t in sve], key=f"{kljuc}_teme",
                          placeholder="Odaberi iz popisa (možeš upisati za pretraživanje)",
                          help="Popis dolazi iz baze zadataka." if opcije else
                          "Popis tema za ovaj predmet još nije povezan — upiši teme ručno ispod.")
    ostale = ", ".join(t for t in spremljene if t not in sve)
    dodatne = st.text_input("Druge teme (slobodan tekst, zarezom)", value=ostale, key=f"{kljuc}_teme_txt")
    c1, c2 = st.columns(2)
    ocjena = c1.radio("Kako je prošao sat", ["", "+", "-"], index=["", "+", "-"].index(ocjena0) if ocjena0 in ("+", "-") else 0,
                      format_func=lambda x: {"": "— (bez ocjene)", "+": "➕ dobro", "-": "➖ slabije"}[x], horizontal=True,
                      key=f"{kljuc}_ocjena", help="Vidite samo vi i admin. Roditelj ocjenu ne vidi.")
    zadaca = c2.checkbox("📝 Zadana zadaća", value=zadaca0, key=f"{kljuc}_zadaca",
                         help="Na sljedećem satu označit ćete je li napravljena.")
    return teme + [x.strip() for x in dodatne.split(",") if x.strip()], ocjena, zadaca


def _blok_zadaca_na_cekanju(sheet, nastavnik, ucenik_id, kljuc: str, df_instr):
    """Prije novog sata: je li napravljena zadaća zadana na prethodnom satu (profesor označava na sljedećem satu)."""
    z = _sat.zadaca_na_cekanju(df_instr, ucenik_id)
    if not z:
        return
    with st.container(border=True):
        st.markdown(f"📝 **Zadaća zadana {z['datum'].strftime('%d.%m.%Y.')}**"
                    + (f" ({z['predmet']})" if z["predmet"] else "") + " — je li napravljena?")
        if z["teme"]:
            st.caption(f"Teme tog sata: {z['teme'].replace(' ; ', ', ')}")
        a, b = st.columns([3, 1])
        izbor = a.radio("Zadaća", _sat.ZADACA_STATUSI, horizontal=True, label_visibility="collapsed",
                        format_func=lambda x: {"Da": "✅ Napravljena", "Djelomično": "🟡 Djelomično",
                                               "Ne": "❌ Nije napravljena"}[x], key=f"zad_{kljuc}_{z['termin_id']}")
        if b.button("💾 Spremi", key=f"zad_s_{kljuc}_{z['termin_id']}"):
            try:
                _sat.oznaci_zadacu(sheet, z["termin_id"], izbor, nastavnik, df_instr, _ucitaj(DODJELE_TAB))
                _poruka("success", "Zadaća označena.")
            except ValueError as e:
                _poruka("error", str(e))
            st.cache_data.clear()
            st.rerun()


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
    # 18.10.2026.: sada_zagreb(), ne date.today() — server je u UTC-u, pa je profesor nakon
    # ponoći po našem vremenu dobivao prethodni dan i "nema aktivnih termina".
    odabrani_datum = st.date_input("Datum termina", value=sada_zagreb().date(),
                                   format="DD.MM.YYYY")
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
    # 18.10.2026.: grupa je "moja" i kad nisam redovni nastavnik, ali toga dana držim blok u njoj
    # (višepredmetni termin, npr. PRELOG — v. kartica 🧩 Moji blokovi).
    s_blokom = grupe_nastavnika_s_blokom(_ucitaj(BLOKOVI_TAB), nastavnik, odabrani_datum)
    je_moja = (redovni_stupac == nastavnik) | grupe_danas["grupa_id"].astype(str).isin(s_blokom)
    moje_g, ostale_g = grupe_danas[je_moja], grupe_danas[~je_moja]
    nacin = st.radio("Sat", ["moje", "zamjena"], horizontal=True, key="dol_nacin",
                     format_func={"moje": f"⭐ Moje grupe ({len(moje_g)})",
                                  "zamjena": f"🔄 Držim sat umjesto kolege ({len(ostale_g)})"}.get)
    izbor_g = (moje_g if nacin == "moje" else ostale_g).sort_values("vrijeme")
    if izbor_g.empty:
        st.info(f"Nemate svojih grupa za {dan_naziv.lower()}. Grupe bez upisanog nastavnika su pod "
                "\"Držim sat umjesto kolege\" — javite adminu da vas upiše kao redovnog nastavnika."
                if nacin == "moje" else "Nema drugih grupa taj dan.")
        return
    opcije = {f"{g['program']} — {g['vrijeme']} ({naziv_ucionice_centra(oznaka_ucionice(g['ucionica']))})"
              + (f" · {g.get('redovni_nastavnik', '') or 'bez nastavnika'}" if nacin == "zamjena" else ""): g["grupa_id"]
              for _, g in izbor_g.iterrows()}
    grupa_id = opcije[st.selectbox(f"Grupa ({dan_naziv})", options=list(opcije))]
    grupa_red = grupe_danas[grupe_danas["grupa_id"] == grupa_id].iloc[0]
    upisani_redovni = str(grupa_red.get("redovni_nastavnik", "") or "")
    redovni = upisani_redovni or nastavnik   # grupa bez redovnog nastavnika → nije zamjena
    danas_predaje = st.text_input("Danas predaje", value=nastavnik)
    if upisani_redovni and danas_predaje != upisani_redovni:
        st.warning(f"⚠ Zamjena — redovni nastavnik je {upisani_redovni}. Bilježi se automatski.")

    if _otkazivanje_termina(sheet, nastavnik, grupa_id, odabrani_datum):
        return          # otkazan termin se ne evidentira

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
            povijest = _sat.povijest_ucenika(_ucitaj("Instrukcije_termini"), u["ucenik_id"])
            if not povijest.empty:
                with st.expander(f"📚 Povijest sati i obrađene teme ({len(povijest)})"):
                    st.caption("Svi dosadašnji sati ovog učenika (i kod drugih profesora, bez imena i plaćanja).")
                    st.dataframe(povijest, hide_index=True, width="stretch")


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
        _blok_zadaca_na_cekanju(sheet, nastavnik, uid, "novi", df_instr)
        with st.form("novi_termin_form", clear_on_submit=True):
            if ima_status:
                status = st.radio("Termin", STATUSI_TERMINA, horizontal=True, format_func=OZNAKE_STATUSA_TERMINA.get,
                                  help=f"📅 Zakazan = budući termin (podsjetnik roditelju šalje admin dan prije). "
                                       f"Otkazivanje kasnije od {OTKAZ_SATI} h ili nedolazak se naplaćuje.")
            else:
                status = "Održan"
            c1, c2, c3 = st.columns(3)
            datum = c1.date_input("Datum", value=sada_zagreb().date(), format="DD.MM.YYYY")
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
            teme_n, ocjena_n, zadaca_n = _polja_sata("novi", predmet, stupanj)
            if st.form_submit_button("💾 Spremi termin", type="primary"):
                danas = sada_zagreb().date()
                if status not in ("Zakazan", "Otkazan na vrijeme") and datum > danas:
                    st.error("Budući termin može biti samo 📅 Zakazan.")
                elif status == "Zakazan" and datum < danas:
                    st.error("Zakazan termin mora biti danas ili kasnije.")
                elif datum < danas - timedelta(days=ROK_PROFESOR_DANA):
                    st.error(f"Termin se može upisati najviše {ROK_PROFESOR_DANA} dana unatrag — za stariji se javite adminu.")
                else:
                    novi_id = dodaj_instrukciju_termin(
                        sheet, ucenik_id=uid, ime_djeteta=ime, nastavnik=nastavnik, datum=str(datum),
                        duljina_min=duljina, oblik=oblik, broj_ucenika_u_grupi=broj if oblik == "Grupa" else None,
                        placeno_oznaka_prof=PLACENO_GOTOVINOM if gotovina else "Ne",
                        napomena_interna=nap_int, napomena_javna=nap_jav, predmet=predmet, stupanj_skolovanja=stupanj,
                        status_termina=status, vrijeme=vrijeme)
                    if status not in _sat.STATUSI_BEZ_SATA and (teme_n or ocjena_n or zadaca_n):
                        try:
                            _sat.spremi_sat(sheet, novi_id, teme_n, ocjena_n, zadaca_n, nastavnik=nastavnik)
                        except ValueError as e:
                            _poruka("warning", f"Termin je spremljen, ali teme/zadaća nisu: {e}")
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
    if "teme" in moji_t.columns:
        tablica["📚 Teme"] = [str(v).replace(" ; ", ", ") for v in moji_t["teme"]]
    if "ocjena_sata" in moji_t.columns:
        tablica["Ocjena"] = moji_t["ocjena_sata"]
    if "zadaca_zadana" in moji_t.columns:
        tablica["📝 Zadaća"] = ["" if str(z) != "Da" else _sat.ZADACA_OZNAKE.get(str(n or ""), "")
                               for z, n in zip(moji_t["zadaca_zadana"],
                                               moji_t["zadaca_napravljena"] if "zadaca_napravljena" in moji_t.columns
                                               else [""] * len(moji_t))]
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
            teme_e, ocjena_e, zadaca_e = _polja_sata(
                f"bilj_{t['termin_id']}", str(t.get("predmet", "") or ""), str(t.get("stupanj_skolovanja", "") or ""),
                teme0=_sat.teme_iz_teksta(t.get("teme", "")), ocjena0=str(t.get("ocjena_sata", "") or ""),
                zadaca0=str(t.get("zadaca_zadana", "") or "") == "Da")
            _blok_zadaca_na_cekanju(sheet, nastavnik, t["ucenik_id"], f"bilj_{t['termin_id']}", df_instr)
            if st.button("💾 Spremi bilješku", key=f"bilj_s_{t['termin_id']}"):
                try:
                    uredi_biljesku_sata(sheet, t["termin_id"], jav, inte, nastavnik=nastavnik, rok_dana=ROK_PROFESOR_DANA)
                    _sat.spremi_sat(sheet, t["termin_id"], teme_e, ocjena_e, zadaca_e, nastavnik=nastavnik,
                                    rok_dana=ROK_PROFESOR_DANA)
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




# ------------------------------------------------------------------ 📥 novi upiti (13.10.2026.)

def _upiti_otvoreni() -> list:
    return _upiti.otvoreni_upiti(_ucitaj("Prijave"), _ucitaj(DODJELE_TAB), sada_zagreb().date(), SEZONA)


def _broj_neodgovorenih_upita(nastavnik) -> int:
    """Za oznaku na kartici i na 🏠 Danas; greška (npr. tab još ne postoji) nikad ne ruši portal."""
    try:
        return _upiti.broj_neodgovorenih(_upiti_otvoreni(), _ucitaj(_upiti.UPITI_TAB), nastavnik,
                                         predmeti_nastavnika(_ucitaj("Nastavnici"), nastavnik))
    except Exception:
        return 0


def _kartica_upiti(sheet, nastavnik):
    st.caption("Novi upiti za instrukcije. Ime i kontakt obitelji ne vide se dok vam admin ne dodijeli učenika. "
               "**Preuzimam** = zainteresirani ste i imate termin; više kolega može preuzeti isti upit, a odluku "
               "donosi admin. Do dodjele **ne kontaktirajte** obitelj.")
    predmeti_prof = predmeti_nastavnika(_ucitaj("Nastavnici"), nastavnik)
    samo_moji = st.toggle("Samo upiti za moje predmete", value=True, key="upiti_samo_moji") if predmeti_prof else False
    upiti = _upiti.upiti_za_profesora(_upiti_otvoreni(), _ucitaj(_upiti.UPITI_TAB), nastavnik, predmeti_prof, samo_moji)
    if not upiti:
        st.success("Trenutno nema otvorenih upita. 👍")
        return
    for u in upiti:
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 4, 3], gap="medium")
            c1.markdown(f"**{u['predmet'] or '—'}**")
            c1.caption(" · ".join(x for x in [u["stupanj"], u["oblik"],
                                              f"prije {u['dana']} dana" if u["dana"] is not None else ""] if x))
            nap = c2.text_input("Kad vam odgovara (nije obavezno)", value=u["moja_napomena"],
                                key=f"upit_nap_{u['redak_id']}", placeholder="npr. ponedjeljkom i srijedom poslije 17 h",
                                max_chars=200)
            if u["moj_odgovor"] == _upiti.ODGOVOR_PREUZIMAM:
                c3.success("🙋 Preuzeli ste — čeka odluku admina")
            elif u["moj_odgovor"] == _upiti.ODGOVOR_NE_MOGU:
                c3.info("🚫 Javili ste da ne možete")
            b1, b2 = c3.columns(2)
            for gumb, odgovor, tekst, tip in ((b1, _upiti.ODGOVOR_PREUZIMAM, "🙋 Preuzimam", "primary"),
                                              (b2, _upiti.ODGOVOR_NE_MOGU, "🚫 Ne mogu", "secondary")):
                if gumb.button(tekst, key=f"upit_{odgovor}_{u['redak_id']}",
                               type=tip if u["moj_odgovor"] != odgovor else "secondary",
                               disabled=u["moj_odgovor"] == odgovor and nap == u["moja_napomena"]):
                    try:
                        _upiti.postavi_odgovor(sheet, u, nastavnik, odgovor, nap)
                        _poruka("success", f"Spremljeno: {odgovor} — {u['predmet']}.")
                    except ValueError as e:
                        _poruka("error", str(e))
                    st.cache_data.clear()
                    st.rerun()


# ------------------------------------------------------------------ 🗓️ dostupnost (13.10.2026.)

def _kartica_dostupnost(sheet, nastavnik):
    """Tjedna dostupnost za NOVE instrukcije. Služi adminu da zna kome može dodijeliti novog učenika; ništa se ne šalje."""
    trenutna = _dost.dostupnost_profesora(_ucitaj(_dost.DOSTUPNOST_TAB), nastavnik)
    st.caption("Označite dane i vrijeme kad biste mogli preuzeti **nove** instrukcije (do dva okvira dnevno). "
               "Admin to vidi kad dodjeljuje nove učenike. Postojeće termine ovo ne mijenja.")
    if not trenutna["prozori"] and not trenutna["pauza"]:
        st.info("Još niste unijeli dostupnost.")
    elif _dost.zastarjelo(trenutna):
        st.warning(f"Dostupnost je zadnji put ažurirana {trenutna['azurirano'][:10] or 'davno'} — provjerite je li još točna "
                   "pa kliknite Spremi.")
    else:
        st.success("Spremljeno: " + _dost.sazetak(trenutna) + f"  ·  ažurirano {trenutna['azurirano'][:16]}")

    g1, g2 = st.columns([2, 3], gap="large")
    pauza = g1.toggle("⏸️ Trenutno ne primam nove učenike", value=trenutna["pauza"], key="dost_pauza")
    napomena = g2.text_input("Napomena za admina (nije obavezno)", value=trenutna["napomena"], key="dost_nap",
                             placeholder="npr. do kraja studenog samo online", max_chars=300)

    po_danu = {d: [p for p in trenutna["prozori"] if p["dan"] == d] for d in DANI_U_TJEDNU}
    h = st.columns([2, 1.2, 1.2, 1.2, 1.2, 1.6])
    for kol, naslov in zip(h, ["Dan", "Od", "Do", "Drugi okvir od", "do", "Oblik"]):
        kol.caption(naslov)

    def _idx(opcije, vrijednost, zadano):
        return opcije.index(vrijednost) if vrijednost in opcije else opcije.index(zadano)

    redovi, greske = [], []
    vrijeme_opcije = _dost.VREMENA
    drugi_opcije = ["—"] + _dost.VREMENA
    for dan in DANI_U_TJEDNU:
        p = po_danu[dan]
        c = st.columns([2, 1.2, 1.2, 1.2, 1.2, 1.6])
        on = c[0].toggle(dan, value=bool(p), key=f"dost_{dan}_on", disabled=pauza)
        od1 = c[1].selectbox("od", vrijeme_opcije, index=_idx(vrijeme_opcije, p[0]["od"] if p else "", "16:00"),
                             key=f"dost_{dan}_od1", disabled=pauza or not on, label_visibility="collapsed")
        do1 = c[2].selectbox("do", vrijeme_opcije, index=_idx(vrijeme_opcije, p[0]["do"] if p else "", "20:00"),
                             key=f"dost_{dan}_do1", disabled=pauza or not on, label_visibility="collapsed")
        od2 = c[3].selectbox("od2", drugi_opcije, index=_idx(drugi_opcije, p[1]["od"] if len(p) > 1 else "—", "—"),
                             key=f"dost_{dan}_od2", disabled=pauza or not on, label_visibility="collapsed")
        do2 = c[4].selectbox("do2", drugi_opcije, index=_idx(drugi_opcije, p[1]["do"] if len(p) > 1 else "—", "—"),
                             key=f"dost_{dan}_do2", disabled=pauza or not on, label_visibility="collapsed")
        oblik = c[5].selectbox("oblik", _dost.OBLICI, index=_idx(_dost.OBLICI, p[0]["oblik"] if p else "", "Oboje"),
                               key=f"dost_{dan}_oblik", disabled=pauza or not on, label_visibility="collapsed")
        if on and not pauza:
            redovi.append({"dan": dan, "od": od1, "do": do1, "oblik": oblik})
            if (od2 == "—") != (do2 == "—"):
                greske.append(f"{dan}: za drugi okvir odaberite i početak i kraj (ili oboje ostavite na —).")
            elif od2 != "—":
                redovi.append({"dan": dan, "od": od2, "do": do2, "oblik": oblik})

    try:
        razdoblja, praznici = _razdoblja_i_praznici()
        blokovi = _danas.moji_blokovi(_ucitaj("Grupe"), _ucitaj(naziv_taba_rasporeda_mature(SEZONA)),
                                      razdoblja, praznici, nastavnik,
                                      _ucitaj(BLOKOVI_TAB))
        for w in _dost.preklapanja_s_grupama(redovi, blokovi):
            st.warning("⚠ " + w)
    except Exception:
        pass
    for g in greske:
        st.error(g)

    if st.button("💾 Spremi dostupnost", type="primary", key="dost_spremi", disabled=bool(greske)):
        try:
            n = _dost.spremi_dostupnost(sheet, nastavnik, redovi, pauza=pauza, napomena=napomena)
            _poruka("success", "Dostupnost spremljena: " + ("ne primate nove učenike." if pauza else f"{n} okvir(a) u tjednu."))
        except ValueError as e:
            _poruka("error", str(e))
        st.cache_data.clear()
        st.rerun()

# ------------------------------------------------------------------ 🏠 danas (12.10.2026.)

def _kartica_danas(nastavnik):
    """Početni pregled: što je danas, što čeka upis i do kada, status izvještaja. Samo čitanje."""
    danas = sada_zagreb().date()
    razdoblja, praznici = _razdoblja_i_praznici()
    blokovi = _danas.moji_blokovi(_ucitaj("Grupe"), _ucitaj(naziv_taba_rasporeda_mature(SEZONA)),
                                  razdoblja, praznici, nastavnik, _ucitaj(BLOKOVI_TAB))
    df_termini = _ucitaj("Termini")
    sati = _danas.danasnji_sati(blokovi, df_termini, danas, praznici)
    kasne = _danas.nezabiljezeni_sati(blokovi, df_termini, danas, praznici)
    instr = _danas.pregled_instrukcija(_ucitaj("Instrukcije_termini"), nastavnik, danas)
    izv = _danas.status_izvjestaja(_ucitaj(IZVJESTAJI_TAB), nastavnik, danas)

    hitno = [k for k in kasne if k["preostalo_dana"] <= 3]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("👥 Grupni sati danas", len(sati))
    m2.metric("📝 Instrukcije danas", len(instr["danas"]))
    m3.metric("⏳ Čeka upis", len(kasne) + len(instr["cekaju_status"]),
              help="Grupni sati bez zabilježenih dolazaka + instrukcije koje su još 'Zakazan', a datum je prošao.")
    m4.metric("🚨 Rok ističe za ≤ 3 dana", len(hitno),
              help=f"Sat se može upisati najviše {ROK_PROFESOR_DANA} dana unatrag, nakon toga ga upisuje admin.")

    if praznici.get(danas):
        st.info(f"Danas je praznik: {praznici[danas]}.")
    n_upita = _broj_neodgovorenih_upita(nastavnik)
    if n_upita:
        st.info(f"📥 Novih upita za instrukcije koje još niste odgovorili: **{n_upita}** — otvorite karticu 📥 Novi upiti.")
    try:
        if _dost.zastarjelo(_dost.dostupnost_profesora(_ucitaj(_dost.DOSTUPNOST_TAB), nastavnik)):
            st.info("🗓️ Dostupnost za nove instrukcije nije unesena ili je stara — ažurirajte je u kartici 🗓️ Dostupnost.")
    except Exception:
        pass

    lijevo, desno = st.columns(2, gap="large")
    with lijevo:
        st.markdown("#### 📅 Danas")
        if not sati and not instr["danas"]:
            st.caption("Danas nemate upisanih grupnih sati ni instrukcija.")
        for b in sati:
            oznaka = "✅ zabilježeno" if b["zabiljezen"] else "⬜ još nije zabilježeno"
            st.markdown(f"**{b['vrijeme']}** · {b['izvor']} · {b['naziv']} · uč. {b['ucionica']} — {oznaka}")
        for r in instr["danas"]:
            st.markdown(f"**📝 Instrukcije** · {r['ucenik']} · {r['predmet'] or '—'} · {r['min']} min · "
                        f"{OZNAKE_STATUSA_TERMINA.get(r['status'], r['status'])}")
        if instr["nadolazece"]:
            st.markdown("#### 🔜 Idućih 7 dana — zakazane instrukcije")
            for r in instr["nadolazece"]:
                st.markdown(f"{r['d']:%d.%m.} ({DANI_U_TJEDNU[r['d'].weekday()][:3]}) · {r['ucenik']} · "
                            f"{r['predmet'] or '—'} · {r['min']} min")
    with desno:
        st.markdown("#### ⏳ Čeka upis")
        if not kasne and not instr["cekaju_status"]:
            st.success("Sve je zabilježeno. 👍")
        if kasne:
            tablica = pd.DataFrame({
                "Sat": [f"{k['datum']:%d.%m.} {DANI_U_TJEDNU[k['datum'].weekday()][:3]} {k['vrijeme']}" for k in kasne],
                "Grupa": [f"{k['naziv']} (uč. {k['ucionica']})" for k in kasne],
                "Kartica": ["🎓 Matura" if k["izvor"] == "Matura" else "✅ Dolasci — grupe" for k in kasne],
                "Zadnji dan za upis": [f"{k['zadnji_dan']:%d.%m.}" + (" 🚨" if k["preostalo_dana"] <= 3 else "")
                                       for k in kasne],
            })
            st.dataframe(tablica, hide_index=True, width="stretch")
        if instr["cekaju_status"]:
            st.markdown("**Instrukcije bez konačnog statusa** (označite Održan / Otkazan u kartici 📝 Instrukcije):")
            st.dataframe(pd.DataFrame({
                "Datum": [f"{r['d']:%d.%m.}" for r in instr["cekaju_status"]],
                "Učenik": [r["ucenik"] for r in instr["cekaju_status"]],
                "Predmet": [r["predmet"] for r in instr["cekaju_status"]],
                "Trajanje (min)": [r["min"] for r in instr["cekaju_status"]],
            }), hide_index=True, width="stretch")

    st.markdown("#### 📄 Mjesečni izvještaj")
    g, m = _danas.prosli_mjesec(danas)
    opis = f"{MJESECI_HR[m - 1]} {g}.: **{izv['status']}**"
    if izv["napomena_admin"]:
        opis += f" — napomena admina: *{izv['napomena_admin']}*"
    (st.warning if izv["status"] in ("Nije poslan", "Vraćeno na ispravak") else st.info)(opis)

# ------------------------------------------------------------------ portal

@st.cache_data(ttl=300)
def _razdoblja_i_praznici():
    sheet = _init_sheet()
    return ucitaj_razdoblja(sheet), ucitaj_praznike(sheet)


def _kartica_blokovi(sheet, nastavnik):
    """🧩 Moji blokovi (18.10.2026.) — višepredmetni termini (npr. PRELOG: BIO/FIZ/KEM). Admin u
    adminu otvori datume i upiše predmet po bloku, a profesor OVDJE preuzme one koje drži.
    Vidi samo blokove svojih predmeta (Nastavnici.predmeti; prazno = vidi sve — isto pravilo kao
    kod Mature). Preuzet blok čini grupu "mojom" u ✅ Dolasci i kad nisam njezin redovni nastavnik."""
    st.caption("Termini s više predmeta (npr. PRELOG: BIO, FIZ, KEM). Admin otvori datume i predmete, "
               "a vi preuzmete blokove koje držite. Preuzeti blok se pojavi u ✅ Dolasci.")
    df_b = _ucitaj(BLOKOVI_TAB)
    if df_b is None or df_b.empty:
        st.info("Još nema otvorenih blokova. Javite se adminu ako očekujete raspored.")
        return
    df_g = _ucitaj("Grupe")
    grupe = {str(g["grupa_id"]): g for _, g in df_g.iterrows()} if df_g is not None and not df_g.empty else {}
    predmeti_prof = predmeti_nastavnika(_ucitaj("Nastavnici"), nastavnik)
    danas = sada_zagreb().date()

    def _opis(b):
        g = grupe.get(b["grupa_id"], {})
        uc = naziv_ucionice_centra(oznaka_ucionice(g.get("ucionica", "")))
        program = str(g.get("program", "") or b["grupa_id"])
        return (f"**{b['datum']:%d.%m.%Y.}** ({DANI_U_TJEDNU[b['datum'].weekday()][:3]}) · {b['vrijeme']} · "
                f"**{b['predmet']}** · {program}" + (f" · {uc}" if uc else ""))

    moji = [b for b in blokovi_nastavnika(df_b, nastavnik) if b["datum"] and b["datum"] >= danas]
    st.markdown(f"#### ⭐ Moji blokovi ({len(moji)})")
    if not moji:
        st.caption("Nemate preuzetih blokova koji tek dolaze.")
    for b in moji:
        c1, c2 = st.columns([4, 1])
        c1.markdown(_opis(b))
        if c2.button("Odjavi se", key=f"blok_off_{b['blok_id']}",
                     help="Blok se vraća među slobodne — javite adminu da zna."):
            try:
                otpusti_blok(sheet, b["blok_id"], nastavnik)
                _poruka("success", "Blok je otpušten.")
            except ValueError as e:
                _poruka("warning", str(e))
            st.cache_data.clear()
            st.rerun()

    slobodni = slobodni_blokovi(df_b, predmeti_prof, danas)
    st.markdown(f"#### 🆓 Slobodni blokovi ({len(slobodni)})")
    if not slobodni:
        st.caption("Trenutno nema slobodnih blokova za vaše predmete." if predmeti_prof
                   else "Trenutno nema slobodnih blokova.")
    for b in slobodni:
        c1, c2 = st.columns([4, 1])
        c1.markdown(_opis(b))
        if c2.button("Preuzimam", key=f"blok_on_{b['blok_id']}", type="primary"):
            try:
                preuzmi_blok(sheet, b["blok_id"], nastavnik)
                _poruka("success", f"Preuzeli ste blok {b['datum']:%d.%m.} {b['vrijeme']} ({b['predmet']}).")
            except ValueError as e:
                _poruka("warning", str(e))
            st.cache_data.clear()
            st.rerun()


def _slobodne_ucionice(datum, vrijeme, bez_najma=""):
    """Oznake učionica koje su u to vrijeme SLOBODNE. Zauzetu nitko ne može upisati (odluka
    18.10.2026.) — provjera ide kroz istu logiku preklapanja kao kod grupa."""
    razdoblja, praznici = _razdoblja_i_praznici()
    blokovi = [b for b in blokovi_zauzetosti(_ucitaj("Grupe"),
                                             _ucitaj(naziv_taba_rasporeda_mature(SEZONA)),
                                             razdoblja, praznici, _ucitaj(NAJAM_TAB))
               if not (b["izvor"] == "NAJAM" and b["id"] == bez_najma)]
    slobodne = []
    for oznaka, _naziv, _kap in UCIONICE_CENTRA:
        dan = DANI_U_TJEDNU[datum.weekday()]
        kandidat = blok_iz_unosa_grupe("", dan, vrijeme, opcija_ucionice_upisi(oznaka),
                                       "NAJAM", "", datum, 1, praznici)
        if not provjeri_grupu_upisa(kandidat, blokovi):
            slobodne.append(oznaka)
    return slobodne


def _kartica_najam(sheet, nastavnik):
    """🔑 Moji termini (18.10.2026.) — za suradnike na modelu najma (npr. Slađana). Upisuju SAMO
    svoj termin: datum, vrijeme i slobodnu učionicu. Nema učenika, dodjela, honorara ni financija
    — sustav ne vodi njihove klijente, samo zauzetost prostora i broj odrađenih termina."""
    st.caption("Upišite termin u kojem koristite učionicu. Zauzete učionice se ne mogu odabrati. "
               "Termin se vidi u pregledu zauzetosti i u kalendaru centra, pa vas nitko ne može "
               "prebukirati.")
    danas = sada_zagreb().date()
    with st.container(border=True):
        st.markdown("**➕ Novi termin**")
        n1, n2 = st.columns(2)
        n_datum = n1.date_input("Datum", value=danas, format="DD.MM.YYYY", key="naj_datum")
        n_vrijeme = n2.text_input("Vrijeme (početak-kraj, npr. 17:00-18:30)", key="naj_vrijeme")
        if n_vrijeme and je_ispravno_vrijeme(n_vrijeme):
            slobodne = _slobodne_ucionice(n_datum, n_vrijeme)
            if slobodne:
                n_uc = st.radio("Slobodne učionice", slobodne, horizontal=True, key="naj_uc",
                                format_func=lambda o: naziv_ucionice_centra(o))
                n_nap = st.text_input("Napomena (nije obavezno)", key="naj_nap")
                if st.button("💾 Upiši termin", type="primary", key="naj_upisi"):
                    try:
                        upisi_najam(sheet, nastavnik, n_datum, n_vrijeme,
                                    opcija_ucionice_upisi(n_uc), n_nap)
                        _poruka("success", f"Termin upisan: {n_datum:%d.%m.} {n_vrijeme}, "
                                           f"{naziv_ucionice_centra(n_uc)}.")
                    except ValueError as e:
                        _poruka("warning", str(e))
                    st.cache_data.clear()
                    st.rerun()
            else:
                st.warning("U to vrijeme nema slobodne učionice. Probajte drugo vrijeme ili datum.")
        elif n_vrijeme:
            st.info("Upišite vrijeme s početkom i krajem, npr. **17:00-18:30**.")

    moji = najam_termini(_ucitaj(NAJAM_TAB), nastavnik)
    nadolaze = [n for n in moji if n["datum"] >= danas]
    st.markdown(f"#### 📅 Moji termini koji dolaze ({len(nadolaze)})")
    if not nadolaze:
        st.caption("Nema upisanih termina koji tek dolaze.")
    for n in nadolaze:
        c1, c2 = st.columns([4, 1])
        c1.markdown(f"**{n['datum']:%d.%m.%Y.}** ({DANI_U_TJEDNU[n['datum'].weekday()][:3]}) · "
                    f"{n['vrijeme']} · {naziv_ucionice_centra(n['ucionica'])}"
                    + (f" · _{n['napomena']}_" if n["napomena"] else ""))
        if c2.button("Otkaži", key=f"naj_otkazi_{n['najam_id']}"):
            try:
                otkazi_najam(sheet, n["najam_id"], nastavnik)
                _poruka("success", "Termin je otkazan — učionica je slobodna.")
            except ValueError as e:
                _poruka("warning", str(e))
            st.cache_data.clear()
            st.rerun()

    sazetak = [x for x in najam_sazetak(_ucitaj(NAJAM_TAB), danas.year, danas.month)
               if x["profesor"] == nastavnik]
    if sazetak:
        st.markdown("#### 📊 Ovaj mjesec")
        st.caption(f"Održanih termina: **{sazetak[0]['termina']}** · ukupno **{sazetak[0]['sati']} h**. "
                   "Obračun naknade radi CAKI centar odvojeno.")


def _otkazivanje_termina(sheet, nastavnik, grupa_id, datum, naziv_termina=""):
    """🚫 Otkazivanje jednog datuma grupnog termina — iz portala smije profesor koji ga drži
    (odluka 18.10.2026.). Kvačica odlučuje hoće li se termin nadoknaditi na kraju serije."""
    otkazani = otkazani_po_kljucu(_ucitaj("Otkazani_termini"))
    vec = otkazani.get((str(grupa_id), datum))
    if vec:
        st.info(f"🚫 Taj termin je otkazan"
                + (f" — {vec['razlog']}" if vec["razlog"] else "")
                + (" (nadoknađuje se na kraju)" if vec["nadoknadi"] else " (bez nadoknade)")
                + (f" · otkazao: {vec['otkazao']}" if vec["otkazao"] else ""))
        return True
    with st.expander("🚫 Otkaži ovaj termin"):
        st.caption("Otkazani termin izlazi iz kalendara i učionica se oslobodi. Admin to vidi.")
        razlog = st.text_input("Razlog (vidi ga admin)", key=f"otk_razlog_{grupa_id}_{datum}")
        nadoknadi = st.checkbox("Nadoknadi na kraju (serija se produži za tjedan)", value=True,
                                key=f"otk_nad_{grupa_id}_{datum}")
        if st.button("🚫 Otkaži termin", key=f"otk_gumb_{grupa_id}_{datum}"):
            try:
                otkazi_termin(sheet, grupa_id, datum, razlog, nadoknadi, nastavnik)
                _poruka("success", f"Termin {datum:%d.%m.} je otkazan"
                                   + (" (nadoknada na kraju)." if nadoknadi else "."))
            except ValueError as e:
                _poruka("warning", str(e))
            st.cache_data.clear()
            st.rerun()
    return False


def _kartica_zauzetost():
    """Tjedni pregled zauzetosti učionica — samo "ZAUZETO", bez detalja (2.10.2026.)."""
    st.caption("Kad su učionice zauzete grupama (Matura, Upisi). **Grupe imaju prednost** — instrukcije u "
               "centru ne dogovarajte u tim terminima.")
    dan = st.date_input("Tjedan (odaberite bilo koji dan)", value=sada_zagreb().date(), format="DD.MM.YYYY",
                        key="zau_tjedan")
    pon = ponedjeljak_tjedna(dan)
    st.caption(f"Tjedan {pon:%d.%m.} – {pon + timedelta(days=6):%d.%m.%Y.}")
    razdoblja, praznici = _razdoblja_i_praznici()
    blokovi = blokovi_zauzetosti(_ucitaj("Grupe"), _ucitaj(naziv_taba_rasporeda_mature(SEZONA)),
                                 razdoblja, praznici, _ucitaj(NAJAM_TAB))
    st.markdown(html_tjedne_mreze(blokovi, pon, javno=True, praznici=praznici), unsafe_allow_html=True)


# 17.10.2026.: kalendari koje portal može prikazati. DODAVANJE NOVOG = jedan red ovdje.
# ID kalendara se nađe u Google kalendaru: Postavke (⚙) → odaberi kalendar u lijevom stupcu →
# odjeljak "Integriraj kalendar" → polje "ID kalendara". Prvi u popisu je zadani prikaz.
KALENDARI_PORTALA = [
    ("🏫 Administracija CAKI centar", "c_classroom6d7434b5@group.calendar.google.com"),
]
KALENDAR_PRAZNICI_ID = "hr.croatian.official#holiday@group.v.calendar.google.com"


def _kalendar_url(kalendar_id: str, nacin: str = "WEEK") -> str:
    """Ugradni (embed) URL jednog kalendara + hrvatski praznici kao sloj preko njega.

    ⚠️ 20.10.2026. — ISPRAVAK Googleove greške „400. To je pogreška.”: `embed?src=` prima OBIČAN
    ID kalendara, samo percent-kodiran (`@` → %40, `#` → %23). Base64 (koji je ovdje bio) koristi
    se isključivo u starom obliku `calendar/render?cid=…`; u `src=` ga Google odbija s 400.
    Zato: urllib.parse.quote sa safe="" (bez toga `#` u ID-u praznika reže URL)."""
    def q(x):
        return urllib.parse.quote(x, safe="")
    return ("https://calendar.google.com/calendar/embed?height=650&wkst=2"
            f"&ctz=Europe%2FZagreb&mode={nacin}"
            f"&src={q(kalendar_id)}&color=%23009688"
            f"&src={q(KALENDAR_PRAZNICI_ID)}")


def _kartica_kalendar():
    """17.10.2026.: prikaz Google kalendara centra u portalu — SAMO ZA GLEDANJE.
    Uređivanje ide u samom Google kalendaru. Raspored i zauzetost učionica se NE vode odavde
    nego iz CRM-a — kalendar je pregled, a mjerodavna je kartica 🏫 Zauzetost učionica.

    VAŽNO o pristupu: ugradnja (iframe) prikazuje kalendar samo ako je kalendar javno dijeljen
    ILI ako je profesor u tom istom pregledniku prijavljen na Google račun koji ima pristup
    kalendaru. Administracijski kalendar nije javan, pa profesor koji nije prijavljen vidi
    Googleovu poruku o pristupu — zato je ispod i gumb za otvaranje u Google kalendaru."""
    st.caption("Kalendar **Administracija CAKI centar** — raspored slobodnih učionica i "
               "organizacija nastave. Ovdje je **samo za gledanje**; za uređivanje otvorite "
               "kalendar u Googleu. Mjerodavna zauzetost grupa je u kartici 🏫 Zauzetost učionica.")
    # Samo jedan kalendar (odluka 17.10.2026.: "Administracija CAKI centar" je uvijek najaktualniji),
    # pa se birač ne prikazuje. Doda li se drugi red u KALENDARI_PORTALA, birač se pojavi sam.
    if len(KALENDARI_PORTALA) > 1:
        kalendar_id = dict(KALENDARI_PORTALA)[st.selectbox(
            "Kalendar", [n for n, _i in KALENDARI_PORTALA], key="kal_koji")]
    else:
        kalendar_id = KALENDARI_PORTALA[0][1]
    nacin = st.radio("Prikaz", ["WEEK", "AGENDA", "MONTH"], horizontal=True, key="kal_nacin",
                     format_func={"WEEK": "Tjedan", "AGENDA": "Popis", "MONTH": "Mjesec"}.get)
    # st.components.v1.iframe je najavljen za uklanjanje poslije 1.6.2026.; st.iframe je novi
    # naziv. Podržavamo oba da kartica ne pukne ni na staroj ni na novoj verziji Streamlita.
    url_kal = _kalendar_url(kalendar_id, nacin)
    try:
        st.iframe(url_kal, height=650)
    except AttributeError:
        _components.iframe(url_kal, height=650, scrolling=True)
    st.caption("Ako kalendar piše da nemate pristup: prijavite se u ovom pregledniku na Google "
               "račun kojem je kalendar podijeljen, pa osvježite stranicu.")
    st.link_button("↗ Otvori u Google kalendaru", "https://calendar.google.com/calendar/r")


def _siri_stranicu():
    """Širi sadržaj (layout="wide" + manji bočni razmaci) da tablice i popisi stanu pregledno."""
    st.markdown("<style>.block-container{max-width:100%!important;padding-left:2rem!important;"
                "padding-right:2rem!important;padding-top:2rem!important}</style>", unsafe_allow_html=True)


def prikazi_portal_profesora():
    _siri_stranicu()
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
    # 18.10.2026.: suradnik na modelu najma (npr. Slađana) vidi SAMO svoje termine i zauzetost —
    # nema pristup učenicima, dodjelama, instrukcijama ni financijama (Cakijeva odluka).
    if je_najmoprimac(_ucitaj(PROFILI_PROFESORA_TAB), nastavnik):
        k_naj, k_zau_n, k_kal_n = st.tabs(["🔑 Moji termini", "🏫 Zauzetost učionica",
                                           "📅 Kalendar centra"])
        with k_naj:
            _kartica_najam(sheet, nastavnik)
        with k_zau_n:
            _kartica_zauzetost()
        with k_kal_n:
            _kartica_kalendar()
        return

    smije_gotovinu = smije_naplatu_gotovinom(_ucitaj("Nastavnici"), nastavnik)
    n_upita = _broj_neodgovorenih_upita(nastavnik)
    (k_dan, k_upiti, k_dost, k_dol, k_blok, k_mat, k_instr, k_uc, k_izv, k_zau,
     k_kal) = st.tabs([
        "🏠 Danas", f"📥 Novi upiti ({n_upita})" if n_upita else "📥 Novi upiti", "🗓️ Dostupnost",
        "✅ Dolasci — grupe", "🧩 Moji blokovi", "🎓 Matura",
        "📝 Instrukcije", "👩‍🎓 Moji učenici", "📄 Mjesečni izvještaj", "🏫 Zauzetost učionica",
        "📅 Kalendar centra"])
    with k_dan:
        _kartica_danas(nastavnik)
    with k_upiti:
        _kartica_upiti(sheet, nastavnik)
    with k_dost:
        _kartica_dostupnost(sheet, nastavnik)
    with k_dol:
        _kartica_dolasci(sheet, nastavnik)
    with k_blok:
        _kartica_blokovi(sheet, nastavnik)
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
    with k_kal:
        _kartica_kalendar()

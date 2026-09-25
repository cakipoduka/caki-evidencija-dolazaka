"""
CAKI — pages/2_Instrukcije.py
Stranica za instruktore: evidencija odrađenih instrukcija (individualnih/grupnih).
Prijava provjerava ime+lozinku protiv 'Nastavnici' taba u Sheetu (uređuje ga admin
na stranici "👤 Nastavnici" u app_upisi_admin.py — dodavanje/uklanjanje/promjena
lozinke se radi TAMO, ne ovdje i ne u kodu). Login odmah određuje identitet —
instruktor NE bira svoje ime sa liste bez provjere (za razliku od
caki-evidencija-dolazaka.py) i vidi/uređuje ISKLJUČIVO svoje retke.

Postavi u repo 'caki-evidencija-dolazaka', mapa pages/, kao 2_Instrukcije.py.

VIŠE NIJE POTREBAN nikakav poseban unos u Streamlit Secrets za ovu stranicu —
šifre sad žive u Sheetu (tab 'Nastavnici'), koje admin uređuje izravno.
"""
import json
from datetime import date

import streamlit as st

# Streamlit Cloud nakon git pulla zna zadržati STARU verziju pipeline_upisi.py u memoriji
# (→ ImportError "cannot import name"). Ako je datoteka novija od učitanog modula, učitaj je ponovno.
import importlib, os, time  # noqa: E401,E402
import pipeline_upisi as _pipeline  # noqa: E402
if os.path.getmtime(_pipeline.__file__) > getattr(_pipeline, "_ucitano_u", 0):
    importlib.reload(_pipeline)
    _pipeline._ucitano_u = time.time()

from pipeline_upisi import (  # noqa: E402
    INSTRUKCIJE_OBLICI,
    INSTRUKCIJE_PREDMETI,
    INSTRUKCIJE_TRAJANJA,
    STUPNJEVI_SKOLOVANJA_INSTR,
    dodaj_instrukciju_termin,
    get_gspread_client,
    load_instrukcije,
    load_nastavnici,
    load_ucenici,
    nastavnici_aktivni,
    pretrazi_ucenike,
    provjeri_lozinku_instruktora,
)

st.set_page_config(page_title="CAKI — Instrukcije", page_icon="📝", layout="centered")


@st.cache_resource
def init_sheet():
    sa_info = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    gc = get_gspread_client(sa_info)
    return gc.open_by_key(st.secrets["SHEET_ID"])


sheet = init_sheet()


@st.cache_data(ttl=30)
def dohvati_nastavnike():
    try:
        return load_nastavnici(sheet)
    except Exception:
        return None


df_nastavnici = dohvati_nastavnike()


def provjeri_instruktora() -> str | None:
    """Vraća ime prijavljenog instruktora ili None. Provjera ide protiv
    'Nastavnici' taba u Sheetu — login = identitet, ne self-report."""
    if st.session_state.get("instruktor_prijavljen"):
        return st.session_state["instruktor_prijavljen"]

    st.title("📝 CAKI — Evidencija instrukcija")

    if df_nastavnici is None or df_nastavnici.empty:
        st.error("Tab 'Nastavnici' još nije postavljen u Sheetu — javi adminu.")
        st.stop()

    ime_pokusaj = st.selectbox("Tko ste vi?", options=nastavnici_aktivni(df_nastavnici))
    lozinka_pokusaj = st.text_input("Vaša lozinka", type="password", key="instr_loz_unos")

    if st.button("Prijava"):
        if provjeri_lozinku_instruktora(df_nastavnici, ime_pokusaj, lozinka_pokusaj):
            st.session_state["instruktor_prijavljen"] = ime_pokusaj
            st.rerun()
        else:
            st.error("Pogrešna lozinka.")
    return None


nastavnik = provjeri_instruktora()
if not nastavnik:
    st.stop()

st.title("📝 Evidencija instrukcija")
st.caption(f"Prijavljeni ste kao: **{nastavnik}**")

if st.sidebar.button("🚪 Odjava"):
    del st.session_state["instruktor_prijavljen"]
    st.rerun()


@st.cache_data(ttl=15)
def dohvati_sve():
    return load_ucenici(sheet), load_instrukcije(sheet)


df_ucenici, df_instrukcije = dohvati_sve()

st.divider()
st.subheader("Novi termin")

upit = st.text_input("Pretraži učenika (ime ili šifra)")
rezultati = pretrazi_ucenike(df_ucenici, upit) if upit else df_ucenici.tail(0)

if upit and rezultati.empty:
    st.warning("Nema rezultata.")
elif upit:
    opcije = {
        f"{r['ime_djeteta']} ({r['ucenik_id']})": r["ucenik_id"]
        for _, r in rezultati.iterrows()
    }
    odabrana_labela = st.selectbox("Odaberite učenika", options=list(opcije.keys()))
    ucenik_id = opcije[odabrana_labela]
    ime_djeteta = rezultati[rezultati["ucenik_id"] == ucenik_id].iloc[0]["ime_djeteta"]

    with st.form("novi_termin_form"):
        datum = st.date_input("Datum", value=date.today())
        duljina = st.selectbox("Duljina termina (min)", options=INSTRUKCIJE_TRAJANJA, index=1)
        predmet = st.selectbox("Predmet", options=INSTRUKCIJE_PREDMETI)
        stupanj = st.selectbox("Stupanj školovanja", options=STUPNJEVI_SKOLOVANJA_INSTR, index=1)
        oblik = st.radio("Oblik", options=INSTRUKCIJE_OBLICI, horizontal=True)
        # Unutar st.form polja se ne pojavljuju/skrivaju dok se forma ne pošalje, pa je
        # broj učenika uvijek vidljiv (koristi se samo ako je odabrano "Grupa").
        broj_u_grupi = st.number_input("Broj učenika u grupi (samo za grupu)", min_value=1, max_value=10, value=1)
        placeno = st.checkbox("Plaćeno (moja napomena — nije službena potvrda)")
        napomena_int = st.text_area("Napomena (interna — vidite samo vi i admin)")
        napomena_jav = st.text_area("Napomena (javna — vidljivo i roditelju)")

        posalji = st.form_submit_button("💾 Spremi termin")
        if posalji:
            dodaj_instrukciju_termin(
                sheet,
                ucenik_id=ucenik_id,
                ime_djeteta=ime_djeteta,
                nastavnik=nastavnik,
                datum=str(datum),
                duljina_min=duljina,
                oblik=oblik,
                broj_ucenika_u_grupi=broj_u_grupi if oblik == "Grupa" else None,
                placeno_oznaka_prof="Da" if placeno else "Ne",
                napomena_interna=napomena_int,
                napomena_javna=napomena_jav,
                predmet=predmet,
                stupanj_skolovanja=stupanj,
                # sifra i cijena se računaju automatski iz Cjenika; nacin_naplate određuje
                # admin (financijska odluka) — novi termin nasljeđuje zadnju vrijednost.
            )
            st.success("Termin spremljen.")
            st.cache_data.clear()
            st.rerun()
else:
    st.info("Upišite ime ili šifru učenika da dodate termin.")

st.divider()
st.subheader("Moji termini")

if df_instrukcije.empty:
    st.info("Još nema evidentiranih termina.")
else:
    # KLJUČNO: filtrirano na prijavljenog instruktora — ne vidi tuđe retke.
    moji = df_instrukcije[df_instrukcije["nastavnik"] == nastavnik].sort_values("datum", ascending=False)
    if moji.empty:
        st.info("Nemate još evidentiranih termina.")
    else:
        stupci = ["datum", "ime_djeteta"] + (["predmet"] if "predmet" in moji.columns else []) + [
            "duljina_min", "oblik",
            "placeno_oznaka_prof", "uplata_potvrdjena_admin", "napomena_interna",
        ]
        prikaz = moji[stupci].rename(columns={
            "duljina_min": "trajanje (min)",
            "placeno_oznaka_prof": "plaćeno (moja oznaka)",
            "uplata_potvrdjena_admin": "uplata potvrđena (admin)",
        })
        st.dataframe(prikaz, width="stretch", hide_index=True)

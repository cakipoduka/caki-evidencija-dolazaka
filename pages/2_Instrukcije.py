"""
CAKI — pages/2_Instrukcije.py
Stranica za instruktore: evidencija odrađenih instrukcija (individualnih/grupnih).
Zasebna, OSOBNA lozinka po instruktoru (ne dijeljena kao ulazna lozinka appa) —
login odmah određuje identitet, instruktor NE bira svoje ime iz padajućeg popisa
(za razliku od caki-evidencija-dolazaka.py) i vidi/uređuje ISKLJUČIVO svoje retke.

Postavi u repo 'caki-evidencija-dolazaka', mapa pages/, kao 2_Instrukcije.py
(brojčani prefiks određuje redoslijed u sidebaru — vidi CAKI_MASTER_BAZA §22).

Sekret koji treba dodati (Streamlit Cloud → Settings → Secrets), NOVI odjeljak:

[INSTRUKCIJE_LOZINKE]
Slađana = "..."
Mirela = "..."
Ivica = "..."
Martina = "..."
Neira = "..."

(Caki/admin ne treba ovdje — admin uređuje sve preko app_upisi_admin.py.)
"""
import json
from datetime import date

import streamlit as st

from pipeline_upisi import (
    INSTRUKCIJE_OBLICI,
    INSTRUKCIJE_TRAJANJA,
    dodaj_instrukciju_termin,
    get_gspread_client,
    load_instrukcije,
    load_ucenici,
    pretrazi_ucenike,
)

st.set_page_config(page_title="CAKI — Instrukcije", page_icon="📝", layout="centered")


def provjeri_instruktora() -> str | None:
    """Vraća ime prijavljenog instruktora ili None. Za razliku od dijeljene
    lozinke appa, ovdje svatko ima SVOJU — login = identitet, ne self-report."""
    if st.session_state.get("instruktor_prijavljen"):
        return st.session_state["instruktor_prijavljen"]

    st.title("📝 CAKI — Evidencija instrukcija")
    ime_pokusaj = st.text_input("Ime (kako je zapisano u sustavu)", key="instr_ime_unos")
    lozinka_pokusaj = st.text_input("Vaša lozinka", type="password", key="instr_loz_unos")

    if st.button("Prijava"):
        lozinke = st.secrets.get("INSTRUKCIJE_LOZINKE", {})
        if ime_pokusaj in lozinke and lozinka_pokusaj == lozinke[ime_pokusaj]:
            st.session_state["instruktor_prijavljen"] = ime_pokusaj
            st.rerun()
        else:
            st.error("Pogrešno ime ili lozinka.")
    return None


nastavnik = provjeri_instruktora()
if not nastavnik:
    st.stop()

st.title("📝 Evidencija instrukcija")
st.caption(f"Prijavljeni ste kao: **{nastavnik}**")

if st.sidebar.button("🚪 Odjava"):
    del st.session_state["instruktor_prijavljen"]
    st.rerun()


@st.cache_resource
def init_sheet():
    sa_info = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    gc = get_gspread_client(sa_info)
    return gc.open_by_key(st.secrets["SHEET_ID"])


sheet = init_sheet()


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
        oblik = st.radio("Oblik", options=INSTRUKCIJE_OBLICI, horizontal=True)
        broj_u_grupi = None
        if oblik == "Grupa":
            broj_u_grupi = st.number_input("Broj učenika u grupi", min_value=2, max_value=10, value=2)
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
                broj_ucenika_u_grupi=broj_u_grupi,
                placeno_oznaka_prof="Da" if placeno else "Ne",
                napomena_interna=napomena_int,
                napomena_javna=napomena_jav,
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
        prikaz = moji[[
            "datum", "ime_djeteta", "duljina_min", "oblik",
            "placeno_oznaka_prof", "uplata_potvrdjena_admin", "napomena_interna",
        ]].rename(columns={
            "duljina_min": "trajanje (min)",
            "placeno_oznaka_prof": "plaćeno (moja oznaka)",
            "uplata_potvrdjena_admin": "uplata potvrđena (admin)",
        })
        st.dataframe(prikaz, use_container_width=True, hide_index=True)

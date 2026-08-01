"""
CAKI Upisi u SŠ — app_dolasci.py
App za nastavnike: evidencija dolazaka. Zajednička lozinka (kao admin panel),
nastavnik bira svoje ime, sustav prepoznaje grupe za odabrani dan, brzi tap
unos prisutnosti (1=prisutan/0=odsutan/2=online), dodavanje gosta iz druge
grupe, i "Danas predaje" polje koje automatski hrani Zamjene log.
"""
import json
from datetime import date

import streamlit as st

from pipeline_upisi import (
    DANI_U_TJEDNU,
    NASTAVNICI,
    get_gspread_client,
    load_grupe,
    load_rezervacije,
    load_ucenici,
    roster_grupe,
    spremi_cijeli_termin,
)

st.set_page_config(page_title="CAKI — Dolasci", page_icon="✅", layout="centered")


def provjeri_lozinku() -> bool:
    def na_unos():
        if st.session_state.get("lozinka_unos") == st.secrets.get("APP_PASSWORD"):
            st.session_state["autoriziran"] = True
        else:
            st.session_state["autoriziran"] = False

    if st.session_state.get("autoriziran"):
        return True

    st.title("✅ CAKI — Evidencija dolazaka")
    st.text_input("Lozinka", type="password", key="lozinka_unos", on_change=na_unos)
    if st.session_state.get("autoriziran") is False:
        st.error("Pogrešna lozinka.")
    return False


if not provjeri_lozinku():
    st.stop()


@st.cache_resource
def init_sheet():
    sa_info = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    gc = get_gspread_client(sa_info)
    return gc.open_by_key(st.secrets["SHEET_ID"])


sheet = init_sheet()

st.title("✅ Evidencija dolazaka")

nastavnik = st.selectbox("Tko ste vi?", options=NASTAVNICI)
odabrani_datum = st.date_input("Datum termina", value=date.today())
dan_naziv = DANI_U_TJEDNU[odabrani_datum.weekday()]
st.caption(f"Dan: {dan_naziv}")


@st.cache_data(ttl=15)
def dohvati_sve():
    return load_grupe(sheet), load_rezervacije(sheet), load_ucenici(sheet)


df_grupe, df_rezervacije, df_ucenici = dohvati_sve()

grupe_danas = df_grupe[
    (df_grupe["dan"] == dan_naziv) & (df_grupe["aktivna"].astype(str).str.lower() == "da")
]

if grupe_danas.empty:
    st.info(f"Nema aktivnih termina za {dan_naziv}.")
    st.stop()

opcije_grupa = {
    f"{g['program']} — {g['vrijeme']} ({g['ucionica']})": g["grupa_id"]
    for _, g in grupe_danas.iterrows()
}
odabrana_labela = st.selectbox("Koja grupa?", options=list(opcije_grupa.keys()))
grupa_id = opcije_grupa[odabrana_labela]
grupa_red = grupe_danas[grupe_danas["grupa_id"] == grupa_id].iloc[0]

redovni = grupa_red.get("redovni_nastavnik", "") or nastavnik
danas_predaje = st.text_input("Danas predaje", value=redovni if redovni else nastavnik)
if danas_predaje != redovni:
    st.warning(f"⚠ Zamjena — redovni nastavnik je {redovni or 'nepoznat'}. Ovo se automatski bilježi u Zamjene log.")

st.divider()

roster = roster_grupe(df_rezervacije, grupa_id)

if roster.empty:
    st.info("Nema potvrđenih učenika u ovoj grupi (nitko još nije platio/potvrđen).")
else:
    st.markdown(f"### Popis učenika ({len(roster)})")
    if "dolasci_status" not in st.session_state:
        st.session_state["dolasci_status"] = {}

    for _, r in roster.iterrows():
        uid = r["ucenik_id"]
        kljuc = f"status_{grupa_id}_{uid}_{odabrani_datum}"
        if kljuc not in st.session_state:
            st.session_state[kljuc] = "1"

        col1, col2 = st.columns([2, 3])
        col1.write(r["ime_djeteta"])
        st.session_state[kljuc] = col2.radio(
            "status", options=["1", "0", "2"],
            format_func=lambda v: {"1": "✅ Prisutan", "0": "❌ Odsutan", "2": "💻 Online"}[v],
            key=f"radio_{kljuc}", horizontal=True, label_visibility="collapsed",
            index=["1", "0", "2"].index(st.session_state[kljuc]),
        )

    st.divider()

    # --- Dodaj gosta iz druge grupe (staging - upisuje se tek na Spremi) ---
    kljuc_gostiju = f"gosti_{grupa_id}_{odabrani_datum}"
    if kljuc_gostiju not in st.session_state:
        st.session_state[kljuc_gostiju] = {}  # {ucenik_id: {"ime": ..., "status": "1", "maticna": ...}}

    with st.expander("➕ Dodaj gosta (učenik iz druge grupe)"):
        upit = st.text_input("Pretraži po imenu")
        if upit:
            vec_na_rosteru = set(roster["ucenik_id"].tolist())
            vec_dodan_gost = set(st.session_state[kljuc_gostiju].keys())
            rezultati = df_ucenici[
                df_ucenici["ime_djeteta"].str.contains(upit, case=False, na=False)
                & ~df_ucenici["ucenik_id"].isin(vec_na_rosteru | vec_dodan_gost)
            ]
            for _, u in rezultati.head(10).iterrows():
                if st.button(f"Dodaj: {u['ime_djeteta']} ({u['ucenik_id']})", key=f"gost_{u['ucenik_id']}"):
                    njegova = df_rezervacije[
                        (df_rezervacije["ucenik_id"] == u["ucenik_id"]) & (df_rezervacije["status"] == "Potvrđeno")
                    ]
                    maticna = njegova.iloc[0]["grupa_id"] if not njegova.empty else "Nepoznato"
                    st.session_state[kljuc_gostiju][u["ucenik_id"]] = {
                        "ime": u["ime_djeteta"], "status": "1", "maticna": maticna
                    }
                    st.rerun()

    if st.session_state[kljuc_gostiju]:
        st.markdown("### Gosti danas")
        for uid, podaci in list(st.session_state[kljuc_gostiju].items()):
            gc1, gc2, gc3 = st.columns([2, 2, 1])
            gc1.write(f"{podaci['ime']} 🔄")
            podaci["status"] = gc2.radio(
                "status_gost", options=["1", "2"],
                format_func=lambda v: {"1": "✅ Prisutan", "2": "💻 Online"}[v],
                key=f"radio_gost_{uid}_{odabrani_datum}", horizontal=True, label_visibility="collapsed",
                index=["1", "2"].index(podaci["status"]),
            )
            if gc3.button("🗑️ Očisti", key=f"clear_gost_{uid}_{odabrani_datum}"):
                del st.session_state[kljuc_gostiju][uid]
                st.rerun()

    st.divider()

    if st.button("💾 Spremi dolazak", type="primary"):
        roster_zapisi = []
        for _, r in roster.iterrows():
            uid = r["ucenik_id"]
            kljuc = f"status_{grupa_id}_{uid}_{odabrani_datum}"
            roster_zapisi.append({
                "ucenik_id": uid, "ime_djeteta": r["ime_djeteta"],
                "status": st.session_state.get(kljuc, "1"),
            })

        gosti_zapisi = [
            {"ucenik_id": uid, "ime_djeteta": p["ime"], "status": p["status"], "maticna_grupa": p["maticna"]}
            for uid, p in st.session_state[kljuc_gostiju].items()
        ]

        spremi_cijeli_termin(sheet, grupa_id, str(odabrani_datum), danas_predaje, redovni, roster_zapisi, gosti_zapisi)

        st.session_state["zadnje_spremljeno"] = True
        st.cache_data.clear()
        st.rerun()

    if st.session_state.get("zadnje_spremljeno"):
        st.success("Dolazak spremljen! Popis ostaje otvoren — možete nastaviti dodavati zakašnjele učenike.")

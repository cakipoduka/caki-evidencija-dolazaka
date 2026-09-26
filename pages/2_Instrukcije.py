"""
CAKI — pages/2_Instrukcije.py — stari link; prikazuje ISTI portal za profesore kao glavna stranica.

26.9.2026.: evidencija dolazaka i evidencija instrukcija spojene u JEDAN portal s jednom
prijavom (osobna lozinka iz taba Nastavnici) — v. profesor_ui.py.
Stari link na stranicu Instrukcije i dalje radi (pages/2_Instrukcije.py prikazuje isto).
"""
import streamlit as st

# Streamlit Cloud nakon git pulla zna zadržati STARU verziju modula u memoriji
# (→ ImportError "cannot import name"). Ako je datoteka novija od učitanog modula, učitaj je ponovno.
import importlib, os, time  # noqa: E401,E402
import pipeline_upisi as _pipeline  # noqa: E402
if os.path.getmtime(_pipeline.__file__) > getattr(_pipeline, "_ucitano_u", 0):
    importlib.reload(_pipeline)
    _pipeline._ucitano_u = time.time()
import profesor_ui as _portal  # noqa: E402
if os.path.getmtime(_portal.__file__) > getattr(_portal, "_ucitano_u", 0) or \
        getattr(_portal, "_pipeline_u", 0) != getattr(_pipeline, "_ucitano_u", 0):
    importlib.reload(_portal)
    _portal._ucitano_u = time.time()
    _portal._pipeline_u = getattr(_pipeline, "_ucitano_u", 0)

st.set_page_config(page_title="CAKI — profesori", page_icon="🎓", layout="centered")
_portal.prikazi_portal_profesora()

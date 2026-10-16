"""
CAKI — pages/2_Instrukcije.py — stari link; prikazuje ISTI portal za profesore kao glavna stranica.

26.9.2026.: evidencija dolazaka i evidencija instrukcija spojene u JEDAN portal s jednom
prijavom (osobna lozinka iz taba Nastavnici) — v. profesor_ui.py.
Stari link na stranicu Instrukcije i dalje radi (pages/2_Instrukcije.py prikazuje isto).

15.10.2026. (nalaz 16): uklonjena je zaobilaznica koja je rucno ponovno ucitavala module.
Postojala je jer je Streamlit Cloud nakon git pulla znao zadrzati staru verziju modula u
memoriji (ImportError "cannot import name"). Radni postupak ionako ukljucuje rucni
"Reboot app" nakon svakog Pusha, a reboot podize novi proces i ucitava svjeze module --
pa zaobilaznica nema sto rijesiti. Ako se ImportError ipak vrati, vrati staru verziju
iz gita (Discard / revert) i javi: znacilo bi da reboot ne radi ono sto mislimo.
"""
import streamlit as st

import profesor_ui as _portal

st.set_page_config(page_title="CAKI — profesori", page_icon="🎓", layout="wide")
_portal.prikazi_portal_profesora()

"""
CAKI — uputa_u_aplikaciji.py  (21.10.2026.)
KRATKE UPUTE UNUTAR APLIKACIJE — profesor ne izlazi iz portala da bi pročitao kako nešto radi.

Cakijev zahtjev: upute ne smiju biti zasebna stranica ni drugi prozor (profesor bi se morao odjaviti,
otvoriti nešto drugo i vratiti se). Zato je uputa **sklopivi blok (expander) na vrhu kartice** koju
profesor upravo gleda — otvori se jednim klikom, zatvori drugim, i ne smeta.

Kako se koristi: na početku funkcije kartice `_uputa.prikazi(st, "instrukcije")`.
Tekstovi su namjerno kratki (5–8 koraka). Detalji su u `upute/UPDATE_*.md` i `upute/UPDATE_21-10y_*`.

Ovaj modul NE uvozi ništa osim Streamlita — ne dira Sheet, ne troši kvotu.
"""
import streamlit as st

UPUTE = {
    "danas": {
        "naslov": "Kako čitati 🏠 Danas",
        "koraci": [
            "**Brojevi gore** su ono što traži tvoju pažnju danas: grupni sati, instrukcije, sati koji "
            "čekaju upis i koliko ih još stigneš upisati.",
            "**⏳ Čeka upis** = sat je bio, a nije zabilježen. Upisati se može **14 dana** unatrag; "
            "poslije toga upisuje admin (🚨 znači da je rok pri kraju).",
            "**📝 Instrukcije bez konačnog statusa** = datum je prošao, a termin je još „Zakazan”. "
            "Označi Održan / Otkazan u kartici 📝 Instrukcije.",
            "**✍️ Osvrt roditelju čeka …** = učenici kojima je vrijeme za kratki osvrt (jednom u "
            "4 tjedna). Otvori 👩‍🎓 Moji učenici → ✍️ Napiši roditelju.",
            "**📄 Mjesečni izvještaj** šalješ nakon završetka mjeseca — status piše na dnu.",
        ],
        "pazi": [
            "Ovo je samo pregled — ništa se ovdje ne mijenja i ne upisuje.",
            "Ako ti nešto ne odgovara stvarnom stanju, prvo klikni **🔄 Osvježi** gore desno.",
        ],
        "dalje": "Iduće kartice: 📝 Instrukcije (upis sata) · 👩‍🎓 Moji učenici (osvrt roditelju) · 📄 Izvještaj.",
    },

    "instrukcije": {
        "naslov": "Kako upisati sat (📝 Instrukcije)",
        "koraci": [
            "U izborniku **Učenik** odaberi učenika — obrazac se otvara tek nakon odabira.",
            "**Datum / Vrijeme / Trajanje**: vrijeme biraš iz popisa (svakih 15 min), ne upisuješ.",
            "**Oblik**: Individualno / Grupa / Online. Ako je Grupa, upiši koliko ih je.",
            "**Plaćanje je obavezno** — 💵 Gotovina (platio ti na satu) ili ❌ Nije plaćeno (ide na obračun). "
            "Bez toga se sat ne sprema.",
            "**📚 Teme / ocjena sata / zadaća** — tema iz popisa (ili ručno), ocjena ➕/➖ je **samo "
            "tvoja i adminova** (roditelj je ne vidi), zadaća ulazi u praćenje „2× zaredom”.",
            "**💾 Spremi termin.** Ispravak je moguć **24 h** nakon upisa (✏️ Ispravak ispod tablice).",
        ],
        "pazi": [
            "**📒 Bilješka sa sata** (javna) vidi roditelj — u njoj nema internih opaski; za to je "
            "**Napomena interna**.",
            "Budući termin može biti samo **📅 Zakazan**; „Održan” se bira na dan sata ili poslije.",
            "Naplatu gotovinom smiješ evidentirati samo ako ti je admin dao ovlaštenje.",
        ],
        "dalje": "Nakon svakog sata upiši barem temu i zadaću — iz toga se poslije sastavlja osvrt roditelju.",
    },

    "moji_ucenici": {
        "naslov": "Kako radi 👩‍🎓 Moji učenici (i ✍️ osvrt roditelju)",
        "koraci": [
            "Ovdje su **samo učenici koje ti je admin dodijelio**. Kontakt vidiš samo ako je dopušten.",
            "**📚 Povijest sati** pokazuje sve sate tog učenika (i kod kolega, bez imena i bez plaćanja).",
            "**✍️ Napiši roditelju** — odabereš razdoblje (zadano: od zadnje poruke), sustav pokaže "
            "brojke, ti označiš 3–5 rečenica i dopišeš cilj.",
            "**🧩 Sastavi poruku** složi tekst iz tvojih odabira. **Možeš ga slobodno urediti.**",
            "**🤖 Sastavi ljepše**, ako je uključeno, prepiše iste podatke ljepšim stilom. Ime djeteta se "
            "nikad ne šalje izvan aplikacije. Uvijek pregledaj prije slanja — tekst je tvoj.",
            "**📤 Pošalji roditelju** — poruka ide u Moj CAKI → 📈 Napredak. Ne šalje se mailom ni "
            "WhatsAppom i **nikad ne odlazi sama**.",
        ],
        "pazi": [
            "Poruka o jednom djetetu **ne smije sadržavati ime drugog** — sustav to blokira.",
            "Ocjena sata (➕/➖) i interna napomena se u poruci **nikad** ne koriste.",
            "Ritam: jedan osvrt po učeniku **svakih 4 tjedna** — dovoljno je, više postaje šum.",
        ],
        "dalje": "Podsjetnik „koga čeka osvrt” stoji na 🏠 Danas.",
    },

    "dolasci": {
        "naslov": "Kako zabilježiti dolaske na grupi (✅ Dolasci — grupe)",
        "koraci": [
            "Odaberi **svoju grupu** i datum sata.",
            "Označi prisutne (i, ako je bilo, gosta iz druge grupe — „➕ Dodaj gosta”).",
            "**💾 Spremi** — jedan upis po terminu, ne po učeniku.",
            "Ako si držao sat umjesto kolege, to je **zamjena** — bira se posebno i vidi se u logu.",
        ],
        "pazi": [
            "Upis je moguć **14 dana** unatrag; starije upisuje admin.",
            "Vidiš samo svoje grupe; tuđe samo kroz „Držim sat umjesto kolege”.",
        ],
    },

    "matura": {
        "naslov": "Kako zabilježiti dolaske na Maturi (🎓 Matura)",
        "koraci": [
            "Kante (dan × termin × učionica) slaže admin u CRM-u; ti vidiš **svoje predmete**.",
            "Odaberi kantu i datum, označi prisutne, spremi.",
            "Zamjena za kolegu je posebna opcija (bilježi se).",
        ],
        "pazi": ["Rok za upis je **14 dana** unatrag.", "Ako kante nema na popisu, admin je još nije složio."],
    },

    "upiti": {
        "naslov": "Kako odgovoriti na 📥 Novi upiti",
        "koraci": [
            "Vidiš **predmet, razred/školu i program**, ali **ne ime ni kontakt** — dok ti admin ne "
            "dodijeli učenika.",
            "**🙋 Preuzimam** = zainteresiran si i imaš termin. Možeš dopisati kad ti odgovara.",
            "**🚫 Ne mogu** = javljaš da ne možeš. Odluku donosi admin.",
            "Više kolega može preuzeti isti upit — admin bira.",
        ],
        "pazi": [
            "**Do dodjele ne kontaktiraj obitelj** — kontakt dobivaš tek kroz dodjelu.",
            "„Samo upiti za moje predmete” filtrira popis.",
        ],
    },

    "dostupnost": {
        "naslov": "Kako unijeti 🗓️ Dostupnost",
        "koraci": [
            "Označi dane i vremenske okvire kad možeš preuzeti **nove** učenike (do 2 okvira dnevno).",
            "Odaberi oblik (Uživo / Online / Oboje).",
            "Ako ne primaš nove učenike, uključi pauzu.",
        ],
        "pazi": [
            "Dostupnost ne mijenja postojeće termine — samo govori adminu kome može dodijeliti novoga.",
            "Zastarjela dostupnost ti se javi na 🏠 Danas.",
        ],
    },

    "izvjestaj": {
        "naslov": "Kako poslati 📄 Mjesečni izvještaj",
        "koraci": [
            "Odaberi mjesec (zadano: prošli — izvještaj se šalje nakon završetka mjeseca).",
            "Provjeri brojke: instrukcije, grupni termini, sati; honorar ako je postavljen.",
            "**📤 Pošalji adminu na provjeru.**",
        ],
        "pazi": [
            "Konačan iznos honorara potvrđuje admin.",
            "Ako je izvještaj vraćen na ispravak, razlog piše iznad gumba.",
        ],
    },
}


def prikazi(st, kljuc: str) -> None:
    """Sklopivi blok s uputom za funkciju koju profesor upravo gleda. Nepoznat ključ = ništa."""
    u = UPUTE.get(str(kljuc or ""))
    if not u:
        return
    with st.expander(f"ℹ️ {u['naslov']}", expanded=False):
        for i, korak in enumerate(u.get("koraci", []), start=1):
            st.markdown(f"**{i}.** {korak}")
        if u.get("pazi"):
            st.markdown("**⚠️ Pazi:**")
            for p in u["pazi"]:
                st.markdown(f"- {p}")
        if u.get("dalje"):
            st.caption(f"➡️ {u['dalje']}")

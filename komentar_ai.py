"""
CAKI — komentar_ai.py  (21.10.2026.)
🤖 „Sastavi ljepše" za ✍️ osvrt profesora roditelju — AI UGLANČAVA tekst, ne odlučuje o njemu.

Kako se uklapa (Cakijeva odluka 21.10.2026., v. `upute/PREDLOG_21-10_napredak_bloom_ai.md`):
  1. PODACI   — `komentar_napretka.kartica_ucenika()` (sati, zadaća, testovi). Bez AI-a.
  2. FRAZE    — profesor označi rečenice; `komentar_napretka.sastavi_tekst()` složi tekst. Bez AI-a.
  3. AI       — ovaj modul: uzme ISTE podatke + profesorove rečenice i napiše ih ljepše. Opcionalno.

Tvrda pravila (ne mijenjati bez Cakija):
  - **Ime djeteta NIKAD ne ide modelu.** Model piše s poljem `{ime}` (samo u nominativu — v. dolje),
    a ime se ubacuje LOKALNO, nakon odgovora. Model dobiva rod (M/Ž), jer bez toga hrvatski tekst
    nije točan, ali ništa drugo što dijete identificira (prezime, šifra, OIB, kontakt, škola).
  - **Interna napomena i ocjena sata (➕/➖) se ne šalju** — roditelj ih ionako ne vidi.
  - **Brojke se ne smiju izmišljati**: u uputi je izričito da smije koristiti samo brojeve iz ulaza.
    Nakon odgovora `komentar_napretka.provjeri_tekst()` traži ime drugog učenika, etikete i obećanja.
  - **Ništa se ne šalje samo** — odgovor ide u tekstualno polje koje profesor pregleda i potpiše.
  - Ako `ANTHROPIC_API_KEY` nije u Secrets, gumb se ne prikazuje i cijela stvar radi bez AI-a.

Zašto Claude, a ne DeepSeek: model dobiva podatke o maloljetnima, pa ostajemo na pružatelju s DPA-om
i obradom u EU. DeepSeek ostaje za interne zadatke bez podataka o djeci (v. `ai_asistent.py`).

Ovaj modul je NAMJERNO samo u `caki-evidencija-dolazaka`: tamo profesor piše osvrt. Čiste funkcije
(bez Streamlita) pokriva `testovi/test_komentar_ai.py`; mrežni poziv se prima kao funkcija.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

MODEL = "claude-sonnet-5"          # isti naziv kao u ai_asistent.py / baza_zadataka_pipeline.py
KLJUC_SECRETS = "ANTHROPIC_API_KEY"
MAX_TOKENA = 900
KONTEKST_DATOTEKA = Path(__file__).with_name("ai_kontekst_komentar.md")

# Prijedlozi nakon kojih ime MORA biti u kosom padežu — model to ne smije napisati s `{ime}`.
# Provjera je prije zamjene imena, na sirovom odgovoru modela.
_PRIJEDLOZI = ("s", "sa", "kod", "od", "do", "za", "iz", "na", "po", "prema", "uz", "bez",
               "pred", "nad", "pod", "među", "pri", "k", "ka", "u", "zbog", "osim", "umjesto",
               "između", "iznad", "ispod", "kroz", "protiv", "preko", "oko", "radi", "tijekom",
               "nakon", "poslije", "prije")
_RE_PADEZ = re.compile(r"\b(" + "|".join(_PRIJEDLOZI) + r")\s+\{ime\}", re.IGNORECASE)

ZADATAK = """ZADATAK: Napiši kratak osvrt o napretku učenika za njegove roditelje.

PRAVILA (obavezna):
1. Piši hrvatskim standardnim jezikom, 2. lice množine prema roditelju („Poštovani”, „Vaše dijete”).
2. Dijete NIKAD ne imenuj. Umjesto imena stavi točno polje `{ime}` i to **samo u nominativu**
   (kao subjekt rečenice): „{ime} je napredovao…”, „Vidi se da {ime} prati…”. NIKAD: „s {ime}”,
   „kod {ime}”, „za {ime}”, „prema {ime}”, „od {ime}” — sklanjanje imena ne postoji, ime se ubacuje
   doslovno i takva rečenica bi bila nepismena.
3. Rod uskladi s poljem `rod` („M” = napisao/sam, „Ž” = napisala/sama).
4. Koristi ISKLJUČIVO brojke i činjenice iz ulaza. Ne izmišljaj postotke, datume ni događaje.
5. Nikad ne etiketiraj dijete („lijen”, „nesposoban”, „beznadan”) — opisuj ponašanje.
6. Nikad ne obećavaj ishod („sigurno će položiti”, „jamčim”).
7. Nikad ne uspoređuj s drugim učenicima i ne spominji drugo dijete.
8. Nikad ne dijagnosticiraj (ADHD, disleksija, terapeut) — to nije posao profesora.
9. Struktura: 1) uvodna rečenica, 2) što je dobro (s brojkom), 3) gdje je zapelo, 4) što radimo
   dalje / što pomaže kod kuće, 5) kratki završetak s kad se javljamo ponovno.
10. Drži se zadane `duljina`: „kratko” = 3–5 rečenica, „srednje” = 2 kraća odlomka (do 900 znakova),
    „detaljno” = do 1.200 znakova. Bez popisa i bez naslova — samo tekst poruke.
11. Rečenice koje je profesor označio (`profesor_je_odabrao`) su njegov odabir sadržaja: prenesi ih
    smislom, ne moraš ih prepisati doslovno, ali **ne dodaj tvrdnje kojih u njima i u podacima nema**.
12. Ako profesor nešto napiše svojim riječima (`profesor_je_napisao`), to je najvažnije — uvaži to.
13. Vrati SAMO tekst poruke, bez uvoda tipa „Evo osvrta” i bez objašnjenja."""


# ------------------------------------------------------------------------------------ pomoćno

def _t(v) -> str:
    return "" if v is None else str(v).strip()


def ucitaj_kontekst() -> str:
    """Cakijev stilski vodič (`ai_kontekst_komentar.md`) — uređuje ga on, čita se pri svakom pozivu."""
    try:
        return KONTEKST_DATOTEKA.read_text(encoding="utf-8")
    except OSError:
        return ""


def sastavi_system(kontekst: str | None = None) -> str:
    kontekst = ucitaj_kontekst() if kontekst is None else kontekst
    return (kontekst.strip() + "\n\n" if kontekst.strip() else "") + ZADATAK


def ima_kljuc(st) -> bool:
    """Je li ključ postavljen u Secrets. Bez ključa se AI gumb ne prikazuje."""
    try:
        return bool(_t(st.secrets.get(KLJUC_SECRETS, "")))
    except Exception:  # noqa: BLE001 — nema secrets.toml (lokalno)
        return False


def sastavi_payload(kartica: dict, ime_ucenika: str = "", rod: str = "", cilj: str = "",
                    fraze=None, ton: str = "Toplo", duljina: str = "srednje") -> dict:
    """Što ide modelu. NAMJERNO bez imena, prezime/šifra/kontakt/škola ne postoje u ulazu.

    `ime_ucenika` se prima samo zato da se zna je li ime poznato (za provjeru padeža) — u payload
    ne ulazi. Vraća dict koji se šalje kao JSON."""
    k = kartica or {}
    sati = k.get("sati") or {}
    zad = k.get("zadaca") or {}
    napredak = k.get("napredak") or {}
    return {
        "rod": "Ž" if _t(rod).upper() == "Ž" else "M",
        "predmet": _t(k.get("predmet")),
        "razdoblje": _t(k.get("razdoblje_tekst")),
        "sati": {"odrzano": sati.get("odrzano", 0), "propusteno": sati.get("propusteno", 0),
                 "ukupno": sati.get("ukupno_sati", 0)},
        "zadaca": {"zadano": zad.get("zadano", 0), "napravljeno": zad.get("napravljeno", 0),
                   "djelomicno": zad.get("djelomicno", 0), "ne": zad.get("ne", 0),
                   "ne_zaredom": zad.get("ne_zaredom", 0)},
        "testovi": [{"naziv": _t(x.get("naziv")), "postotak": x.get("postotak")}
                    for x in (k.get("testovi") or [])],
        "napredak": ({"prvi": napredak.get("prvi"), "zadnji": napredak.get("zadnji"),
                      "razlika": napredak.get("razlika")} if napredak else None),
        "teme": [_t(x) for x in (k.get("teme") or [])][:8],
        "profesor_je_odabrao": [_t(f.get("tekst")) for f in (fraze or ()) if _t(f.get("tekst"))],
        "profesor_je_napisao": _t(cilj),
        "ton": _t(ton) or "Toplo",
        "duljina": _t(duljina) or "srednje",
    }


def sastavi_user(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=1)


def ocisti_odgovor(tekst: str) -> str:
    """Skini ``` ograde, uvodne navodnike i prazne redove s početka/kraja."""
    t = str(tekst or "").strip()
    t = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", t).strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in ('"', "'", "„", "“"):
        t = t[1:-1].strip()
    return re.sub(r"\n{3,}", "\n\n", t)


def ime_u_pogresnom_padezu(sirovi_tekst: str) -> bool:
    """Je li model napisao `{ime}` nakon prijedloga („s {ime}”, „kod {ime}”)? Tada se ime ne može
    doslovno ubaciti — provjera ide PRIJE zamjene, na sirovom odgovoru."""
    return _RE_PADEZ.search(str(sirovi_tekst or "")) is not None


def ubaci_ime(tekst: str, ime: str) -> str:
    """Lokalna zamjena `{ime}` -> stvarno ime. Model ime nikad nije vidio."""
    ime = _t(ime)
    if not ime:
        return str(tekst or "")
    return str(tekst or "").replace("{ime}", ime)


def pripremi_odgovor(sirovi_tekst: str, ime_ucenika: str = "", rod: str = "") -> dict:
    """Očisti odgovor, provjeri padež, ubaci ime. Vraća {"tekst", "upozorenja", "padez_los"}.

    `padez_los` = model je stavio `{ime}` u kosi padež; tekst se ipak vraća (profesor vidi i ispravi),
    ali sučelje na to upozori i ne nudi ga kao „točno". """
    sirovi = ocisti_odgovor(sirovi_tekst)
    lose = ime_u_pogresnom_padezu(sirovi)
    tekst = ubaci_ime(sirovi, ime_ucenika)
    upozorenja = []
    if lose:
        upozorenja.append("Model je ime stavio u kosi padež (npr. „s {ime}”) — ime se ubacuje doslovno, "
                          "pa provjeri tu rečenicu i preformuliraj (npr. „{ime} je…”).")
    if "{" in tekst and "}" in tekst:
        upozorenja.append("U tekstu je ostalo neko polje u vitičastim zagradama — popuni ga.")
    return {"tekst": tekst, "upozorenja": upozorenja, "padez_los": lose}


# ------------------------------------------------------------------------------------ mrežni poziv

def pozovi_claude(kljuc: str, system: str, user: str, model: str = MODEL, max_tokens: int = MAX_TOKENA) -> dict:
    """Poziv modelu. Vraća {"tekst", "tokeni_ulaz", "tokeni_izlaz", "odrezano"}."""
    try:
        import anthropic
    except ImportError as e:
        raise RuntimeError("paket 'anthropic' nije instaliran (dodaj ga u requirements.txt i Reboot)") from e
    klijent = anthropic.Anthropic(api_key=kljuc)
    # thinking isključen: za pisanje kratkog teksta troši tokene bez koristi (isto kao u ai_asistent.py)
    with klijent.messages.stream(model=model, max_tokens=max_tokens, system=system,
                                 messages=[{"role": "user", "content": user}],
                                 thinking={"type": "disabled"}) as stream:
        odg = stream.get_final_message()
    tekst = "".join(getattr(b, "text", "") for b in odg.content if getattr(b, "type", "") == "text")
    return {"tekst": tekst, "tokeni_ulaz": odg.usage.input_tokens, "tokeni_izlaz": odg.usage.output_tokens,
            "odrezano": odg.stop_reason == "max_tokens"}


def napravi_pozivatelja(st):
    """Funkcija pozovi(system, user) vezana na ključ iz Secrets. Baca RuntimeError ako ključa nema."""
    try:
        kljuc = _t(st.secrets.get(KLJUC_SECRETS, ""))
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Nema {KLJUC_SECRETS} u Secrets.") from e
    if not kljuc:
        raise RuntimeError(f"Nema {KLJUC_SECRETS} u Secrets — AI gumb se ne prikazuje.")
    return lambda system, user: pozovi_claude(kljuc, system, user)


def sastavi(payload: dict, ime_ucenika: str = "", rod: str = "", pozovi=None, kontekst: str | None = None) -> dict:
    """Cijeli tok: system + user -> model -> priprema za sučelje.

    Vraća {"tekst", "upozorenja", "padez_los", "model", "tokeni_ulaz", "tokeni_izlaz", "odrezano"}.
    `pozovi` se u testovima zamjenjuje lažnom funkcijom (bez mreže)."""
    if pozovi is None:
        raise ValueError("Nedostaje funkcija za poziv modela.")
    system = sastavi_system(kontekst)
    odg = pozovi(system, sastavi_user(payload)) or {}
    pr = pripremi_odgovor(odg.get("tekst", ""), ime_ucenika, rod)
    upozorenja = list(pr["upozorenja"])
    if odg.get("odrezano"):
        upozorenja.append("Odgovor je odrezan (max_tokens) — tekst može biti nedovršen.")
    if not pr["tekst"]:
        upozorenja.append("Model nije vratio tekst — pokušaj ponovno ili napiši sam.")
    return {"tekst": pr["tekst"], "upozorenja": upozorenja, "padez_los": pr["padez_los"],
            "model": MODEL, "tokeni_ulaz": odg.get("tokeni_ulaz", 0),
            "tokeni_izlaz": odg.get("tokeni_izlaz", 0), "odrezano": bool(odg.get("odrezano"))}

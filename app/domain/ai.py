"""Automatyczna kategoryzacja zgłoszeń IT.

Moduł przypisuje zgłoszeniu **kategorię**, **priorytet** (a przez to termin SLA)
oraz **pewność** własnej decyzji. Działa lokalnie — bez kluczy API, kosztów
i połączenia z internetem.

Jak to działa
-------------
1. Tekst jest normalizowany: polskie znaki sprowadzane są do postaci bez
   diakrytyków, żeby „hasło", „haslo" i „HASŁA" trafiały w to samo słowo
   kluczowe. Bez tego kroku moduł nie rozpoznawał poprawnie napisanej
   polszczyzny.
2. Każde dopasowane słowo kluczowe dokłada punkty swojej kategorii — decyduje
   suma dowodów, a nie pierwsze trafienie.
3. Priorytet wynika z najpoważniejszego dopasowania, a następnie jest
   podnoszony, jeśli w tekście widać skalę awarii („cały dział", „nikt nie
   może") lub pilność („pilne", „natychmiast").
4. Zgłoszenia bezpieczeństwa zawsze dostają priorytet krytyczny.
5. Gdy dowodów brakuje, moduł **przyznaje się do niewiedzy** zamiast zgadywać:
   zwraca niską pewność i flagę `wymaga_weryfikacji`.

Podmiana na model językowy
--------------------------
Kontraktem modułu jest funkcja `categorize(title, description)` zwracająca
słownik. Wystarczy podmienić jej wnętrze na wywołanie modelu, zachowując
zwracane pola.

Uwaga wydajnościowa: wywołanie sieciowe w ścieżce tworzenia zgłoszenia
sprawia, że użytkownik czeka na odpowiedź obcej usługi. Jeśli taki model
zostanie podłączony, powinien mieć krótki limit czasu i awaryjne przejście
do dopasowania słownikowego poniżej — inaczej awaria dostawcy zablokuje
zakładanie zgłoszeń.
"""

import unicodedata

CATEGORIES = [
    "Sprzet", "Oprogramowanie", "Siec", "Poczta",
    "Konta i dostep", "Bezpieczenstwo", "Peryferia",
]

SLA_HOURS = {"Krytyczny": 1, "Wysoki": 4, "Sredni": 8, "Niski": 24}

_KOLEJNOSC_PRIORYTETOW = ["Niski", "Sredni", "Wysoki", "Krytyczny"]
_RANGA = {p: i for i, p in enumerate(_KOLEJNOSC_PRIORYTETOW)}

# Poniżej tej wartości zgłoszenie trafia do ręcznej weryfikacji technika.
PROG_PEWNOSCI = 0.40

# Słowa kluczowe: rdzeń -> (kategoria, priorytet, waga).
#
# Zapisujemy RDZENIE bez końcówek, bo polski odmienia się przez przypadki:
# „drukark" trafia w „drukarka", „drukarki", „drukarkę".
#
# Waga oddaje jednoznaczność sygnału: „phishing" mówi o zgłoszeniu znacznie
# więcej niż „mail", więc powinien ważyć więcej przy zliczaniu dowodów.
KEYWORDS = {
    # --- Bezpieczeństwo (najwyższa waga: pomyłka w tę stronę jest kosztowna) ---
    "phishing":   ("Bezpieczenstwo", "Krytyczny", 3),
    "wirus":      ("Bezpieczenstwo", "Krytyczny", 3),
    "malware":    ("Bezpieczenstwo", "Krytyczny", 3),
    "ransomware": ("Bezpieczenstwo", "Krytyczny", 3),
    "wyludz":     ("Bezpieczenstwo", "Krytyczny", 3),
    "wlaman":     ("Bezpieczenstwo", "Krytyczny", 3),
    "zaszyfrowa": ("Bezpieczenstwo", "Krytyczny", 3),
    "okup":       ("Bezpieczenstwo", "Krytyczny", 3),
    "podszywa":   ("Bezpieczenstwo", "Krytyczny", 3),
    "trojan":     ("Bezpieczenstwo", "Krytyczny", 3),
    "podejrzan":  ("Bezpieczenstwo", "Krytyczny", 2),
    "oszust":     ("Bezpieczenstwo", "Krytyczny", 3),
    "szkodliw":   ("Bezpieczenstwo", "Krytyczny", 2),

    # --- Sieć ---
    "vpn":        ("Siec", "Wysoki", 3),
    "serwer":     ("Siec", "Krytyczny", 2),
    "internet":   ("Siec", "Wysoki", 2),
    "wi-fi":      ("Siec", "Sredni", 3),
    "wifi":       ("Siec", "Sredni", 3),
    "siec":       ("Siec", "Sredni", 2),
    "polaczen":   ("Siec", "Sredni", 1),
    "router":     ("Siec", "Wysoki", 3),
    "zasieg":     ("Siec", "Niski", 2),
    "dysk siecio":("Siec", "Krytyczny", 3),

    # --- Sprzęt ---
    "komputer":   ("Sprzet", "Sredni", 2),
    "laptop":     ("Sprzet", "Sredni", 2),
    "monitor":    ("Sprzet", "Sredni", 2),
    "ekran":      ("Sprzet", "Sredni", 2),
    "stacja robo":("Sprzet", "Sredni", 3),
    "zasilani":   ("Sprzet", "Wysoki", 2),
    "przegrzew":  ("Sprzet", "Wysoki", 3),
    "bateri":     ("Sprzet", "Niski", 1),
    "dysk tward": ("Sprzet", "Wysoki", 3),
    "niebieski ekran": ("Sprzet", "Wysoki", 3),
    "bsod":       ("Sprzet", "Wysoki", 3),

    # --- Peryferia ---
    "drukark":    ("Peryferia", "Niski", 3),
    "skaner":     ("Peryferia", "Niski", 3),
    "myszk":      ("Peryferia", "Niski", 3),
    "klawiatur":  ("Peryferia", "Niski", 3),
    "pendrive":   ("Peryferia", "Niski", 3),
    "sluchawk":   ("Peryferia", "Niski", 3),
    "kamerk":     ("Peryferia", "Niski", 3),
    "toner":      ("Peryferia", "Niski", 3),

    # --- Konta i dostęp ---
    "haslo":      ("Konta i dostep", "Sredni", 3),
    "hasla":      ("Konta i dostep", "Sredni", 3),
    "konto":      ("Konta i dostep", "Sredni", 2),
    "konta":      ("Konta i dostep", "Sredni", 2),
    "logowan":    ("Konta i dostep", "Sredni", 3),
    "zalogowa":   ("Konta i dostep", "Sredni", 3),
    "uprawnien":  ("Konta i dostep", "Sredni", 3),
    "dostep do":  ("Konta i dostep", "Sredni", 2),
    "zablokowan": ("Konta i dostep", "Wysoki", 2),
    "reset":      ("Konta i dostep", "Sredni", 1),

    # --- Poczta ---
    "outlook":    ("Poczta", "Sredni", 3),
    "mail":       ("Poczta", "Sredni", 1),
    "poczt":      ("Poczta", "Sredni", 2),
    "skrzynk":    ("Poczta", "Sredni", 2),
    "wiadomosc":  ("Poczta", "Sredni", 1),
    "zalacznik":  ("Poczta", "Sredni", 1),

    # --- Oprogramowanie ---
    "licencj":    ("Oprogramowanie", "Niski", 3),
    "zawiesz":    ("Oprogramowanie", "Sredni", 2),
    "crash":      ("Oprogramowanie", "Wysoki", 2),
    "erp":        ("Oprogramowanie", "Wysoki", 3),
    "excel":      ("Oprogramowanie", "Sredni", 3),
    "word":       ("Oprogramowanie", "Sredni", 3),
    "office":     ("Oprogramowanie", "Sredni", 3),
    "aplikacj":   ("Oprogramowanie", "Sredni", 2),
    "program":    ("Oprogramowanie", "Sredni", 1),
    "instalac":   ("Oprogramowanie", "Niski", 2),
    "aktualizac": ("Oprogramowanie", "Niski", 2),
    "system ksie":("Oprogramowanie", "Wysoki", 3),
}

# Zwroty świadczące o SKALI awarii — jedna osoba to nie to samo co cały dział.
_ZWROTY_SKALI = (
    "caly dzial", "cala firma", "wszyscy", "nikt nie", "wszystkie stanowiska",
    "cale biuro", "cały zespol", "caly zespol", "kilkanascie osob", "wiele osob",
)

# Zwroty świadczące o PILNOŚCI lub całkowitej niesprawności.
#
# Celowo NIE ma tu „nie działa" — po polsku to domyślny sposób opisania
# dowolnej usterki („drukarka nie działa", „myszka nie działa"). Traktowanie
# go jako sygnału pilności podnosiłoby priorytet niemal każdemu zgłoszeniu,
# a wtedy priorytety przestają cokolwiek rozróżniać.
#
# Zostają zwroty mówiące o CAŁKOWITEJ niesprawności lub realnym wpływie na pracę.
_ZWROTY_PILNOSCI = (
    "pilne", "natychmiast", "awaria", "nie wlacza", "nie uruchamia",
    "calkowicie", "w ogole nie", "blokuje prace", "produkcj",
    "nie moge pracowac", "krytyczn", "restartuje", "sam sie wylacza",
    "traci dane", "utrata danych",
)


def _bez_diakrytykow(tekst: str) -> str:
    """Sprowadza polskie znaki do postaci podstawowej.

    „hasło" -> „haslo", „sieć" -> „siec", „sprzęt" -> „sprzet".

    Bez tego kroku słownik (pisany bez diakrytyków) nie trafiał w poprawnie
    napisaną polszczyznę — a użytkownicy piszą z polskimi znakami.
    Litera „ł" nie rozkłada się przez unicodedata, więc wymaga podmiany wprost.
    """
    tekst = tekst.replace("ł", "l").replace("Ł", "L")
    rozlozony = unicodedata.normalize("NFD", tekst)
    return "".join(z for z in rozlozony if unicodedata.category(z) != "Mn")


def _normalizuj(title, description) -> str:
    return _bez_diakrytykow(f"{title} {description}").lower()


def _podnies_priorytet(priorytet: str, o: int = 1) -> str:
    return _KOLEJNOSC_PRIORYTETOW[min(_RANGA[priorytet] + o, len(_KOLEJNOSC_PRIORYTETOW) - 1)]


def categorize(title, description):
    """Zwraca kategorię, priorytet, pewność i uzasadnienie decyzji.

    Zwracane pola:
        kategoria           — jedna z CATEGORIES
        priorytet           — jeden z SLA_HOURS
        pewnosc             — 0.0–1.0, siła przesłanek
        wymaga_weryfikacji  — True, gdy pewność jest poniżej progu
        dopasowania         — słowa, które zadecydowały (uzasadnienie dla technika)
    """
    tekst = _normalizuj(title, description)

    punkty = {}       # kategoria -> suma wag
    najlepszy = {}    # kategoria -> najpowazniejszy priorytet w tej kategorii
    trafienia = {}    # kategoria -> lista dopasowanych slow

    for rdzen, (kategoria, priorytet, waga) in KEYWORDS.items():
        if rdzen in tekst:
            punkty[kategoria] = punkty.get(kategoria, 0) + waga
            trafienia.setdefault(kategoria, []).append(rdzen)
            obecny = najlepszy.get(kategoria)
            if obecny is None or _RANGA[priorytet] > _RANGA[obecny]:
                najlepszy[kategoria] = priorytet

    # Brak jakichkolwiek przesłanek — moduł nie zgaduje, tylko to sygnalizuje.
    if not punkty:
        return {
            "kategoria": "Oprogramowanie",
            "priorytet": "Sredni",
            "pewnosc": 0.0,
            "wymaga_weryfikacji": True,
            "dopasowania": [],
        }

    suma = sum(punkty.values())
    kategoria = max(punkty, key=lambda k: (punkty[k], _RANGA[najlepszy[k]]))
    priorytet = najlepszy[kategoria]

    # Incydent bezpieczeństwa nigdy nie schodzi poniżej priorytetu krytycznego —
    # zaniżenie go jest znacznie kosztowniejsze niż fałszywy alarm.
    if kategoria == "Bezpieczenstwo":
        priorytet = "Krytyczny"
    else:
        if any(z in tekst for z in _ZWROTY_SKALI):
            priorytet = _podnies_priorytet(priorytet)
        if any(z in tekst for z in _ZWROTY_PILNOSCI):
            priorytet = _podnies_priorytet(priorytet)

    # Pewność łączy dwa czynniki: jak bardzo zwycięska kategoria dominuje nad
    # pozostałymi oraz ile niezależnych przesłanek ją wskazuje.
    dominacja = punkty[kategoria] / suma
    liczba_przeslanek = min(1.0, len(trafienia[kategoria]) / 2)
    pewnosc = round(dominacja * (0.5 + 0.5 * liczba_przeslanek), 2)

    return {
        "kategoria": kategoria,
        "priorytet": priorytet,
        "pewnosc": pewnosc,
        "wymaga_weryfikacji": pewnosc < PROG_PEWNOSCI,
        "dopasowania": sorted(trafienia[kategoria]),
    }

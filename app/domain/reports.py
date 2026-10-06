"""Raporty dla klientów — reguły niezależne od bazy danych i HTTP.

Moduł operuje na gotowych liczbach: ustala okres raportu i okres
porównawczy, grupuje trend, liczy zmiany procentowe i formułuje
rekomendacje. Zapytania do bazy są w `app/data/reports.py`.

Rekomendacje są regułowe, tak jak moduł kategoryzacji: każda wynika
z konkretnej liczby w raporcie, więc klient widzi, skąd się wzięła.
"""

from datetime import date, timedelta

DOMYSLNIE_DNI = 30
MAX_DNI = 366

# Dolna granica dat. Okres porównawczy leży PRZED raportem, więc data bliska
# 0001-01-01 kończyłaby się przepełnieniem przy odejmowaniu dni.
NAJWCZESNIEJ = date(2000, 1, 1)

# Grupowanie trendu dobrane tak, by wykres miał czytelną liczbę słupków.
DO_DNI_DZIENNIE = 31
DO_DNI_TYGODNIOWO = 183

KOLEJNOSC_PRIORYTETOW = ["Krytyczny", "Wysoki", "Sredni", "Niski"]

# Raport czyta klient, nie programista — nazwy z polskimi znakami zamiast
# wartości technicznych zapisanych w bazie.
ETYKIETY_KATEGORII = {
    "Sprzet": "Sprzęt", "Oprogramowanie": "Oprogramowanie", "Siec": "Sieć",
    "Poczta": "Poczta", "Konta i dostep": "Konta i dostęp",
    "Bezpieczenstwo": "Bezpieczeństwo", "Peryferia": "Peryferia",
}

# Rdzenie słów kluczowych modułu AI („drukark", „licencj") w czytelnej
# formie. Różne rdzenie tego samego problemu („haslo", „hasla") dostają tę
# samą etykietę, więc w raporcie liczą się razem. Test pilnuje, by każdy
# rdzeń ze słownika modułu AI miał tu swoją etykietę.
ETYKIETY_PROBLEMOW = {
    "phishing": "phishing", "wirus": "wirus", "malware": "złośliwe oprogramowanie",
    "ransomware": "ransomware", "wyludz": "próba wyłudzenia", "wlaman": "włamanie",
    "zaszyfrowa": "zaszyfrowane pliki", "okup": "żądanie okupu",
    "podszywa": "podszywanie się", "trojan": "trojan",
    "podejrzan": "podejrzana wiadomość", "oszust": "oszustwo",
    "szkodliw": "złośliwe oprogramowanie",
    "vpn": "VPN", "serwer": "serwer", "internet": "internet", "wi-fi": "Wi-Fi",
    "wifi": "Wi-Fi", "siec": "sieć", "polaczen": "połączenie z siecią",
    "router": "router", "zasieg": "zasięg sieci", "dysk siecio": "dysk sieciowy",
    "komputer": "komputer", "laptop": "laptop", "monitor": "monitor", "ekran": "ekran",
    "stacja robo": "stacja robocza", "zasilani": "zasilanie",
    "przegrzew": "przegrzewanie się", "bateri": "bateria", "dysk tward": "dysk twardy",
    "niebieski ekran": "niebieski ekran (BSOD)", "bsod": "niebieski ekran (BSOD)",
    "drukark": "drukarka", "skaner": "skaner", "myszk": "myszka",
    "klawiatur": "klawiatura", "pendrive": "pendrive", "sluchawk": "słuchawki",
    "kamerk": "kamerka", "toner": "toner",
    "haslo": "hasło", "hasla": "hasło", "konto": "konto", "konta": "konto",
    "logowan": "logowanie", "zalogowa": "logowanie", "uprawnien": "uprawnienia",
    "dostep do": "dostęp do zasobów", "zablokowan": "zablokowane konto",
    "reset": "reset hasła",
    "outlook": "Outlook", "mail": "e-mail", "poczt": "poczta",
    "skrzynk": "skrzynka pocztowa", "wiadomosc": "wiadomość e-mail",
    "zalacznik": "załącznik",
    "licencj": "licencja", "zawiesz": "zawieszanie się programu",
    "crash": "awaria programu", "erp": "system ERP", "excel": "Excel", "word": "Word",
    "office": "pakiet Office", "aplikacj": "aplikacja", "program": "program",
    "instalac": "instalacja", "aktualizac": "aktualizacja",
    "system ksie": "system księgowy",
}

# Progi rekomendacji — poniżej nich pojedyncze zgłoszenia dawałyby
# „wnioski" bez pokrycia (np. 1 z 2 zgłoszeń to 50%, ale nic nie znaczy).
MIN_ZGLOSZEN_DO_WNIOSKU = 3
PROG_UDZIALU_KATEGORII = 0.30
PROG_WZROSTU_PROC = 50.0
PROG_SLA_PROC = 80.0
MIN_ROZWIAZANYCH_DO_SLA = 5
MIN_PRZYROSTU = 3            # +1 → +2 to „+100%", ale nie trend
MAX_WZROSTOW = 2
MAX_REKOMENDACJI = 5


class BladOkresu(ValueError):
    """Nieprawidłowy okres raportu — komunikat trafia do klienta API."""


def _data(tekst, nazwa):
    if not isinstance(tekst, str) or len(tekst) != 10:
        raise BladOkresu(f"Parametr '{nazwa}' musi miec format RRRR-MM-DD")
    try:
        wynik = date.fromisoformat(tekst)
    except ValueError:
        raise BladOkresu(f"Parametr '{nazwa}' musi miec format RRRR-MM-DD") from None
    if wynik < NAJWCZESNIEJ:
        raise BladOkresu(f"Parametr '{nazwa}' nie moze byc wczesniejszy niz {NAJWCZESNIEJ}")
    return wynik


def okres(od_tekst, do_tekst, dzis):
    """Okres raportu (od, do) — obie daty włącznie.

    Brak dat oznacza ostatnie 30 dni. Sama data `od` oznacza „od tego dnia
    do dziś", sama data `do` — 30 dni kończących się tego dnia.
    """
    od = _data(od_tekst, "od") if od_tekst else None
    do = _data(do_tekst, "do") if do_tekst else None

    if do is None:
        do = dzis
    if od is None:
        od = do - timedelta(days=DOMYSLNIE_DNI - 1)

    if od > do:
        raise BladOkresu("Data 'od' nie moze byc pozniejsza niz 'do'")
    if od > dzis:
        raise BladOkresu("Okres raportu nie moze zaczynac sie w przyszlosci")
    if (do - od).days + 1 > MAX_DNI:
        raise BladOkresu(f"Okres raportu moze miec najwyzej {MAX_DNI} dni")
    return od, do


def poprzedni_okres(od, do):
    """Okres tej samej długości bezpośrednio przed raportowanym."""
    dlugosc = (do - od).days + 1
    return od - timedelta(days=dlugosc), od - timedelta(days=1)


def grupowanie(od, do):
    dni = (do - od).days + 1
    if dni <= DO_DNI_DZIENNIE:
        return "dzien"
    if dni <= DO_DNI_TYGODNIOWO:
        return "tydzien"
    return "miesiac"


def _poczatek_kolejnego_miesiaca(d):
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def trend(od, do, dziennie):
    """Liczba zgłoszeń w kolejnych przedziałach okresu — także zerowych.

    `dziennie` to słownik {data: liczba}. Przedziały pokrywają cały okres,
    więc dni bez zgłoszeń też są na wykresie; inaczej przerwa w zgłoszeniach
    byłaby niewidoczna. Tygodnie liczone są od pierwszego dnia raportu,
    miesiące kalendarzowo — skrajne przedziały mogą być niepełne.
    """
    sposob = grupowanie(od, do)
    wynik = []
    poczatek = od
    while poczatek <= do:
        if sposob == "dzien":
            koniec = poczatek
            etykieta = poczatek.isoformat()
        elif sposob == "tydzien":
            koniec = min(poczatek + timedelta(days=6), do)
            etykieta = poczatek.isoformat()
        else:
            koniec = min(_poczatek_kolejnego_miesiaca(poczatek) - timedelta(days=1), do)
            etykieta = poczatek.strftime("%Y-%m")

        liczba = sum(n for d, n in dziennie.items() if poczatek <= d <= koniec)
        wynik.append({"okres": etykieta, "liczba": liczba})
        poczatek = koniec + timedelta(days=1)
    return wynik


def zmiana_proc(teraz, poprzednio):
    """Zmiana procentowa; None, gdy nie ma do czego porównać (zero wcześniej)."""
    if not poprzednio:
        return None
    return round((teraz - poprzednio) / poprzednio * 100, 1)


def procent(czesc, calosc):
    return round(czesc / calosc * 100, 1) if calosc else None


def kategorie_z_porownaniem(teraz, poprzednio):
    """Rozkład kategorii z liczbą z poprzedniego okresu i zmianą procentową.

    Kategorie obecne tylko w poprzednim okresie też są na liście — spadek do
    zera to informacja, którą klient chce zobaczyć.
    """
    wszystkie = set(teraz) | set(poprzednio)
    wiersze = [
        {"kategoria": k,
         "etykieta": etykieta_kategorii(k),
         "liczba": teraz.get(k, 0),
         "poprzednio": poprzednio.get(k, 0),
         "zmiana_proc": zmiana_proc(teraz.get(k, 0), poprzednio.get(k, 0))}
        for k in wszystkie
    ]
    # Najczęstsze na górze; przy remisie kolejność alfabetyczna (stabilna),
    # zgłoszenia bez kategorii na końcu.
    return sorted(wiersze, key=lambda w: (-w["liczba"], w["kategoria"] is None,
                                         w["kategoria"] or ""))


def etykieta_kategorii(kategoria):
    if kategoria is None:
        return "Bez kategorii"
    return ETYKIETY_KATEGORII.get(kategoria, kategoria)


def odmiana(n, jeden, kilka, wiele):
    """Polska odmiana po liczebniku: 1 zgłoszenie, 3 zgłoszenia, 5 zgłoszeń.

    Liczby kończące się na 2–4 biorą formę „kilka", z wyjątkiem 12–14
    („12 zgłoszeń"), tak jak w języku polskim.
    """
    if n == 1:
        return jeden
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return kilka
    return wiele


def priorytety_w_kolejnosci(liczby):
    """Wszystkie priorytety od najpoważniejszego, także z zerem."""
    wynik = [{"priorytet": p, "liczba": liczby.get(p, 0)} for p in KOLEJNOSC_PRIORYTETOW]
    nieznane = sum(n for p, n in liczby.items() if p not in KOLEJNOSC_PRIORYTETOW)
    if nieznane:
        wynik.append({"priorytet": None, "liczba": nieznane})
    return wynik


def rekomendacje(podsumowanie, kategorie, problemy):
    """Wnioski dla klienta wyprowadzone wprost z liczb w raporcie.

    Kolejność odpowiada wadze sprawy — bezpieczeństwo i terminy przed
    statystyką — a liczba wniosków jest ograniczona: lista dziesięciu
    drobnych uwag przestaje być czytana.
    """
    zgloszen = podsumowanie["zgloszen"]
    if not zgloszen:
        return ["W wybranym okresie nie było zgłoszeń."]

    wnioski = []

    bezpieczenstwo = next((k["liczba"] for k in kategorie
                           if k["kategoria"] == "Bezpieczenstwo"), 0)
    if bezpieczenstwo:
        wnioski.append(
            f"Odnotowano {bezpieczenstwo} "
            f"{odmiana(bezpieczenstwo, 'incydent', 'incydenty', 'incydentów')} "
            f"bezpieczeństwa — warto przypomnieć pracownikom zasady rozpoznawania "
            f"podejrzanych wiadomości.")

    sla = podsumowanie["procent_w_terminie_sla"]
    if (sla is not None and sla < PROG_SLA_PROC
            and podsumowanie["rozwiazanych_z_terminem"] >= MIN_ROZWIAZANYCH_DO_SLA):
        wnioski.append(
            f"W terminie SLA rozwiązano {round(sla)}% zgłoszeń — poniżej "
            f"oczekiwanych {round(PROG_SLA_PROC)}%.")

    po_terminie = podsumowanie["otwartych_po_terminie"]
    if po_terminie:
        wnioski.append(
            f"{po_terminie} "
            f"{odmiana(po_terminie, 'otwarte zgłoszenie przekroczyło', 'otwarte zgłoszenia przekroczyły', 'otwartych zgłoszeń przekroczyło')} "
            f"już termin SLA.")

    for k in kategorie:
        if (k["kategoria"] is not None and k["liczba"] >= MIN_ZGLOSZEN_DO_WNIOSKU
                and k["liczba"] / zgloszen >= PROG_UDZIALU_KATEGORII):
            wnioski.append(
                f"{round(k['liczba'] / zgloszen * 100)}% zgłoszeń dotyczy kategorii "
                f"{k['etykieta']} — to główne źródło problemów w tym okresie.")

    wzrosty = sorted(
        (k for k in kategorie
         if k["kategoria"] is not None and k["zmiana_proc"] is not None
         and k["zmiana_proc"] >= PROG_WZROSTU_PROC
         and k["liczba"] - k["poprzednio"] >= MIN_PRZYROSTU),
        key=lambda k: -(k["liczba"] - k["poprzednio"]))
    for k in wzrosty[:MAX_WZROSTOW]:
        wnioski.append(
            f"Liczba zgłoszeń w kategorii {k['etykieta']} wzrosła o "
            f"{round(k['zmiana_proc'])}% ({k['poprzednio']} → {k['liczba']}) "
            f"względem poprzedniego okresu.")

    if problemy and problemy[0]["liczba"] >= MIN_ZGLOSZEN_DO_WNIOSKU:
        p = problemy[0]
        wnioski.append(
            f"Najczęściej powtarzający się problem: {p['problem']} "
            f"({p['liczba']} {odmiana(p['liczba'], 'zgłoszenie', 'zgłoszenia', 'zgłoszeń')}) "
            f"— możliwa wspólna przyczyna.")

    return wnioski[:MAX_REKOMENDACJI] or ["Brak niepokojących sygnałów w wybranym okresie."]

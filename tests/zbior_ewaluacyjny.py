"""Zbiór ewaluacyjny modułu kategoryzacji AI.

Zgłoszenia napisane tak, jak pisze je człowiek w polskim biurze: z polskimi
znakami, w różnych formach gramatycznych, czasem skrótowo. Każdy wpis ma
ręcznie przypisaną poprawną kategorię i priorytet — to punkt odniesienia,
względem którego mierzona jest skuteczność modułu.

Format: (tytuł, opis, oczekiwana_kategoria, oczekiwany_priorytet)

Priorytet oczekiwany bywa przedziałem — dla zgłoszeń, gdzie sensowna jest
więcej niż jedna ocena, podano zbiór akceptowalnych wartości.
"""

# (tytul, opis, kategoria, dopuszczalne_priorytety)
ZBIOR = [
    # --- Konta i dostęp ---
    ("Zapomniane hasło", "Nie pamiętam hasła do komputera, proszę o reset",
     "Konta i dostep", {"Sredni", "Niski"}),
    ("Konto zablokowane", "Po trzech próbach logowania konto zostało zablokowane",
     "Konta i dostep", {"Sredni", "Wysoki"}),
    ("Brak uprawnień do folderu", "Nie mam dostępu do katalogu działu kadr",
     "Konta i dostep", {"Sredni", "Niski"}),
    ("Nie mogę się zalogować", "System nie przyjmuje mojego hasła od rana",
     "Konta i dostep", {"Sredni", "Wysoki"}),

    # --- Sieć ---
    ("Awaria sieci", "Cały dział nie ma dostępu do sieci od godziny",
     "Siec", {"Wysoki", "Krytyczny"}),
    ("Nie działa VPN", "Nie mogę połączyć się z firmowym VPN, błąd TLS",
     "Siec", {"Wysoki", "Krytyczny"}),
    ("Słaby zasięg Wi-Fi", "Na drugim piętrze bardzo słaby sygnał sieci",
     "Siec", {"Niski", "Sredni"}),
    ("Serwer plików nie odpowiada", "Dysk sieciowy Z niedostępny dla całego działu",
     "Siec", {"Krytyczny", "Wysoki"}),
    ("Brak internetu", "W sali konferencyjnej nie ma połączenia z internetem",
     "Siec", {"Wysoki", "Sredni", "Krytyczny"}),

    # --- Sprzęt ---
    ("Laptop się nie włącza", "Służbowy laptop w ogóle nie reaguje na przycisk zasilania",
     "Sprzet", {"Wysoki", "Krytyczny"}),
    ("Komputer się przegrzewa", "Stacja robocza wyłącza się po 30 minutach pracy",
     "Sprzet", {"Wysoki", "Sredni"}),
    ("Monitor migocze", "Ekran zewnętrznego monitora co chwilę gaśnie",
     "Sprzet", {"Sredni", "Wysoki"}),
    ("Niebieski ekran", "Komputer pokazuje niebieski ekran i restartuje się",
     "Sprzet", {"Wysoki", "Krytyczny"}),

    # --- Peryferia ---
    ("Drukarka nie drukuje", "Drukarka w sekretariacie nie przyjmuje zleceń",
     "Peryferia", {"Niski", "Sredni"}),
    ("Skaner nie wykrywa dokumentów", "Skaner nie widzi kartki na szybie",
     "Peryferia", {"Niski", "Sredni"}),
    ("Myszka nie działa", "Bezprzewodowa myszka nie reaguje mimo nowych baterii",
     "Peryferia", {"Niski", "Sredni"}),
    ("Wymiana klawiatury", "Kilka klawiszy przestało działać, proszę o wymianę",
     "Peryferia", {"Niski", "Sredni"}),

    # --- Poczta ---
    ("Outlook nie wysyła", "Wiadomości zostają w skrzynce nadawczej",
     "Poczta", {"Sredni", "Wysoki"}),
    ("Problem z pocztą", "Nie przychodzą wiadomości e-mail od wczoraj",
     "Poczta", {"Sredni", "Wysoki"}),
    ("Konfiguracja poczty na telefonie", "Proszę o pomoc w ustawieniu skrzynki na komórce",
     "Poczta", {"Niski", "Sredni"}),

    # --- Oprogramowanie ---
    ("Excel się zawiesza", "Przy dużych arkuszach program przestaje odpowiadać",
     "Oprogramowanie", {"Sredni", "Wysoki"}),
    ("Brak licencji Office", "Przy starcie Worda komunikat o wygasłej licencji",
     "Oprogramowanie", {"Niski", "Sredni"}),
    ("System ERP działa wolno", "Odpowiedzi z systemu ERP przychodzą z dużym opóźnieniem",
     "Oprogramowanie", {"Wysoki", "Krytyczny", "Sredni"}),
    ("Program się nie uruchamia", "Aplikacja księgowa zamyka się od razu po starcie",
     "Oprogramowanie", {"Wysoki", "Sredni"}),

    # --- Bezpieczeństwo (najważniejsze, by nie zaniżyć priorytetu) ---
    ("Podejrzana wiadomość", "Dostałem maila z prośbą o podanie hasła, wygląda na phishing",
     "Bezpieczenstwo", {"Krytyczny"}),
    ("Wirus na komputerze", "Antywirus zgłasza malware na moim komputerze",
     "Bezpieczenstwo", {"Krytyczny"}),
    ("Podejrzany załącznik", "Otworzyłem załącznik i teraz komputer dziwnie działa",
     "Bezpieczenstwo", {"Krytyczny"}),
    ("Próba wyłudzenia danych", "Ktoś dzwonił i podawał się za informatyka, prosił o hasło",
     "Bezpieczenstwo", {"Krytyczny"}),
    ("Zaszyfrowane pliki", "Wszystkie pliki na dysku mają dziwne rozszerzenie i żądanie okupu",
     "Bezpieczenstwo", {"Krytyczny"}),
]


# Zgłoszenia, których moduł NIE powinien rozpoznać — poprawną odpowiedzią
# jest przyznanie się do niewiedzy, a nie zgadywanie kategorii.
NIEROZPOZNAWALNE = [
    ("Prośba o spotkanie", "Chciałbym umówić się na rozmowę w sprawie projektu"),
    ("Pytanie organizacyjne", "Kiedy odbędzie się szkolenie dla nowych pracowników"),
    ("Zamówienie", "Proszę o zamówienie wizytówek dla nowego handlowca"),
]

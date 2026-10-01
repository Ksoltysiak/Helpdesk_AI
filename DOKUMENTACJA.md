# Inteligentny HelpDesk IT — dokumentacja projektu

**Praca inżynierska** · System zgłoszeń serwisowych z automatyczną
kategoryzacją zgłoszeń

**Wersja dokumentu:** 23 września 2026 · **Stan kodu:** gałąź `main`

---

## Spis treści

1. [Wprowadzenie](#1-wprowadzenie)
2. [Wymagania](#2-wymagania)
3. [Zastosowane technologie](#3-zastosowane-technologie)
4. [Architektura systemu](#4-architektura-systemu)
5. [Model danych](#5-model-danych)
6. [Interfejs programistyczny (API)](#6-interfejs-programistyczny-api)
7. [Cykl życia zgłoszenia](#7-cykl-życia-zgłoszenia)
8. [Mechanizm kluczowy — automatyczna kategoryzacja](#8-mechanizm-kluczowy--automatyczna-kategoryzacja)
9. [Bezpieczeństwo](#9-bezpieczeństwo)
10. [Testowanie i zapewnienie jakości](#10-testowanie-i-zapewnienie-jakości)
11. [Wydajność](#11-wydajność)
12. [Wdrożenie i uruchomienie](#12-wdrożenie-i-uruchomienie)
13. [Wyniki](#13-wyniki)
14. [Ograniczenia i kierunki rozwoju](#14-ograniczenia-i-kierunki-rozwoju)
15. [Dokumentacja szczegółowa](#15-dokumentacja-szczegółowa)

---

## 1. Wprowadzenie

### 1.1. Problem

W małych i średnich firmach zgłoszenia awarii IT trafiają do działu wsparcia
kanałami nieustrukturyzowanymi — pocztą elektroniczną, komunikatorem, telefonem.
Rodzi to trzy praktyczne problemy:

- **brak priorytetyzacji** — zgłoszenie o zaszyfrowaniu dysku przez ransomware
  czeka w tej samej kolejce co prośba o wymianę tonera;
- **brak historii** — nie wiadomo, kto i kiedy podjął decyzję o zamknięciu
  zgłoszenia;
- **koszt ręcznej segregacji** — technik poświęca czas na klasyfikowanie
  zgłoszeń, zanim zacznie je rozwiązywać.

### 1.2. Cel pracy

Celem było zaprojektowanie i zaimplementowanie systemu HelpDesk, który
**automatycznie klasyfikuje zgłoszenie w chwili jego utworzenia** — przypisuje
kategorię, priorytet i wynikający z priorytetu termin realizacji (SLA) — a przy
tym spełnia wymagania stawiane systemowi produkcyjnemu: kontrolę dostępu,
ścieżkę audytu, odporność na typowe ataki i przewidywalną wydajność przy
rosnącej liczbie danych.

### 1.3. Zakres opracowania

Niniejsza dokumentacja opisuje **backend systemu** (serwer aplikacyjny, API,
baza danych, moduł kategoryzacji, warstwa bezpieczeństwa, testy, wdrożenie).
Interfejs użytkownika powstał jako odrębna część projektu zespołowego
i został zintegrowany z opisanym tu API.

---

## 2. Wymagania

### 2.1. Wymagania funkcjonalne

| Nr | Wymaganie |
|----|-----------|
| F1 | Pracownik zakłada zgłoszenie, podając tytuł i opis |
| F2 | System automatycznie nadaje kategorię, priorytet i termin SLA |
| F3 | Pracownik widzi **wyłącznie własne** zgłoszenia |
| F4 | Technik widzi wszystkie zgłoszenia i może je filtrować |
| F5 | Technik zmienia status zgodnie ze zdefiniowanym cyklem życia |
| F6 | Technik dodaje notatki — wewnętrzne lub widoczne dla zgłaszającego |
| F7 | Każda zmiana trafia do ścieżki audytu z autorem i znacznikiem czasu |
| F8 | System raportuje skuteczność kategoryzacji na podstawie korekt techników |
| F9 | Pulpit prezentuje statystyki w zakresie odpowiednim dla roli |

### 2.2. Wymagania niefunkcjonalne

| Nr | Wymaganie | Realizacja |
|----|-----------|------------|
| N1 | Uwierzytelnianie odporne na podszycie się | Token JWT podpisany HMAC-SHA256 |
| N2 | Hasła nieodwracalne w razie wycieku bazy | Funkcja `scrypt` |
| N3 | Ochrona przed zgadywaniem haseł | Limity żądań na adres IP i na konto |
| N4 | Czas odpowiedzi listy zgłoszeń niezależny od wielkości bazy | Stronicowanie + indeksy |
| N5 | Kontrakt API opisany formalnie | Specyfikacja OpenAPI 3.0 + testy zgodności |
| N6 | Powtarzalne środowisko uruchomieniowe | Docker Compose (aplikacja + nginx) |
| N7 | Weryfikowalna poprawność | 374 automatyczne testy, 100% pokrycia kodu |

---

## 3. Zastosowane technologie

| Warstwa | Technologia | Uzasadnienie wyboru |
|---------|-------------|---------------------|
| Język | Python 3.12 | Bogaty ekosystem bibliotek, czytelność kodu |
| Framework HTTP | Flask 3.1.3 | Mikroframework — nie narzuca struktury, co pozwoliło zaprojektować własny podział warstwowy |
| Baza danych | SQLite (tryb WAL) | Brak osobnego serwera bazy; wystarczająca dla skali MŚP (ograniczenia — p. 14) |
| Uwierzytelnianie | PyJWT 2.13.0 | Standard RFC 7519, tokeny bezstanowe |
| Limity żądań | flask-limiter 4.1.1 | Ochrona punktu logowania |
| Serwer WSGI | gunicorn 26.1.0 | Wieloprocesowa obsługa żądań |
| Odwrotne proxy | nginx 1.27 | Buforowanie wolnych klientów, miejsce na terminację TLS |
| Dokumentacja API | OpenAPI 3.0 + Swagger UI | Formalny, testowalny kontrakt |
| Testy | pytest 9.1.1, pytest-cov 7.1.0 | Trzy warstwy testów + pomiar pokrycia |
| Konteneryzacja | Docker Compose | Identyczne środowisko lokalnie i w CI |

Wszystkie zależności są przypięte do konkretnych wersji i skanowane pod kątem
znanych podatności narzędziem `pip-audit` w ramach każdego uruchomienia CI.

---

## 4. Architektura systemu

### 4.1. Podział na warstwy

System zbudowano w architekturze warstwowej, w której **zależności biegną
wyłącznie w jedną stronę**:

```
                    ┌─────────────────────────────┐
   HTTP  ─────────► │  app/api/                   │  trasy, walidacja żądań,
                    │  (warstwa prezentacji)      │  kody odpowiedzi HTTP
                    └────────┬───────────┬────────┘
                             │           │
              ┌──────────────┘           └──────────────┐
              ▼                                         ▼
   ┌────────────────────────┐              ┌────────────────────────┐
   │  app/domain/           │              │  app/data/             │
   │  (reguły biznesowe)    │              │  (dostęp do danych)    │
   │  kategoryzacja AI,     │              │  schemat, zapytania    │
   │  cykl życia zgłoszenia │              │  SQL, migracje         │
   └────────────────────────┘              └───────────┬────────────┘
        nie zna HTTP ani bazy                          ▼
                                                 ┌──────────┐
   ┌────────────────────────┐                    │  SQLite  │
   │  app/security/         │                    └──────────┘
   │  tokeny JWT, dekoratory│
   │  kontroli dostępu      │
   └────────────────────────┘

   app/config.py — jedyne miejsce odczytu zmiennych środowiskowych
```

Reguła zależności: `api → domain, data, security` · `data → wyłącznie baza` ·
`domain → nic z aplikacji`.

**Znaczenie praktyczne:** warstwa `domain` — w tym cały moduł kategoryzacji —
nie importuje Flaska ani `sqlite3`. Dzięki temu można ją testować i czytać
w oderwaniu od sposobu wywołania, a wymiana bazy danych lub frameworku nie
dotyka reguł biznesowych.

### 4.2. Egzekwowanie podziału

Podział warstwowy jest wart tyle, ile jego przestrzeganie. Aby nie pozostał
samą konwencją nazw katalogów, napisano zestaw testów
(`tests/test_architektura.py`), które analizują drzewo składniowe (AST) każdego
pliku źródłowego i **odrzucają zmianę** naruszającą reguły:

- warstwa `domain` nie może importować `flask` ani `sqlite3`,
- warstwa `api` nie może zawierać zapytań SQL,
- zmienne środowiskowe wolno czytać wyłącznie w `config.py`,
- każdy moduł musi mieć docstring,
- każdy plik `app/**/*.py` musi być śledzony przez git.

Ostatnia reguła powstała po realnym incydencie: niezakotwiczony wzorzec
`data/` w pliku `.gitignore` wykluczył z repozytorium cały nowo utworzony
pakiet `app/data/`. Testy lokalnie przechodziły, bo pliki istniały na dysku —
brak ujawnił się dopiero przy świeżym klonowaniu repozytorium.

### 4.3. Architektura wdrożeniowa

```
   przeglądarka
        │  :8080
        ▼
   ┌──────────┐   sieć wewnętrzna    ┌──────────────────┐
   │  nginx   │ ───────────────────► │ gunicorn + Flask │ ──► SQLite
   │  :80     │      :5000           │  (kontener)      │     (wolumen)
   └──────────┘                      └──────────────────┘
```

Kontener aplikacji **nie publikuje portu na hoście** — jedynym wejściem do
systemu jest nginx. Rozdzielenie ról jest celowe:

- nginx buforuje wolnych klientów (bez tego klient wysyłający żądanie bajt po
  bajcie blokuje proces gunicorna na czas całej transmisji), ogranicza rozmiar
  żądania i stanowi miejsce na terminację TLS;
- kompresję i nagłówki bezpieczeństwa ustawia **aplikacja**, nie nginx —
  zdublowanie ich w obu miejscach dałoby dwie polityki, które z czasem
  przestałyby być spójne.

---

## 5. Model danych

### 5.1. Tabele

| Tabela | Rola | Kluczowe kolumny |
|--------|------|------------------|
| `users` | Konta i role | `username` (unikalny), `password` (hash scrypt), `role` |
| `tickets` | Zgłoszenia | `title`, `description`, `category`, `priority`, `status`, `created_by`, `assigned_to`, `ai_pewnosc`, `sla_deadline` |
| `notes` | Notatki do zgłoszeń | `ticket_id`, `author_id`, `content`, `internal` |
| `audit_log` | Ścieżka audytu | `ticket_id`, `user_id`, `action`, `old_value`, `new_value`, `timestamp` |

Rola użytkownika jest ograniczona na poziomie schematu
(`CHECK(role IN ('pracownik','technik','admin'))`) — baza nie przyjmie wiersza
z rolą spoza zbioru, niezależnie od błędu w kodzie aplikacji.

### 5.2. Indeksy

Utworzono dziewięć indeksów pokrywających wszystkie realne wzorce dostępu:
filtrowanie po statusie, priorytecie i kategorii, listę zgłoszeń pracownika
(`created_by, id DESC`), filtry łączone (`status, priority`) oraz pobieranie
notatek i historii pojedynczego zgłoszenia. Wpływ tej zmiany na czas odpowiedzi
opisuje punkt 11.

### 5.3. Ścieżka audytu

Każda operacja zmieniająca stan zgłoszenia zapisuje wiersz w `audit_log`.
Wpisy pełnią **podwójną rolę**: są historią zgłoszenia dla technika oraz
źródłem danych o jakości kategoryzacji. Wpis bez `user_id` oznacza czynność
wykonaną przez moduł automatyczny, a nie przez człowieka — w historii
prezentowany jest jako „System AI".

---

## 6. Interfejs programistyczny (API)

### 6.1. Punkty końcowe

| Metoda | Ścieżka | Rola | Opis |
|--------|---------|------|------|
| GET | `/api/health` | — | Kontrola zdrowia (dla monitoringu) |
| POST | `/api/auth/login` | — | Logowanie, zwraca token JWT |
| GET | `/api/auth/me` | każdy | Odtworzenie sesji po odświeżeniu strony |
| GET | `/api/dashboard` | każdy | Statystyki i rozkład kategorii |
| GET | `/api/tickets` | każdy | Lista zgłoszeń, filtrowana wg roli |
| POST | `/api/tickets` | pracownik | Nowe zgłoszenie + kategoryzacja |
| GET | `/api/tickets/{id}` | każdy | Szczegóły zgłoszenia wraz z notatkami |
| PATCH | `/api/tickets/{id}` | technik/admin | Zmiana statusu, kategorii, przypisania |
| POST | `/api/tickets/{id}/notes` | technik/admin | Dodanie notatki |
| GET | `/api/tickets/{id}/audit` | technik/admin | Pełna ścieżka audytu |
| GET | `/api/ai/skutecznosc` | technik/admin | Skuteczność kategoryzacji |
| POST | `/api/ai/categorize` | każdy | Test kategoryzacji bez zapisu |

### 6.2. Kontrakt i jego weryfikacja

Źródłem prawdy o API jest plik `openapi.yaml` (OpenAPI 3.0), serwowany pod
adresem `/api/openapi.yaml`, z interaktywną dokumentacją Swagger UI pod
`/api/docs`. Pliki Swagger UI są dołączone do aplikacji — nie są pobierane
z zewnętrznej sieci CDN, dzięki czemu dokumentacja działa bez dostępu do
internetu i nie wymaga rozluźnienia polityki CSP.

Dokumentacja może rozminąć się z implementacją, dlatego napisano **testy
zgodności** (`tests/test_openapi.py`), które porównują specyfikację
z rzeczywistymi trasami aplikacji. Test kończy się niepowodzeniem, gdy trasa
istnieje, a nie została opisana — i odwrotnie.

### 6.3. Obsługa błędów

Każda ścieżka `/api/*` zwraca błędy w formacie JSON, również dla kodów
generowanych przez framework (404, 405, 429, 500). Domyślne strony HTML
Flaska łamałyby udokumentowany kontrakt. Treść wyjątku **nigdy** nie trafia do
klienta — mogłaby ujawnić szczegóły implementacji lub fragmenty danych.

Nieznana ścieżka `/api/...` zwraca kod 404 w JSON, a nie stronę `index.html`
z kodem 200 — była to jedna z wykrytych i naprawionych usterek: klient API nie
mógł odróżnić literówki w adresie od poprawnej odpowiedzi.

---

## 7. Cykl życia zgłoszenia

Zgłoszenie przechodzi przez zdefiniowany automat stanów. Próba przeskoczenia
etapu jest odrzucana przez API kodem 400 wraz z listą dozwolonych przejść.

```
   Nowe ──► W trakcie ──► Rozwiazane ──► Zamkniete
                 ▲   ╲         │
                 │    ╲        │ (ponowne otwarcie)
                 │     ▼       ▼
                 └── Wstrzymane
```

Reguły zapisano deklaratywnie w warstwie domenowej:

```python
TRANSITIONS = {
    "Nowe":       ["W trakcie"],
    "W trakcie":  ["Rozwiazane", "Wstrzymane"],
    "Wstrzymane": ["W trakcie"],
    "Rozwiazane": ["Zamkniete", "W trakcie"],
    "Zamkniete":  [],
}
```

Brak przejścia `Nowe → Zamkniete` jest decyzją projektową: zgłoszenie musi
przejść przez obsługę, ponieważ w przeciwnym razie ścieżka audytu nie
pokazywałaby, kto się nim faktycznie zajął.

Zmiana statusu z `Nowe` na `W trakcie` dodatkowo **przypisuje zgłoszenie
technikowi**, który jej dokonał — o ile zgłoszenie nie miało jeszcze opiekuna.

---

## 8. Mechanizm kluczowy — automatyczna kategoryzacja

To główny mechanizm projektu. Moduł przypisuje zgłoszeniu kategorię (jedną
z siedmiu), priorytet (jeden z czterech, przekładający się na termin SLA) oraz
**miarę pewności własnej decyzji**. Działa lokalnie — bez kluczy API, kosztów
i połączenia z internetem.

### 8.1. Zasada działania

1. **Normalizacja** — tekst sprowadzany jest do postaci bez polskich znaków
   diakrytycznych, aby „hasło", „haslo" i „HASŁA" trafiały w to samo słowo
   kluczowe.
2. **Zliczanie dowodów** — każde dopasowane słowo kluczowe dokłada punkty
   swojej kategorii. Decyduje **suma dowodów**, a nie pierwsze trafienie.
   Słowa mają wagi odpowiadające ich jednoznaczności: „phishing" (waga 3) mówi
   o zgłoszeniu znacznie więcej niż „mail" (waga 1).
3. **Eskalacja priorytetu** — priorytet wynika z najpoważniejszego dopasowania,
   a następnie jest podnoszony, jeśli tekst wskazuje na **skalę** awarii
   („cały dział", „nikt nie może") lub **pilność** („pilne", „natychmiast").
4. **Zasada bezpieczeństwa** — zgłoszenie zaklasyfikowane jako incydent
   bezpieczeństwa zawsze otrzymuje priorytet krytyczny. Zaniżenie priorytetu
   ransomware jest kosztowniejsze niż fałszywy alarm.
5. **Przyznanie się do niewiedzy** — przy braku przesłanek moduł nie zgaduje:
   zwraca pewność 0,0 i flagę `wymaga_weryfikacji`, kierując zgłoszenie do
   ręcznej weryfikacji technika.

Słowa kluczowe zapisane są jako **rdzenie bez końcówek** (`drukark`, `logowan`,
`uprawnien`), ponieważ język polski odmienia się przez przypadki — rdzeń
`drukark` trafia w „drukarka", „drukarki" i „drukarkę".

### 8.2. Listing 1 — funkcja `categorize()`

Pełna implementacja mechanizmu decyzyjnego
(plik [`app/domain/ai.py`](app/domain/ai.py); docstring skrócono na potrzeby
listingu, kod wykonywany jest identyczny ze źródłem):

```python
def categorize(title, description):
    """Zwraca kategorię, priorytet, pewność i uzasadnienie decyzji."""
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
```

Zwracane pole `dopasowania` zawiera słowa, które zadecydowały o klasyfikacji —
jest to **uzasadnienie decyzji** przedstawiane technikowi. Moduł nie działa
jak czarna skrzynka: pokazuje, na jakiej podstawie podjął decyzję.

### 8.3. Wykryty błąd — moduł nie rozumiał polszczyzny

Pomiar skuteczności ujawnił poważną usterkę. Słownik słów kluczowych zapisany
był bez polskich znaków (`haslo`, `siec`, `sprzet`), a dopasowanie polegało na
zwykłym wyszukiwaniu podciągu. Użytkownicy piszą natomiast z polskimi znakami —
w efekcie `"haslo"` **nie pasowało** do `"hasło"`, bo `ł` to inny znak niż `l`.

Poprawnie napisane zgłoszenie „Zapomniane hasło" nie dopasowywało się do
niczego i po cichu wpadało do kategorii domyślnej. Błąd był częściowo
zamaskowany: zgłoszenie trafiało czasem do właściwej kategorii **przez
przypadek**, ponieważ pasowało inne słowo.

Rozwiązaniem jest normalizacja tekstu wejściowego przed dopasowaniem. Litera
`ł` nie rozkłada się przez `unicodedata.normalize`, więc wymaga podmiany
wprost:

```python
def _bez_diakrytykow(tekst: str) -> str:
    tekst = tekst.replace("ł", "l").replace("Ł", "L")
    rozlozony = unicodedata.normalize("NFD", tekst)
    return "".join(z for z in rozlozony if unicodedata.category(z) != "Mn")
```

Osobny test pilnuje, aby żaden rdzeń w słowniku nie zawierał polskiego znaku —
taki rdzeń nigdy nie mógłby się dopasować.

### 8.4. Zmierzona skuteczność

| Miara | Przed naprawą | Po naprawie |
|-------|---------------|-------------|
| Kategoria — zbiór ewaluacyjny (29 zgłoszeń) | 79,3% | **100%** |
| Priorytet — zbiór ewaluacyjny | 79,3% | **100%** |
| Kategoria — **zbiór kontrolny** (18 zgłoszeń) | — | **94,4%** |
| Incydenty bezpieczeństwa rozpoznane | 2/5 | **5/5** |
| Zgłoszenia spoza IT oznaczone do weryfikacji | 0/3 | **3/3** |

**Zastrzeżenie metodologiczne.** Słownik był strojony na zbiorze ewaluacyjnym,
więc wynik 100% jest z definicji optymistyczny. Dlatego podano również wynik na
**zbiorze kontrolnym** — zgłoszeniach napisanych przed tą pracą i nieużywanych
do strojenia. To wartość **94,4%** należy traktować jako uczciwy szacunek
jakości modułu. Oba zbiory są małe; rzetelna ocena wymagałaby kilkuset
prawdziwych zgłoszeń.

### 8.5. Pomiar skuteczności na danych produkcyjnych

Ponieważ ocena na zbiorze kilkudziesięciu zgłoszeń jest niewystarczająca,
w system wbudowano mechanizm liczenia skuteczności z **rzeczywistej pracy
techników**. Każda ręczna zmiana kategorii zapisywana jest w ścieżce audytu
i stanowi sygnał pomyłki modułu na konkretnym zgłoszeniu. Punkt końcowy
`GET /api/ai/skutecznosc` zwraca na tej podstawie:

- liczbę zgłoszeń skategoryzowanych automatycznie,
- liczbę korekt wprowadzonych ręcznie,
- wyliczoną skuteczność,
- średnią pewność i liczbę zgłoszeń poniżej progu,
- **najczęstsze kierunki korekt** — wprost wskazujące, których słów kluczowych
  brakuje w słowniku.

Skuteczność nie jest zatem deklarowana, lecz **wyliczana z tego, jak często
człowiek poprawia maszynę**.

### 8.6. Decyzja projektowa: „nie działa" nie jest sygnałem pilności

Zwrot „nie działa" celowo **nie znajduje się** wśród fraz podnoszących
priorytet. Po polsku jest to domyślny sposób opisania dowolnej usterki
(„drukarka nie działa", „myszka nie działa"). Potraktowanie go jako sygnału
pilności podniosłoby priorytet niemal każdemu zgłoszeniu — a wtedy priorytety
przestałyby cokolwiek rozróżniać.

### 8.7. Możliwość podmiany na model językowy

Kontraktem modułu jest funkcja `categorize(title, description)` zwracająca
słownik o ustalonych polach. Zastąpienie mechanizmu słownikowego wywołaniem
modelu językowego wymaga wyłącznie podmiany wnętrza tej funkcji.

Istotna uwaga projektowa: wywołanie sieciowe na ścieżce tworzenia zgłoszenia
sprawia, że użytkownik czeka na odpowiedź obcej usługi. Taki model musiałby
mieć krótki limit czasu i awaryjne przejście do dopasowania słownikowego —
w przeciwnym razie awaria dostawcy zablokowałaby zakładanie zgłoszeń.

---

## 9. Bezpieczeństwo

System poddano audytowi według dwudziestopunktowej listy kontrolnej; pełne
wyniki wraz z uzasadnieniem każdej pozycji zawiera plik `SECURITY.md`.

### 9.1. Uwierzytelnianie i autoryzacja

| Obszar | Rozwiązanie |
|--------|-------------|
| Tożsamość | Token JWT podpisany HMAC-SHA256, ważność 8 godzin |
| Hasła | Funkcja `scrypt` (Werkzeug), hash nigdy nie opuszcza warstwy logowania |
| Klucz podpisu | Wymagany, minimum 32 bajty (RFC 7518 §3.2); brak lub zbyt krótki klucz generuje ostrzeżenie |
| Kontrola dostępu | Dekoratory `@login_required` i `@roles_required(...)` sprawdzane **serwerowo przy każdym żądaniu** |
| Limity logowania | 10/min na adres IP oraz 5/min na konto |

Interfejs użytkownika nie decyduje o uprawnieniach — jedynie odzwierciedla to,
na co pozwala serwer.

### 9.2. Listing 2 — twarda granica dostępu do danych

Najważniejszy fragment warstwy autoryzacji. Pracownik może widzieć wyłącznie
własne zgłoszenia i **nie da się tego ograniczenia obejść parametrami
zapytania** (plik [`app/data/tickets.py`](app/data/tickets.py)):

```python
def zbuduj_warunki(user, filtry):
    """Warunki WHERE zależne od roli.

    Dla pracownika ograniczenie do własnych zgłoszeń jest **pierwszym**
    warunkiem i nie da się go pominąć parametrami filtrowania — to twarda
    granica dostępu, nie ukrywanie danych w interfejsie.
    """
    warunki, params = [], []

    if user["role"] == "pracownik":
        warunki.append("t.created_by = ?")
        params.append(user["id"])
    else:
        for pole in ("status", "priority", "category"):
            wartosc = filtry.get(pole)
            if wartosc:
                warunki.append(f"t.{pole} = ?")
                params.append(wartosc)

    where = (" WHERE " + " AND ".join(warunki)) if warunki else ""
    return where, params
```

Konstrukcja ma trzy istotne własności:

1. **Ograniczenie roli jest bezwarunkowe** — dla pracownika warunek
   `created_by = ?` dodawany jest zawsze, niezależnie od przesłanych filtrów.
2. **Filtry są rozłączne z ograniczeniem** — pracownik w ogóle nie trafia do
   gałęzi przetwarzającej parametry zapytania, więc nie może ich użyć do
   rozszerzenia widocznego zbioru.
3. **Brak wstrzyknięcia SQL** — nazwy kolumn pochodzą ze stałej listy w kodzie,
   a wartości trafiają wyłącznie jako parametry zapytania (`?`), nigdy przez
   sklejanie łańcuchów.

Ta sama zasada obowiązuje na pulpicie: pracownik otrzymuje statystyki własnych
zgłoszeń, a nie liczby z całego systemu.

### 9.3. Zabezpieczenia warstwy HTTP

Aplikacja ustawia komplet nagłówków bezpieczeństwa: `Content-Security-Policy`
(skrypty wyłącznie z własnego serwera), `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy` oraz — po
włączeniu HTTPS — `Strict-Transport-Security`.

Odpowiedzi API otrzymują `Cache-Control: no-store`: odpowiedź zapisana
w pamięci podręcznej przeglądarki mogłaby zostać pokazana innemu użytkownikowi
tego samego urządzenia.

### 9.4. Usterki wykryte i naprawione

| Usterka | Konsekwencja |
|---------|--------------|
| Nagłówek `X-User-Id` jako uwierzytelnienie | Dowolna osoba mogła podszyć się pod dowolnego użytkownika, wpisując liczbę |
| Hasła przechowywane jawnym tekstem | Wyciek bazy oznaczał wyciek haseł |
| 15 znanych podatności w zależnościach (12 w PyJWT) | Biblioteka uwierzytelniająca każde żądanie |
| Dane wejściowe innego typu niż tekst | Błąd HTTP 500 zamiast czytelnego 400 |
| Skrypt zewnętrznej sieci CDN na każdej stronie | Przejęta CDN mogła odczytać token z przeglądarki |
| `GET /tickets` zwracał wszystkie zgłoszenia | Odpowiedź 9 MB przy 20 000 zgłoszeń — również wektor ataku DoS |
| Pulpit zwracał pracownikowi dane całej firmy | Naruszenie zasady najmniejszych uprawnień |

### 9.5. Decyzje świadome

Trzy rozwiązania celowo **nie** zostały wdrożone, mimo że bywają
rekomendowane:

- **Brak blokady konta po N nieudanych logowaniach** — napastnik znający nazwę
  użytkownika mógłby celowo odciąć prawdziwych użytkowników od systemu.
  Spowolnienie (throttling) chroni przed zgadywaniem hasła, nie dając
  jednocześnie narzędzia do blokowania ludzi.
- **Brak CAPTCHA** — narzędzie wewnętrzne o znanym gronie użytkowników.
  CAPTCHA dodaje zależność od podmiotu zewnętrznego i wysyła dane użytkowników
  na zewnątrz, nie adresując rzeczywistego zagrożenia.
- **Logowanie trwa około 100 ms** — to czas pracy funkcji `scrypt`.
  Przyspieszenie go osłabiłoby odporność na odgadywanie haseł. Jest to jedyne
  miejsce w systemie, w którym wolniej znaczy lepiej.

---

## 10. Testowanie i zapewnienie jakości

### 10.1. Struktura testów

```
   ┌──────────────────────────────────────────┐
   │  Warstwa 3 — testy E2E (21 sprawdzeń)    │  pełny przepływ przez
   │  demo.py, wymaga działającego serwera    │  działający serwer
   ├──────────────────────────────────────────┤
   │  Warstwa 2 — testy integracyjne (264)    │  Flask + baza danych
   │  API, autoryzacja, walidacja, wydajność  │
   ├──────────────────────────────────────────┤
   │  Warstwa 1 — testy jednostkowe (89)      │  czysta logika, bez I/O
   │  kategoryzacja, cykl życia, tokeny       │
   └──────────────────────────────────────────┘

   Razem: 353 testy pytest + 21 sprawdzeń E2E = 374 automatyczne kontrole
   Pokrycie kodu aplikacji: 100% (561 instrukcji)
```

Testy integracyjne przeważają nad jednostkowymi **celowo**. Logika biznesowa
jest w tym systemie cienka, a rzeczywiste ryzyko leży na styku HTTP ↔
uwierzytelnianie ↔ baza danych. Rozbicie tych testów na jednostkowe z atrapami
dałoby ładniejszą piramidę i słabszą ochronę.

### 10.2. Weryfikacja skuteczności testów

Sam fakt, że testy przechodzą, nie dowodzi, że cokolwiek wykrywają. Dlatego dla
testów krytycznych zastosowano **testowanie mutacyjne**: do kodu celowo
wprowadzano z powrotem naprawiony błąd i sprawdzano, czy zestaw testów
faktycznie się załamie, a następnie przywracano poprawną wersję. Procedurę
przeprowadzono dla testów bezpieczeństwa, testów zgodności ze specyfikacją
OpenAPI oraz testów architektury.

### 10.3. Ciągła integracja

Każdy `push` i każde zgłoszenie zmian na gałąź `main` uruchamia trzy niezależne
zadania:

| Zadanie | Zakres |
|---------|--------|
| Testy | Warstwy 1 i 2 z pomiarem pokrycia, następnie warstwa E2E wobec serwera gunicorn |
| Skanowanie zależności | `pip-audit --strict` wobec bazy podatności PyPI |
| Pełny stos | Uruchomienie Docker Compose (nginx + aplikacja) i weryfikacja działania |

---

## 11. Wydajność

### 11.1. Metoda pomiaru

Wygenerowano realistyczny wolumen danych — **20 000 zgłoszeń**, 4 000 notatek
i 20 000 wpisów audytu (baza 5,5 MB) — i zmierzono medianę z 15 wywołań każdego
punktu końcowego. Ten sam pomiar powtórzono po wprowadzeniu optymalizacji.

Wolumen jest celowo większy niż realny dla MŚP: przy 20 zgłoszeniach każda
implementacja wygląda dobrze, a problemy skalowania ujawniają się dopiero
wtedy, gdy na tanią poprawkę jest już za późno.

### 11.2. Wyniki

| Punkt końcowy | Przed | Po | Zmiana |
|---------------|-------|-----|--------|
| `GET /tickets` (technik) | 251,3 ms / **9 024 KB** | 4,9 ms / **22,6 KB** | **51× szybciej, 399× mniej danych** |
| `GET /tickets` (pracownik) | 85,4 ms / 2 969 KB | 9,5 ms / 22,6 KB | 9× szybciej |
| `GET /tickets?status=Nowe` | 49,6 ms / 1 812 KB | 5,8 ms / 22,4 KB | 8,5× szybciej |
| `GET /dashboard` | 37,1 ms | 22,1 ms | 1,7× szybciej |

Po włączeniu kompresji gzip odpowiedź o rozmiarze 17,6 KB zmniejszyła się do
**1,0 KB** (−95%).

### 11.3. Wprowadzone optymalizacje

1. **Stronicowanie listy zgłoszeń** — największy problem. Punkt końcowy
   zwracał wszystkie zgłoszenia; przy 20 000 rekordów dawało to odpowiedź 9 MB
   budowaną przy każdym żądaniu. Wprowadzono stronicowanie z górnym limitem
   200 rekordów na stronę.
2. **Indeksy bazy danych** — przed zmianą każde filtrowanie i każdy licznik na
   pulpicie oznaczały przeszukanie całej tabeli.
3. **Tryb WAL** — w domyślnym trybie dziennika pojedynczy zapis blokuje
   wszystkie odczyty, co przy kilku procesach gunicorna kończy się błędem
   „database is locked".
4. **Pulpit: pięć zapytań zastąpiono jednym** — liczniki wyliczane są jednym
   przejściem po tabeli.
5. **Kompresja gzip** — dla odpowiedzi tekstowych powyżej 1 KB.

---

## 12. Wdrożenie i uruchomienie

### 12.1. Uruchomienie w kontenerach (zalecane)

```bash
cp .env.example .env            # ustaw SECRET_KEY (min. 32 bajty)
docker compose up --build       # aplikacja na http://localhost:8080
docker compose exec helpdesk python seed.py   # dane demonstracyjne
```

### 12.2. Uruchamianie testów

```bash
py -m pytest                                  # testy jednostkowe i integracyjne
py -m pytest -m unit                          # wyłącznie warstwa szybka
py -m pytest --cov --cov-report=term          # z pomiarem pokrycia
BASE_URL=http://localhost:8080 py demo.py     # testy E2E, wymaga serwera
```

### 12.3. Konfiguracja

Cała konfiguracja środowiskowa odczytywana jest **wyłącznie** w pliku
`app/config.py`. Wcześniej zmienne były rozproszone po czterech modułach
i odpowiedź na pytanie „czym w ogóle da się skonfigurować tę aplikację"
wymagała przeszukania całego projektu.

| Zmienna | Znaczenie | Wartość domyślna |
|---------|-----------|------------------|
| `SECRET_KEY` | Klucz podpisujący tokeny (min. 32 bajty) | wymagana |
| `DB_PATH` | Ścieżka pliku bazy danych | `helpdesk.db` |
| `FORCE_HTTPS` | Przekierowanie na HTTPS i nagłówek HSTS | wyłączone |
| `TRUST_PROXY` | Odczyt adresu klienta z `X-Forwarded-For` | wyłączone |
| `RATELIMIT_STORAGE_URI` | Wspólny magazyn liczników limitów | `memory://` |

Dwa przełączniki są domyślnie wyłączone z powodów bezpieczeństwa:
`TRUST_PROXY` włączony przy bezpośrednim wystawieniu aplikacji pozwoliłby
podrobić nagłówek `X-Forwarded-For` i obejść limity żądań, natomiast HSTS
wysłany po HTTP jest ignorowany, a lokalnie potrafi zablokować dostęp do
`localhost`.

---

## 13. Wyniki

| Obszar | Rezultat |
|--------|----------|
| Skuteczność kategoryzacji | 94,4% na zbiorze kontrolnym; 5/5 incydentów bezpieczeństwa rozpoznanych |
| Wydajność | 51-krotne przyspieszenie listy zgłoszeń, 399-krotna redukcja wielkości odpowiedzi |
| Bezpieczeństwo | Audyt 20-punktowy; usunięto uwierzytelnianie możliwe do podrobienia, hasła jawnym tekstem i 15 znanych podatności |
| Jakość kodu | 374 automatyczne kontrole, 100% pokrycia, podział warstwowy egzekwowany testami |
| Powtarzalność | Pełny stos uruchamiany jednym poleceniem, weryfikowany w CI |

Wartością projektu jest nie tylko działający system, ale też **weryfikowalność
postawionych tez**: skuteczność kategoryzacji zmierzono na zbiorze kontrolnym,
zyski wydajnościowe udokumentowano pomiarem przed i po, a skuteczność samych
testów potwierdzono testowaniem mutacyjnym.

---

## 14. Ograniczenia i kierunki rozwoju

### 14.1. Ograniczenia obecnego rozwiązania

- **Kategoryzacja słownikowa** rozpoznaje wyłącznie zjawiska opisane słowami
  z listy. Nowe określenie problemu (np. nazwa nowego systemu firmowego)
  wymaga uzupełnienia słownika. Moduł nie rozumie kontekstu ani zaprzeczeń.
- **Zbiory oceny są małe** (29 i 18 zgłoszeń). Rzetelna ocena wymagałaby
  kilkuset prawdziwych zgłoszeń — stąd wbudowany mechanizm pomiaru na danych
  produkcyjnych.
- **SQLite serializuje zapisy** nawet w trybie WAL. Przy skali MŚP jest to
  wystarczające, natomiast stanowi górną granicę skalowania.
- **Brak powiadomień** (poczta elektroniczna, komunikator) o przekroczeniu SLA.

### 14.2. Kierunki dalszych prac

1. **Migracja SQLite → PostgreSQL** — warunek konieczny dla wdrożenia
   całodobowego. Na efemerycznym systemie plików platformy PaaS baza SQLite
   traci dane przy każdym restarcie. Ta jedna decyzja odblokowuje jednocześnie
   hosting i dalsze podnoszenie wydajności.
2. **Wdrożenie produkcyjne 24/7** wraz z terminacją TLS.
3. **Infrastruktura jako kod** (Terraform) — powtarzalne tworzenie środowiska.
4. **Rozbudowa kategoryzacji** o model językowy, z zachowaniem awaryjnego
   przejścia do mechanizmu słownikowego (p. 8.7).
5. **Powiadomienia o zbliżającym się terminie SLA.**

---

## 15. Dokumentacja szczegółowa

Niniejszy dokument stanowi opracowanie całościowe. Poszczególne zagadnienia
opisano szczegółowo w osobnych plikach repozytorium:

| Plik | Zawartość |
|------|-----------|
| [`README.md`](README.md) | Przegląd, szybki start, rozwiązywanie problemów |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Warstwy, uzasadnienie nginx, CI/CD |
| [`SECURITY.md`](SECURITY.md) | Audyt 20-punktowy z uzasadnieniem każdej pozycji |
| [`PERFORMANCE.md`](PERFORMANCE.md) | Metoda pomiaru, wyniki, optymalizacje |
| [`AI.md`](AI.md) | Kategoryzacja: działanie, skuteczność, ograniczenia |
| [`TESTING.md`](TESTING.md) | Piramida testów, pokrycie, testy mutacyjne |
| [`openapi.yaml`](openapi.yaml) | Formalna specyfikacja API (OpenAPI 3.0) |

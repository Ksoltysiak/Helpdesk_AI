# Architektura

Dokument opisuje strukturę projektu po podziale na warstwy oraz sposób
uruchomienia produkcyjnego (nginx + aplikacja).

**Data:** 26 sierpnia 2026

---

## Dlaczego podział na warstwy

Wcześniej projekt był płaski: `routes.py` miał **443 linie** i mieszał trzy
odpowiedzialności — obsługę HTTP, reguły biznesowe i SQL. Konfiguracja była
rozproszona po **czterech modułach**, więc na pytanie „czym da się
skonfigurować tę aplikację" nie dało się odpowiedzieć bez przeszukania
całego projektu.

Najpoważniejsza konsekwencja była praktyczna: zapytania SQL budowane w trasach
omijały jedyne miejsce, w którym pilnowana jest granica dostępu. Łatwo było
dopisać endpoint, który przypadkiem pokazuje cudze zgłoszenia.

---

## Warstwy

```
app/
├── config.py          Cała konfiguracja środowiskowa — jedno miejsce
├── extensions.py      Rozszerzenia Flaska (limiter)
├── __init__.py        Fabryka aplikacji: nagłówki, kompresja, cache, HTTPS
│
├── api/               WARSTWA HTTP — trasy, walidacja żądań, kody odpowiedzi
│   ├── auth.py            logowanie, odtwarzanie sesji
│   ├── tickets.py         zgłoszenia, notatki, audyt
│   ├── meta.py            kontrola zdrowia, pulpit, moduł AI
│   ├── validation.py      sprawdzanie typów i długości pól
│   └── errors.py          błędy zawsze w JSON dla /api/*
│
├── domain/            REGUŁY BIZNESOWE — bez HTTP, bez bazy
│   ├── ai.py              kategoryzacja zgłoszeń
│   └── tickets.py         cykl życia zgłoszenia (maszyna stanów)
│
├── data/              DOSTĘP DO DANYCH — cały SQL
│   ├── database.py        połączenie, schemat, indeksy, migracje
│   ├── tickets.py         zapytania o zgłoszenia i notatki
│   ├── users.py           zapytania o użytkowników
│   └── audit.py           ścieżka audytu i statystyki skuteczności AI
│
└── security/          KONTROLA DOSTĘPU
    ├── tokens.py          wystawianie i weryfikacja JWT
    └── decorators.py      login_required, roles_required
```

Zależności biegną **w jedną stronę**:

```
api  ──>  domain,  data,  security
data ──>  (tylko baza danych)
domain ──> nic z aplikacji
```

Warstwa domenowa nie importuje Flaska ani `sqlite3` — reguły biznesowe da się
testować i czytać bez uruchamiania czegokolwiek. To ta część, która przetrwa
zmianę frameworka albo bazy.

### Podział jest egzekwowany testami

Sam podział na katalogi rozjeżdża się po kilku tygodniach. `tests/test_architektura.py`
sprawdza automatycznie, że:

- warstwa domenowa nie importuje `flask`, `sqlite3` ani innych warstw,
- warstwa danych nie zależy od warstwy HTTP,
- **w warstwie HTTP nie ma SQL-a**,
- zmienne środowiskowe czyta wyłącznie `config.py`,
- każdy moduł ma docstring mówiący, za co odpowiada.

Test SQL-a wykrył realny przeciek już przy pierwszym uruchomieniu: kontrola
zdrowia wykonywała `SELECT 1` bezpośrednio w trasie. Zapytanie przeniesiono
do `data/database.py`.

---

## Uruchomienie produkcyjne: nginx + aplikacja

```
             :8080
Przeglądarka ──────> nginx ──────> gunicorn (2 procesy) ──> SQLite
                     (proxy)        aplikacja Flask         (wolumen)
```

Aplikacja **nie publikuje portu na host** — ruch wchodzi wyłącznie przez nginx.
Bezpośrednie połączenie z `localhost:5000` nie działa.

### Po co osobna warstwa nginx

Gunicorn sam obsługuje HTTP, więc warto wiedzieć, co dokłada proxy:

| Funkcja | Znaczenie |
|---|---|
| **Buforowanie wolnych klientów** | Bez tego klient wysyłający żądanie bajt po bajcie zajmuje workera gunicorna na cały czas transmisji. Przy 2 workerach wystarczy dwóch takich klientów, by zablokować usługę. |
| **Miejsce na TLS** | Certyfikat kończy się na nginx; aplikacja nie musi nic o nim wiedzieć. |
| **Limit rozmiaru żądania** | `client_max_body_size 1m` odcina duże ładunki, zanim dotrą do aplikacji. |
| **Limity czasu** | Zerwane połączenia nie trzymają zasobów w nieskończoność. |
| **Jeden punkt wejścia** | Gdy dojdą kolejne usługi, adresacja się nie zmienia. |

### Świadome decyzje w konfiguracji

**Kompresja po stronie aplikacji, nie nginx.** Aplikacja zna typ odpowiedzi
i próg opłacalności; podwójne pakowanie kosztowałoby tylko CPU. W nginx
`gzip off`.

**Nagłówki bezpieczeństwa tylko w aplikacji.** Dublowanie ich w nginx
prowadziłoby do dwóch rozjeżdżających się polityk. Jedno źródło prawdy.

**`TRUST_PROXY=1` włączone dopiero za nginx.** Bez tego aplikacja widzi adres
proxy zamiast klienta i **wszyscy użytkownicy dzielą jeden licznik limitu
logowania** — jeden atakujący zablokowałby wszystkim logowanie. Ustawienie
jest jawne, bo zaufanie do `X-Forwarded-For` przy aplikacji wystawionej wprost
do sieci pozwoliłoby ten nagłówek podrobić i obejść limity.

**Kontrola zdrowia poza logiem dostępu.** Sonda odpytuje `/api/health` co
kilkanaście sekund i zaśmiecałaby zapis.

---

## CI/CD

`.github/workflows/tests.yml` uruchamia się przy każdym pushu na `main`
i przy każdym pull requeście:

| Zadanie | Zakres |
|---|---|
| **Testy** | Jednostkowe, integracyjne i architektoniczne + raport pokrycia; osobno E2E przy działającym serwerze |
| **Skanowanie zależności** | `pip-audit --strict` względem bazy podatnosci PyPI |
| **Pełny stos** | `docker compose up` z nginx; sprawdza zdrowie przez proxy, brak uprawnień root, dostępność dokumentacji i frontendu |
| **Publikacja obrazu (CD)** | Tylko z `main`, tylko gdy wszystko powyżej przeszło i tylko po włączeniu (opis niżej) — obraz trafia do GHCR ze znacznikiem `latest` oraz SHA commita |

### Publikacja obrazu — domyślnie wyłączona i dlaczego

Krok CD uruchamia się tylko wtedy, gdy w repozytorium istnieje zmienna
`PUBLIKUJ_OBRAZ` o wartości `true`. **Domyślnie jej nie ma** i tak ma zostać
do czasu wyboru docelowego hostingu — dopóki nic nie pobiera obrazu,
publikowanie go niczemu nie służy.

Zapis do rejestru GHCR wymaga podniesienia uprawnień domyślnego tokenu
(*Settings → Actions → General → Workflow permissions → Read and write*).
Warto wiedzieć, co to naprawdę oznacza, zanim się je włączy:

| Skutek | Znaczenie |
|---|---|
| Ustawienie działa **na całe repozytorium** | Podnosi pułap uprawnień dla *każdego* przebiegu, także zadań testowych, które zapisu nie potrzebują |
| Obejmuje przebiegi z pull requestów | Dla PR-ów z gałęzi **w tym samym repozytorium** token dziedziczy to ustawienie (PR-y z forków zawsze dostają token tylko do odczytu) |
| Workflow bierze się z gałęzi PR-a | Współpracownik może w PR zmienić `.github/workflows/` i uruchomić własny kod z tokenem mającym prawo zapisu — do repozytorium, pakietów i wydań |

Przy zespole pracującym na gałęziach w tym samym repozytorium jest to realna
ścieżka podniesienia uprawnień — ta sama klasa ryzyka, przed którą chroni
ochrona gałęzi.

**Zalecenie:** zostawić uprawnienia domyślne (tylko odczyt) i nie tworzyć
zmiennej, dopóki nie ma dokąd wdrażać.

Gdy przyjdzie czas na wdrożenie, bezpieczniejszy wariant niż podnoszenie
uprawnień całego repozytorium to token PAT o wąskim zakresie (`packages:write`)
trzymany jako sekret i używany wyłącznie przez zadanie publikujące — najlepiej
w **Environment** z wymaganą akceptacją, żeby pull request nie mógł go użyć.

Stos testowany jest przez `docker compose`, a nie jako sam kontener aplikacji:
błąd w konfiguracji nginx albo w połączeniu między usługami nie ujawniłby się
przy uruchomieniu samego obrazu.

Znacznik z SHA commita pozwala wdrożyć dokładnie tę wersję i wrócić do
poprzedniej, gdy coś pójdzie nie tak.

---

## Punkty wejścia

| Plik | Rola |
|---|---|
| `wsgi.py` | Wejście dla gunicorna (`gunicorn wsgi:app`) i uruchomienia lokalnego |
| `seed.py` | Wypełnienie bazy danymi startowymi |
| `demo.py` | Testy E2E; adres konfigurowalny zmienną `BASE_URL` |

---

## Czego ta struktura nie rozwiązuje

- **SQLite pozostaje pojedynczym plikiem.** Podział na warstwy ułatwia
  późniejszą zmianę bazy (cały SQL jest w `data/`), ale jej nie wykonuje.
- **Brak warstwy serwisów.** Logika tworzenia zgłoszenia jest nadal w trasie
  `api/tickets.py`. Przy tej wielkości osobna warstwa serwisów byłaby
  ceremonią bez treści — warto ją dodać, gdy reguły się rozrosną.
- **Nginx nie terminuje TLS** w obecnej konfiguracji — to miejsce jest
  przygotowane, ale certyfikat trzeba dołożyć przy wdrożeniu.

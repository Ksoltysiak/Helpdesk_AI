# Inteligentny HelpDesk IT

Back-end + front-end systemu HelpDesk dla MŚP: REST API w technologii
**Flask + SQLite** z interfejsem użytkownika HTML/CSS/JS. Obsługuje pełny cykl
życia zgłoszenia IT, kontrolę dostępu opartą na rolach (RBAC), automatyczną
kategoryzację zgłoszeń przez moduł AI oraz pełną ścieżkę audytu.

---

## Spis treści

- [Struktura plików](#struktura-plików)
- [Szybki start (Docker)](#szybki-start-docker)
- [Szybki start (lokalnie, bez Dockera)](#szybki-start-lokalnie-bez-dockera)
- [Testy](#testy)
- [Weryfikacja działania](#weryfikacja-działania)
- [Architektura](#architektura)
- [Bezpieczeństwo](#bezpieczeństwo)
- [Wydajność](#wydajność)
- [Role użytkowników](#role-użytkowników)
- [Punkty końcowe API](#punkty-końcowe-api)
- [Cykl życia zgłoszenia](#cykl-życia-zgłoszenia-dozwolone-przejścia-statusów)
- [Kategoryzacja AI](#kategoryzacja-ai)
- [Dane testowe (logowanie)](#dane-testowe-logowanie)
- [Rozwiązywanie problemów](#rozwiązywanie-problemów)

---

## Struktura plików

| Ścieżka                | Odpowiada za                                              |
|------------------------|------------------------------------------------------------|
| `app/api/`             | Warstwa HTTP — trasy, walidacja żądań, obsługa błędów      |
| `app/domain/`          | Reguły biznesowe — kategoryzacja AI, cykl życia zgłoszenia |
| `app/data/`            | Dostęp do bazy — schemat, zapytania, migracje              |
| `app/security/`        | Tokeny JWT i kontrola dostępu                              |
| `app/config.py`        | Cała konfiguracja środowiskowa w jednym miejscu            |
| `app/__init__.py`      | Fabryka aplikacji — nagłówki, kompresja, cache, HTTPS      |
| `wsgi.py`              | Punkt wejścia dla gunicorna                                |
| `deploy/nginx/`        | Konfiguracja odwrotnego proxy                              |
| `openapi.yaml`         | Specyfikacja API — źródło prawdy dla dokumentacji          |
| `ARCHITECTURE.md`      | Podział na warstwy, nginx, CI/CD                           |
| `SECURITY.md`          | Audyt bezpieczeństwa — weryfikacja 20 zabezpieczeń         |
| `PERFORMANCE.md`       | Pomiary wydajności i wprowadzone optymalizacje             |
| `AI.md`                | Moduł kategoryzacji — działanie, skuteczność, ograniczenia |
| `seed.py`              | Wypełnienie bazy danymi testowymi                          |
| `demo.py`              | Testy E2E (adres przez `BASE_URL`)                         |
| `tests/`               | Testy jednostkowe, integracyjne i architektoniczne         |
| `frontend/`            | Interfejs użytkownika (HTML + CSS + JS)                    |

---

## Szybki start (Docker)

Wymaga zainstalowanego **Docker** / **Docker Desktop**.

**1. Skonfiguruj zmienne środowiskowe:**

```bash
cp .env.example .env
# Ustaw SECRET_KEY w pliku .env na długi, losowy ciąg znaków
```

**2. Uruchom:**

```bash
docker compose up --build
```

**3. Wypełnij bazę danych:**

```bash
docker compose exec helpdesk python seed.py
```

Aplikacja będzie dostępna pod **`http://localhost:8080`** (przez nginx).
Sama aplikacja nie publikuje portu na host — ruch wchodzi wyłącznie przez proxy. Baza danych SQLite jest
przechowywana w trwałym wolumenie `helpdesk-data` — dane przetrwają restart
kontenera.

Zatrzymanie:

```bash
docker compose down
```

---

## Szybki start (lokalnie, bez Dockera)

Wymagany **Python 3.8+**.

```bash
cp .env.example .env          # ustaw SECRET_KEY
py -m pip install -r requirements.txt
py seed.py                    # tworzy i wypełnia bazę danymi testowymi
py wsgi.py                    # startuje serwer na http://127.0.0.1:5000
```

---

## Testy

Projekt ma zestaw **296 automatycznych sprawdzeń** w trzech warstwach
(275 testów `pytest` + 21 sprawdzeń E2E), przy **100% pokryciu kodu aplikacji**.

```bash
py -m pip install -r requirements-dev.txt
py -m pytest
```

| Warstwa | Liczba | Zakres |
|---|---|---|
| Jednostkowe | 85 | Kategoryzacja AI i jej skuteczność, tokeny JWT, maszyna stanów |
| Integracyjne | 252 | Flask + baza: RBAC, walidacja, nagłówki, limity, stronicowanie, indeksy, zgodność dokumentacji |
| E2E (`demo.py`) | 21 | Pełny przepływ przez działający serwer |

Testy uruchamiają się automatycznie przy każdym pull requeście
(`.github/workflows/tests.yml`).

Pełny opis — zakres każdej warstwy, raport pokrycia, weryfikacja mutacyjna
i znane ograniczenia — znajduje się w pliku **[TESTING.md](TESTING.md)**.
Wyniki audytu bezpieczeństwa: **[SECURITY.md](SECURITY.md)**,
pomiary wydajności: **[PERFORMANCE.md](PERFORMANCE.md)**.

---

## Weryfikacja działania

Gdy serwer działa, skrypt `demo.py` sprawdza wszystkie operacje API — logowanie
JWT, kategoryzację AI, przejścia statusów, ścieżkę audytu oraz testy negatywne
(brak tokenu, podrobiony token, przekroczone limity długości, nieznany endpoint):

```bash
BASE_URL=http://localhost:8080 py demo.py
```

Oczekiwany wynik:

```
WYNIK: 21 testow OK, 0 bledow
```

Ręczne sprawdzenie endpointów (wymaga najpierw zalogowania się i pobrania tokenu):

```bash
# Zaloguj się i zapisz token
TOKEN=$(curl -s -X POST http://localhost:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"m.lewandowski","password":"tech123"}' \
  | python -c "import json,sys; print(json.load(sys.stdin)['token'])")

# Użyj tokenu w nagłówku Authorization
curl http://localhost:8080/api/dashboard \
  -H "Authorization: Bearer $TOKEN"
```

---

## Architektura

Projekt jest podzielony na warstwy o jednokierunkowych zależnościach:

```
api  ──>  domain,  data,  security      (warstwa HTTP)
data ──>  tylko baza danych             (cały SQL)
domain ──> nic z aplikacji              (reguły biznesowe)
```

Uruchomienie produkcyjne: **nginx** jako odwrotne proxy przed **gunicornem**.
Aplikacja nie jest wystawiona bezpośrednio.

Podział jest **egzekwowany testami** — `tests/test_architektura.py` sprawdza
m.in., że w warstwie HTTP nie ma SQL-a, a warstwa domenowa nie importuje
Flaska. Pełny opis: **[ARCHITECTURE.md](ARCHITECTURE.md)**.

---

## Bezpieczeństwo

| Mechanizm | Implementacja |
|-----------|---------------|
| Hashowanie haseł | `werkzeug` scrypt — brak plaintext w bazie |
| Uwierzytelnianie | JWT (HS256, ważność 8h) — weryfikowane po stronie serwera przy każdym żądaniu |
| Klucz podpisujący | `SECRET_KEY` wymagany; ostrzeżenie przy kluczu krótszym niż 32 bajty |
| Izolacja danych | Pracownik widzi wyłącznie własne zgłoszenia — filtrowanie w zapytaniu SQL, nie w interfejsie |
| Ochrona przed IDOR | Odczyt cudzego zgłoszenia kończy się kodem 403 |
| Manipulacja polami | Status, priorytet, kategoria i autor ustawiane wyłącznie po stronie serwera |
| Ograniczanie żądań | Dwa limity: 10/min na adres IP **oraz** 5/min na konto (chroni przed rozproszonym zgadywaniem hasła) |
| Zapytania SQL | Wyłącznie parametryzowane — brak sklejania wartości |
| Walidacja wejścia | Sprawdzanie typu i długości; nieprawidłowe dane dają 400 w JSON, nigdy 500 |
| Escapowanie treści | Dane użytkownika renderowane przez `escHtml()` — zweryfikowane testem XSS |
| Nagłówki HTTP | `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Content-Security-Policy`, `Permissions-Policy`, `Strict-Transport-Security` (przy HTTPS) |
| HTTPS | Przekierowanie 308 + HSTS po ustawieniu `FORCE_HTTPS=1` |
| CORS | Brak — frontend serwowany z tego samego serwera (same-origin) |
| Ciasteczka | Nieużywane — brak sesji serwerowej, token w `sessionStorage` |
| Odpowiedzi błędów | Zawsze JSON dla `/api/*`; treść wyjątku nigdy nie trafia do klienta |
| Docker | Proces gunicorn działa jako użytkownik bez uprawnień root |
| Zależności | `pip-audit` w CI + Dependabot (pip, Docker, GitHub Actions) |

**Wymaganie produkcyjne:** wygeneruj `SECRET_KEY` poleceniem:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

**Przy wdrożeniu za HTTPS/proxy** ustaw dodatkowo (opis w `.env.example`):

| Zmienna | Kiedy włączyć |
|---|---|
| `FORCE_HTTPS=1` | Gdy aplikacja ma certyfikat TLS — włącza przekierowanie i HSTS |
| `TRUST_PROXY=1` | **Tylko** za odwrotnym proxy — inaczej `X-Forwarded-For` można podrobić i obejść limity |
| `RATELIMIT_STORAGE_URI` | Przy `--workers > 1` — bez wspólnego magazynu każdy proces liczy limit osobno |

---

## Wydajność

Back-end został zmierzony na **20 000 zgłoszeń** i zoptymalizowany —
szczegółowe wyniki w pliku **[PERFORMANCE.md](PERFORMANCE.md)**.

| Mechanizm | Efekt |
|---|---|
| Stronicowanie listy (`page`, `per_page`) | Odpowiedź 9 MB → 23 KB |
| Indeksy bazy danych | Filtrowanie 8,5× szybsze |
| Tryb WAL + `busy_timeout` | Odczyt równolegle z zapisem, brak „database is locked" |
| Pulpit jednym zapytaniem | 5 zapytań → 1 |
| Kompresja gzip | −95% rozmiaru odpowiedzi |
| Nagłówki cache | Pliki statyczne cache'owane, dane API — nigdy |

> Czas logowania (~100 ms) **nie jest** optymalizowany celowo — to koszt
> hashowania `scrypt`, które ma być wolne, by utrudnić zgadywanie haseł.

---

## Role użytkowników

| Rola        | Uprawnienia                                                           |
|-------------|------------------------------------------------------------------------|
| `pracownik` | Tworzenie zgłoszeń, podgląd **wyłącznie własnych** zgłoszeń            |
| `technik`   | Podgląd wszystkich zgłoszeń, zmiana statusu/kategorii, notatki, audyt  |
| `admin`     | Pełny dostęp                                                           |

---

## Punkty końcowe API

**Pełna, interaktywna dokumentacja:** po uruchomieniu aplikacji dostępna pod
adresem **`http://localhost:8080/api/docs`** (Swagger UI). Można z niej wysyłać
prawdziwe żądania — wystarczy zalogować się przez `POST /auth/login`, skopiować
token i wkleić go przyciskiem **Authorize**.

Źródłem prawdy jest plik **[`openapi.yaml`](openapi.yaml)** (OpenAPI 3.0),
serwowany również pod `/api/openapi.yaml`. Poniższa tabela to skrót
orientacyjny — jej zgodność ze specyfikacją pilnuje test automatyczny
(`tests/test_openapi.py`).

| Metoda | Ścieżka                   | Rola          | Opis                                      |
|--------|----------------------------|---------------|---------------------------------------------|
| GET    | `/api/health`              | —             | Kontrola zdrowia (dla load balancera)       |
| POST   | `/api/auth/login`          | —             | Logowanie — zwraca JWT token                |
| GET    | `/api/auth/me`             | każdy         | Dane zalogowanego użytkownika (odtworzenie sesji) |
| GET    | `/api/dashboard`           | każdy         | Statystyki + rozkład kategorii              |
| GET    | `/api/tickets`             | każdy         | Lista zgłoszeń (filtrowana wg roli)         |
| POST   | `/api/tickets`             | pracownik     | Nowe zgłoszenie + kategoryzacja AI          |
| GET    | `/api/tickets/{id}`        | każdy         | Szczegóły zgłoszenia + notatki              |
| PATCH  | `/api/tickets/{id}`        | technik/admin | Zmiana statusu / kategorii / przypisania    |
| POST   | `/api/tickets/{id}/notes`  | technik/admin | Notatka (wewnętrzna lub widoczna)           |
| GET    | `/api/tickets/{id}/audit`  | technik/admin | Pełna ścieżka audytu                        |
| GET    | `/api/ai/skutecznosc`      | technik/admin | Skuteczność AI liczona z korekt techników   |
| POST   | `/api/ai/categorize`       | każdy         | Test modułu AI na dowolnym tekście          |

**Autoryzacja:** każde żądanie (poza logowaniem) wymaga nagłówka:
```
Authorization: Bearer <token>
```
Token jest zwracany przez endpoint `/api/auth/login`.

**Filtry dla `GET /api/tickets`** (tylko technik/admin):
`?status=Nowe`, `?priority=Krytyczny`, `?category=Siec`.

---

## Cykl życia zgłoszenia (dozwolone przejścia statusów)

```
Nowe → W trakcie → Rozwiazane → Zamkniete
              ↘ Wstrzymane ↗
```

Próba przeskoczenia etapu (np. `Nowe → Zamkniete`) jest odrzucana przez API
z kodem 400 i listą dozwolonych przejść.

---

## Kategoryzacja AI

**Skuteczność:** 100% na zbiorze ewaluacyjnym (29 zgłoszeń), **94,4% na zbiorze
kontrolnym** nieużywanym do strojenia. Pełny opis działania, pomiary
i ograniczenia: **[AI.md](AI.md)**.

Moduł `ai.py` przy każdym nowym zgłoszeniu automatycznie nadaje **kategorię**
(Sprzęt, Oprogramowanie, Sieć, Poczta, Konta i dostęp, Bezpieczeństwo,
Peryferia) oraz **priorytet** (Niski, Średni, Wysoki, Krytyczny). Priorytet
wyznacza termin SLA. Domyślnie moduł działa lokalnie (bez kluczy API i
kosztów); w pliku `ai.py` opisano, jak podłączyć prawdziwy model językowy
(np. OpenAI) bez zmian w reszcie back-endu.

Moduł zwraca też **pewność** swojej decyzji i listę słów, które o niej
zadecydowały. Gdy nic nie pasuje, zamiast zgadywać oznacza zgłoszenie jako
wymagające weryfikacji — w interfejsie widoczne jako znacznik **„AI ?"**.

**Zasada triażu:** gdy zgłoszenie pasuje do kilku słów kluczowych naraz,
decyduje suma dowodów, a zgłoszenia bezpieczeństwa zawsze dostają priorytet
krytyczny (SLA 1h). Priorytet jest podnoszony, gdy w treści widać skalę awarii
(„cały dział") lub pilność („nie włącza się", „pilne").

**Pomiar na żywo:** `GET /api/ai/skutecznosc` liczy jakość modułu z ręcznych
korekt techników i wskazuje, które kategorie mylą się najczęściej.

---

## Dane testowe (logowanie)

Dostępne po uruchomieniu `seed.py`. Hasła są hashowane — poniżej podane są
oryginalne wartości do zalogowania się przez interfejs.

| Login          | Hasło    | Rola      |
|-----------------|----------|-----------|
| k.nowak         | haslo123 | pracownik |
| p.wisniewski    | haslo123 | pracownik |
| a.kowalczyk     | haslo123 | pracownik |
| m.lewandowski   | tech123  | technik   |
| j.zielinska     | tech123  | technik   |
| admin           | admin123 | admin     |

---

## Rozwiązywanie problemów

| Komunikat                                        | Rozwiązanie                                                  |
|---------------------------------------------------|--------------------------------------------------------------|
| `required variable SECRET_KEY is missing`        | Skopiuj `.env.example` do `.env` i ustaw `SECRET_KEY`        |
| `'py' nie jest rozpoznawane...`                  | Zainstaluj Pythona z python.org, zaznacz „Add to PATH"       |
| `No module named flask`                          | Wpisz `py -m pip install -r requirements.txt`                |
| `Address already in use` / port zajęty           | Zamknij poprzedni serwer (Ctrl+C w jego terminalu)           |
| `401 Wymagana autoryzacja`                       | Token wygasł lub nie podano — zaloguj się ponownie           |
| `429 Too Many Requests`                          | Zbyt wiele prób logowania — odczekaj minutę                  |

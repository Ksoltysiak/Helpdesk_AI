# Inteligentny HelpDesk IT

Back-end + front-end systemu HelpDesk dla MŚP: REST API w technologii
**Flask + SQLite** z interfejsem użytkownika HTML/CSS/JS. Obsługuje pełny cykl
życia zgłoszenia IT, kontrolę dostępu opartą na rolach (RBAC), automatyczną
kategoryzację zgłoszeń przez moduł AI oraz pełną ścieżkę audytu.

System jest skonteneryzowany w architekturze wielokontenerowej **Nginx (Reverse Proxy) + Flask Backend**, z automatycznym monitoringiem zdrowia (Healthcheck) oraz potokiem CI/CD.

---

## Spis treści

- [Struktura projektu](#struktura-projektu)
- [Architektura DevOps & Konteneryzacja](#architektura-devops--konteneryzacja)
- [Szybki start (Docker Compose)](#szybki-start-docker-compose)
- [Automatyzacja deweloperska (Makefile)](#automatyzacja-deweloperska-makefile)
- [Szybki start (lokalnie, bez Dockera)](#szybki-start-lokalnie-bez-dockera)
- [Testy](#testy)
- [Weryfikacja działania](#weryfikacja-działania)
- [Potok CI/CD (GitHub Actions)](#potok-cicd-github-actions)
- [Bezpieczeństwo](#bezpieczeństwo)
- [Role użytkowników](#role-użytkowników)
- [Punkty końcowe API](#punkty-końcowe-api)
- [Cykl życia zgłoszenia](#cykl-życia-zgłoszenia-dozwolone-przejścia-statusów)
- [Kategoryzacja AI](#kategoryzacja-ai)
- [Dane testowe (logowanie)](#dane-testowe-logowanie)

---

## Struktura projektu

```
Helpdesk_AI/
├── backend/                    # Warstwa serwerowa (Python/Flask)
│   ├── app.py                  # Punkt startowy, nagłówki bezpieczeństwa, Swagger UI
│   ├── auth.py                 # JWT, generowanie/weryfikacja tokenów, RBAC
│   ├── ai.py                   # Automatyczna kategoryzacja zgłoszeń
│   ├── db.py                   # Schemat bazy danych, połączenie, zapis audytu
│   ├── routes.py               # Wszystkie punkty końcowe API
│   ├── rate_limit.py           # Instancja Flask-Limiter
│   ├── seed.py                 # Wypełnienie bazy danymi testowymi
│   └── requirements.txt        # Zależności podstawowe Pythona
│
├── frontend/                   # Warstwa kliencka (HTML/CSS/JS)
│   ├── index.html              # Interfejs użytkownika
│   ├── script.js               # Logika SPA (Single Page Application)
│   └── style.css               # Style i design tokens (Dark/Light mode)
│
├── docker/                     # Konteneryzacja & Nginx
│   ├── Dockerfile              # Obraz kontenera backend z HEALTHCHECK
│   ├── docker-entrypoint.sh    # Automatyczna inicjalizacja bazy
│   ├── nginx.conf              # Konfiguracja Nginx (Reverse Proxy & Gzip)
│   └── .dockerignore           # Wykluczenia plików z kontekstu builda
│
├── .github/workflows/          # Potok CI/CD (GitHub Actions)
│   └── tests.yml               # Automatyczne testowanie i weryfikacja (wcześniej ci.yml)
│
├── scripts/                    # Skrypty pomocnicze
│   ├── demo.py                 # Skrypt testów integracyjnych REST API (E2E)
│   └── generate_ssl.py         # Skrypt generowania certyfikatów SSL
│
├── tests/                      # Testy jednostkowe i integracyjne (pytest)
│   ├── conftest.py             # Konfiguracja środowiska testowego
│   ├── test_ai.py              # Testy modułu AI
│   ├── test_api_auth.py        # Testy uwierzytelniania i autoryzacji
│   ├── test_api_security.py    # Testy bezpieczeństwa (limity, nagłówki)
│   ├── test_api_tickets.py     # Testy zgłoszeń (tworzenie, filtry)
│   ├── test_openapi.py         # Testy zgodności ze specyfikacją OpenAPI
│   ├── test_tokens.py          # Testy sprawdzania i ważności tokenów
│   └── test_transitions.py     # Testy dozwolonych przejść statusów
│
├── docs/                       # Dokumentacja projektowa
│   └── projekt.txt             # Założenia projektu inżynierskiego
│
├── Makefile                    # Skróty komend operacyjnych (CLI)
├── docker-compose.yml          # Wielokontenerowa orkiestracja (Nginx + Backend)
├── openapi.yaml                # Specyfikacja API w formacie OpenAPI 3.0
├── pytest.ini                  # Konfiguracja testów pytest
├── .coveragerc                 # Konfiguracja analizy pokrycia kodu (coverage)
├── requirements-dev.txt        # Zależności potrzebne wyłącznie do testów
├── .env.example                # Szablon zmiennych środowiskowych
├── .gitignore                  # Pliki ignorowane przez Git
└── README.md                   # Dokumentacja projektu
```

---

## Architektura DevOps & Konteneryzacja

Aplikacja wykorzystuje **izolowaną architekturę wielokontenerową**:

1. **`web` (Nginx:alpine)** – wystawiony na porcie `80`:
   - Serwuje pliki statyczne z `frontend/` ze stopniem kompresji **gzip**.
   - Przekierowuje zapytania do `/api/` (Reverse Proxy) do kontenera backendowego.
   - Wymusza nagłówki bezpieczeństwa HTTP.
2. **`backend` (Python Flask + Gunicorn)** – ukryty w prywatnej sieci `helpdesk-net`:
   - Działa jako nieuprzywilejowany użytkownik (`USER app`).
   - Posiada automatyczny monitoring zdrowia (`HEALTHCHECK CMD curl`).
   - Trwały wolumen `helpdesk-data` dla bazy SQLite.

---

## Szybki start (Docker Compose)

Wymaga zainstalowanego **Docker** / **Docker Desktop**.

**1. Skonfiguruj zmienne środowiskowe:**

```bash
cp .env.example .env
# Ustaw SECRET_KEY w pliku .env
```

**2. Uruchom:**

```bash
docker compose up -d --build
```

**3. Wypełnij bazę danymi testowymi:**

```bash
docker compose exec backend python backend/seed.py
```

Aplikacja dostępna pod adresem: `http://localhost`.

Zatrzymanie:
```bash
docker compose down
```

---

## Automatyzacja deweloperska (Makefile)

Wszystkie kluczowe komendy operacyjne są dostępne przez `Makefile`:

- `make up` – uruchomienie środowiska kontenerowego w tle
- `make down` – zatrzymanie i usunięcie kontenerów
- `make seed` – zasilenie bazy danych testowymi rekordami
- `make test` – uruchomienie pakietu testów integracyjnych
- `make logs` – podgląd logów w czasie rzeczywistym
- `make build` – przebudowanie obrazów Docker

---

## Szybki start (lokalnie, bez Dockera)

Wymagany **Python 3.8+**.

```bash
cp .env.example .env
py -m pip install -r backend/requirements.txt
py backend/seed.py
py backend/app.py
```

---

## Testy

Projekt ma zestaw **187 automatycznych sprawdzeń** w trzech warstwach (166 testów `pytest` + 21 sprawdzeń E2E), przy **100% pokryciu kodu aplikacji**.

```bash
py -m pip install -r requirements-dev.txt
py -m pytest
```

| Warstwa | Liczba | Zakres |
|---|---|---|
| Jednostkowe | 36 | Kategoryzacja AI, tokeny JWT, maszyna stanów |
| Integracyjne | 130 | Flask + baza: RBAC, walidacja, nagłówki, limit żądań, zgodność dokumentacji |
| E2E (`demo.py`) | 21 | Pełny przepływ przez działający serwer |

Testy uruchamiają się automatycznie przy każdym pull requeście (`.github/workflows/tests.yml`).

Pełny opis — zakres każdej warstwy, raport pokrycia, weryfikacja mutacyjna i znane ograniczenia — znajduje się w pliku **[TESTING.md](TESTING.md)**.

---

## Weryfikacja działania

Gdy serwer działa, skrypt `scripts/demo.py` automatycznie sprawdza wszystkie operacje API — logowanie JWT, kategoryzację AI, przejścia statusów, ścieżkę audytu oraz testy negatywne (brak tokenu, podrobiony token, przekroczone limity długości, nieznany endpoint):

```bash
py scripts/demo.py
# lub: make test
```

Oczekiwany wynik:

```
WYNIK: 21 testow OK, 0 bledow
```

## Potok CI/CD (GitHub Actions)

Plik `.github/workflows/tests.yml` (wcześniej `ci.yml`) automatycznie wykonuje następujące kroki przy każdym commicie / pull requeście na gałąź `main`:
1. Weryfikacja składni i linter kodu Python.
2. Wykonanie testów jednostkowych i integracyjnych przy użyciu `pytest`.
3. Testowe przebudowanie architektury Docker Compose.

## Potok CI/CD (GitHub Actions)

Plik `.github/workflows/ci.yml` automatycznie wykonuje następujące kroki przy każdym commicie / pull requescie na gałąź `main`:
1. Weryfikacja składni i linter kodu Python.
2. Zasilenie bazy testowej i uruchomienie serwera.
3. Wykonanie 17 testów integracyjnych REST API.
4. Testowe przebudowanie architektury Docker Compose.

---

## Bezpieczeństwo

| Mechanizm | Implementacja |
|-----------|---------------|
| Hashowanie haseł | `werkzeug` scrypt |
| Uwierzytelnianie | JWT (HS256, ważność 8h) |
| Ograniczanie żądań | Flask-Limiter (10 próby/min na logowaniu) |
| Nagłówki HTTP | Nginx + Flask: `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy` |
| Izolacja sieciowa | Backend ukryty w prywatnej sieci `helpdesk-net`, dostęp tylko przez Reverse Proxy |
| Docker Security | Kontener backend działa z dedykowanym kontem `USER app` bez uprawnień roota |

---

## Role użytkowników

| Rola        | Uprawnienia                                                           |
|-------------|------------------------------------------------------------------------|
| `pracownik` | Tworzenie zgłoszeń, podgląd **wyłącznie własnych** zgłoszeń            |
| `technik`   | Podgląd wszystkich zgłoszeń, zmiana statusu/kategorii, notatki, audyt  |
| `admin`     | Pełny dostęp                                                           |

---

## Punkty końcowe API

**Pełna, interaktywna dokumentacja:** po uruchomieniu aplikacji dostępna pod adresem **`http://localhost:5000/api/docs`** (Swagger UI). Źródłem prawdy jest plik **[`openapi.yaml`](openapi.yaml)** (OpenAPI 3.0).

| Metoda | Ścieżka                   | Rola          | Opis                                      |
|--------|----------------------------|---------------|---------------------------------------------|
| POST   | `/api/auth/login`          | —             | Logowanie — zwraca JWT token                |
| GET    | `/api/auth/me`             | każdy         | Dane zalogowanego użytkownika (odtworzenie sesji) |
| GET    | `/api/dashboard`           | każdy         | Statystyki + rozkład kategorii              |
| GET    | `/api/tickets`             | każdy         | Lista zgłoszeń (filtrowana wg roli)         |
| POST   | `/api/tickets`             | pracownik     | Nowe zgłoszenie + kategoryzacja AI          |
| GET    | `/api/tickets/{id}`        | każdy         | Szczegóły zgłoszenia + notatki              |
| PATCH  | `/api/tickets/{id}`        | technik/admin | Zmiana statusu / kategorii / przypisania    |
| POST   | `/api/tickets/{id}/notes`  | technik/admin | Notatka (wewnętrzna lub widoczna)           |
| GET    | `/api/tickets/{id}/audit`  | technik/admin | Pełna ścieżka audytu                        |
| POST   | `/api/ai/categorize`       | każdy         | Test modułu AI na dowolnym tekście          |

**Autoryzacja:** każde żądanie (poza logowaniem) wymaga nagłówka:
```
Authorization: Bearer <token>
```

**Filtry dla `GET /api/tickets`** (tylko technik/admin):
`?status=Nowe`, `?priority=Krytyczny`, `?category=Siec`.

---

## Cykl życia zgłoszenia (dozwolone przejścia statusów)

```
Nowe → W trakcie → Rozwiazane → Zamkniete
              ↘ Wstrzymane ↗
```

Próba przeskoczenia etapu (np. `Nowe → Zamkniete`) jest odrzucana przez API z kodem 400 i listą dozwolonych przejść.

---

## Kategoryzacja AI

Moduł `backend/ai.py` przy każdym nowym zgłoszeniu automatycznie nadaje **kategorię** (Sprzęt, Oprogramowanie, Sieć, Poczta, Konta i dostęp, Bezpieczeństwo, Peryferia) oraz **priorytet** (Niski, Średni, Wysoki, Krytyczny). Priorytet wyznacza termin SLA. Domyślnie moduł działa lokalnie (bez kluczy API i kosztów).

**Zasada triażu:** gdy zgłoszenie pasuje do kilku słów kluczowych naraz (np. „phishing" i „hasło"), wybierane jest dopasowanie o **najwyższym priorytecie**.

---

## Dane testowe (logowanie)

| Login          | Hasło    | Rola      |
|-----------------|----------|-----------| 
| k.nowak         | haslo123 | pracownik |
| p.wisniewski    | haslo123 | pracownik |
| a.kowalczyk     | haslo123 | pracownik |
| m.lewandowski   | tech123  | technik   |
| j.zielinska     | tech123  | technik   |
| admin           | admin123 | admin     |

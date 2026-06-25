# Inteligentny HelpDesk IT

Back-end systemu HelpDesk dla MŚP: REST API w technologii **Flask + SQLite**.
Obsługuje pełny cykl życia zgłoszenia IT, kontrolę dostępu opartą na rolach
(RBAC), automatyczną kategoryzację zgłoszeń przez moduł AI oraz pełną ścieżkę
audytu.

---

## Spis treści

- [Struktura plików](#struktura-plików)
- [Szybki start (Docker)](#szybki-start-docker)
- [Szybki start (lokalnie, bez Dockera)](#szybki-start-lokalnie-bez-dockera)
- [Weryfikacja działania](#weryfikacja-działania)
- [Role użytkowników](#role-użytkowników)
- [Punkty końcowe API](#punkty-końcowe-api)
- [Cykl życia zgłoszenia](#cykl-życia-zgłoszenia-dozwolone-przejścia-statusów)
- [Kategoryzacja AI](#kategoryzacja-ai)
- [Dane testowe (logowanie)](#dane-testowe-logowanie)
- [Rozwiązywanie problemów](#rozwiązywanie-problemów)

---

## Struktura plików

| Plik                 | Odpowiada za                                          |
|-----------------------|--------------------------------------------------------|
| `app.py`              | Punkt startowy aplikacji, konfiguracja, CORS            |
| `db.py`               | Schemat bazy danych, połączenie, zapis audytu           |
| `auth.py`             | Kontrola dostępu według ról (RBAC)                      |
| `ai.py`               | Automatyczna kategoryzacja zgłoszeń                     |
| `routes.py`           | Wszystkie punkty końcowe API                            |
| `seed.py`             | Wypełnienie bazy danymi testowymi                       |
| `demo.py`             | Skrypt sprawdzający — uruchamia i weryfikuje całe API   |
| `Dockerfile`          | Obraz kontenera dla back-endu                           |
| `docker-compose.yml`  | Uruchomienie usługi wraz z trwałym wolumenem danych     |

---

## Szybki start (Docker)

Wymaga zainstalowanego **Docker** / **Docker Desktop**.

```bash
docker compose up --build
```

API będzie dostępne pod `http://localhost:5000`. Baza danych SQLite jest
inicjalizowana automatycznie przy pierwszym starcie i przechowywana w trwałym
wolumenie `helpdesk-data`, więc dane przetrwają restart kontenera.

Zatrzymanie:

```bash
docker compose down
```

---

## Szybki start (lokalnie, bez Dockera)

Wymagany **Python 3.8+**.

```bash
py -m pip install -r requirements.txt
py seed.py      # tworzy i wypełnia bazę danymi testowymi
py app.py       # startuje serwer na http://127.0.0.1:5000
```

Pierwszy terminal z serwerem musi zostać otwarty — w drugim terminalu można
odpytywać API lub uruchomić skrypt weryfikujący.

---

## Weryfikacja działania

Gdy serwer działa (lokalnie lub w Dockerze), w drugim terminalu:

```bash
py demo.py
```

Skrypt wykonuje po kolei wszystkie operacje back-endu (logowanie, kategoryzacja
AI, zmiana statusów, audyt, kontrola uprawnień) i na końcu wypisuje
podsumowanie, np.:

```
WYNIK: 17 testow OK, 0 bledow
```

Ręczne sprawdzenie pojedynczych endpointów:

```bash
curl http://localhost:5000/api/dashboard -H "X-User-Id: 4"

curl -X POST http://localhost:5000/api/ai/categorize \
  -H "Content-Type: application/json" -H "X-User-Id: 1" \
  -d "{\"title\":\"phishing\",\"description\":\"podejrzany mail z prosba o haslo\"}"
```

---

## Role użytkowników

| Rola        | Uprawnienia                                                           |
|-------------|------------------------------------------------------------------------|
| `pracownik` | Tworzenie zgłoszeń, podgląd **wyłącznie własnych** zgłoszeń            |
| `technik`   | Podgląd wszystkich zgłoszeń, zmiana statusu/kategorii, notatki, audyt   |
| `admin`     | Pełny dostęp                                                           |

---

## Punkty końcowe API

| Metoda | Ścieżka                   | Rola          | Opis                                      |
|--------|----------------------------|---------------|---------------------------------------------|
| POST   | `/api/auth/login`          | —             | Logowanie                                   |
| GET    | `/api/dashboard`           | każdy         | Statystyki + rozkład kategorii              |
| GET    | `/api/tickets`             | każdy         | Lista zgłoszeń (filtrowana wg roli)         |
| POST   | `/api/tickets`             | pracownik     | Nowe zgłoszenie + kategoryzacja AI          |
| GET    | `/api/tickets/{id}`        | każdy         | Szczegóły zgłoszenia + notatki              |
| PATCH  | `/api/tickets/{id}`        | technik/admin | Zmiana statusu / kategorii / przypisania    |
| POST   | `/api/tickets/{id}/notes`  | technik/admin | Notatka (wewnętrzna lub widoczna)           |
| GET    | `/api/tickets/{id}/audit`  | technik/admin | Pełna ścieżka audytu                        |
| POST   | `/api/ai/categorize`       | każdy         | Test modułu AI na dowolnym tekście          |

**Autoryzacja:** po zalogowaniu każde zapytanie wymaga nagłówka
`X-User-Id: <id>` (np. `1` = pracownik, `4` = technik).

**Filtry dla `GET /api/tickets`** (tylko technik/admin):
`?status=Nowe`, `?priority=Krytyczny`, `?category=Siec`.

---

## Cykl życia zgłoszenia (dozwolone przejścia statusów)

```
Nowe → W trakcie → Rozwiazane → Zamkniete
              ↘ Wstrzymane ↗
```

Próba przeskoczenia etapu (np. `Nowe → Zamkniete`) jest odrzucana przez API.

---

## Kategoryzacja AI

Moduł `ai.py` przy każdym nowym zgłoszeniu automatycznie nadaje **kategorię**
(Sprzęt, Oprogramowanie, Sieć, Poczta, Konta i dostęp, Bezpieczeństwo,
Peryferia) oraz **priorytet** (Niski, Średni, Wysoki, Krytyczny). Priorytet
wyznacza termin SLA. Domyślnie moduł działa lokalnie (bez kluczy API i
kosztów); w pliku `ai.py` opisano, jak podłączyć prawdziwy model językowy
(np. OpenAI) bez zmian w reszcie back-endu.

---

## Dane testowe (logowanie)

| Login          | Hasło    | Rola      | ID |
|-----------------|----------|-----------|----|
| k.nowak         | haslo123 | pracownik | 1  |
| p.wisniewski    | haslo123 | pracownik | 2  |
| a.kowalczyk     | haslo123 | pracownik | 3  |
| m.lewandowski   | tech123  | technik   | 4  |
| j.zielinska     | tech123  | technik   | 5  |
| admin           | admin123 | admin     | 6  |

---

## Rozwiązywanie problemów

| Komunikat                              | Rozwiązanie                                             |
|------------------------------------------|------------------------------------------------------------|
| `'py' nie jest rozpoznawane...`          | Zainstaluj Pythona z python.org, zaznacz „Add to PATH”     |
| `No module named pip`                    | Wpisz `py -m ensurepip --upgrade`                          |
| `No module named flask`                  | Wpisz `py -m pip install -r requirements.txt`              |
| `Address already in use` / port zajęty   | Zamknij poprzedni serwer (Ctrl+C w jego terminalu)         |
| Serwer nie odpowiada przy `demo.py`      | Najpierw uruchom serwer (`py app.py` lub `docker compose up`) |

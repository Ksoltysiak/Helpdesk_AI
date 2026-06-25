# Inteligentny system zarządzania zgłoszeniami IT klasy HelpDesk z automatyczną kategoryzacją AI dla MŚP

Back-end systemu HelpDesk: REST API w technologii **Flask + SQLite**. Obsługuje
pełny cykl życia zgłoszenia IT, kontrolę dostępu opartą na rolach (RBAC),
automatyczną kategoryzację zgłoszeń przez moduł AI oraz pełną ścieżkę audytu.

> Instrukcja uruchomienia krok po kroku znajduje się w pliku **URUCHOMIENIE.md**.

---

## Struktura plików

| Plik           | Odpowiada za                                              |
|----------------|----------------------------------------------------------|
| `app.py`       | Punkt startowy aplikacji, konfiguracja, CORS             |
| `db.py`        | Schemat bazy danych, połączenie, zapis audytu            |
| `auth.py`      | Kontrola dostępu według ról (RBAC)                       |
| `ai.py`        | Automatyczna kategoryzacja zgłoszeń                       |
| `routes.py`    | Wszystkie punkty końcowe API                             |
| `seed.py`      | Wypełnienie bazy danymi testowymi                        |
| `demo.py`      | Skrypt sprawdzający — uruchamia i weryfikuje całe API     |

---

## Role użytkowników

| Rola        | Uprawnienia                                                           |
|-------------|----------------------------------------------------------------------|
| `pracownik` | Tworzenie zgłoszeń, podgląd **wyłącznie własnych** zgłoszeń           |
| `technik`   | Podgląd wszystkich zgłoszeń, zmiana statusu/kategorii, notatki, audyt |
| `admin`     | Pełny dostęp                                                          |

---

## Punkty końcowe API

| Metoda | Ścieżka                       | Rola          | Opis                                  |
|--------|-------------------------------|---------------|---------------------------------------|
| POST   | `/api/auth/login`             | —             | Logowanie                             |
| GET    | `/api/dashboard`              | każdy         | Statystyki + rozkład kategorii        |
| GET    | `/api/tickets`                | każdy         | Lista zgłoszeń (filtrowana wg roli)   |
| POST   | `/api/tickets`                | pracownik     | Nowe zgłoszenie + kategoryzacja AI    |
| GET    | `/api/tickets/{id}`           | każdy         | Szczegóły zgłoszenia + notatki        |
| PATCH  | `/api/tickets/{id}`           | technik/admin | Zmiana statusu / kategorii / przypisania |
| POST   | `/api/tickets/{id}/notes`     | technik/admin | Notatka (wewnętrzna lub widoczna)     |
| GET    | `/api/tickets/{id}/audit`     | technik/admin | Pełna ścieżka audytu                  |
| POST   | `/api/ai/categorize`          | każdy         | Test modułu AI na dowolnym tekście    |

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
(Sprzęt, Oprogramowanie, Sieć, Poczta, Konta i dostęp, Bezpieczeństwo, Peryferia)
oraz **priorytet** (Niski, Średni, Wysoki, Krytyczny). Priorytet wyznacza termin
SLA. Domyślnie moduł działa lokalnie (bez kluczy API i kosztów); w pliku `ai.py`
opisano, jak podłączyć prawdziwy model językowy (np. OpenAI) bez zmian w reszcie
back-endu.

---

## Dane testowe (logowanie)

| Login           | Hasło     | Rola      | ID |
|-----------------|-----------|-----------|----|
| k.nowak         | haslo123  | pracownik | 1  |
| p.wisniewski    | haslo123  | pracownik | 2  |
| a.kowalczyk     | haslo123  | pracownik | 3  |
| m.lewandowski   | tech123   | technik   | 4  |
| j.zielinska     | tech123   | technik   | 5  |
| admin           | admin123  | admin     | 6  |

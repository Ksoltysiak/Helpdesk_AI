# Testy — dokumentacja

Dokument opisuje zestaw testów automatycznych projektu: strukturę, zakres,
sposób uruchomienia oraz dowód, że testy faktycznie wykrywają błędy.

**Stan na dzień:** 1 sierpnia 2026

| Miara | Wartość |
|---|---|
| Testy `pytest` | **139** (36 jednostkowych + 103 integracyjne) |
| Testy E2E (`demo.py`) | **21** sprawdzeń |
| Łącznie automatycznych sprawdzeń | **160** |
| Pokrycie kodu aplikacji | **100%** (299 instrukcji, 0 pominiętych) |
| Czas wykonania `pytest` | ~10 s |
| Wynik ostatniego przebiegu | 139 passed, 0 failed |

---

## Spis treści

- [Struktura piramidy](#struktura-piramidy)
- [Warstwa 1 — testy jednostkowe](#warstwa-1--testy-jednostkowe)
- [Warstwa 2 — testy integracyjne](#warstwa-2--testy-integracyjne)
- [Warstwa 3 — testy E2E](#warstwa-3--testy-e2e)
- [Uruchamianie testów](#uruchamianie-testów)
- [Pokrycie kodu](#pokrycie-kodu)
- [Weryfikacja skuteczności testów (testy mutacyjne)](#weryfikacja-skuteczności-testów-testy-mutacyjne)
- [Testy regresji dla wykrytych błędów](#testy-regresji-dla-wykrytych-błędów)
- [Ciągła integracja (CI)](#ciągła-integracja-ci)
- [Ograniczenia](#ograniczenia)

---

## Struktura piramidy

```
                    ┌───────────────────────┐
                    │   E2E — demo.py       │   21 sprawdzeń
                    │   działający serwer   │   ~3 s
                    ├───────────────────────┤
                │      Integracyjne         │   103 testy
                │   Flask + baza danych     │   ~9 s
            ├───────────────────────────────────┤
        │          Jednostkowe                  │   36 testów
        │      czysta logika, bez I/O           │   ~0,3 s
    └───────────────────────────────────────────────┘
```

| Warstwa | Plik | Testy | Zakres |
|---|---|---|---|
| Jednostkowa | `tests/test_ai.py` | 17 | Kategoryzacja AI, priorytety, SLA |
| Jednostkowa | `tests/test_tokens.py` | 10 | Generowanie i weryfikacja JWT |
| Jednostkowa | `tests/test_transitions.py` | 9 | Maszyna stanów zgłoszenia |
| Integracyjna | `tests/test_api_auth.py` | 28 | Logowanie, ochrona endpointów |
| Integracyjna | `tests/test_api_tickets.py` | 59 | RBAC, CRUD, notatki, audyt |
| Integracyjna | `tests/test_api_security.py` | 16 | Nagłówki, 404 API, limit żądań |
| E2E | `demo.py` | 21 | Pełny przepływ przez HTTP |

**Uwaga o kształcie piramidy.** Warstwa integracyjna jest tu liczniejsza niż
jednostkowa — odwrotnie niż w podręcznikowym modelu. Jest to świadomy wybór:
własna logika biznesowa tego projektu jest cienka (kategoryzacja + tabela
przejść), a rzeczywiste ryzyko leży na styku HTTP ↔ autoryzacja ↔ baza danych.
Testowanie tej granicy wymaga testów integracyjnych. Sztuczne rozdrabnianie ich
na testy jednostkowe z atrapami dawałoby ładniejszy wykres i słabszą ochronę.

---

## Warstwa 1 — testy jednostkowe

Czysta logika, bez bazy danych i bez HTTP. Wykonują się w ułamku sekundy,
więc można je uruchamiać po każdej zmianie.

**`test_ai.py`** — kontrakt funkcji `categorize()`: zwracane pola, przynależność
kategorii do listy dozwolonych, wartość domyślna przy braku dopasowania,
niezależność od wielkości liter. Osobna grupa sprawdza **wybór najpoważniejszego
dopasowania** oraz brak nieuzasadnionej eskalacji zwykłych zgłoszeń. Dwa testy
pilnują niezmienników słownika: każde słowo kluczowe wskazuje istniejącą
kategorię i priorytet mający zdefiniowane SLA.

**`test_tokens.py`** — token zawiera identyfikator użytkownika, wygasa po 8 h.
Każda ścieżka odrzucenia ma własny test: obcy klucz podpisujący, naruszony
podpis, token wygasły, ciąg niebędący tokenem oraz atak `alg=none`. Ostatni test
sprawdza w podprocesie, że uruchomienie bez `SECRET_KEY` **głośno ostrzega**,
zamiast po cichu użyć klucza domyślnego.

**`test_transitions.py`** — tabela przejść: brak przejść w samego siebie,
`Zamkniete` jest stanem końcowym, każdy inny status ma wyjście (zgłoszenie nie
utknie), nie da się przeskoczyć z `Nowe` do `Zamkniete`, a wszystkie statusy są
osiągalne z `Nowe`.

---

## Warstwa 2 — testy integracyjne

Pełny stos Flask z prawdziwą bazą SQLite. Każdy test dostaje **własną, świeżą
bazę** w katalogu tymczasowym (`tmp_path`), wypełnioną minimalnym, przewidywalnym
zestawem danych z `tests/conftest.py` — niezależnym od `seed.py`. Testy nie
wpływają na siebie nawzajem i nie dotykają bazy deweloperskiej.

**`test_api_auth.py`** — poprawne i błędne logowanie. Osobno sprawdzane jest, że
odpowiedź **nie ujawnia hasła ani jego skrótu**, że hasło jest w bazie zapisane
jako hash (`scrypt`), oraz że komunikat błędu jest **identyczny** dla złego hasła
i nieznanego loginu (brak wskazówki, które konta istnieją). Testy odrzucania
obejmują brak tokenu, token wygasły, token bez pola `sub`, token dla usuniętego
użytkownika i **stary nagłówek `X-User-Id`**, który nie może już działać.

**`test_api_tickets.py`** — największy zestaw, skupiony na granicy dostępu:
pracownik widzi wyłącznie własne zgłoszenia, nie odczyta cudzego (403), nie
ominie izolacji filtrem, nie zobaczy notatek wewnętrznych. Dalej: tworzenie
zgłoszeń z kategoryzacją AI, walidacja długości pól (z testem wartości
granicznej), maszyna stanów w praktyce, automatyczne przypisanie technika przy
podjęciu, ręczna korekta kategorii i przypisania oraz kompletność ścieżki audytu.

**`test_api_security.py`** — nagłówki bezpieczeństwa (również na odpowiedziach
API), brak CORS z gwiazdką, poprawna obsługa nieznanych ścieżek `/api/*`,
serwowanie frontendu i plików statycznych oraz ograniczanie liczby prób
logowania (429 po przekroczeniu limitu, przy jednoczesnym braku wpływu na zwykłe
odczyty).

---

## Warstwa 3 — testy E2E

`demo.py` odpytuje **działający serwer** przez HTTP, tak jak zrobiłaby to
przeglądarka lub klient API. Przechodzi pełną ścieżkę: logowanie obu ról →
pulpit → odtworzenie sesji → kategoryzacja AI → utworzenie zgłoszenia →
widoczność wg roli → obsługa przez technika → audyt → testy negatywne
(brak tokenu, podrobiony token, przekroczona długość pola, nieznany endpoint).

Wymaga uruchomionego serwera — dlatego jest wierzchołkiem piramidy, a nie jej
podstawą.

---

## Uruchamianie testów

**Instalacja zależności testowych:**

```bash
py -m pip install -r requirements-dev.txt
```

**Wszystkie testy `pytest`:**

```bash
py -m pytest
```

**Tylko szybka warstwa jednostkowa** (przydatne w trakcie pisania kodu):

```bash
py -m pytest -m unit
```

**Tylko testy integracyjne:**

```bash
py -m pytest -m integration
```

**Testy E2E** (wymagają działającego serwera w drugim terminalu):

```bash
py demo.py
```

---

## Pokrycie kodu

```
Name            Stmts   Miss  Cover
-----------------------------------
ai.py              14      0   100%
app.py             28      0   100%
auth.py            57      0   100%
db.py              22      0   100%
rate_limit.py       3      0   100%
routes.py         175      0   100%
-----------------------------------
TOTAL             299      0   100%
```

Raport generuje polecenie:

```bash
py -m pytest --cov --cov-report=term-missing
```

Konfiguracja w `.coveragerc` pomija katalog `tests/` oraz skrypty uruchamiane
ręcznie (`seed.py`, `demo.py`) — liczba dotyczy **kodu aplikacji**.

> **Czego pokrycie nie oznacza.** 100% to miara wykonania linii, nie poprawności.
> Mówi, że każda linia została uruchomiona przez jakiś test — nie, że jej
> zachowanie jest właściwe. Realnym dowodem skuteczności jest poniższa
> weryfikacja mutacyjna.

---

## Weryfikacja skuteczności testów (testy mutacyjne)

Zestaw testów, który przechodzi za pierwszym razem, bywa zestawem, który
niczego nie sprawdza. Aby to wykluczyć, do działającego kodu **celowo
wprowadzono z powrotem naprawione wcześniej błędy** i sprawdzono, czy testy je
wychwycą.

| # | Wprowadzona usterka | Wynik |
|---|---|---|
| 1 | Powrót do starej logiki AI (wygrywa **pierwsze** dopasowanie, nie najpoważniejsze) | **4 testy nie przeszły** — `test_incydent_bezpieczenstwa_ma_najwyzszy_priorytet` |
| 2 | Usunięcie obsługi nieznanych ścieżek `/api/*` (powrót do HTML z kodem 200) | **5 testów nie przeszło** — `test_nieznany_endpoint_api_zwraca_json_404`, `..._nie_zwraca_html` |
| 3 | Złamanie izolacji danych: pracownik widzi wszystkie zgłoszenia, brak kontroli 403, widoczne notatki wewnętrzne | **5 testów nie przeszło** — `test_pracownik_widzi_wylacznie_wlasne_zgloszenia`, `test_pracownik_nie_odczyta_cudzego_zgloszenia`, `test_filtr_nie_omija_izolacji_pracownika`, `test_pracownik_nie_widzi_notatek_wewnetrznych`, `test_drugi_pracownik_widzi_inny_zestaw` |

Po każdej próbie pliki źródłowe przywrócono do stanu zgodnego z repozytorium
(zweryfikowane poleceniem `git status`). Wszystkie trzy mutacje zostały
wykryte — testy pilnują tych zachowań realnie, a nie pozornie.

---

## Testy regresji dla wykrytych błędów

Każdy błąd znaleziony wcześniej ręcznie ma dziś test, który nie pozwoli mu
wrócić. W kodzie testów opatrzono je komentarzem wyjaśniającym przyczynę.

| Błąd | Test broniący |
|---|---|
| Incydenty bezpieczeństwa klasyfikowane jako rutynowe (SLA 8 h zamiast 1 h), bo wygrywało pierwsze słowo kluczowe | `test_ai.py::test_incydent_bezpieczenstwa_ma_najwyzszy_priorytet` (4 przypadki) |
| Nieznane ścieżki `/api/*` zwracały stronę HTML z kodem 200 | `test_api_security.py::test_nieznany_endpoint_api_zwraca_json_404` (4 przypadki) |
| Nagłówek `X-User-Id` pozwalał podszyć się pod dowolnego użytkownika | `test_api_auth.py::test_niepoprawny_naglowek_autoryzacji_daje_401` |
| Hasła przechowywane otwartym tekstem | `test_api_auth.py::test_haslo_jest_hashowane_w_bazie` |

---

## Ciągła integracja (CI)

Plik `.github/workflows/tests.yml` uruchamia testy przy każdym `push` na `main`
oraz przy **każdym pull requeście**. Zadania:

1. **Testy jednostkowe i integracyjne** — `pytest` z raportem pokrycia.
2. **Testy E2E** — uruchomienie serwera (`gunicorn`), wypełnienie bazy, `demo.py`.
3. **Budowa obrazu Docker** — sprawdzenie, że obraz się buduje, kontener
   odpowiada na żądania i **nie działa jako `root`**.

> **Zalecenie konfiguracyjne.** Aby testy faktycznie blokowały wadliwe zmiany,
> w ustawieniach repozytorium (*Settings → Branches → reguła dla `main`*) należy
> włączyć **Require status checks to pass before merging** i wskazać zadania
> z tego workflow. Sama ochrona gałęzi wymusza przegląd przez człowieka; dopiero
> wymagane statusy sprawiają, że niedziałający kod nie zostanie scalony.

---

## Ograniczenia

Rzetelny obraz tego, czego testy **nie** obejmują:

- **Brak testów frontendu.** `frontend/script.js` nie ma testów jednostkowych —
  warstwa E2E sprawdza API, ale nie zachowanie interfejsu w przeglądarce.
  Naturalnym kolejnym krokiem byłby Playwright lub Vitest.
- **Ograniczanie żądań testowane na magazynie w pamięci.** W środowisku
  wieloprocesowym (`gunicorn --workers 2`) każdy proces ma własny licznik —
  produkcyjnie wymaga to wspólnego magazynu (np. Redis).
- **Brak testów współbieżności.** Zapisy SQLite pod równoległym obciążeniem nie
  są sprawdzane; to znany punkt do rozstrzygnięcia przy wdrożeniu.
- **Brak testów wydajnościowych i obciążeniowych.**

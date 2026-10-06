# Inteligentny HelpDesk IT — dokumentacja projektu

**Projekt inżynierski** · System zgłoszeń awarii IT z automatyczną oceną
priorytetu zgłoszenia

**Wersja dokumentu:** 4 października 2026 · **Stan kodu:** gałąź `main`

---

## W skrócie

- Pracownik opisuje problem, a system **sam ocenia, jak pilne jest
  zgłoszenie**: nadaje kategorię, priorytet i termin realizacji (SLA).
- Technik podejmuje zgłoszenie, dodaje komentarze i prowadzi je przez kolejne
  statusy aż do zamknięcia. Każda zmiana jest zapisywana w historii.
- Ocena zgłoszeń: **94,4% trafności** na zbiorze kontrolnym, **5 z 5**
  incydentów bezpieczeństwa rozpoznanych jako krytyczne.
- Jakość: **440 testów automatycznych**, 100% pokrycia kodu, cały system
  uruchamiany jednym poleceniem (Docker).

## Spis treści

1. [Problem i cel](#1-problem-i-cel)
2. [Jak działa system](#2-jak-działa-system)
3. [Moduł oceny zgłoszeń (AI)](#3-moduł-oceny-zgłoszeń-ai)
4. [Architektura i technologie](#4-architektura-i-technologie)
5. [Bezpieczeństwo](#5-bezpieczeństwo)
6. [Testy i wydajność](#6-testy-i-wydajność)
7. [Uruchomienie](#7-uruchomienie)
8. [Wyniki, ograniczenia i dalszy rozwój](#8-wyniki-ograniczenia-i-dalszy-rozwój)

---

## 1. Problem i cel

W małych i średnich firmach awarie IT zgłaszane są mailem, telefonem lub na
komunikatorze. Prowadzi to do trzech problemów:

- **brak priorytetów** — atak ransomware czeka w tej samej kolejce co prośba
  o wymianę tonera;
- **brak historii** — nie wiadomo, kto i kiedy zajął się zgłoszeniem;
- **strata czasu technika** na ręczne segregowanie zgłoszeń.

**Cel projektu:** system, który w chwili utworzenia zgłoszenia automatycznie
ocenia jego wagę i nadaje termin realizacji, a następnie prowadzi zgłoszenie
przez obsługę technika z pełną historią zmian.

Dokument opisuje backend systemu (API, baza danych, moduł oceny, bezpieczeństwo,
testy, wdrożenie). Interfejs użytkownika powstał jako odrębna część projektu
zespołowego.

---

## 2. Jak działa system

```
  PRACOWNIK                 MODUŁ AI                      TECHNIK
  zakłada zgłoszenie  ──►   ocenia zgłoszenie:      ──►   podejmuje zgłoszenie,
  (tytuł + opis)            kategoria, priorytet,         dodaje komentarze,
                            termin SLA, pewność           zmienia status,
                                                          w razie potrzeby
                                                          poprawia kategorię
                                   │                            │
                                   ▼                            ▼
                         ┌─────────────────────────────────────────────┐
                         │  ŚCIEŻKA AUDYTU — kto, co i kiedy zmienił   │
                         └─────────────────────────────────────────────┘
```

### Klienci i role

Helpdesk obsługuje kilka **firm-klientów**. Każdy pracownik należy do jednej
z nich, a zgłoszenie zapamiętuje firmę autora w chwili utworzenia — dzięki
temu można później przygotować zestawienie dla konkretnego klienta.

| Rola | Co może |
|------|---------|
| **Pracownik** (firmy-klienta) | Zakłada zgłoszenia; widzi **wyłącznie własne** zgłoszenia i komentarze oznaczone jako jawne |
| **Technik** (helpdesk) | Widzi i filtruje wszystkie zgłoszenia, także według klienta; przegląda listę klientów; zmienia status, kategorię i przypisanie; dodaje komentarze (wewnętrzne lub jawne); przegląda historię zmian |
| **Administrator** | Uprawnienia technika |

### Cykl życia zgłoszenia

```
  Nowe ──► W trakcie ──────► Rozwiązane ──► Zamknięte
           ▲  │  ▲           │
           │  ▼  └───────────┘
        Wstrzymane  (ponowne otwarcie)
```

- Nie można pominąć etapu (np. zamknąć nowego zgłoszenia) — historia musi
  pokazywać, kto faktycznie zajął się problemem.
- Podjęcie zgłoszenia (`Nowe → W trakcie`) automatycznie przypisuje je
  technikowi, który to zrobił.

---

## 3. Moduł oceny zgłoszeń (AI)

To kluczowy element projektu. Moduł działa **lokalnie** — bez zewnętrznych
usług, kluczy API i kosztów. Jest to **system regułowy** oparty na ważonych
słowach kluczowych, a nie model uczenia maszynowego; dzięki temu każdą jego
decyzję da się wyjaśnić.

### Zasada działania

1. **Normalizacja tekstu** — usunięcie polskich znaków, aby „hasło", „haslo"
   i „HASŁA" były tym samym słowem.
2. **Zliczanie dowodów** — każde rozpoznane słowo kluczowe (np. `vpn`,
   `drukark`, `phishing`) dodaje punkty swojej kategorii. Wygrywa kategoria
   z największą sumą punktów.
3. **Ustalenie priorytetu** — wynika z najpoważniejszego rozpoznanego słowa
   i jest podnoszony, gdy opis wskazuje na **skalę** („cały dział", „nikt
   nie może") lub **pilność** („pilne", „awaria").
4. **Zasada bezpieczeństwa** — incydent bezpieczeństwa zawsze dostaje
   priorytet krytyczny.
5. **Pewność decyzji** — gdy dowodów jest mało, moduł **nie zgaduje**, tylko
   oznacza zgłoszenie do ręcznej weryfikacji przez technika.

Priorytet wyznacza termin realizacji: **Krytyczny — 1 h, Wysoki — 4 h,
Średni — 8 h, Niski — 24 h**.

### Przykłady (rzeczywiste wyniki modułu)

| Zgłoszenie (tytuł — opis) | Kategoria | Priorytet (SLA) | Pewność | Dlaczego |
|------------|-----------|-----------------|---------|----------|
| **Nie działa VPN** — „Cały dział nie może połączyć się z VPN, pilne" | Sieć | **Krytyczny** (1 h) | 0,75 | `vpn` daje priorytet wysoki, „cały dział" podnosi go do krytycznego |
| **Drukarka** — „Brak tonera w drukarce na 2 piętrze" | Peryferia | Niski (24 h) | 1,00 | dwa zgodne słowa: `drukark`, `toner` |
| **Pytanie** — „Kiedy jest wigilia firmowa?" | Oprogramowanie (domyślna) | Średni (8 h) | 0,00 | brak słów związanych z IT → **oznaczone do weryfikacji przez technika** |

Moduł zwraca też listę słów, które zadecydowały o ocenie — technik widzi
uzasadnienie, a nie „czarną skrzynkę".

### Skuteczność

| Miara | Wynik |
|-------|-------|
| Trafność kategorii — zbiór kontrolny (18 zgłoszeń, nieużywanych do strojenia) | **94,4%** |
| Incydenty bezpieczeństwa rozpoznane jako krytyczne | **5 / 5** |
| Zgłoszenia spoza IT skierowane do weryfikacji | **3 / 3** |

Zbiory testowe są małe, dlatego system **mierzy skuteczność także w trakcie
pracy**: każda ręczna zmiana kategorii przez technika jest traktowana jako
pomyłka modułu. Raport (`GET /api/ai/skutecznosc`) pokazuje odsetek trafnych
ocen i najczęstsze pomyłki — czyli które słowa kluczowe warto dopisać.

Szczegóły, pełny słownik i opis naprawionego błędu z polskimi znakami:
[`AI.md`](AI.md), kod: [`app/domain/ai.py`](app/domain/ai.py).

---

## 4. Architektura i technologie

```
  przeglądarka ──► nginx ──► gunicorn + Flask ──► SQLite
                  (proxy)          │
                                   ├── app/api       trasy HTTP i walidacja danych
                                   ├── app/domain    moduł AI, cykl życia zgłoszenia
                                   ├── app/data      zapytania do bazy
                                   └── app/security  tokeny i uprawnienia
```

Kod podzielono na warstwy z jednym kierunkiem zależności. Moduł AI
(`app/domain`) nie zna ani protokołu HTTP, ani bazy danych — można go testować
i wymienić niezależnie od reszty. Przestrzeganie tego podziału sprawdzają
automatyczne testy.

| Element | Technologia | Dlaczego |
|---------|-------------|----------|
| Język i framework | Python 3.12, Flask | Czytelność, swoboda w zaprojektowaniu własnych warstw |
| Baza danych | SQLite | Bez osobnego serwera; wystarczająca dla małej firmy |
| Logowanie | Tokeny JWT | Standard (RFC 7519), serwer nie przechowuje sesji |
| Serwer | gunicorn za nginx | Obsługa wielu żądań naraz; nginx chroni przed wolnymi klientami |
| Dokumentacja API | OpenAPI 3.0 + Swagger UI | Interaktywny opis API pod adresem `/api/docs` |
| Wdrożenie | Docker Compose | Identyczne środowisko na każdym komputerze i w CI |

Dokładne wersje bibliotek: [`requirements.txt`](requirements.txt). Szczegóły
architektury: [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## 5. Bezpieczeństwo

| Zagrożenie | Zabezpieczenie |
|------------|----------------|
| Podszycie się pod innego użytkownika | Podpisany token JWT, ważny 8 godzin |
| Wyciek bazy danych | Hasła przechowywane wyłącznie jako hash (`scrypt`) |
| Zgadywanie haseł | Limit prób logowania: na adres IP i na konto |
| Podgląd cudzych zgłoszeń | Uprawnienia sprawdzane przez serwer przy **każdym** żądaniu; pracownik nie zobaczy cudzego zgłoszenia nawet przez ręcznie zmodyfikowane zapytanie |
| Wstrzyknięcie SQL | Wyłącznie zapytania parametryzowane |
| Ataki przez przeglądarkę | Nagłówki bezpieczeństwa (CSP, HSTS i inne) |

**Najważniejsze usterki wykryte i naprawione w trakcie projektu:**

- tożsamość użytkownika była odczytywana z nagłówka, który każdy mógł
  podrobić — zastąpiono to podpisanym tokenem;
- hasła były zapisane jawnym tekstem — obecnie tylko jako hash;
- 15 znanych podatności w bibliotekach (12 w bibliotece do tokenów) — biblioteki
  zaktualizowano, a CI sprawdza je przy każdej zmianie;
- pulpit pokazywał pracownikowi statystyki całej firmy — obecnie tylko własne.

Pełny audyt (20 punktów kontrolnych): [`SECURITY.md`](SECURITY.md).

---

## 6. Testy i wydajność

| Rodzaj testów | Liczba | Co sprawdzają |
|---------------|--------|---------------|
| Jednostkowe i integracyjne | 419 | Moduł AI, cykl życia, API, uprawnienia, klientów, walidację danych |
| Kompletny przepływ (E2E) | 21 | Działający serwer — od logowania do zamknięcia zgłoszenia |

- **Pokrycie kodu: 100%.**
- Skuteczność samych testów potwierdzono **testowaniem mutacyjnym** — celowo
  wprowadzano błąd i sprawdzano, czy testy go wykryją.
- Każda zmiana w repozytorium uruchamia automatycznie (CI): testy, skanowanie
  bibliotek pod kątem podatności i start całego systemu w Dockerze.

**Wydajność** zmierzono na bazie z 20 000 zgłoszeń. Po wprowadzeniu
stronicowania i indeksów lista zgłoszeń działa **51 razy szybciej**
(251 ms → 5 ms), a odpowiedź jest **399 razy mniejsza** (9 MB → 23 KB).

Szczegóły: [`TESTING.md`](TESTING.md), [`PERFORMANCE.md`](PERFORMANCE.md).

---

## 7. Uruchomienie

```bash
cp .env.example .env                           # ustaw SECRET_KEY (min. 32 znaki)
docker compose up --build                      # aplikacja: http://localhost:8080
docker compose exec helpdesk python seed.py    # dane demonstracyjne
```

Konta demonstracyjne:

| Login | Hasło | Rola |
|-------|-------|------|
| `k.nowak` | `haslo123` | pracownik (Piekarnia Złoty Kłos) |
| `m.lewandowski` | `tech123` | technik |
| `admin` | `admin123` | administrator |

Dane demonstracyjne zawierają 5 fikcyjnych firm; pełna lista kont:
[`README.md`](README.md#dane-testowe-logowanie).

Interaktywna dokumentacja API: `http://localhost:8080/api/docs`.
Testy: `py -m pytest`. Konfiguracja i rozwiązywanie problemów:
[`README.md`](README.md).

---

## 8. Wyniki, ograniczenia i dalszy rozwój

### Wyniki

| Obszar | Rezultat |
|--------|----------|
| Ocena zgłoszeń | 94,4% trafności na zbiorze kontrolnym; 5/5 incydentów bezpieczeństwa rozpoznanych |
| Wydajność | Lista zgłoszeń 51× szybsza, odpowiedź 399× mniejsza |
| Bezpieczeństwo | Audyt 20-punktowy; usunięto m.in. możliwość podszycia się i 15 podatności |
| Jakość | 440 testów automatycznych, 100% pokrycia kodu |
| Wdrożenie | Cały system uruchamiany jednym poleceniem, sprawdzany w CI |

### Ograniczenia

- Moduł rozpoznaje tylko słowa ze słownika i nie rozumie kontekstu — nie
  odróżnia zaprzeczenia („to nie jest wirus") i reaguje na fragmenty słów
  („kontakt" zawiera rdzeń „konta").
- Zbiory do oceny modułu są małe (29 i 18 zgłoszeń); wiarygodną miarę da
  dopiero pomiar na rzeczywistych zgłoszeniach.
- SQLite wykonuje zapisy pojedynczo — wystarcza dla małej firmy, ale
  ogranicza skalowanie.
- System nie wysyła powiadomień o zbliżającym się terminie SLA.

### Dalszy rozwój

1. **Raporty dla klientów** z wykresami — które kategorie awarii powtarzają
   się najczęściej i jak zmieniają się w czasie. Podstawa jest gotowa:
   każde zgłoszenie jest przypisane do firmy.
2. Powiadomienia (e-mail, komunikator) o zbliżającym się i przekroczonym
   terminie SLA.
3. Ocena zgłoszeń z pomocą modelu językowego, z powrotem do obecnego modułu
   w razie awarii usługi.
4. Przejście na PostgreSQL przy większej skali.

---

## Dokumentacja szczegółowa

| Plik | Zawartość |
|------|-----------|
| [`README.md`](README.md) | Szybki start, konfiguracja, lista punktów końcowych API |
| [`AI.md`](AI.md) | Moduł oceny zgłoszeń: słownik, pomiary, ograniczenia |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Warstwy, nginx, CI/CD |
| [`SECURITY.md`](SECURITY.md) | Audyt bezpieczeństwa |
| [`TESTING.md`](TESTING.md) | Testy, pokrycie, testowanie mutacyjne |
| [`PERFORMANCE.md`](PERFORMANCE.md) | Metoda i wyniki pomiarów wydajności |
| [`BACKUP.md`](BACKUP.md) | Kopie zapasowe i odtwarzanie |
| [`openapi.yaml`](openapi.yaml) | Formalna specyfikacja API |

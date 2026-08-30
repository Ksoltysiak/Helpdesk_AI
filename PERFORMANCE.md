# Wydajność i skalowalność

Dokument opisuje słabe punkty back-endu znalezione **pomiarem**, wprowadzone
zmiany oraz to, co świadomie pozostawiono bez zmian.

**Data:** 26 sierpnia 2026

---

## Metoda pomiaru

Wygenerowano realistyczny wolumen danych — **20 000 zgłoszeń**, 4 000 notatek
i 20 000 wpisów audytu (baza 5,5 MB) — i zmierzono medianę z 15 wywołań każdego
punktu końcowego. Ten sam pomiar powtórzono po zmianach.

Wolumen jest celowo większy niż realny dla MŚP: przy 20 zgłoszeniach każda
implementacja wygląda dobrze, a problemy skalowania ujawniają się dopiero
wtedy, gdy jest za późno na tanią poprawkę.

---

## Wyniki

| Punkt końcowy | Przed | Po | Zmiana |
|---|---|---|---|
| `GET /tickets` (technik) | 251,3 ms / **9 024 KB** | 4,9 ms / **22,6 KB** | **51× szybciej, 399× mniej danych** |
| `GET /tickets` (pracownik) | 85,4 ms / 2 969 KB | 9,5 ms / 22,6 KB | 9× szybciej, 131× mniej danych |
| `GET /tickets?status=Nowe` | 49,6 ms / 1 812 KB | 5,8 ms / 22,4 KB | 8,5× szybciej |
| `GET /tickets` (dwa filtry) | 21,3 ms / 461 KB | 6,1 ms / 22,6 KB | 3,5× szybciej |
| `GET /dashboard` | 37,1 ms | 22,1 ms | 1,7× szybciej |
| `POST /auth/login` | 150,7 ms | 102,3 ms | bez zmian merytorycznych — patrz niżej |

Dodatkowo, po włączeniu kompresji (pomiar w kontenerze, 318 zgłoszeń):

| | Rozmiar |
|---|---|
| Odpowiedź bez kompresji | 17,6 KB |
| Ta sama odpowiedź z gzip | **1,0 KB** (−95%) |

---

## Co zostało zmienione

### 1. Stronicowanie listy zgłoszeń — największy problem

`GET /api/tickets` zwracał **wszystkie** zgłoszenia w jednej odpowiedzi. Przy
20 000 rekordów oznaczało to **9 MB JSON-a** na jedno żądanie. Skutki:

- na łączu mobilnym odpowiedź nie do użycia,
- przeglądarka musiała sparsować i wyrenderować komplet rekordów,
- serwer budował całość w pamięci — jedno żądanie mogło wysycić pamięć procesu,
  co czyniło z tego również wektor odmowy usługi.

Wprowadzono `page` i `per_page` (domyślnie 50, maksymalnie 200). Wartości spoza
zakresu są przycinane, a nie odrzucane błędem. Pole `total` oznacza teraz liczbę
**wszystkich pasujących** zgłoszeń, dzięki czemu klient może zbudować nawigację.

Interfejs dostał sterowanie stronami; zmiana filtra lub widoku wraca na stronę 1.

### 2. Indeksy bazy danych

Tabela `tickets` nie miała **żadnego** indeksu poza kluczem głównym. Każde
filtrowanie i każdy licznik na pulpicie oznaczał przeszukanie całej tabeli.

Dodano indeksy na `created_by`, `status`, `priority`, `category`, `assigned_to`,
indeks złożony `(status, priority)` dla filtrów łączonych, `(created_by, id DESC)`
dla listy pracownika oraz indeksy kluczy obcych w `notes` i `audit_log`.

Testy sprawdzają plan zapytania (`EXPLAIN QUERY PLAN`), więc utrata indeksu
zatrzyma budowanie — nie tylko jego brak w schemacie.

### 3. Tryb WAL i ustawienia połączenia

Baza działała w domyślnym trybie dziennika, w którym **zapis blokuje odczyty**.
Przy `gunicorn --workers 2` prowadzi to wprost do błędów „database is locked".

Włączono `journal_mode = WAL` (odczyt równolegle z zapisem) oraz
`busy_timeout = 5000` (czekanie na zwolnienie blokady zamiast natychmiastowego
błędu). Tryb dziennika ustawiany jest **raz**, przy inicjalizacji — jest zapisany
w nagłówku pliku bazy, więc powtarzanie go przy każdym żądaniu byłoby zbędną
operacją dyskową na ścieżce każdego zapytania.

### 4. Pulpit: pięć zapytań zamienione na jedno

Statystyki liczone były pięcioma osobnymi zapytaniami `COUNT(*)`, z których
każde przechodziło całą tabelę. Zastąpiono je jednym zapytaniem z agregacją
warunkową.

### 5. Zakres pulpitu zależny od roli

Przy okazji ujawniło się, że `GET /api/dashboard` zwracał **liczby z całego
systemu każdemu** — pracownik widział, ile zgłoszeń ma cała organizacja.
Statystyki są teraz ograniczone tak samo jak lista: pracownik widzi wyłącznie
własne.

Poprawiło to również poprawność interfejsu: pulpit pracownika liczył zgłoszenia
z pobranej listy, co po wprowadzeniu stronicowania dawałoby maksymalnie 50
niezależnie od stanu faktycznego.

### 6. Kompresja gzip

Odpowiedzi tekstowe powyżej 1 KB są kompresowane (95% redukcji na liście
zgłoszeń). Poniżej progu narzut przewyższa zysk, więc kompresja jest pomijana.

### 7. Nagłówki cache

Pliki statyczne: `max-age=3600, must-revalidate`. Odpowiedzi API: **`no-store`** —
dane zgłoszeń w cache przeglądarki mogłyby zostać pokazane kolejnej osobie
korzystającej z tego samego urządzenia po wylogowaniu.

### 8. Mniejsze zapytanie o użytkownika

`current_user()` pobierał `SELECT *` z tabeli `users` przy **każdym**
uwierzytelnionym żądaniu, wciągając do aplikacji hash hasła bez powodu.
Ograniczono do potrzebnych kolumn.

---

## Czego świadomie nie „optymalizowano"

**Czas logowania (~100 ms) jest zamierzony.** To koszt funkcji `scrypt`,
która celowo jest wolna — właśnie po to, by utrudnić masowe zgadywanie haseł.
Przyspieszenie logowania oznaczałoby **osłabienie** zabezpieczenia. To jedyne
miejsce w systemie, gdzie wolniej znaczy lepiej.

**Nie wprowadzono cache'owania odpowiedzi API.** Przy tej skali zysk byłby
marginalny, a koszt — realny: unieważnianie cache przy zmianie statusu
zgłoszenia to klasyczne źródło błędów polegających na pokazywaniu nieaktualnych
danych.

**Nie zmieniano modelu połączeń z bazą.** Otwieranie połączenia na żądanie
kosztuje poniżej 1 ms i jest bezpieczne przy wielu procesach. Pula połączeń ma
sens dopiero przy bazie sieciowej (np. PostgreSQL).

---

## Pozostałe ograniczenia

- **SQLite pozostaje pojedynczym plikiem.** WAL rozwiązuje konflikt
  odczyt–zapis, ale **równoległe zapisy** nadal są serializowane. Przy większym
  natężeniu zgłoszeń właściwym krokiem jest PostgreSQL — to ta sama decyzja,
  która blokuje wdrożenie 24/7 (patrz `README.md`).
- **Licznik limitu żądań jest w pamięci procesu.** Bez `RATELIMIT_STORAGE_URI`
  przy N procesach limit jest N razy wyższy niż zadeklarowany.
- **Brak stronicowania w ścieżce audytu.** Zgłoszenie z bardzo długą historią
  zwróci ją w całości. W praktyce liczba wpisów na zgłoszenie jest niewielka,
  ale przy dużym ruchu warto to ograniczyć.
- **Brak pomiaru pod obciążeniem równoległym.** Pomiary są sekwencyjne;
  zachowanie przy wielu jednoczesnych użytkownikach nie było badane.

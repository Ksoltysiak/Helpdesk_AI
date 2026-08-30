# Moduł kategoryzacji AI

Automatyczna kategoryzacja zgłoszeń to główny mechanizm tego projektu.
Dokument opisuje, jak działa, jak zmierzono jego skuteczność i co zmieniono.

**Data:** 26 sierpnia 2026

---

## Skuteczność

| Miara | Przed | Po |
|---|---|---|
| Kategoria (zbiór ewaluacyjny, 29 zgłoszeń) | 79,3% | **100%** |
| Priorytet (zbiór ewaluacyjny) | 79,3% | **100%** |
| Kategoria (zbiór kontrolny, 18 zgłoszeń) | — | **94,4%** |
| Incydenty bezpieczeństwa rozpoznane | 2/5 | **5/5** |
| Zgłoszenia spoza IT oznaczone do weryfikacji | 0/3 | **3/3** |

> **Uczciwe zastrzeżenie.** Słownik był strojony na zbiorze ewaluacyjnym, więc
> wynik 100% jest z definicji optymistyczny. Dlatego podano też wynik na
> **zbiorze kontrolnym** (zgłoszenia z `seed.py`, napisane przed tą pracą i
> nieużywane do strojenia): **94,4%**. To ta druga liczba jest uczciwym
> szacunkiem jakości.
>
> Oba zbiory są małe (29 i 18 zgłoszeń). Rzetelna ocena wymagałaby kilkuset
> prawdziwych zgłoszeń — dlatego wbudowano mechanizm liczenia skuteczności
> z realnej pracy techników (opis niżej).

---

## Znaleziony błąd: moduł nie rozumiał polszczyzny

Słownik słów kluczowych zapisany był **bez polskich znaków** (`haslo`, `siec`,
`sprzet`, `uprawnien`), a dopasowanie polegało na zwykłym wyszukiwaniu
podciągu. Użytkownicy piszą natomiast z polskimi znakami.

W efekcie `"haslo"` **nie pasowało** do `"hasło"` — litera `ł` to inny znak niż
`l`. Poprawnie napisane zgłoszenie „Zapomniane hasło" nie dopasowywało się do
niczego i po cichu wpadało do kategorii domyślnej.

Ta sama wada dotyczyła `sieć`, `sprzęt`, `uprawnień`, `wyłudzenie` i innych.
Problem był częściowo zamaskowany: zgłoszenie trafiało czasem do właściwej
kategorii **przez przypadek**, bo pasowało inne słowo (np. „Nie pamiętam hasła
do poczty" trafiało do kategorii *Poczta* — z właściwego powodu, ale nie tego,
o który chodziło).

**Rozwiązanie:** tekst wejściowy jest normalizowany przed dopasowaniem —
polskie znaki sprowadzane są do postaci podstawowej. Litera `ł` nie rozkłada
się przez `unicodedata`, więc wymaga podmiany wprost. Test pilnuje, by żaden
rdzeń w słowniku nie zawierał polskiego znaku — taki rdzeń nigdy by się nie
dopasował.

---

## Jak działa moduł

### 1. Normalizacja
`„Zapomniane HASŁO"` → `„zapomniane haslo"`. Dzięki temu wielkość liter,
odmiana i polskie znaki przestają mieć znaczenie.

### 2. Zliczanie dowodów
Każde dopasowane słowo dokłada punkty swojej kategorii. Wygrywa **suma
dowodów**, a nie pierwsze trafienie. Słowa mają wagi 1–3, bo nie są równie
jednoznaczne: `phishing` mówi o zgłoszeniu znacznie więcej niż `mail`.

Rdzenie zapisujemy bez końcówek (`drukark`), co obsługuje polską odmianę:
*drukarka, drukarki, drukarkę*.

### 3. Priorytet i eskalacja
Priorytet bierze się z najpoważniejszego dopasowanego słowa, a następnie jest
podnoszony, gdy w tekście widać:

- **skalę awarii** — „cały dział", „wszyscy", „nikt nie",
- **pilność lub całkowitą niesprawność** — „pilne", „awaria", „nie włącza",
  „blokuje pracę".

> Celowo **nie** traktujemy „nie działa" jako sygnału pilności. Po polsku to
> domyślny sposób opisania dowolnej usterki („drukarka nie działa", „myszka
> nie działa"). Gdyby podnosiło priorytet, niemal każde zgłoszenie byłoby
> pilne — a wtedy priorytety przestają cokolwiek rozróżniać. Osobny test
> tego pilnuje.

### 4. Bezpieczeństwo zawsze krytyczne
Zgłoszenie zaklasyfikowane jako *Bezpieczeństwo* dostaje priorytet krytyczny
niezależnie od reszty tekstu. Fałszywy alarm kosztuje godzinę pracy technika;
przeoczony phishing może kosztować znacznie więcej.

### 5. Przyznanie się do niewiedzy
Gdy nie pasuje **żadne** słowo, moduł nie zgaduje po cichu. Zwraca pewność
`0.0` i flagę `wymaga_weryfikacji`. W interfejsie takie zgłoszenie dostaje
znacznik **„AI ?"** z podpowiedzią, że kategoria wymaga sprawdzenia.

Pewność liczona jest z dwóch czynników: jak bardzo zwycięska kategoria dominuje
nad pozostałymi oraz ile niezależnych słów ją wskazuje. Próg weryfikacji: 0,4.

### 6. Uzasadnienie decyzji
Moduł zwraca listę słów, które zadecydowały (`dopasowania`). Technik widzi
**dlaczego** zgłoszenie trafiło do danej kategorii, zamiast dostawać
nieprzejrzysty werdykt.

---

## Pomiar skuteczności na żywo

`GET /api/ai/skutecznosc` (technik/admin) liczy jakość modułu z **rzeczywistej
pracy zespołu**, a nie z deklaracji. Każda ręczna zmiana kategorii przez
technika to sygnał pomyłki na konkretnym zgłoszeniu.

Zestawienie zawiera:

| Pole | Znaczenie |
|---|---|
| `zgloszen_z_ai` | Ile zgłoszeń skategoryzował moduł |
| `poprawionych_recznie` | Ile z nich technik przekwalifikował |
| `skutecznosc` | `1 − poprawione / wszystkie` |
| `srednia_pewnosc` | Średnia pewność decyzji |
| `wymaga_weryfikacji` | Zgłoszenia poniżej progu pewności |
| `najczestsze_pomylki` | Z jakiej kategorii na jaką poprawiano |

Ostatnia pozycja jest najbardziej praktyczna: wprost wskazuje, których słów
kluczowych brakuje. Jeśli technicy regularnie poprawiają *Oprogramowanie* na
*Konta i dostęp*, wiadomo, gdzie uzupełnić słownik.

To zamyka pętlę: moduł jest mierzalny i można go ulepszać na podstawie danych,
zamiast zgadywać.

---

## Podmiana na model językowy

Kontraktem modułu jest funkcja `categorize(title, description)` zwracająca
słownik. Wystarczy podmienić jej wnętrze, zachowując zwracane pola.

**Ostrzeżenie wydajnościowe.** Wywołanie modelu przez sieć w ścieżce tworzenia
zgłoszenia oznacza, że użytkownik czeka na odpowiedź obcej usługi — zamiast
milisekund, setki milisekund lub sekundy. Co gorsza, awaria dostawcy
zablokowałaby **zakładanie zgłoszeń**, czyli podstawową funkcję systemu.

Jeśli model językowy ma zostać podłączony, powinien mieć:

1. **krótki limit czasu** (1–2 s),
2. **awaryjne przejście** do dopasowania słownikowego, gdy model nie odpowie,
3. rozważenie **przetwarzania w tle** — zgłoszenie powstaje natychmiast
   z kategorią wstępną, a model uściśla ją chwilę później.

Obecne rozwiązanie działa lokalnie: bez kluczy API, kosztów, opóźnień
sieciowych i bez wysyłania treści zgłoszeń (często zawierających dane
firmowe) do zewnętrznego dostawcy.

---

## Ograniczenia

- **Dopasowanie słownikowe nie rozumie kontekstu.** „Nie chcę zgłaszać
  phishingu" zostanie zaklasyfikowane jako incydent bezpieczeństwa. W praktyce
  taka konstrukcja w zgłoszeniach do helpdesku jest rzadka, a błąd jest
  bezpieczny (fałszywy alarm, nie przeoczenie).
- **Brak obsługi literówek.** „drukrka" nie dopasuje się do „drukark".
- **Zbiory oceny są małe** (29 i 18 zgłoszeń) i tworzone ręcznie.
- **Słownik jest jednojęzyczny** — obsługuje wyłącznie polski.
- **Wagi dobrano ręcznie**, na podstawie oceny eksperckiej, a nie danych.

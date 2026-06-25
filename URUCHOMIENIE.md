# JAK URUCHOMIĆ I POKAZAĆ, ŻE BACK-END DZIAŁA

Ta instrukcja prowadzi krok po kroku. Wystarczy wpisywać polecenia w kolejności.
Całość zajmuje około 3 minuty.

---

## CO JEST POTRZEBNE

- Zainstalowany **Python 3.8 lub nowszy**
- Edytor **Visual Studio Code** (zalecane) lub zwykły terminal

Sprawdź, czy masz Pythona — wpisz w terminalu:

```
py --version
```

Jeśli pojawi się numer wersji (np. `Python 3.11.6`) — jest dobrze.
Jeśli pojawi się błąd — zainstaluj Pythona ze strony **python.org** i podczas
instalacji zaznacz pole **„Add Python to PATH”**.

---

## KROK 0 — OTWÓRZ FOLDER W VS CODE

1. Otwórz Visual Studio Code
2. `File → Open Folder` i wybierz folder z plikami back-endu (`hd`)
3. Otwórz terminal: menu `Terminal → New Terminal` (lub klawisze ``Ctrl + ` ``)

Wszystkie poniższe polecenia wpisujesz w tym terminalu.

---

## KROK 1 — ZAINSTALUJ BIBLIOTEKI (jednorazowo)

```
py -m pip install flask requests
```

Jeśli pojawi się błąd `No module named pip`, najpierw wpisz:

```
py -m ensurepip --upgrade
```

a potem ponownie polecenie instalacji.

---

## KROK 2 — PRZYGOTUJ BAZĘ DANYCH

```
py seed.py
```

Powinno pojawić się:

```
Baza danych utworzona i wypełniona.
  Uzytkownicy:        6
  Zgloszenia (razem): 18
  Otwarte:            15
  W trakcie:          5
  Krytyczne:          2
```

To znaczy, że baza działa i jest wypełniona przykładowymi danymi.

---

## KROK 3 — URUCHOM SERWER

```
py app.py
```

Powinno pojawić się:

```
 * Running on http://127.0.0.1:5000
```

**Zostaw ten terminal otwarty** — serwer musi działać przez cały pokaz.

> Uwaga: otwarcie adresu `http://127.0.0.1:5000` w przeglądarce pokaże tylko
> krótką informację w formacie JSON, że API działa. To normalne — back-end nie
> ma strony głównej, tylko punkty końcowe pod `/api/...`.

---

## KROK 4 — SPRAWDŹ, ŻE WSZYSTKO DZIAŁA (najważniejszy krok)

Otwórz **drugi terminal**: w panelu terminala kliknij ikonę **„+”**
(lub `Terminal → New Terminal`). Pierwszy terminal z serwerem zostaje nietknięty.

W nowym terminalu wpisz:

```
py demo.py
```

Skrypt wykona po kolei wszystkie operacje back-endu i przy każdej wypisze wynik.
Na końcu zobaczysz podsumowanie:

```
  WYNIK: 17 testow OK, 0 bledow
```

**Jeśli widzisz `0 bledow` — back-end działa w pełni poprawnie.**

---

## CO DOKŁADNIE POKAZUJE `demo.py` (do omówienia na pokazie)

Skrypt jest podzielony na 7 sekcji. Każda potwierdza inną funkcję back-endu:

1. **Logowanie i role (RBAC)** — logowanie pracownika i technika; błędne hasło
   zwraca błąd 401.
2. **Pulpit** — dane do dashboardu: liczba zgłoszeń otwartych, w trakcie,
   krytycznych oraz rozkład zgłoszeń według kategorii (do wykresu).
3. **Automatyczna kategoryzacja AI** — pracownik tworzy zgłoszenie „Nie działa
   VPN”, a moduł AI **samodzielnie** nadaje kategorię *Sieć* i priorytet *Wysoki*
   oraz wyznacza termin SLA.
4. **Widoczność według roli** — pracownik widzi tylko swoje zgłoszenia, technik
   widzi wszystkie i może je filtrować (np. tylko krytyczne).
5. **Obsługa zgłoszenia** — technik podejmuje zgłoszenie, dodaje notatkę
   wewnętrzną (niewidoczną dla pracownika), rozwiązuje je i zamyka. Każda zmiana
   statusu jest sprawdzana.
6. **Ścieżka audytu** — pełna historia zgłoszenia: kto, co i kiedy zmienił —
   od utworzenia, przez kategoryzację AI, aż po zamknięcie.
7. **Kontrola uprawnień (testy negatywne)** — system celowo **odmawia**
   niedozwolonych operacji: pracownik nie może zamknąć zgłoszenia (błąd 403),
   nie można przeskoczyć statusu (błąd 400), brak autoryzacji blokuje dostęp
   (błąd 401). Te „błędy” są **zamierzone** i potwierdzają, że zabezpieczenia
   działają.

---

## SZYBKIE SPRAWDZENIE POJEDYNCZYCH FUNKCJI (opcjonalnie)

Gdy serwer działa, można odpytać API również ręcznie. W drugim terminalu:

Statystyki pulpitu:
```
curl http://localhost:5000/api/dashboard -H "X-User-Id: 4"
```

Test samej kategoryzacji AI na dowolnym tekście:
```
curl -X POST http://localhost:5000/api/ai/categorize -H "Content-Type: application/json" -H "X-User-Id: 1" -d "{\"title\":\"phishing\",\"description\":\"podejrzany mail z prosba o haslo\"}"
```

---

## PROBLEMY I ROZWIĄZANIA

| Komunikat                              | Rozwiązanie                                            |
|----------------------------------------|-------------------------------------------------------|
| `'py' nie jest rozpoznawane...`        | Zainstaluj Pythona z python.org, zaznacz „Add to PATH”|
| `No module named pip`                  | Wpisz `py -m ensurepip --upgrade`                     |
| `No module named flask`                | Wpisz `py -m pip install flask requests`              |
| `Address already in use` / port zajęty | Zamknij poprzedni serwer (Ctrl+C w jego terminalu)    |
| `Serwer nie odpowiada` przy `demo.py`  | Najpierw uruchom serwer (`py app.py`) w 1. terminalu  |

---

## RESET DANYCH PRZED POKAZEM

Aby zacząć od czystych, przewidywalnych danych:

1. W terminalu z serwerem naciśnij `Ctrl + C` (zatrzymanie serwera)
2. `py seed.py`
3. `py app.py`
4. W drugim terminalie `py demo.py`

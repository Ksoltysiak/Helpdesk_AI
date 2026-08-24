# Audyt bezpieczeństwa

Weryfikacja projektu względem listy 20 zabezpieczeń. Każdy punkt sprawdzono
w działającym kodzie — nie na podstawie założeń. Punkty nieadekwatne do
architektury tego projektu zostały **odrzucone wraz z uzasadnieniem**, zamiast
udawać, że są spełnione.

**Data audytu:** 24 sierpnia 2026

## Wynik zbiorczy

| Status | Liczba | Znaczenie |
|---|---|---|
| Było już wdrożone | 9 | Zweryfikowane testem, bez zmian |
| Wdrożone w tym audycie | 7 | Znalezione braki, uzupełnione |
| Nie dotyczy | 4 | Uzasadnienie poniżej |
| Świadomie odrzucone | 1 | Uzasadnienie poniżej |

---

## Tabela wyników

| # | Zabezpieczenie | Status | Uwagi |
|---|---|---|---|
| 1 | Ukrycie kluczy API | ✅ Było | Brak kluczy zewnętrznych; `SECRET_KEY` ze zmiennej środowiskowej, `.env` w `.gitignore` |
| 2 | Usunięcie sekretów z historii Git | ✅ Było | Zweryfikowano całą historię — w repozytorium jest wyłącznie szablon `.env.example` |
| 3 | Publiczny klucz bazy danych | ➖ Nie dotyczy | Pojęcie z Supabase/Firebase; tu baza jest dostępna wyłącznie po stronie serwera |
| 4 | Bezpieczeństwo na poziomie wiersza (RLS) | ✅ Odpowiednik | SQLite nie ma RLS — filtrowanie w zapytaniu SQL wg roli |
| 5 | Szyfrowanie danych wrażliwych | ⚠️ Częściowo | Hasła hashowane; szyfrowanie pliku bazy — decyzja wdrożeniowa |
| 6 | Autoryzacja po stronie serwera | ✅ Było | JWT weryfikowany przy każdym żądaniu |
| 7 | Blokada dostępu do cudzych rekordów | ✅ Było | Zweryfikowano: 403 na wszystkich ścieżkach międzykontowych |
| 8 | Blokada manipulacji polami | ✅ Było | Zweryfikowano: pola narzucone przez klienta są ignorowane |
| 9 | Bezpieczne ciasteczka sesji | ➖ Nie dotyczy | Aplikacja nie używa ciasteczek ani sesji serwerowej |
| 10 | Hashowanie haseł | ✅ Było | `scrypt` (werkzeug) |
| 11 | Limit prób logowania | 🔧 **Wzmocnione** | Dodano limit na konto + obsługę wspólnego magazynu liczników |
| 12 | Ochrona przed botami | 🔧 **Wdrożone inaczej** | Zamiast CAPTCHY — spowolnienie per konto (uzasadnienie niżej) |
| 13 | Parametryzowane zapytania | ✅ Było | Zweryfikowano: brak sklejania wartości w SQL |
| 14 | Walidacja danych wejściowych | 🔧 **Naprawiony błąd** | Nietekstowe dane powodowały HTTP 500 — patrz niżej |
| 15 | Escapowanie treści użytkownika | ✅ Było | Zweryfikowano atakiem XSS w przeglądarce — żaden ładunek się nie wykonał |
| 16 | Ograniczenia wysyłania plików | ➖ Nie dotyczy | Brak endpointu przyjmującego pliki |
| 17 | Ograniczenie danych w odpowiedziach | ✅ Było | Zweryfikowano: brak wycieku hasła i pól wewnętrznych |
| 18 | Nagłówki bezpieczeństwa | 🔧 **Uzupełnione** | Dodano `Permissions-Policy`, `Strict-Transport-Security`, `object-src`, `base-uri`, `form-action`, `frame-ancestors` |
| 19 | Wymuszanie HTTPS | 🔧 **Wdrożone** | Przekierowanie 308 + HSTS, włączane `FORCE_HTTPS=1` |
| 20 | Skanowanie zależności | 🔧 **Wdrożone** | `pip-audit` w CI + Dependabot — **znaleziono 15 podatności** |

---

## Znalezione problemy i ich naprawa

### 20. Podatne zależności — 15 znanych luk (najpoważniejsze znalezisko)

Pierwsze uruchomienie `pip-audit` wykazało podatności w trzech pakietach:

| Pakiet | Wersja | Liczba luk | Naprawiono w |
|---|---|---|---|
| **PyJWT** | 2.9.0 | **12** | 2.13.0 |
| requests | 2.32.3 | 2 | 2.33.0 |
| Flask | 3.0.3 | 1 | 3.1.3 |

Najpoważniejszy jest **PyJWT** — to biblioteka, która uwierzytelnia **każde**
żądanie w tej aplikacji. Wszystkie zależności podniesiono; ponowne skanowanie
zwraca *„No known vulnerabilities found"*.

Aktualizacja ujawniła zmianę wymagań: PyJWT od wersji 2.12 egzekwuje RFC 7519
i odrzuca tokeny, w których pole `sub` nie jest tekstem. Kod zapisywał tam
liczbę, więc **cała autoryzacja przestała działać** — wykrył to zestaw testów
(70 nieudanych testów). Poprawiono zapis i odczyt pola.

> **Skutek wdrożeniowy:** tokeny wydane przed tą zmianą przestają być ważne.
> Użytkownicy muszą zalogować się ponownie — jednorazowo, przy aktualizacji.

Zabezpieczenie na przyszłość: `pip-audit --strict` jako osobne zadanie w CI oraz
Dependabot śledzący zależności Pythona, obraz Dockera i wersje akcji CI.

### 14. Nieprawidłowy typ danych powodował błąd HTTP 500

Pola tekstowe sprawdzały tylko obecność i długość, ale nie **typ**. Przysłanie
liczby lub obiektu kończyło się nieobsłużonym wyjątkiem:

```
POST /api/tickets  {"title": 12345, "description": "ok"}
  → TypeError: object of type 'int' has no len()
  → HTTP 500, treść: text/html
```

Dotyczyło to `POST /tickets` oraz `POST /tickets/{id}/notes`. Konsekwencje:
odpowiedź HTML zamiast JSON łamała udokumentowany kontrakt API, a każde takie
żądanie generowało ślad wyjątku po stronie serwera.

Wprowadzono wspólną funkcję `pole_tekstowe()` sprawdzającą typ, przycinającą
białe znaki i weryfikującą długość. Dodatkowo zarejestrowano obsługę błędów,
która dla ścieżek `/api/*` zawsze zwraca JSON — również dla kodów 405 i 500 —
i **nigdy** nie ujawnia treści wyjątku.

### 11 i 12. Limit logowania: braki i świadome decyzje

Istniejący limit 10/min działał, ale miał dwa ograniczenia:

**Licznik w pamięci procesu.** Przy `gunicorn --workers 2` każdy proces liczy
osobno, więc rzeczywisty limit jest dwukrotnie wyższy. Widać to w praktyce —
blokada następowała przy siódmej próbie zamiast szóstej. Dodano obsługę
`RATELIMIT_STORAGE_URI`; ustawienie wspólnego magazynu przywraca zadeklarowany
limit.

**Brak ochrony konta przy ataku rozproszonym.** Limit na adres IP nie utrudnia
zgadywania hasła do jednego konta z wielu adresów. Dodano drugi limit —
5/min i 20/h — z kluczem zawierającym nazwę użytkownika.

**Dlaczego nie CAPTCHA (punkt 12).** To wewnętrzne narzędzie dla znanych,
kilkuosobowych zespołów. CAPTCHA wprowadziłaby zależność od usługi zewnętrznej,
przekazywała dane użytkowników stronie trzeciej i utrudniała pracę ludziom,
którzy logują się codziennie — nie rozwiązując przy tym rzeczywistego zagrożenia,
jakim jest zgadywanie hasła. Spowolnienie per konto adresuje to zagrożenie
bezpośrednio.

**Dlaczego nie blokada konta po N próbach.** Blokada byłaby narzędziem do
odcinania ludzi od systemu: napastnik, znając cudzy login, mógłby celowo
zablokować mu dostęp. Spowolnienie daje ochronę przed zgadywaniem hasła, nie
dając możliwości zablokowania prawdziwego użytkownika. Osobny test pilnuje, że
wyczerpanie limitu jednego konta nie wpływa na pozostałe.

### Dodatkowo: usunięto zbędny skrypt z obcego serwera

Audyt nagłówka CSP ujawnił, że frontend ładował bibliotekę `lucide`
z `unpkg.com`. Sprawdzenie wykazało, że **nie była do niczego używana**:
wszystkie ikony są osadzone jako inline SVG, a wywołanie `lucide.createIcons()`
(7 razy w kodzie) nie miało czego przetworzyć — w całym projekcie nie ma ani
jednego atrybutu `data-lucide`.

Oznaczało to, że każde wczytanie strony pobierało i **wykonywało** obcy skrypt,
który nic nie robił. Skrypt z sieci CDN działa z pełnymi uprawnieniami strony —
w tym z dostępem do tokenu w `sessionStorage`. Gdyby pakiet albo sam serwer CDN
został przejęty, byłaby to droga do wykradzenia sesji wszystkich użytkowników.

Bibliotekę i wszystkie jej wywołania usunięto. Pozwoliło to zaostrzyć politykę
CSP: `script-src` nie zezwala już na żaden obcy serwer, a przy okazji dodano
`object-src 'none'`, `base-uri 'self'`, `form-action 'self'` oraz
`frame-ancestors 'none'`. Interfejs działa bez zmian (zweryfikowane w
przeglądarce: brak błędów JavaScript, wszystkie ikony na miejscu), a osobny
test pilnuje, by obcy skrypt nie wrócił niepostrzeżenie.

> **Pozostała zależność zewnętrzna:** krój pisma Inter z `fonts.googleapis.com`.
> Nie usunięto go, bo wpływa na wygląd przygotowany przez inną osobę z zespołu,
> a arkusz stylów i plik czcionki nie mogą wykonać kodu. Warto jednak wiedzieć,
> że każde wczytanie strony ujawnia adres IP użytkownika serwerom Google —
> jeśli to problem, czcionkę należy hostować lokalnie.

### 18 i 19. HTTPS i brakujące nagłówki

Dodano `Permissions-Policy` (jawne wyłączenie kamery, mikrofonu, geolokalizacji,
płatności i USB — aplikacja ich nie używa) oraz `Strict-Transport-Security`.

Wymuszanie HTTPS (przekierowanie 308) i HSTS włącza zmienna `FORCE_HTTPS=1`.
Oba mechanizmy są **domyślnie wyłączone**, ponieważ HSTS wysłany po HTTP jest
ignorowany przez przeglądarkę, a przy pracy lokalnej potrafi trwale zablokować
dostęp do `localhost`.

Dodano też obsługę `TRUST_PROXY`. Za odwrotnym proxy prawdziwy adres klienta
znajduje się w nagłówku `X-Forwarded-For`; bez jego odczytania wszystkie żądania
wyglądają jak pochodzące z jednego adresu i **dzielą jeden licznik limitu** —
jeden atakujący zablokowałby logowanie wszystkim. Zaufanie do tego nagłówka jest
włączane wyłącznie jawnie: gdyby aplikacja stała bezpośrednio w sieci,
napastnik mógłby go podrobić i obejść limity.

---

## Punkty nieadekwatne do tej architektury

**3. Publiczny klucz bazy danych.** Pojęcie z platform typu Supabase czy
Firebase, gdzie przeglądarka łączy się z bazą bezpośrednio i potrzebuje klucza
o ograniczonych uprawnieniach. Tutaj przeglądarka nigdy nie rozmawia z bazą —
każde zapytanie przechodzi przez API, które sprawdza token i rolę. Nie ma klucza
do upublicznienia.

**9. Bezpieczne ciasteczka sesji.** Aplikacja nie używa ciasteczek ani sesji
serwerowej — potwierdzono brakiem nagłówka `Set-Cookie` i brakiem odwołań do
`flask.session`. Token trafia do `sessionStorage`.

> **Uczciwa uwaga o tym wyborze.** Ciasteczko `HttpOnly` jest odporne na
> odczyt przez JavaScript, a `sessionStorage` nie — przy skutecznym ataku XSS
> token można wykraść. W zamian znika cała klasa podatności CSRF. Przy obecnym
> stanie (potwierdzone escapowanie treści, restrykcyjne CSP) uznano ten
> kompromis za akceptowalny. Przejście na ciasteczka `HttpOnly` + `SameSite`
> wymagałoby dołożenia ochrony CSRF.

**16. Ograniczenia wysyłania plików.** Aplikacja nie przyjmuje plików. Pierwotny
frontend miał pole załącznika kodujące obraz do base64 i trzymające go w pamięci
przeglądarki, ale nie istniał żaden endpoint, który by go przyjął — pole usunięto
przy integracji z API. Gdyby wysyłanie plików miało wrócić, wymagałoby:
weryfikacji typu MIME po zawartości (nie po rozszerzeniu), limitu rozmiaru,
zapisu poza katalogiem serwowanym statycznie i losowych nazw plików.

**5. Szyfrowanie danych wrażliwych — częściowo.** Hasła są hashowane
(nieodwracalnie). Plik bazy SQLite nie jest szyfrowany na dysku — treść zgłoszeń
i adresy e-mail są w nim jawne. Nie wdrożono tego, ponieważ przy obecnym modelu
wdrożenia (jeden kontener, wolumen Dockera) szyfrowanie w spoczynku ma sens
dopiero razem z decyzją o docelowej bazie i sposobie hostowania. Zalecenie:
rozstrzygnąć przy przejściu na hosting — szyfrowanie wolumenu po stronie
dostawcy zwykle wystarcza i nie wymaga zmian w kodzie.

---

## Czego audyt nie obejmuje

- **Brak testów bezpieczeństwa frontendu poza XSS** — nie sprawdzano np.
  clickjackingu w praktyce (nagłówek `X-Frame-Options` jest ustawiony,
  ale nie testowano zachowania w osadzonej ramce).
- **Brak testów obciążeniowych i odporności na DoS** na poziomie aplikacji.
- **Brak audytu samego SQLite pod kątem współbieżnych zapisów** — znany temat
  do rozstrzygnięcia przy wdrożeniu (patrz `README.md`).
- **Skanowanie zależności obejmuje wyłącznie pakiety Pythona i obraz bazowy.**
  Frontend nie ma menedżera pakietów. Po usunięciu biblioteki `lucide` jedyną
  zewnętrzną zależnością pozostaje krój pisma z Google Fonts (nie wykonuje kodu).

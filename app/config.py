"""Konfiguracja aplikacji — jedyne miejsce, w którym czytane są zmienne
środowiskowe.

Wcześniej były rozproszone po czterech modułach (`SECRET_KEY` w warstwie
uwierzytelniania, `DB_PATH` w dostępie do bazy, `FORCE_HTTPS` w punkcie
startowym, `RATELIMIT_STORAGE_URI` w limitach). Trudno było odpowiedzieć na
pytanie „czym w ogóle da się skonfigurować tę aplikację" — trzeba było
przeszukać cały projekt.

Wartości są modułowymi atrybutami, a nie stałymi importowanymi po nazwie:
moduły odczytują je przez `config.NAZWA` w momencie użycia. Dzięki temu testy
mogą je podmienić bez przeładowywania połowy aplikacji.
"""

import os
import warnings

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _wlaczone(nazwa: str) -> bool:
    """Czy przełącznik środowiskowy jest włączony."""
    return os.environ.get(nazwa, "").lower() in ("1", "true", "yes", "on")


# --- Baza danych -------------------------------------------------------
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "helpdesk.db"))

# --- Klucz podpisujący tokeny -----------------------------------------
MIN_DLUGOSC_KLUCZA = 32  # RFC 7518 sekcja 3.2 dla HMAC-SHA256

KLUCZ_DOMYSLNY = "dev-only-insecure-key"


def rozstrzygnij_klucz(klucz):
    """Zwraca (klucz_do_uzycia, ostrzezenie_albo_None).

    Wydzielone z kodu wykonywanego przy imporcie, zeby dalo sie sprawdzic
    kazdy przypadek zwyklym testem — bez przeladowywania modulu, ktore
    nadpisywaloby stan wspoldzielony z reszta testow.
    """
    if not klucz:
        return KLUCZ_DOMYSLNY, (
            "SECRET_KEY env var not set — using insecure default. "
            "Set SECRET_KEY in production."
        )
    if len(klucz.encode()) < MIN_DLUGOSC_KLUCZA:
        return klucz, (
            f"SECRET_KEY is shorter than {MIN_DLUGOSC_KLUCZA} bytes — weak signing key. "
            f"Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    return klucz, None


SECRET_KEY, _ostrzezenie = rozstrzygnij_klucz(os.environ.get("SECRET_KEY"))
if _ostrzezenie:
    # Sama tresc ostrzezenia jest sprawdzana testami `rozstrzygnij_klucz`,
    # a jego faktyczne wyemitowanie — testami uruchamiajacymi interpreter
    # w podprocesie (pokrycie nie siega do podprocesu).
    warnings.warn(_ostrzezenie, stacklevel=1)  # pragma: no cover

TOKEN_TTL = 8 * 3600  # ważność tokenu w sekundach

# --- Wdrożenie ---------------------------------------------------------
# Przekierowanie na HTTPS i nagłówek HSTS. Domyślnie wyłączone: HSTS wysłany
# po HTTP jest ignorowany, a lokalnie potrafi zablokować dostęp do localhost.
FORCE_HTTPS = _wlaczone("FORCE_HTTPS")

# Odczyt adresu klienta z X-Forwarded-For. Włączać WYŁĄCZNIE za odwrotnym
# proxy — inaczej nagłówek można podrobić i obejść limity żądań.
TRUST_PROXY = _wlaczone("TRUST_PROXY")

# Wspólny magazyn liczników limitu. Bez niego każdy proces gunicorna liczy
# osobno, więc przy N procesach limit jest N razy wyższy niż zadeklarowany.
RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")

# --- Limity danych wejściowych ----------------------------------------
TITLE_MAX = 200
DESC_MAX = 5000
NOTE_MAX = 2000

# Górny limit rozmiaru ciała żądania. Limity długości pól działają dopiero
# po sparsowaniu JSON-a — bez tego klient mógłby przysłać wielomegabajtowe
# ciało, które proces i tak wczyta w całości do pamięci. 64 KB mieści
# najdłuższy poprawny opis nawet przy kodowaniu każdego znaku jako \uXXXX.
MAX_ROZMIAR_ZADANIA = 64 * 1024

# --- Stronicowanie -----------------------------------------------------
# Bez górnego limitu pojedyncze żądanie może zmusić serwer do zbudowania
# odpowiedzi o rozmiarze całej bazy.
PER_PAGE_DOMYSLNIE = 50
PER_PAGE_MAX = 200

# --- Kompresja odpowiedzi ---------------------------------------------
MIN_BAJTOW_DO_KOMPRESJI = 1024  # poniżej narzut gzip przeważa nad zyskiem
TYPY_KOMPRESOWANE = {
    "application/json", "application/yaml",
    "text/html", "text/css", "text/javascript", "application/javascript",
    "image/svg+xml",
}

# --- Eskalacja SLA i powiadomienia ------------------------------------
# Proces roboczy (`python -m app.zadania`) co tyle sekund sprawdza terminy
# SLA i wysyła zaległe e-maile.
WORKER_INTERWAL = int(os.environ.get("WORKER_INTERWAL", "60"))

# Plik, którego czas modyfikacji proces roboczy odświeża po każdym przebiegu.
# Kontrola zdrowia kontenera sprawdza na tej podstawie, czy pętla nie stoi.
# Puste = bez znacznika (np. przy uruchomieniu lokalnym).
WORKER_HEARTBEAT = os.environ.get("WORKER_HEARTBEAT", "")

# Wysyłka e-maili. Bez SMTP_HOST powiadomienia działają tylko w aplikacji.
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
# starttls (port 587) | ssl (port 465) | brak (tylko serwer w sieci lokalnej,
# np. mailpit do testów — hasło szłoby jawnym tekstem)
SMTP_TLS = os.environ.get("SMTP_TLS", "starttls").lower()
SMTP_FROM = os.environ.get("SMTP_FROM", "helpdesk@localhost")

# Adres aplikacji widziany przez użytkownika — do linku w treści e-maila.
APP_URL = os.environ.get("APP_URL", "").rstrip("/")

# E-mail, którego nie udało się wysłać tyle razy, przestaje być ponawiany.
EMAIL_MAX_PROB = 5
# Starsze powiadomienia nie idą już e-mailem — po dłuższej awarii serwera
# poczty (albo po włączeniu SMTP po czasie) użytkownik nie dostanie lawiny
# nieaktualnych wiadomości. Nadal widzi je w aplikacji.
EMAIL_WAZNOSC_GODZIN = 24

# Ile powiadomień zwraca lista (dzwonek w nagłówku).
POWIADOMIEN_DOMYSLNIE = 20
POWIADOMIEN_MAX = 100

# --- Ścieżki -----------------------------------------------------------
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
SPEC_FILE = "openapi.yaml"
DOCS_URL = "/api/docs"
SPEC_URL = "/api/openapi.yaml"

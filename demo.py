import requests
import json
import os
import sys

# Adres da sie nadpisac, bo aplikacja moze stac za nginx (port 8080)
# albo byc uruchomiona bezposrednio (port 5000).
BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000").rstrip("/")
BASE = f"{BASE_URL}/api"

ok = 0
fail = 0


def show(label, resp, expect=200):
    global ok, fail
    passed = resp.status_code == expect
    mark = "[OK] " if passed else "[BLAD]"
    if passed:
        ok += 1
    else:
        fail += 1
    print(f"\n{mark} {label}  (HTTP {resp.status_code}, oczekiwano {expect})")
    try:
        print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
    except Exception:
        print(resp.text)


def section(title):
    print("\n" + "=" * 64)
    print("  " + title)
    print("=" * 64)


def auth(token):
    """Naglowek autoryzacyjny z tokenem JWT."""
    return {"Authorization": f"Bearer {token}"}


try:
    requests.get(f"{BASE_URL}/", timeout=2)
except requests.exceptions.RequestException:
    print(f"Serwer pod {BASE_URL} nie odpowiada. Uruchom go najpierw.")
    sys.exit(1)


section("1. LOGOWANIE I ROLE (RBAC)")

r_prac = requests.post(f"{BASE}/auth/login",
                       json={"username": "k.nowak", "password": "haslo123"})
show("Logowanie pracownika (Katarzyna)", r_prac)

r_tech = requests.post(f"{BASE}/auth/login",
                       json={"username": "m.lewandowski", "password": "tech123"})
show("Logowanie technika (Marek)", r_tech)

show("Bledne haslo zwraca 401", requests.post(f"{BASE}/auth/login",
     json={"username": "k.nowak", "password": "zle"}), expect=401)

if r_prac.status_code != 200 or r_tech.status_code != 200:
    print("\nLogowanie nie powiodlo sie — czy baza zostala wypelniona (seed.py)?")
    sys.exit(1)

PRACOWNIK = auth(r_prac.json()["token"])
TECHNIK = auth(r_tech.json()["token"])


section("2. PULPIT (DANE DLA DASHBOARDU)")
show("Statystyki + rozklad kategorii", requests.get(f"{BASE}/dashboard", headers=TECHNIK))
show("Odtworzenie sesji z tokenu (/auth/me)", requests.get(f"{BASE}/auth/me", headers=PRACOWNIK))


section("3. AUTOMATYCZNA KATEGORYZACJA AI")
show("Test modulu AI (samo zapytanie)", requests.post(f"{BASE}/ai/categorize",
     headers=PRACOWNIK, json={"title": "Nie dziala VPN", "description": "Blad TLS na laptopie"}))

r = requests.post(f"{BASE}/tickets", headers=PRACOWNIK,
     json={"title": "Nie dziala VPN na moim laptopie",
           "description": "Od rana nie moge polaczyc sie z firmowym VPN. Blad TLS handshake."})
show("Pracownik tworzy zgloszenie -> AI nadaje kategorie i priorytet", r, expect=201)
ticket_id = r.json().get("id")


section("4. WIDOCZNOSC WG ROLI")
show("Pracownik widzi tylko swoje zgloszenia", requests.get(f"{BASE}/tickets", headers=PRACOWNIK))
show("Technik widzi wszystkie zgloszenia", requests.get(f"{BASE}/tickets", headers=TECHNIK))
show("Technik filtruje po priorytecie = Krytyczny",
     requests.get(f"{BASE}/tickets?priority=Krytyczny", headers=TECHNIK))


section("5. OBSLUGA ZGLOSZENIA PRZEZ TECHNIKA")
show("Podjecie zgloszenia (Nowe -> W trakcie)",
     requests.patch(f"{BASE}/tickets/{ticket_id}", headers=TECHNIK, json={"status": "W trakcie"}))
show("Notatka wewnetrzna (ukryta przed pracownikiem)",
     requests.post(f"{BASE}/tickets/{ticket_id}/notes", headers=TECHNIK,
     json={"content": "Certyfikat VPN wygasl. Odnawiam.", "internal": True}), expect=201)
show("Rozwiazanie (W trakcie -> Rozwiazane)",
     requests.patch(f"{BASE}/tickets/{ticket_id}", headers=TECHNIK, json={"status": "Rozwiazane"}))
show("Zamkniecie (Rozwiazane -> Zamkniete)",
     requests.patch(f"{BASE}/tickets/{ticket_id}", headers=TECHNIK, json={"status": "Zamkniete"}))


section("6. SCIEZKA AUDYTU (PELNA HISTORIA)")
show(f"Audit trail zgloszenia #{ticket_id}", requests.get(f"{BASE}/tickets/{ticket_id}/audit", headers=TECHNIK))


section("7. KONTROLA UPRAWNIEN I BEZPIECZENSTWO (TESTY NEGATYWNE)")
show("Pracownik NIE moze zmienic statusu (403)",
     requests.patch(f"{BASE}/tickets/1", headers=PRACOWNIK, json={"status": "Zamkniete"}), expect=403)
show("Niedozwolone przejscie Nowe -> Zamkniete (400)",
     requests.patch(f"{BASE}/tickets/2", headers=TECHNIK, json={"status": "Zamkniete"}), expect=400)
show("Brak tokenu (401)", requests.get(f"{BASE}/tickets"), expect=401)
show("Podrobiony token zostaje odrzucony (401)",
     requests.get(f"{BASE}/tickets", headers=auth("niepoprawny.token.jwt")), expect=401)
show("Zbyt dlugi tytul zostaje odrzucony (400)",
     requests.post(f"{BASE}/tickets", headers=PRACOWNIK,
     json={"title": "x" * 300, "description": "opis"}), expect=400)
show("Nieznany punkt koncowy API zwraca JSON 404",
     requests.get(f"{BASE}/nieistniejacy"), expect=404)


print("\n" + "=" * 64)
print(f"  WYNIK: {ok} testow OK, {fail} bledow")
print("=" * 64)

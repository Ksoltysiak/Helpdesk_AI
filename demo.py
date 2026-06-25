import requests
import json
import sys

BASE = "http://localhost:5000/api"

PRACOWNIK = {"X-User-Id": "1"}   # Katarzyna Nowak
TECHNIK = {"X-User-Id": "4"}     # Marek Lewandowski

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


try:
    requests.get("http://localhost:5000/", timeout=2)
except requests.exceptions.RequestException:
    print("Serwer nie odpowiada. Uruchom najpierw:  py app.py")
    sys.exit(1)


section("1. LOGOWANIE I ROLE (RBAC)")
show("Logowanie pracownika (Katarzyna)", requests.post(f"{BASE}/auth/login",
     json={"username": "k.nowak", "password": "haslo123"}))
show("Logowanie technika (Marek)", requests.post(f"{BASE}/auth/login",
     json={"username": "m.lewandowski", "password": "tech123"}))
show("Bledne haslo zwraca 401", requests.post(f"{BASE}/auth/login",
     json={"username": "k.nowak", "password": "zle"}), expect=401)


section("2. PULPIT (DANE DLA DASHBOARDU)")
show("Statystyki + rozklad kategorii", requests.get(f"{BASE}/dashboard", headers=TECHNIK))


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


section("7. KONTROLA UPRAWNIEN (TESTY NEGATYWNE)")
show("Pracownik NIE moze zmienic statusu (403)",
     requests.patch(f"{BASE}/tickets/1", headers=PRACOWNIK, json={"status": "Zamkniete"}), expect=403)
show("Niedozwolone przejscie Nowe -> Zamkniete (400)",
     requests.patch(f"{BASE}/tickets/2", headers=TECHNIK, json={"status": "Zamkniete"}), expect=400)
show("Brak naglowka X-User-Id (401)", requests.get(f"{BASE}/tickets"), expect=401)


print("\n" + "=" * 64)
print(f"  WYNIK: {ok} testow OK, {fail} bledow")
print("=" * 64)

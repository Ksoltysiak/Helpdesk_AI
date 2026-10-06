"""Punkty końcowe zgłoszeń: lista, tworzenie, obsługa, notatki i audyt."""

import json
from datetime import timedelta

from flask import Blueprint, request, jsonify, g

from app import config
from app.api.validation import obiekt_json, pole_tekstowe, parametr_calkowity
from app.data import audit, users
from app.data import tickets as repo
from app.data.database import get_db, czas_utc, teraz_utc
from app.domain import tickets as reguly
from app.domain.ai import categorize, CATEGORIES, SLA_HOURS
from app.security.decorators import login_required, roles_required

bp = Blueprint("tickets", __name__)

# Role, którym można przypisać zgłoszenie do obsługi.
ROLE_OBSLUGI = ("technik", "admin")


@bp.route("/tickets", methods=["GET"])
@login_required
def lista():
    where, params = repo.zbuduj_warunki(g.user, request.args)

    total = repo.policz(where, params)
    per_page = parametr_calkowity("per_page", config.PER_PAGE_DOMYSLNIE,
                                  1, config.PER_PAGE_MAX)
    stron = max(1, -(-total // per_page))          # zaokrąglenie w górę
    page = parametr_calkowity("page", 1, 1, stron)

    wiersze = repo.strona(where, params, per_page, (page - 1) * per_page)

    return jsonify({
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "pages":    stron,
        "tickets":  [repo.serialize(t) for t in wiersze],
    })


@bp.route("/tickets", methods=["POST"])
@roles_required("pracownik")
def utworz():
    dane = obiekt_json()

    title, blad = pole_tekstowe(dane, "title", config.TITLE_MAX)
    if blad:
        return jsonify({"error": blad}), 400
    description, blad = pole_tekstowe(dane, "description", config.DESC_MAX)
    if blad:
        return jsonify({"error": blad}), 400

    wynik = categorize(title, description)
    # UTC, jak wszystkie znaczniki czasu zapisywane przez SQLite. Czas lokalny
    # serwera rozjeżdżał się z `created_at` o przesunięcie strefy.
    deadline = teraz_utc(timedelta(hours=SLA_HOURS[wynik["priorytet"]]))
    # Zgłoszenie należy do firmy autora z chwili utworzenia (opis w schemacie).
    ticket_id = repo.utworz(title, description, g.user["id"], g.user["client_id"],
                            wynik["kategoria"], wynik["priorytet"], wynik["pewnosc"],
                            deadline)

    audit.zapisz(ticket_id, g.user["id"], "Utworzenie", None, reguly.STATUS_POCZATKOWY)
    # Wpis bez użytkownika — czynność wykonał moduł, nie człowiek.
    audit.zapisz(ticket_id, None, "Kategoryzacja AI", None,
                 json.dumps(wynik, ensure_ascii=False))
    get_db().commit()

    return jsonify({"id": ticket_id, "kategoryzacja_ai": wynik,
                    "sla_deadline": czas_utc(deadline)}), 201


@bp.route("/tickets/<int:ticket_id>", methods=["GET"])
@login_required
def szczegoly(ticket_id):
    t = repo.pobierz(ticket_id)
    if not t:
        return jsonify({"error": "Nie znaleziono zgloszenia"}), 404

    pracownik = g.user["role"] == "pracownik"
    if pracownik and t["created_by"] != g.user["id"]:
        return jsonify({"error": "Brak dostepu do tego zgloszenia"}), 403

    dane = repo.serialize(t)
    dane["notes"] = repo.notatki(ticket_id, tylko_jawne=pracownik)
    return jsonify(dane)


@bp.route("/tickets/<int:ticket_id>", methods=["PATCH"])
@roles_required("technik", "admin")
def aktualizuj(ticket_id):
    dane = obiekt_json()
    t = repo.pobierz_surowe(ticket_id)
    if not t:
        return jsonify({"error": "Nie znaleziono zgloszenia"}), 404

    # Najpierw walidacja WSZYSTKICH pól, dopiero potem zapis — błąd w jednym
    # polu nie może zostawić połowicznie wykonanej zmiany.
    if "status" in dane and not reguly.czy_przejscie_dozwolone(t["status"], dane["status"]):
        return jsonify({
            "error": f"Niedozwolona zmiana statusu: {t['status']} -> {dane['status']}",
            "dozwolone": reguly.dozwolone_przejscia(t["status"]),
        }), 400

    if "category" in dane:
        kategoria = dane["category"]
        if not isinstance(kategoria, str) or kategoria not in CATEGORIES:
            return jsonify({"error": "Nieprawidlowa kategoria",
                            "dozwolone": CATEGORIES}), 400

    if "assigned_to" in dane:
        osoba = dane["assigned_to"]
        # bool jest w Pythonie podklasą int — `true` przypisywałoby do id=1.
        if not isinstance(osoba, int) or isinstance(osoba, bool):
            return jsonify({"error": "assigned_to musi byc liczba calkowita"}), 400
        # Bez tego nieistniejący identyfikator kończył się naruszeniem klucza
        # obcego i błędem 500, a zgłoszenie dało się przypisać pracownikowi.
        cel = users.po_id(osoba)
        if not cel or cel["role"] not in ROLE_OBSLUGI:
            return jsonify({"error": "assigned_to musi wskazywac technika lub administratora"}), 400

    zmienione = []

    if "status" in dane:
        nowy = dane["status"]
        # Podjęcie przypisuje zgłoszenie osobie, która je podejmuje —
        # o ile nie miało jeszcze opiekuna.
        przypisz = g.user["id"] if reguly.czy_podjecie(t["status"], nowy) else None
        if not repo.zmien_status(ticket_id, t["status"], nowy, przypisz,
                                 reguly.czy_zamkniecie(nowy)):
            return jsonify({"error": "Zgloszenie zostalo zmienione w miedzyczasie"
                                     " — odswiez je i sprobuj ponownie"}), 409
        audit.zapisz(ticket_id, g.user["id"], "Zmiana statusu", t["status"], nowy)
        zmienione.append("status")

    if "category" in dane:
        repo.zmien_kategorie(ticket_id, dane["category"])
        # Ten wpis jest jednocześnie sygnałem pomyłki modułu AI —
        # na jego podstawie liczona jest skuteczność kategoryzacji.
        audit.zapisz(ticket_id, g.user["id"], audit.AKCJA_ZMIANA_KATEGORII,
                     t["category"], dane["category"])
        zmienione.append("category")

    if "assigned_to" in dane:
        repo.zmien_przypisanie(ticket_id, dane["assigned_to"])
        poprzednio = t["assigned_to"]
        audit.zapisz(ticket_id, g.user["id"], "Przypisanie",
                     str(poprzednio) if poprzednio is not None else None,
                     str(dane["assigned_to"]))
        zmienione.append("assigned_to")

    if not zmienione:
        return jsonify({"error": "Brak pol do aktualizacji (status, category, assigned_to)"}), 400

    get_db().commit()
    return jsonify({"id": ticket_id, "zaktualizowano": zmienione})


@bp.route("/tickets/<int:ticket_id>/notes", methods=["POST"])
@roles_required("technik", "admin")
def dodaj_notatke(ticket_id):
    dane = obiekt_json()

    content, blad = pole_tekstowe(dane, "content", config.NOTE_MAX)
    if blad:
        return jsonify({"error": blad}), 400

    if not repo.istnieje(ticket_id):
        return jsonify({"error": "Nie znaleziono zgloszenia"}), 404

    # Domyślnie notatka jest wewnętrzna — udostępnienie jej zgłaszającemu
    # musi być świadomą decyzją technika.
    repo.dodaj_notatke(ticket_id, g.user["id"], content, dane.get("internal", True))
    audit.zapisz(ticket_id, g.user["id"], "Notatka", None, content[:60])
    get_db().commit()
    return jsonify({"ok": True}), 201


@bp.route("/tickets/<int:ticket_id>/audit", methods=["GET"])
@roles_required("technik", "admin")
def historia(ticket_id):
    if not repo.istnieje(ticket_id):
        return jsonify({"error": "Nie znaleziono zgloszenia"}), 404
    return jsonify(audit.historia(ticket_id))

"""Punkty końcowe zespołu: statystyki techników i kolejka kierownika."""

from datetime import timedelta

from flask import Blueprint, jsonify, g

from app.api.validation import okres_z_parametrow, opis_okresu
from app.data import team as repo
from app.data import tickets as zgloszenia
from app.data import users
from app.data.database import teraz_utc
from app.domain import reports as reguly_raportow
from app.domain import team as reguly
from app.security.decorators import roles_required

bp = Blueprint("team", __name__)

# Zgłoszenie jest „zagrożone", gdy do terminu SLA zostało mniej niż tyle
# godzin — albo termin już minął.
PROG_ZAGROZENIA_H = 2
LIMIT_LISTY = 20


@bp.route("/team", methods=["GET"])
@roles_required("kierownik")
def zespol():
    """Statystyki wszystkich techników za okres — panel i raport kierownika."""
    od, do, blad = okres_z_parametrow()
    if blad:
        return blad
    okres, pop_od, pop_do = opis_okresu(od, do)

    obciazenie = repo.obciazenie(teraz_utc())
    podjecia = repo.podjecia(od, do)
    rozwiazania = repo.rozwiazania(od, do)
    poprzednio = repo.rozwiazania(pop_od, pop_do)
    notatki = repo.notatki(od, do)

    technicy = [
        {"id": t["id"], "name": t["name"], "role": t["role"],
         **reguly.statystyki_technika(obciazenie.get(t["id"]), podjecia.get(t["id"]),
                                      rozwiazania.get(t["id"]), poprzednio.get(t["id"]),
                                      notatki.get(t["id"]))}
        for t in users.personel()
    ]
    return jsonify({
        "okres": okres,
        "poprzedni_okres": {"od": pop_od.isoformat(), "do": pop_do.isoformat()},
        "technicy": technicy,
        "zespol": reguly.suma_zespolu(technicy),
    })


@bp.route("/team/<int:technik_id>", methods=["GET"])
@roles_required("technik", "kierownik")
def technik(technik_id):
    """Raport jednego technika. Technik widzi wyłącznie własne statystyki."""
    if g.user["role"] != "kierownik" and technik_id != g.user["id"]:
        return jsonify({"error": "Mozesz przegladac tylko wlasne statystyki"}), 403

    osoba = users.po_id(technik_id)
    if not osoba or osoba["role"] not in ("technik", "kierownik"):
        return jsonify({"error": "Nie znaleziono technika"}), 404

    od, do, blad = okres_z_parametrow()
    if blad:
        return blad
    okres, pop_od, pop_do = opis_okresu(od, do)

    statystyki = reguly.statystyki_technika(
        repo.obciazenie(teraz_utc(), technik_id).get(technik_id),
        repo.podjecia(od, do, technik_id).get(technik_id),
        repo.rozwiazania(od, do, technik_id).get(technik_id),
        repo.rozwiazania(pop_od, pop_do, technik_id).get(technik_id),
        repo.notatki(od, do, technik_id).get(technik_id),
    )
    kategorie = sorted(repo.rozwiazania_wg_kategorii(od, do, technik_id).items(),
                       key=lambda k: (-k[1], k[0] is None, k[0] or ""))

    return jsonify({
        "technik": {"id": osoba["id"], "name": osoba["name"], "role": osoba["role"]},
        "okres": okres,
        "poprzedni_okres": {"od": pop_od.isoformat(), "do": pop_do.isoformat()},
        "statystyki": statystyki,
        "trend": reguly_raportow.trend(od, do, repo.rozwiazania_dziennie(od, do, technik_id)),
        "wg_kategorii": [{"kategoria": k, "etykieta": reguly_raportow.etykieta_kategorii(k),
                          "liczba": n} for k, n in kategorie],
        "otwarte": [zgloszenia.serialize(t)
                    for t in zgloszenia.otwarte_przypisane(technik_id, LIMIT_LISTY)],
    })


@bp.route("/queue", methods=["GET"])
@roles_required("kierownik")
def kolejka():
    """Zgłoszenia wymagające decyzji kierownika: bez opiekuna i bliskie terminu."""
    granica = teraz_utc(timedelta(hours=PROG_ZAGROZENIA_H))
    bez_opiekuna, wolne = zgloszenia.nieprzypisane(LIMIT_LISTY)
    zagrozonych, pilne = zgloszenia.zagrozone(granica, LIMIT_LISTY)
    return jsonify({
        "prog_godzin": PROG_ZAGROZENIA_H,
        "nieprzypisane": {"liczba": bez_opiekuna,
                          "zgloszenia": [zgloszenia.serialize(t) for t in wolne]},
        "zagrozone": {"liczba": zagrozonych,
                      "zgloszenia": [zgloszenia.serialize(t) for t in pilne]},
    })

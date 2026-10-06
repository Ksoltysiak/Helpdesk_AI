"""Punkt końcowy raportów dla klientów."""

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from app.data import clients as klienci
from app.data import reports as repo
from app.data.database import teraz_utc
from app.domain import reports as reguly
from app.security.decorators import roles_required

bp = Blueprint("reports", __name__)


def _klient_z_parametru():
    """(client_id albo None, odpowiedź błędu albo None)."""
    surowy = request.args.get("client_id", "")
    if surowy == "":
        return None, None
    # isdigit() odrzuca też znak minus i spacje — identyfikatory są dodatnie.
    if not surowy.isascii() or not surowy.isdigit() or len(surowy) > 18:
        return None, (jsonify({"error": "client_id musi byc dodatnia liczba calkowita"}), 400)
    return int(surowy), None


@bp.route("/reports", methods=["GET"])
@roles_required("technik", "admin")
def raport():
    """Raport zgłoszeń klienta (albo wszystkich klientów) za wybrany okres.

    Parametry: `client_id` (opcjonalny), `od` i `do` w formacie RRRR-MM-DD
    (domyślnie ostatnie 30 dni, obie daty włącznie, doby UTC).
    """
    client_id, blad = _klient_z_parametru()
    if blad:
        return blad

    klient = None
    if client_id is not None:
        klient = klienci.po_id(client_id)
        if not klient:
            return jsonify({"error": "Nie znaleziono klienta"}), 404

    dzis = datetime.now(timezone.utc).date()
    try:
        od, do = reguly.okres(request.args.get("od"), request.args.get("do"), dzis)
    except reguly.BladOkresu as e:
        return jsonify({"error": str(e)}), 400
    pop_od, pop_do = reguly.poprzedni_okres(od, do)

    s = repo.podsumowanie(client_id, od, do, teraz_utc())
    poprzednio = repo.wg_kategorii(client_id, pop_od, pop_do)
    kategorie = reguly.kategorie_z_porownaniem(repo.wg_kategorii(client_id, od, do), poprzednio)
    problemy = repo.najczestsze_problemy(client_id, od, do, reguly.ETYKIETY_PROBLEMOW)

    podsumowanie = {
        "zgloszen":                s["zgloszen"],
        "otwartych":               s["zgloszen"] - s["rozwiazanych"],
        "rozwiazanych":            s["rozwiazanych"],
        "procent_rozwiazanych":    reguly.procent(s["rozwiazanych"], s["zgloszen"]),
        "krytycznych":             s["krytycznych"],
        "sredni_czas_rozwiazania_h": (round(s["sredni_czas_h"], 1)
                                      if s["sredni_czas_h"] is not None else None),
        "rozwiazanych_z_terminem": s["z_terminem"],
        "w_terminie_sla":          s["w_terminie"],
        "procent_w_terminie_sla":  reguly.procent(s["w_terminie"], s["z_terminem"]),
        "otwartych_po_terminie":   s["po_terminie"],
    }
    zgloszen_poprzednio = sum(poprzednio.values())

    return jsonify({
        "klient": {"id": klient["id"], "name": klient["name"]} if klient else None,
        "okres": {
            "od": od.isoformat(),
            "do": do.isoformat(),
            "dni": (do - od).days + 1,
            "grupowanie": reguly.grupowanie(od, do),
        },
        "podsumowanie": podsumowanie,
        "poprzedni_okres": {
            "od": pop_od.isoformat(),
            "do": pop_do.isoformat(),
            "zgloszen": zgloszen_poprzednio,
            "zmiana_proc": reguly.zmiana_proc(s["zgloszen"], zgloszen_poprzednio),
        },
        "wg_kategorii": kategorie,
        "wg_priorytetu": reguly.priorytety_w_kolejnosci(repo.wg_priorytetu(client_id, od, do)),
        "trend": reguly.trend(od, do, repo.dziennie(client_id, od, do)),
        "najczestsze_problemy": problemy,
        "rekomendacje": reguly.rekomendacje(podsumowanie, kategorie, problemy),
    })

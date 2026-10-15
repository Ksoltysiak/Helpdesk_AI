"""Ustawienia helpdesku zmieniane przez kierownika — czasy SLA."""

from flask import Blueprint, jsonify, g

from app.api.validation import obiekt_json
from app.data import settings as repo
from app.data.database import czas_utc, get_db
from app.domain import ai
from app.security.decorators import roles_required

bp = Blueprint("settings", __name__)


def _stan():
    return {
        "godziny": ai.godziny_sla(repo.sla_godziny()),
        "domyslne": dict(ai.SLA_HOURS),
        "zakres": {"min": ai.SLA_MIN_GODZIN, "max": ai.SLA_MAX_GODZIN},
        "historia": [
            {"ustawienie": h["setting"], "stara": h["old_value"], "nowa": h["new_value"],
             "kto": h["user_name"], "kiedy": czas_utc(h["timestamp"])}
            for h in repo.historia()
        ],
    }


@bp.route("/settings/sla", methods=["GET"])
@roles_required("technik", "kierownik")
def odczyt_sla():
    """Obowiązujące czasy SLA — technik widzi je, zmienia tylko kierownik."""
    return jsonify(_stan())


@bp.route("/settings/sla", methods=["PUT"])
@roles_required("kierownik")
def zmiana_sla():
    """Nowe czasy SLA dla wybranych priorytetów.

    Dotyczą wyłącznie zgłoszeń utworzonych po zmianie — termin istniejących
    zgłoszeń został im obiecany w chwili zgłoszenia i nie przesuwa się wstecz.
    Każda faktyczna zmiana trafia do historii z autorem i czasem.
    """
    zmiany, blad = ai.sprawdz_zmiany_sla(obiekt_json().get("godziny"))
    if blad:
        return jsonify({"error": blad}), 400

    obecne = ai.godziny_sla(repo.sla_godziny())
    for priorytet, godziny in zmiany.items():
        if obecne[priorytet] != godziny:
            repo.zapisz_sla(priorytet, godziny, obecne[priorytet], g.user["id"])
    get_db().commit()
    return jsonify(_stan())

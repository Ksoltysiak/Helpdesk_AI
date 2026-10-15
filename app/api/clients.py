"""Punkty końcowe klientów — firm obsługiwanych przez helpdesk."""

from flask import Blueprint, jsonify, g

from app.data import clients as repo
from app.data import users
from app.security.decorators import roles_required

bp = Blueprint("clients", __name__)


@bp.route("/clients", methods=["GET"])
@roles_required("technik", "kierownik")
def lista():
    """Klienci z liczbą pracowników i zgłoszeń.

    Tylko dla personelu helpdesku — pracownik jednej firmy nie powinien
    poznawać nazw ani skali zgłoszeń innych klientów. Pole `obslugiwany`
    mówi, czy pytający technik obsługuje daną firmę (i może tworzyć dla niej
    raporty); kierownik obsługuje wszystkie.
    """
    obslugiwane = None if g.user["role"] == "kierownik" else users.obslugiwani_klienci(g.user["id"])
    return jsonify(repo.lista(obslugiwane))

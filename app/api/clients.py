"""Punkty końcowe klientów — firm obsługiwanych przez helpdesk."""

from flask import Blueprint, jsonify

from app.data import clients as repo
from app.security.decorators import roles_required

bp = Blueprint("clients", __name__)


@bp.route("/clients", methods=["GET"])
@roles_required("technik", "admin")
def lista():
    """Klienci z liczbą pracowników i zgłoszeń.

    Tylko dla personelu helpdesku — pracownik jednej firmy nie powinien
    poznawać nazw ani skali zgłoszeń innych klientów.
    """
    return jsonify(repo.lista())

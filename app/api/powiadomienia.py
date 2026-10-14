"""Punkty końcowe powiadomień — dzwonek w nagłówku aplikacji.

Każdy użytkownik widzi i oznacza wyłącznie własne powiadomienia; nie ma
parametru, którym dałoby się poprosić o cudze.
"""

from flask import Blueprint, jsonify, g

from app import config
from app.api.validation import obiekt_json, parametr_calkowity
from app.data import powiadomienia as repo
from app.data.database import get_db
from app.security.decorators import login_required

bp = Blueprint("powiadomienia", __name__)


@bp.route("/notifications", methods=["GET"])
@login_required
def lista():
    limit = parametr_calkowity("limit", config.POWIADOMIEN_DOMYSLNIE, 1,
                               config.POWIADOMIEN_MAX)
    return jsonify({
        "nieprzeczytane": repo.liczba_nieprzeczytanych(g.user["id"]),
        "powiadomienia":  repo.dla_uzytkownika(g.user["id"], limit),
    })


@bp.route("/notifications/read", methods=["POST"])
@login_required
def oznacz_przeczytane():
    """Bez pola `ids` oznacza wszystkie powiadomienia użytkownika."""
    dane = obiekt_json()
    ids = dane.get("ids")
    if ids is not None:
        # bool jest w Pythonie podklasą int — `true` oznaczałoby id=1.
        if (not isinstance(ids, list) or len(ids) > config.POWIADOMIEN_MAX
                or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids)):
            return jsonify({"error": "Pole 'ids' musi byc lista liczb calkowitych"
                                     f" (max {config.POWIADOMIEN_MAX})"}), 400

    oznaczono = repo.oznacz_przeczytane(g.user["id"], ids)
    get_db().commit()
    return jsonify({"oznaczono": oznaczono,
                    "nieprzeczytane": repo.liczba_nieprzeczytanych(g.user["id"])})

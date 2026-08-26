"""Punkty końcowe pomocnicze: kontrola zdrowia, pulpit i moduł AI."""

from flask import Blueprint, request, jsonify, g

from app.data import audit
from app.data import tickets as repo
from app.data.database import sprawdz_polaczenie
from app.domain.ai import categorize, PROG_PEWNOSCI
from app.extensions import limiter
from app.security.decorators import login_required, roles_required

bp = Blueprint("meta", __name__)


@bp.route("/health", methods=["GET"])
@limiter.exempt
def health():
    """Kontrola zdrowia dla load balancera i monitoringu.

    Celowo bez autoryzacji — sonda infrastruktury nie ma tokenu. Odpowiedź
    nie zawiera żadnych szczegółów o systemie: potwierdza tylko, że proces
    żyje i ma działające połączenie z bazą.
    """
    if not sprawdz_polaczenie():
        return jsonify({"status": "error"}), 503
    return jsonify({"status": "ok"})


@bp.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    # Pracownik dostaje statystyki WŁASNYCH zgłoszeń — pulpit ma pokazywać to
    # samo, co jego lista, a liczby z całego systemu nie są mu potrzebne.
    if g.user["role"] == "pracownik":
        where, params = " WHERE created_by = ?", (g.user["id"],)
    else:
        where, params = "", ()

    return jsonify({
        "statystyki":   repo.statystyki(where, params),
        "wg_kategorii": repo.rozklad_kategorii(where, params),
    })


@bp.route("/ai/skutecznosc", methods=["GET"])
@roles_required("technik", "admin")
def skutecznosc():
    """Jakość kategoryzacji liczona z rzeczywistej pracy techników.

    Każda ręczna zmiana kategorii to sygnał, że moduł pomylił się na
    konkretnym zgłoszeniu. Zamiast deklarować skuteczność, wyliczamy ją z tego,
    jak często człowiek poprawia maszynę.
    """
    razem = audit.liczba_zgloszen_z_ai()
    poprawione = audit.liczba_recznych_korekt()
    srednia = audit.srednia_pewnosc()

    return jsonify({
        "zgloszen_z_ai":        razem,
        "poprawionych_recznie": poprawione,
        "skutecznosc":          round(1 - poprawione / razem, 3) if razem else None,
        "srednia_pewnosc":      round(srednia, 3) if srednia is not None else None,
        "wymaga_weryfikacji":   audit.liczba_niepewnych(PROG_PEWNOSCI),
        "prog_pewnosci":        PROG_PEWNOSCI,
        "najczestsze_pomylki":  audit.najczestsze_pomylki(),
    })


@bp.route("/ai/categorize", methods=["POST"])
@login_required
def kategoryzuj():
    """Testowe uruchomienie kategoryzacji bez zapisywania zgłoszenia."""
    dane = request.get_json(silent=True) or {}
    title = dane.get("title", "")
    description = dane.get("description", "")

    if not isinstance(title, str) or not isinstance(description, str):
        return jsonify({"error": "Pola 'title' i 'description' musza byc tekstem"}), 400
    if not title and not description:
        return jsonify({"error": "Podaj pole title lub description"}), 400

    return jsonify(categorize(title, description))

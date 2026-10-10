"""Punkty końcowe pomocnicze: kontrola zdrowia, pulpit i moduł AI."""

from datetime import date

from flask import Blueprint, jsonify, g

from app.api.validation import obiekt_json
from app.data import audit
from app.data import pulpit
from app.data import tickets as repo
from app.data.database import sprawdz_polaczenie, teraz_utc
from app.domain.ai import categorize, PROG_PEWNOSCI
from app.extensions import limiter
from app.security.decorators import login_required, roles_required

bp = Blueprint("meta", __name__)

# Ile ostatnich dni pokazuje wykres trendu na pulpicie konsoli IT.
DNI_TRENDU = 14


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
    autor_id = g.user["id"] if g.user["role"] == "pracownik" else None

    wynik = {
        "statystyki":   repo.statystyki(autor_id),
        "wg_kategorii": repo.rozklad_kategorii(autor_id),
        "aktywnosc":    pulpit.ostatnia_aktywnosc(autor_id),
    }

    # Obraz pracy całego helpdesku (SLA, obciążenie zespołu) jest dla
    # personelu — pracownik firmy klienta nie powinien go widzieć.
    if autor_id is None:
        teraz = teraz_utc()
        wynik.update({
            "puls":            pulpit.puls(teraz, g.user["id"]),
            "trend":           pulpit.trend(date.fromisoformat(teraz[:10]), DNI_TRENDU),
            "wg_priorytetu":   pulpit.aktywne_wg_priorytetu(),
            "pilne_sla":       pulpit.pilne_sla(teraz),
            "obciazenie":      pulpit.obciazenie_technikow(),
        })

    return jsonify(wynik)


@bp.route("/ai/skutecznosc", methods=["GET"])
@roles_required("technik", "admin")
def skutecznosc():
    """Jakość kategoryzacji liczona z rzeczywistej pracy techników.

    Każda ręczna zmiana kategorii to sygnał, że moduł pomylił się na
    konkretnym zgłoszeniu. Zamiast deklarować skuteczność, wyliczamy ją z tego,
    jak często człowiek poprawia maszynę.
    """
    razem, niepewne, srednia = audit.podsumowanie_kategoryzacji(PROG_PEWNOSCI)
    poprawione = audit.liczba_recznych_korekt()

    return jsonify({
        "zgloszen_z_ai":        razem,
        "poprawionych_recznie": poprawione,
        "skutecznosc":          round(1 - poprawione / razem, 3) if razem else None,
        "srednia_pewnosc":      round(srednia, 3) if srednia is not None else None,
        "wymaga_weryfikacji":   niepewne,
        "prog_pewnosci":        PROG_PEWNOSCI,
        "najczestsze_pomylki":  audit.najczestsze_pomylki(),
    })


@bp.route("/ai/categorize", methods=["POST"])
@login_required
def kategoryzuj():
    """Testowe uruchomienie kategoryzacji bez zapisywania zgłoszenia."""
    dane = obiekt_json()
    title = dane.get("title", "")
    description = dane.get("description", "")

    if not isinstance(title, str) or not isinstance(description, str):
        return jsonify({"error": "Pola 'title' i 'description' musza byc tekstem"}), 400
    if not title and not description:
        return jsonify({"error": "Podaj pole title lub description"}), 400

    return jsonify(categorize(title, description))

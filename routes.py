from flask import Blueprint, request, jsonify, g
from datetime import datetime, timedelta
from werkzeug.security import check_password_hash
import json
from db import get_db, log_audit
from auth import login_required, roles_required, generate_token
from ai import categorize, CATEGORIES, SLA_HOURS
from rate_limit import limiter, klucz_logowania

api = Blueprint("api", __name__)

TRANSITIONS = {
    "Nowe":       ["W trakcie"],
    "W trakcie":  ["Rozwiazane", "Wstrzymane"],
    "Wstrzymane": ["W trakcie"],
    "Rozwiazane": ["Zamkniete", "W trakcie"],
    "Zamkniete":  [],
}

_TITLE_MAX = 200
_DESC_MAX  = 5000
_NOTE_MAX  = 2000

# Stronicowanie listy zgloszen. Bez gornego limitu pojedyncze zadanie moze
# zmusic serwer do zbudowania odpowiedzi o rozmiarze calej bazy.
_PER_PAGE_DOMYSLNIE = 50
_PER_PAGE_MAX       = 200


def parametr_calkowity(nazwa, domyslnie, minimum, maksimum):
    """Odczyt liczbowego parametru zapytania z ograniczeniem zakresu."""
    surowa = request.args.get(nazwa)
    if surowa is None or surowa == "":
        return domyslnie
    try:
        wartosc = int(surowa)
    except (TypeError, ValueError):
        return domyslnie
    return max(minimum, min(wartosc, maksimum))


def pole_tekstowe(dane, nazwa, maks):
    """Zwraca (wartosc, blad) dla pola tekstowego z zadania.

    Klient moze przyslac dowolny JSON, wiec typ trzeba sprawdzic przed
    wywolaniem len() i przed przekazaniem wartosci do sterownika bazy —
    inaczej liczba lub obiekt konczy sie wyjatkiem i odpowiedzia HTTP 500.
    """
    wartosc = dane.get(nazwa, "")
    if not isinstance(wartosc, str):
        return None, f"Pole '{nazwa}' musi byc tekstem"
    wartosc = wartosc.strip()
    if not wartosc:
        return None, f"Pole '{nazwa}' jest wymagane"
    if len(wartosc) > maks:
        return None, f"Pole '{nazwa}' jest za dlugie (max {maks} znakow)"
    return wartosc, None


def serialize(t):
    keys = t.keys()
    data = {
        "id":            t["id"],
        "title":         t["title"],
        "description":   t["description"],
        "category":      t["category"],
        "priority":      t["priority"],
        "status":        t["status"],
        "created_by":    t["created_by"],
        "assigned_to":   t["assigned_to"],
        "ai_categorized": bool(t["ai_categorized"]),
        "sla_deadline":  t["sla_deadline"],
        "created_at":    t["created_at"],
        "updated_at":    t["updated_at"],
        "closed_at":     t["closed_at"],
    }
    # Nazwiska dolaczane przez LEFT JOIN — pozwalaja pokazac w interfejsie
    # osobe zamiast surowego identyfikatora.
    if "created_by_name" in keys:
        data["created_by_name"] = t["created_by_name"]
    if "assigned_to_name" in keys:
        data["assigned_to_name"] = t["assigned_to_name"]
    return data


_TICKET_SELECT = """
    SELECT t.*, uc.name created_by_name, ua.name assigned_to_name
    FROM tickets t
    LEFT JOIN users uc ON t.created_by = uc.id
    LEFT JOIN users ua ON t.assigned_to = ua.id
"""


@api.route("/health", methods=["GET"])
@limiter.exempt
def health():
    """Kontrola zdrowia dla load balancera i monitoringu.

    Celowo bez autoryzacji — sonda infrastruktury nie ma tokenu. Odpowiedz
    nie zawiera zadnych szczegolow o systemie: potwierdza tylko, ze proces
    zyje i ma dzialajace polaczenie z baza.
    """
    try:
        get_db().execute("SELECT 1").fetchone()
    except Exception:
        return jsonify({"status": "error"}), 503
    return jsonify({"status": "ok"})


@api.route("/auth/login", methods=["POST"])
@limiter.limit("10 per minute; 30 per hour")                              # na adres IP
@limiter.limit("5 per minute; 20 per hour", key_func=klucz_logowania)     # na konto
def login():
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "")
    password = data.get("password", "")

    if not isinstance(username, str) or not isinstance(password, str):
        return jsonify({"error": "Nieprawidlowy login lub haslo"}), 401

    user = get_db().execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()

    if not user or not check_password_hash(user["password"], password):
        return jsonify({"error": "Nieprawidlowy login lub haslo"}), 401

    token = generate_token(user["id"])
    return jsonify({"id": user["id"], "name": user["name"], "role": user["role"], "token": token})


@api.route("/auth/me", methods=["GET"])
@login_required
def me():
    """Odtworzenie sesji na podstawie zapisanego tokenu (np. po odswiezeniu strony)."""
    return jsonify({"id": g.user["id"], "name": g.user["name"], "role": g.user["role"]})


@api.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    db = get_db()

    # Pracownik dostaje statystyki WLASNYCH zgloszen. Liczby z calego systemu
    # nie sa mu do niczego potrzebne, a pulpit ma pokazywac to samo, co jego
    # lista zgloszen.
    if g.user["role"] == "pracownik":
        where, params = " WHERE created_by = ?", (g.user["id"],)
    else:
        where, params = "", ()

    # Jedno przejscie po tabeli zamiast czterech osobnych zapytan liczacych.
    wiersz = db.execute(f"""
        SELECT
            COUNT(*)                                                AS wszystkie,
            SUM(status != 'Zamkniete')                              AS otwarte,
            SUM(status =  'W trakcie')                              AS w_trakcie,
            SUM(status =  'Rozwiazane')                             AS rozwiazane,
            SUM(status =  'Zamkniete')                              AS zamkniete,
            SUM(priority = 'Krytyczny' AND status != 'Zamkniete')   AS krytyczne
        FROM tickets{where}
    """, params).fetchone()

    # SUM() zwraca NULL dla pustego zbioru — pulpit ma pokazac zera.
    klucze = ("wszystkie", "otwarte", "w_trakcie", "rozwiazane", "zamkniete", "krytyczne")
    stats = {k: wiersz[k] or 0 for k in klucze}

    rows = db.execute(
        f"SELECT category, COUNT(*) c FROM tickets{where}"
        + (" AND" if where else " WHERE") + " category IS NOT NULL"
        " GROUP BY category ORDER BY c DESC",
        params,
    ).fetchall()

    return jsonify({
        "statystyki":   stats,
        "wg_kategorii": [{"kategoria": r["category"], "liczba": r["c"]} for r in rows],
    })


@api.route("/tickets", methods=["GET"])
@login_required
def list_tickets():
    db   = get_db()
    user = g.user

    warunki = []
    params  = []

    if user["role"] == "pracownik":
        # Twarda granica dostepu — pracownik nigdy nie widzi cudzych zgloszen,
        # a parametry filtrowania jej nie omijaja.
        warunki.append("t.created_by = ?")
        params.append(user["id"])
    else:
        for field in ("status", "priority", "category"):
            value = request.args.get(field)
            if value:
                warunki.append(f"t.{field} = ?")
                params.append(value)

    where = (" WHERE " + " AND ".join(warunki)) if warunki else ""

    # Liczba wszystkich pasujacych zgloszen — potrzebna do zbudowania stronicowania.
    total = db.execute(f"SELECT COUNT(*) c FROM tickets t{where}", params).fetchone()["c"]

    per_page = parametr_calkowity("per_page", _PER_PAGE_DOMYSLNIE, 1, _PER_PAGE_MAX)
    stron    = max(1, -(-total // per_page))          # zaokraglenie w gore
    page     = parametr_calkowity("page", 1, 1, stron)

    rows = db.execute(
        _TICKET_SELECT + where + " ORDER BY t.id DESC LIMIT ? OFFSET ?",
        params + [per_page, (page - 1) * per_page],
    ).fetchall()

    return jsonify({
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "pages":    stron,
        "tickets":  [serialize(t) for t in rows],
    })


@api.route("/tickets", methods=["POST"])
@roles_required("pracownik")
def create_ticket():
    data = request.get_json(silent=True) or {}

    title, blad = pole_tekstowe(data, "title", _TITLE_MAX)
    if blad:
        return jsonify({"error": blad}), 400
    description, blad = pole_tekstowe(data, "description", _DESC_MAX)
    if blad:
        return jsonify({"error": blad}), 400

    db        = get_db()
    ticket_id = db.execute(
        "INSERT INTO tickets (title, description, created_by) VALUES (?,?,?)",
        (title, description, g.user["id"]),
    ).lastrowid

    result   = categorize(title, description)
    deadline = (datetime.now() + timedelta(hours=SLA_HOURS[result["priorytet"]])).isoformat(timespec="seconds")
    db.execute(
        "UPDATE tickets SET category=?, priority=?, ai_categorized=1, sla_deadline=?, updated_at=datetime('now') WHERE id=?",
        (result["kategoria"], result["priorytet"], deadline, ticket_id),
    )
    log_audit(db, ticket_id, g.user["id"], "Utworzenie", None, "Nowe")
    log_audit(db, ticket_id, None, "Kategoryzacja AI", None, json.dumps(result, ensure_ascii=False))
    db.commit()

    return jsonify({"id": ticket_id, "kategoryzacja_ai": result, "sla_deadline": deadline}), 201


@api.route("/tickets/<int:ticket_id>", methods=["GET"])
@login_required
def get_ticket(ticket_id):
    db = get_db()
    t  = db.execute(_TICKET_SELECT + " WHERE t.id = ?", (ticket_id,)).fetchone()
    if not t:
        return jsonify({"error": "Nie znaleziono zgloszenia"}), 404
    if g.user["role"] == "pracownik" and t["created_by"] != g.user["id"]:
        return jsonify({"error": "Brak dostepu do tego zgloszenia"}), 403

    note_query = "SELECT n.*, u.name author FROM notes n JOIN users u ON n.author_id = u.id WHERE n.ticket_id = ?"
    if g.user["role"] == "pracownik":
        note_query += " AND n.internal = 0"
    notes = db.execute(note_query + " ORDER BY n.id", (ticket_id,)).fetchall()

    data         = serialize(t)
    data["notes"] = [
        {"author": n["author"], "content": n["content"], "internal": bool(n["internal"]), "created_at": n["created_at"]}
        for n in notes
    ]
    return jsonify(data)


@api.route("/tickets/<int:ticket_id>", methods=["PATCH"])
@roles_required("technik", "admin")
def update_ticket(ticket_id):
    data = request.get_json(silent=True) or {}
    db   = get_db()
    t    = db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if not t:
        return jsonify({"error": "Nie znaleziono zgloszenia"}), 404

    changed = []

    if "status" in data:
        new_status = data["status"]
        allowed    = TRANSITIONS.get(t["status"], [])
        if new_status not in allowed:
            return jsonify({
                "error":    f"Niedozwolona zmiana statusu: {t['status']} -> {new_status}",
                "dozwolone": allowed,
            }), 400

        sql    = "UPDATE tickets SET status = ?, updated_at = datetime('now')"
        params = [new_status]
        if t["status"] == "Nowe" and not t["assigned_to"]:
            sql += ", assigned_to = ?"
            params.append(g.user["id"])
        if new_status == "Zamkniete":
            sql += ", closed_at = datetime('now')"
        sql += " WHERE id = ?"
        params.append(ticket_id)
        db.execute(sql, params)
        log_audit(db, ticket_id, g.user["id"], "Zmiana statusu", t["status"], new_status)
        changed.append("status")

    if "category" in data:
        cat = data["category"]
        if not isinstance(cat, str) or cat not in CATEGORIES:
            return jsonify({"error": "Nieprawidlowa kategoria", "dozwolone": CATEGORIES}), 400
        db.execute(
            "UPDATE tickets SET category = ?, updated_at = datetime('now') WHERE id = ?",
            (cat, ticket_id),
        )
        log_audit(db, ticket_id, g.user["id"], "Zmiana kategorii", t["category"], cat)
        changed.append("category")

    if "assigned_to" in data:
        assignee = data["assigned_to"]
        if not isinstance(assignee, int):
            return jsonify({"error": "assigned_to musi byc liczba calkowita"}), 400
        db.execute(
            "UPDATE tickets SET assigned_to = ?, updated_at = datetime('now') WHERE id = ?",
            (assignee, ticket_id),
        )
        log_audit(db, ticket_id, g.user["id"], "Przypisanie", str(t["assigned_to"]), str(assignee))
        changed.append("assigned_to")

    if not changed:
        return jsonify({"error": "Brak pol do aktualizacji (status, category, assigned_to)"}), 400

    db.commit()
    return jsonify({"id": ticket_id, "zaktualizowano": changed})


@api.route("/tickets/<int:ticket_id>/notes", methods=["POST"])
@roles_required("technik", "admin")
def add_note(ticket_id):
    data = request.get_json(silent=True) or {}

    content, blad = pole_tekstowe(data, "content", _NOTE_MAX)
    if blad:
        return jsonify({"error": blad}), 400

    db = get_db()
    if not db.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone():
        return jsonify({"error": "Nie znaleziono zgloszenia"}), 404

    internal = 1 if data.get("internal", True) else 0
    db.execute(
        "INSERT INTO notes (ticket_id, author_id, content, internal) VALUES (?,?,?,?)",
        (ticket_id, g.user["id"], content, internal),
    )
    log_audit(db, ticket_id, g.user["id"], "Notatka", None, content[:60])
    db.commit()
    return jsonify({"ok": True}), 201


@api.route("/tickets/<int:ticket_id>/audit", methods=["GET"])
@roles_required("technik", "admin")
def ticket_audit(ticket_id):
    rows = get_db().execute(
        "SELECT a.*, u.name user_name FROM audit_log a LEFT JOIN users u ON a.user_id = u.id WHERE a.ticket_id = ? ORDER BY a.id",
        (ticket_id,),
    ).fetchall()
    return jsonify([
        {"action": r["action"], "user": r["user_name"] or "System AI",
         "old": r["old_value"], "new": r["new_value"], "timestamp": r["timestamp"]}
        for r in rows
    ])


@api.route("/ai/categorize", methods=["POST"])
@login_required
def ai_categorize():
    data        = request.get_json(silent=True) or {}
    title       = data.get("title", "")
    description = data.get("description", "")
    if not isinstance(title, str) or not isinstance(description, str):
        return jsonify({"error": "Pola 'title' i 'description' musza byc tekstem"}), 400
    if not title and not description:
        return jsonify({"error": "Podaj pole title lub description"}), 400
    return jsonify(categorize(title, description))

from flask import Blueprint, request, jsonify, g
from datetime import datetime, timedelta
from werkzeug.security import check_password_hash
import json
from db import get_db, log_audit
from auth import login_required, roles_required, generate_token
from ai import categorize, CATEGORIES, SLA_HOURS
from rate_limit import limiter

api = Blueprint("api", __name__)

TRANSITIONS = {
    "Nowe":       ["W trakcie"],
    "W trakcie":  ["Rozwiazane", "Wstrzymane"],
    "Wstrzymane": ["W trakcie"],
    "Rozwiazane": ["Zamkniete", "W trakcie"],
    "Zamkniete":  [],
}

_TITLE_MAX    = 200
_DESC_MAX     = 5000
_NOTE_MAX     = 2000
_CATEGORY_MAX = 50


def serialize(t):
    return {
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


@api.route("/auth/login", methods=["POST"])
@limiter.limit("10 per minute; 30 per hour")
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


@api.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    db = get_db()
    stats = {
        "otwarte":   db.execute("SELECT COUNT(*) c FROM tickets WHERE status != 'Zamkniete'").fetchone()["c"],
        "w_trakcie": db.execute("SELECT COUNT(*) c FROM tickets WHERE status = 'W trakcie'").fetchone()["c"],
        "rozwiazane":db.execute("SELECT COUNT(*) c FROM tickets WHERE status = 'Rozwiazane'").fetchone()["c"],
        "krytyczne": db.execute("SELECT COUNT(*) c FROM tickets WHERE priority = 'Krytyczny' AND status != 'Zamkniete'").fetchone()["c"],
    }
    rows = db.execute(
        "SELECT category, COUNT(*) c FROM tickets WHERE category IS NOT NULL GROUP BY category ORDER BY c DESC"
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

    if user["role"] == "pracownik":
        rows = db.execute(
            "SELECT * FROM tickets WHERE created_by = ? ORDER BY id DESC", (user["id"],)
        ).fetchall()
    else:
        query  = "SELECT * FROM tickets WHERE 1=1"
        params = []
        for field in ("status", "priority", "category"):
            value = request.args.get(field)
            if value:
                query  += f" AND {field} = ?"
                params.append(value)
        query += " ORDER BY id DESC"
        rows   = db.execute(query, params).fetchall()

    return jsonify({"total": len(rows), "tickets": [serialize(t) for t in rows]})


@api.route("/tickets", methods=["POST"])
@roles_required("pracownik")
def create_ticket():
    data        = request.get_json(silent=True) or {}
    title       = data.get("title", "")
    description = data.get("description", "")

    if not title or not description:
        return jsonify({"error": "Wymagane pola: title, description"}), 400
    if len(title) > _TITLE_MAX:
        return jsonify({"error": f"Tytul za dlugi (max {_TITLE_MAX} znakow)"}), 400
    if len(description) > _DESC_MAX:
        return jsonify({"error": f"Opis za dlugi (max {_DESC_MAX} znakow)"}), 400

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
    t  = db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
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
    data    = request.get_json(silent=True) or {}
    content = data.get("content", "")

    if not content:
        return jsonify({"error": "Wymagane pole: content"}), 400
    if len(content) > _NOTE_MAX:
        return jsonify({"error": f"Notatka za dluga (max {_NOTE_MAX} znakow)"}), 400

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
    if not title and not description:
        return jsonify({"error": "Podaj pole title lub description"}), 400
    return jsonify(categorize(title, description))

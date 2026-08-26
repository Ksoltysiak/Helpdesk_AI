"""Dostęp do danych zgłoszeń.

Cały SQL dotyczący zgłoszeń jest tutaj — warstwa HTTP nie buduje zapytań.
Dzięki temu widać w jednym miejscu, jakimi zapytaniami system obciąża bazę,
i łatwiej sprawdzić, że każde filtrowanie respektuje granicę dostępu.
"""

from app.data.database import get_db

# Nazwiska dołączane przez LEFT JOIN — interfejs pokazuje osobę zamiast
# surowego identyfikatora.
SELECT_ZGLOSZENIA = """
    SELECT t.*, uc.name created_by_name, ua.name assigned_to_name
    FROM tickets t
    LEFT JOIN users uc ON t.created_by = uc.id
    LEFT JOIN users ua ON t.assigned_to = ua.id
"""


def serialize(t):
    """Wiersz bazy -> słownik odpowiedzi API.

    Pola wyliczane są jawnie: `SELECT *` zwraca też kolumny, których klient
    nie powinien dostać, więc lista poniżej jest świadomą granicą.
    """
    keys = t.keys()
    data = {
        "id":             t["id"],
        "title":          t["title"],
        "description":    t["description"],
        "category":       t["category"],
        "priority":       t["priority"],
        "status":         t["status"],
        "created_by":     t["created_by"],
        "assigned_to":    t["assigned_to"],
        "ai_categorized": bool(t["ai_categorized"]),
        "ai_pewnosc":     t["ai_pewnosc"] if "ai_pewnosc" in keys else None,
        "sla_deadline":   t["sla_deadline"],
        "created_at":     t["created_at"],
        "updated_at":     t["updated_at"],
        "closed_at":      t["closed_at"],
    }
    if "created_by_name" in keys:
        data["created_by_name"] = t["created_by_name"]
    if "assigned_to_name" in keys:
        data["assigned_to_name"] = t["assigned_to_name"]
    return data


def zbuduj_warunki(user, filtry):
    """Warunki WHERE zależne od roli.

    Dla pracownika ograniczenie do własnych zgłoszeń jest **pierwszym**
    warunkiem i nie da się go pominąć parametrami filtrowania — to twarda
    granica dostępu, nie ukrywanie danych w interfejsie.
    """
    warunki, params = [], []

    if user["role"] == "pracownik":
        warunki.append("t.created_by = ?")
        params.append(user["id"])
    else:
        for pole in ("status", "priority", "category"):
            wartosc = filtry.get(pole)
            if wartosc:
                warunki.append(f"t.{pole} = ?")
                params.append(wartosc)

    where = (" WHERE " + " AND ".join(warunki)) if warunki else ""
    return where, params


def policz(where, params):
    return get_db().execute(
        f"SELECT COUNT(*) c FROM tickets t{where}", params
    ).fetchone()["c"]


def strona(where, params, limit, offset):
    return get_db().execute(
        SELECT_ZGLOSZENIA + where + " ORDER BY t.id DESC LIMIT ? OFFSET ?",
        list(params) + [limit, offset],
    ).fetchall()


def pobierz(ticket_id):
    return get_db().execute(
        SELECT_ZGLOSZENIA + " WHERE t.id = ?", (ticket_id,)
    ).fetchone()


def pobierz_surowe(ticket_id):
    """Bez złączeń — gdy potrzebny jest tylko stan zgłoszenia."""
    return get_db().execute(
        "SELECT * FROM tickets WHERE id = ?", (ticket_id,)
    ).fetchone()


def istnieje(ticket_id):
    return get_db().execute(
        "SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)
    ).fetchone() is not None


def utworz(title, description, created_by):
    return get_db().execute(
        "INSERT INTO tickets (title, description, created_by) VALUES (?,?,?)",
        (title, description, created_by),
    ).lastrowid


def zapisz_kategoryzacje(ticket_id, kategoria, priorytet, pewnosc, sla_deadline):
    get_db().execute(
        "UPDATE tickets SET category=?, priority=?, ai_categorized=1, ai_pewnosc=?,"
        " sla_deadline=?, updated_at=datetime('now') WHERE id=?",
        (kategoria, priorytet, pewnosc, sla_deadline, ticket_id),
    )


def zmien_status(ticket_id, nowy_status, przypisz_do=None, zamknij=False):
    sql = "UPDATE tickets SET status = ?, updated_at = datetime('now')"
    params = [nowy_status]
    if przypisz_do is not None:
        sql += ", assigned_to = ?"
        params.append(przypisz_do)
    if zamknij:
        sql += ", closed_at = datetime('now')"
    sql += " WHERE id = ?"
    params.append(ticket_id)
    get_db().execute(sql, params)


def zmien_kategorie(ticket_id, kategoria):
    get_db().execute(
        "UPDATE tickets SET category = ?, updated_at = datetime('now') WHERE id = ?",
        (kategoria, ticket_id),
    )


def zmien_przypisanie(ticket_id, uzytkownik_id):
    get_db().execute(
        "UPDATE tickets SET assigned_to = ?, updated_at = datetime('now') WHERE id = ?",
        (uzytkownik_id, ticket_id),
    )


# --- Notatki -----------------------------------------------------------

def notatki(ticket_id, tylko_jawne):
    """Notatki zgłoszenia; pracownik nie widzi wewnętrznych."""
    sql = ("SELECT n.*, u.name author FROM notes n "
           "JOIN users u ON n.author_id = u.id WHERE n.ticket_id = ?")
    if tylko_jawne:
        sql += " AND n.internal = 0"
    return get_db().execute(sql + " ORDER BY n.id", (ticket_id,)).fetchall()


def dodaj_notatke(ticket_id, author_id, content, internal):
    get_db().execute(
        "INSERT INTO notes (ticket_id, author_id, content, internal) VALUES (?,?,?,?)",
        (ticket_id, author_id, content, 1 if internal else 0),
    )


# --- Statystyki --------------------------------------------------------

def statystyki(where, params):
    """Liczniki pulpitu jednym przejściem po tabeli zamiast pięcioma."""
    wiersz = get_db().execute(f"""
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
    return {k: wiersz[k] or 0 for k in klucze}


def rozklad_kategorii(where, params):
    rows = get_db().execute(
        f"SELECT category, COUNT(*) c FROM tickets{where}"
        + (" AND" if where else " WHERE") + " category IS NOT NULL"
        " GROUP BY category ORDER BY c DESC",
        params,
    ).fetchall()
    return [{"kategoria": r["category"], "liczba": r["c"]} for r in rows]

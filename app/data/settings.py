"""Ustawienia zmieniane przez kierownika — czasy SLA i historia ich zmian."""

from app.data.database import get_db


def sla_godziny():
    """Czasy SLA zapisane w bazie — {priorytet: godziny}.

    Zawiera tylko priorytety, które kierownik zmienił; pozostałe mają
    wartość domyślną z modułu kategoryzacji.
    """
    return {r["priority"]: r["hours"] for r in get_db().execute(
        "SELECT priority, hours FROM sla_settings")}


def zapisz_sla(priorytet, godziny, poprzednio, uzytkownik_id):
    """Nowy czas SLA wraz z wpisem w historii zmian."""
    db = get_db()
    db.execute(
        "INSERT INTO sla_settings (priority, hours, updated_by, updated_at)"
        " VALUES (?, ?, ?, datetime('now'))"
        " ON CONFLICT(priority) DO UPDATE SET hours = excluded.hours,"
        " updated_by = excluded.updated_by, updated_at = excluded.updated_at",
        (priorytet, godziny, uzytkownik_id),
    )
    db.execute(
        "INSERT INTO settings_history (user_id, setting, old_value, new_value)"
        " VALUES (?, ?, ?, ?)",
        (uzytkownik_id, f"SLA {priorytet}", str(poprzednio), str(godziny)),
    )


def historia(limit=20):
    """Ostatnie zmiany ustawień, od najnowszej."""
    return get_db().execute(
        "SELECT h.setting, h.old_value, h.new_value, h.timestamp, u.name AS user_name"
        " FROM settings_history h LEFT JOIN users u ON u.id = h.user_id"
        " ORDER BY h.id DESC LIMIT ?", (limit,)
    ).fetchall()

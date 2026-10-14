"""Dostęp do danych powiadomień, kolejki e-maili i eskalacji SLA."""

from app.data.database import get_db, czas_utc
from app.data.tickets import WARUNEK_AKTYWNE


def dodaj(powiadomienia):
    """Zapisuje listę powiadomień zbudowaną przez warstwę domenową."""
    if not powiadomienia:
        return
    get_db().executemany(
        "INSERT INTO notifications (user_id, ticket_id, typ, tresc) VALUES (?,?,?,?)",
        [(p["user_id"], p["ticket_id"], p["typ"], p["tresc"]) for p in powiadomienia],
    )


def _serializuj(r):
    return {"id": r["id"], "ticket_id": r["ticket_id"], "typ": r["typ"],
            "tresc": r["tresc"], "created_at": czas_utc(r["created_at"]),
            "przeczytane": r["read_at"] is not None}


def dla_uzytkownika(user_id, limit):
    rows = get_db().execute(
        "SELECT id, ticket_id, typ, tresc, created_at, read_at FROM notifications"
        " WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    return [_serializuj(r) for r in rows]


def liczba_nieprzeczytanych(user_id):
    return get_db().execute(
        "SELECT COUNT(*) c FROM notifications WHERE user_id = ? AND read_at IS NULL",
        (user_id,),
    ).fetchone()["c"]


def oznacz_przeczytane(user_id, ids=None):
    """Oznacza powiadomienia jako przeczytane; bez `ids` — wszystkie.

    Warunek `user_id` sprawia, że cudzych powiadomień nie da się oznaczyć,
    nawet podając ich identyfikatory.
    """
    sql = ("UPDATE notifications SET read_at = datetime('now')"
           " WHERE user_id = ? AND read_at IS NULL")
    params = [user_id]
    if ids is not None:
        if not ids:
            return 0
        sql += f" AND id IN ({','.join('?' * len(ids))})"
        params += list(ids)
    return get_db().execute(sql, params).rowcount


# --- Odbiorcy ----------------------------------------------------------

def personel():
    """Identyfikatory techników i administratorów: (technicy, administratorzy)."""
    rows = get_db().execute(
        "SELECT id, role FROM users WHERE role IN ('technik', 'admin') ORDER BY id"
    ).fetchall()
    return ([r["id"] for r in rows if r["role"] == "technik"],
            [r["id"] for r in rows if r["role"] == "admin"])


# --- Eskalacja ---------------------------------------------------------

def po_terminie(teraz):
    """Aktywne zgłoszenia po terminie SLA wraz z opóźnieniem w godzinach.

    Porównanie przez julianday() — w bazie występują dwa zapisy znacznika
    czasu (ze spacją i z literą T), opis w `app/data/pulpit.py`.
    """
    return get_db().execute(f"""
        SELECT id, title, priority, assigned_to, eskalacja,
               (julianday(?) - julianday(sla_deadline)) * 24 AS spoznienie
        FROM tickets
        WHERE {WARUNEK_AKTYWNE} AND sla_deadline IS NOT NULL
          AND julianday(sla_deadline) <= julianday(?)
        ORDER BY id
    """, (teraz, teraz)).fetchall()


def podnies_stopien(ticket_id, obecny, nowy):
    """Zapisuje wyższy stopień eskalacji, o ile nikt nie zrobił tego wcześniej.

    Zwraca False, gdy stopień w bazie jest już inny niż `obecny` — np. drugi
    proces roboczy uruchomiony przez pomyłkę obok pierwszego. Tylko jeden
    z nich wyśle wtedy powiadomienia.
    """
    return get_db().execute(
        "UPDATE tickets SET eskalacja = ? WHERE id = ? AND eskalacja = ?",
        (nowy, ticket_id, obecny),
    ).rowcount == 1


# --- Kolejka e-maili ---------------------------------------------------

def do_wysylki(od, max_prob, limit=200):
    """Powiadomienia czekające na e-mail — tylko dla osób z adresem."""
    return get_db().execute(
        "SELECT n.id, n.ticket_id, n.tresc, u.email, u.name"
        " FROM notifications n JOIN users u ON u.id = n.user_id"
        " WHERE n.email_wyslany IS NULL AND n.email_proby < ?"
        "   AND julianday(n.created_at) >= julianday(?)"
        "   AND u.email IS NOT NULL AND u.email != ''"
        " ORDER BY n.id LIMIT ?",
        (max_prob, od, limit),
    ).fetchall()


def oznacz_wyslany(powiadomienie_id):
    get_db().execute(
        "UPDATE notifications SET email_wyslany = datetime('now') WHERE id = ?",
        (powiadomienie_id,),
    )


def oznacz_nieudana_probe(powiadomienie_id):
    get_db().execute(
        "UPDATE notifications SET email_proby = email_proby + 1 WHERE id = ?",
        (powiadomienie_id,),
    )

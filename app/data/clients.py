"""Dostęp do danych klientów — firm, których pracownicy zgłaszają awarie."""

from app.data.database import get_db


def lista():
    """Klienci z liczbą pracowników oraz wszystkich i otwartych zgłoszeń.

    Jedno zapytanie zamiast trzech na każdego klienta — lista nie zwalnia
    wraz z liczbą firm. LEFT JOIN zachowuje klientów bez żadnych zgłoszeń.
    """
    rows = get_db().execute("""
        SELECT c.id, c.name,
               (SELECT COUNT(*) FROM users u WHERE u.client_id = c.id) AS pracownikow,
               COUNT(t.id)                                            AS zgloszen,
               COALESCE(SUM(t.status != 'Zamkniete'), 0)              AS otwartych
        FROM clients c
        LEFT JOIN tickets t ON t.client_id = c.id
        GROUP BY c.id
        ORDER BY c.name
    """).fetchall()
    return [
        {"id": r["id"], "name": r["name"], "pracownikow": r["pracownikow"],
         "zgloszen": r["zgloszen"], "otwartych": r["otwartych"]}
        for r in rows
    ]


def po_id(client_id):
    """Klient o podanym identyfikatorze albo None."""
    return get_db().execute(
        "SELECT id, name FROM clients WHERE id = ?", (client_id,)
    ).fetchone()

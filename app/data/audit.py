"""Ścieżka audytu — zapis zmian i statystyki jakości kategoryzacji.

Wpisy audytu pełnią podwójną rolę: są historią zgłoszenia dla technika oraz
źródłem danych o tym, jak często człowiek poprawia moduł AI.
"""

from app.data.database import get_db, czas_utc

AKCJA_ZMIANA_KATEGORII = "Zmiana kategorii"


def zapisz(ticket_id, user_id, action, old=None, new=None):
    get_db().execute(
        "INSERT INTO audit_log (ticket_id, user_id, action, old_value, new_value)"
        " VALUES (?,?,?,?,?)",
        (ticket_id, user_id, action, old, new),
    )


def historia(ticket_id):
    rows = get_db().execute(
        "SELECT a.*, u.name user_name FROM audit_log a"
        " LEFT JOIN users u ON a.user_id = u.id"
        " WHERE a.ticket_id = ? ORDER BY a.id",
        (ticket_id,),
    ).fetchall()
    return [
        {"action": r["action"],
         # Wpisy bez użytkownika pochodzą od modułu AI, nie od człowieka.
         "user": r["user_name"] or "System AI",
         "old": r["old_value"],
         "new": r["new_value"],
         "timestamp": czas_utc(r["timestamp"])}
        for r in rows
    ]


# --- Skuteczność kategoryzacji ----------------------------------------

def podsumowanie_kategoryzacji(prog):
    """Liczba zgłoszeń z AI, niepewnych i średnia pewność — jednym przejściem.

    Trzy osobne zapytania przeszukiwały tę samą tabelę trzy razy.
    """
    wiersz = get_db().execute(
        "SELECT COUNT(*) AS razem,"
        "       COALESCE(SUM(ai_pewnosc < ?), 0) AS niepewne,"
        "       AVG(ai_pewnosc) AS srednia"
        " FROM tickets WHERE ai_categorized = 1",
        (prog,),
    ).fetchone()
    return wiersz["razem"], wiersz["niepewne"], wiersz["srednia"]


def liczba_recznych_korekt():
    """Ile zgłoszeń technik przekwalifikował — każde to sygnał pomyłki AI."""
    return get_db().execute(
        "SELECT COUNT(DISTINCT ticket_id) c FROM audit_log WHERE action = ?",
        (AKCJA_ZMIANA_KATEGORII,),
    ).fetchone()["c"]


def najczestsze_pomylki(limit=5):
    """Kierunki korekt — wprost wskazują, których słów kluczowych brakuje."""
    rows = get_db().execute(
        "SELECT old_value AS z, new_value AS na, COUNT(*) c FROM audit_log"
        " WHERE action = ? AND old_value IS NOT NULL"
        " GROUP BY old_value, new_value ORDER BY c DESC LIMIT ?",
        (AKCJA_ZMIANA_KATEGORII, limit),
    ).fetchall()
    return [{"z": r["z"], "na": r["na"], "liczba": r["c"]} for r in rows]

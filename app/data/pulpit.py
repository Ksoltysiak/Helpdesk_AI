"""Zapytania pulpitu konsoli IT — dane „na żywo" dla techników.

Liczniki z `tickets.statystyki` mówią, ILE jest zgłoszeń. Te zapytania
odpowiadają na pytania, które technik zadaje sobie na początku zmiany: co się
pali (SLA), co nikt nie wziął, co się właśnie wydarzyło i kto jest zawalony.

Znaczniki czasu porównywane są przez `julianday()`, bo w bazie występują dwa
zapisy (`2026-10-01 10:00:00` i `2026-10-01T10:00:00`) — porównanie tekstowe
myliłoby je ze sobą.
"""

from datetime import date, timedelta

from app.data.database import get_db, czas_utc
# Rozwiązane czeka tylko na potwierdzenie zamknięcia, więc SLA już go nie
# dotyczy — ta sama definicja co w filtrze listy zgłoszeń.
from app.data.tickets import WARUNEK_AKTYWNE

# Ile godzin przed terminem SLA zgłoszenie uznajemy za zagrożone.
GODZIN_DO_ZAGROZENIA = 2


def puls(teraz, user_id):
    """Liczniki „co się dzieje teraz" jednym przejściem po tabeli."""
    wiersz = get_db().execute(f"""
        SELECT
            SUM({WARUNEK_AKTYWNE} AND julianday(sla_deadline) < julianday(?))     AS po_terminie,
            SUM({WARUNEK_AKTYWNE} AND julianday(sla_deadline) >= julianday(?)
                AND julianday(sla_deadline) < julianday(?) + ? / 24.0)     AS zagrozone,
            SUM({WARUNEK_AKTYWNE} AND assigned_to IS NULL)                        AS nieprzypisane,
            SUM({WARUNEK_AKTYWNE} AND assigned_to = ?)                            AS moje,
            SUM(date(created_at) = date(?))                                AS dzis_nowe,
            SUM(date(closed_at) = date(?))                                 AS dzis_zamkniete
        FROM tickets
    """, (teraz, teraz, teraz, GODZIN_DO_ZAGROZENIA, user_id, teraz, teraz)).fetchone()
    klucze = ("po_terminie", "zagrozone", "nieprzypisane", "moje",
              "dzis_nowe", "dzis_zamkniete")
    return {k: wiersz[k] or 0 for k in klucze}


def trend(dzis, dni):
    """Nowe i zamknięte zgłoszenia w kolejnych dniach — z zerami dla dni bez ruchu."""
    od = (dzis - timedelta(days=dni - 1)).isoformat()
    db = get_db()
    nowe = dict(db.execute(
        "SELECT date(created_at), COUNT(*) FROM tickets"
        " WHERE date(created_at) >= ? GROUP BY 1", (od,)).fetchall())
    zamkniete = dict(db.execute(
        "SELECT date(closed_at), COUNT(*) FROM tickets"
        " WHERE closed_at IS NOT NULL AND date(closed_at) >= ? GROUP BY 1", (od,)).fetchall())

    wynik = []
    for i in range(dni):
        d = (date.fromisoformat(od) + timedelta(days=i)).isoformat()
        wynik.append({"data": d, "nowe": nowe.get(d, 0), "zamkniete": zamkniete.get(d, 0)})
    return wynik


def aktywne_wg_priorytetu():
    rows = get_db().execute(
        f"SELECT priority, COUNT(*) c FROM tickets WHERE {WARUNEK_AKTYWNE}"
        " AND priority IS NOT NULL GROUP BY priority").fetchall()
    return {r["priority"]: r["c"] for r in rows}


def pilne_sla(teraz, limit=6):
    """Aktywne zgłoszenia najbliżej (albo już po) terminie SLA."""
    rows = get_db().execute(f"""
        SELECT t.id, t.title, t.priority, t.status, t.sla_deadline,
               ua.name assigned_to_name
        FROM tickets t LEFT JOIN users ua ON t.assigned_to = ua.id
        WHERE t.{WARUNEK_AKTYWNE} AND t.sla_deadline IS NOT NULL
          AND julianday(t.sla_deadline) < julianday(?) + ? / 24.0
        ORDER BY julianday(t.sla_deadline) LIMIT ?
    """, (teraz, GODZIN_DO_ZAGROZENIA, limit)).fetchall()
    return [{"id": r["id"], "title": r["title"], "priority": r["priority"],
             "status": r["status"], "sla_deadline": czas_utc(r["sla_deadline"]),
             "assigned_to_name": r["assigned_to_name"]} for r in rows]


def obciazenie_technikow():
    """Aktywne zgłoszenia na osobę z personelu — także na tych, którzy nie mają żadnych."""
    rows = get_db().execute(f"""
        SELECT u.id, u.name,
               COUNT(t.id) AS aktywne,
               COALESCE(SUM(t.priority = 'Krytyczny'), 0) AS krytyczne
        FROM users u
        LEFT JOIN tickets t ON t.assigned_to = u.id AND t.{WARUNEK_AKTYWNE}
        WHERE u.role IN ('technik', 'admin')
        GROUP BY u.id ORDER BY aktywne DESC, u.name
    """).fetchall()
    return [{"id": r["id"], "name": r["name"], "aktywne": r["aktywne"],
             "krytyczne": r["krytyczne"]} for r in rows]


def ostatnia_aktywnosc(autor_id=None, limit=12):
    """Najnowsze wpisy ścieżki audytu — kanał „co się właśnie wydarzyło".

    Pracownik nie ma dostępu do ścieżki audytu, więc widzi tylko swoje
    zgłoszenia i tylko zdarzenia, które i tak zna z listy: utworzenie i zmianę
    statusu. Notatki odpadają, bo treść notatki wewnętrznej trafia do audytu.

    Kolejność po czasie zdarzenia, nie po identyfikatorze: dane wczytane
    hurtowo (seed, import) mają wpisy dopisane w innej kolejności, niż zaszły.
    """
    warunek, params = "", []
    if autor_id is not None:
        warunek = (" WHERE t.created_by = ?"
                   " AND a.action IN ('Utworzenie', 'Zmiana statusu')")
        params.append(autor_id)
    rows = get_db().execute(
        "SELECT a.ticket_id, a.action, a.old_value, a.new_value, a.timestamp,"
        "       u.name user_name, t.title"
        " FROM audit_log a"
        " JOIN tickets t ON a.ticket_id = t.id"
        " LEFT JOIN users u ON a.user_id = u.id"
        + warunek + " ORDER BY julianday(a.timestamp) DESC, a.id DESC LIMIT ?",
        params + [limit],
    ).fetchall()
    return [{"ticket_id": r["ticket_id"], "title": r["title"], "action": r["action"],
             "old": r["old_value"], "new": r["new_value"],
             "user": r["user_name"] or "System AI",
             "timestamp": czas_utc(r["timestamp"])} for r in rows]

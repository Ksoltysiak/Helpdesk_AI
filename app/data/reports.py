"""Zapytania raportów dla klientów.

Każde zapytanie ogranicza się do zgłoszeń jednego klienta (albo wszystkich,
gdy klienta nie podano) utworzonych w podanym okresie. Granice okresu to
pełne doby UTC: od `od` 00:00:00 włącznie do dnia po `do` 00:00:00
wyłącznie.

Znaczniki czasu w bazie występują w dwóch zapisach — `2026-10-01 10:00:00`
(SQLite) i `2026-10-01T10:00:00` (starsze dane demonstracyjne). Porównania
tekstowe z granicą o północy działają poprawnie dla obu, a obliczenia
czasu przechodzą przez `julianday()`, które rozumie oba zapisy.
"""

from datetime import date, timedelta

from app.data.database import get_db


def _warunek(client_id, od, do):
    """WHERE dla zgłoszeń klienta z okresu [od, do] (daty włącznie)."""
    granice = [f"{od.isoformat()} 00:00:00",
               f"{(do + timedelta(days=1)).isoformat()} 00:00:00"]
    where = "t.created_at >= ? AND t.created_at < ?"
    if client_id is not None:
        return f"t.client_id = ? AND {where}", [client_id, *granice]
    return where, granice


def podsumowanie(client_id, od, do, teraz):
    """Liczby zbiorcze okresu jednym przejściem po zgłoszeniach.

    Chwila rozwiązania to OSTATNIE przejście do statusu „Rozwiazane" —
    zgłoszenie otwarte ponownie było naprawdę rozwiązane dopiero za drugim
    razem. Gdy w historii brak takiego wpisu (dane sprzed audytu), za
    rozwiązanie uznajemy zamknięcie.
    """
    where, params = _warunek(client_id, od, do)
    wiersz = get_db().execute(f"""
        WITH z AS (
            SELECT t.status, t.priority, t.created_at, t.sla_deadline,
                   CASE WHEN t.status IN ('Rozwiazane', 'Zamkniete') THEN
                       COALESCE((SELECT MAX(a.timestamp) FROM audit_log a
                                 WHERE a.ticket_id = t.id
                                   AND a.action = 'Zmiana statusu'
                                   AND a.new_value = 'Rozwiazane'),
                                t.closed_at)
                   END AS rozwiazano
            FROM tickets t
            WHERE {where}
        ), czasy AS (
            SELECT *,
                   (julianday(rozwiazano) - julianday(created_at)) * 24 AS godzin,
                   julianday(rozwiazano) <= julianday(sla_deadline)      AS w_terminie
            FROM z
        )
        SELECT
            COUNT(*)                                                    AS zgloszen,
            COALESCE(SUM(status IN ('Rozwiazane', 'Zamkniete')), 0)     AS rozwiazanych,
            COALESCE(SUM(priority = 'Krytyczny'), 0)                    AS krytycznych,
            -- Ujemny czas oznaczałby uszkodzone dane — nie zaniżamy nim średniej.
            AVG(CASE WHEN godzin >= 0 THEN godzin END)                  AS sredni_czas_h,
            COALESCE(SUM(w_terminie IS NOT NULL), 0)                    AS z_terminem,
            COALESCE(SUM(w_terminie = 1), 0)                            AS w_terminie,
            COALESCE(SUM(status NOT IN ('Rozwiazane', 'Zamkniete')
                         AND julianday(sla_deadline) < julianday(?)), 0) AS po_terminie
        FROM czasy
    """, [*params, teraz]).fetchone()
    return dict(wiersz)


def wg_kategorii(client_id, od, do):
    where, params = _warunek(client_id, od, do)
    rows = get_db().execute(
        f"SELECT t.category, COUNT(*) c FROM tickets t WHERE {where} GROUP BY t.category",
        params,
    ).fetchall()
    return {r["category"]: r["c"] for r in rows}


def wg_priorytetu(client_id, od, do):
    where, params = _warunek(client_id, od, do)
    rows = get_db().execute(
        f"SELECT t.priority, COUNT(*) c FROM tickets t WHERE {where} GROUP BY t.priority",
        params,
    ).fetchall()
    return {r["priority"]: r["c"] for r in rows}


def dziennie(client_id, od, do):
    """Liczba zgłoszeń w kolejnych dniach — {data: liczba}, tylko dni z danymi."""
    where, params = _warunek(client_id, od, do)
    rows = get_db().execute(
        f"SELECT date(t.created_at) d, COUNT(*) c FROM tickets t WHERE {where}"
        " GROUP BY date(t.created_at)",
        params,
    ).fetchall()
    return {date.fromisoformat(r["d"]): r["c"] for r in rows if r["d"]}


def najczestsze_problemy(client_id, od, do, etykiety, limit=5):
    """Najczęstsze problemy według słów kluczowych modułu AI.

    Każde zgłoszenie ma wpis audytu „Kategoryzacja AI" z wynikiem modułu
    w formacie JSON — pole `dopasowania` mówi, CO się psuło („drukark",
    „vpn"), dokładniej niż sama kategoria. Wpis z uszkodzonym JSON-em jest
    pomijany zamiast przerywać raport.

    `etykiety` zamienia rdzenie na czytelne nazwy. Grupowanie odbywa się po
    etykiecie W ZAPYTANIU, a nie po fakcie: zgłoszenie z „haslo" i „hasla"
    liczy się raz jako „hasło", a limit dotyczy już scalonych pozycji.
    Rdzeń bez etykiety pozostaje sobą.

    CROSS JOIN ustala kolejność złączenia: najpierw zgłoszenia z okresu
    (indeks raportowy), potem ich wpisy audytu. SQLite nie przestawia
    tabel złączonych w ten sposób — bez tego, przy zebranych statystykach,
    planista potrafił zacząć od całego dziennika audytu i raport zwalniał
    trzykrotnie.
    """
    where, params = _warunek(client_id, od, do)
    pary = list(etykiety.items()) or [("", "")]
    wartosci = ", ".join("(?, ?)" for _ in pary)
    rows = get_db().execute(f"""
        WITH etykiety(slowo, problem) AS (VALUES {wartosci})
        SELECT COALESCE(e.problem, j.value) AS problem, COUNT(DISTINCT t.id) AS liczba
        FROM tickets t
        CROSS JOIN audit_log a
        CROSS JOIN json_each(CASE WHEN json_valid(a.new_value) THEN a.new_value
                                  ELSE '{{}}' END, '$.dopasowania') j
        LEFT JOIN etykiety e ON e.slowo = j.value
        WHERE {where}
          AND a.ticket_id = t.id AND a.action = 'Kategoryzacja AI'
          AND j.type = 'text'
        GROUP BY COALESCE(e.problem, j.value)
        ORDER BY liczba DESC, problem
        LIMIT ?
    """, [*(v for para in pary for v in para), *params, limit]).fetchall()
    return [{"problem": r["problem"], "liczba": r["liczba"]} for r in rows]

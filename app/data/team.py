"""Statystyki techników — dla kierownika (cały zespół) i dla samego technika.

Definicje są zgodne z raportami dla klientów:

- **rozwiązanie** liczy się osobie, która wykonała OSTATNIE przejście
  zgłoszenia do „Rozwiazane", w dniu tego przejścia. Zgłoszenie musi nadal
  być rozwiązane lub zamknięte — otwarte ponownie nie jest sukcesem;
- **podjęcie** (pierwsza reakcja) to przejście „Nowe → W trakcie". Zdarza
  się raz na zgłoszenie, bo do statusu „Nowe" nie da się wrócić;
- **obciążenie** to zgłoszenia otwarte i przypisane TERAZ, niezależnie od
  wybranego okresu.

Funkcje zwracają słowniki {id_technika: wartości}; `technik_id` zawęża
wynik do jednej osoby.
"""

from datetime import date

from app.data.database import get_db, godziny_miedzy, granice_dob

# Rozwiązania z okresu, które są OSTATNIM przejściem zgłoszenia do „Rozwiazane"
# — wpis liczy się tylko wtedy, gdy później (także już po okresie) nie było
# kolejnego rozwiązania. Takie „nie istnieje późniejszy" to jedno wyszukanie
# w małym indeksie częściowym na wpis; wcześniejsza wersja z ROW_NUMBER()
# sortowała wszystkie rozwiązania okresu i była ~3× wolniejsza.
#
# INDEXED BY wskazuje indeksy wprost. Bez tego SQLite wybierał ogólny indeks
# rodzaju akcji i przeglądał każdą zmianę statusu w historii — przy 100 000
# zgłoszeń statystyki za 30 dni trwały 350 ms zamiast kilkunastu.
_ROZWIAZANIA = """
    WITH rozwiazania AS (
        SELECT a.user_id, t.id, t.category, a.timestamp AS rozwiazano,
               {godziny} AS godzin,
               julianday(a.timestamp) <= julianday(t.sla_deadline) AS w_terminie
        FROM audit_log a INDEXED BY idx_audit_rozwiazania_w_czasie
        JOIN tickets t ON t.id = a.ticket_id
        WHERE a.action = 'Zmiana statusu' AND a.new_value = 'Rozwiazane'
          AND a.timestamp >= ? AND a.timestamp < ? {technik}
          AND t.status IN ('Rozwiazane', 'Zamkniete')
          AND NOT EXISTS (
              SELECT 1 FROM audit_log b INDEXED BY idx_audit_rozwiazanie
              WHERE b.ticket_id = a.ticket_id
                AND b.action = 'Zmiana statusu' AND b.new_value = 'Rozwiazane'
                AND (b.timestamp > a.timestamp
                     OR (b.timestamp = a.timestamp AND b.id > a.id)))
    )
"""


def _rozwiazania(od, do, technik_id, select):
    jeden = technik_id is not None
    return get_db().execute(
        _ROZWIAZANIA.format(technik="AND a.user_id = ?" if jeden else "",
                            godziny=godziny_miedzy("t.created_at", "a.timestamp")) + select,
        [*granice_dob(od, do), *([technik_id] if jeden else [])],
    ).fetchall()


def rozwiazania(od, do, technik_id=None):
    """Liczba rozwiązań, średni czas i dotrzymanie SLA — na technika."""
    rows = _rozwiazania(od, do, technik_id, """
        SELECT user_id,
               COUNT(*)                                   AS rozwiazanych,
               AVG(CASE WHEN godzin >= 0 THEN godzin END) AS sredni_czas_h,
               COALESCE(SUM(w_terminie IS NOT NULL), 0)   AS z_terminem,
               COALESCE(SUM(w_terminie = 1), 0)           AS w_terminie
        FROM rozwiazania GROUP BY user_id
    """)
    return {r["user_id"]: dict(r) for r in rows}


def rozwiazania_dziennie(od, do, technik_id):
    rows = _rozwiazania(od, do, technik_id, """
        SELECT date(rozwiazano) d, COUNT(*) c FROM rozwiazania GROUP BY date(rozwiazano)
    """)
    return {date.fromisoformat(r["d"]): r["c"] for r in rows if r["d"]}


def rozwiazania_wg_kategorii(od, do, technik_id):
    rows = _rozwiazania(od, do, technik_id, """
        SELECT category, COUNT(*) c FROM rozwiazania GROUP BY category
    """)
    return {r["category"]: r["c"] for r in rows}


def podjecia(od, do, technik_id=None):
    """Podjęte zgłoszenia i średni czas pierwszej reakcji — na technika."""
    granice = granice_dob(od, do)
    filtr, params = ("AND a.user_id = ?", [technik_id]) if technik_id is not None else ("", [])
    rows = get_db().execute(f"""
        SELECT user_id, COUNT(*) AS podjetych,
               AVG(CASE WHEN godzin >= 0 THEN godzin END) AS sredni_czas_reakcji_h
        FROM (
            SELECT a.user_id,
                   {godziny_miedzy("t.created_at", "a.timestamp")} AS godzin
            FROM audit_log a INDEXED BY idx_audit_podjecia_w_czasie
            JOIN tickets t ON t.id = a.ticket_id
            WHERE a.action = 'Zmiana statusu' AND a.old_value = 'Nowe'
              AND a.new_value = 'W trakcie'
              AND a.timestamp >= ? AND a.timestamp < ? {filtr}
        )
        GROUP BY user_id
    """, [*granice, *params]).fetchall()
    return {r["user_id"]: dict(r) for r in rows}


def obciazenie(teraz, technik_id=None):
    """Otwarte zgłoszenia przypisane teraz i ile z nich przekroczyło termin."""
    filtr, params = ("AND assigned_to = ?", [technik_id]) if technik_id is not None else ("", [])
    rows = get_db().execute(f"""
        SELECT assigned_to AS user_id, COUNT(*) AS otwartych,
               COALESCE(SUM(julianday(sla_deadline) < julianday(?)), 0) AS po_terminie
        FROM tickets
        WHERE status IN ('Nowe', 'W trakcie', 'Wstrzymane')
          AND assigned_to IS NOT NULL {filtr}
        GROUP BY assigned_to
    """, [teraz, *params]).fetchall()
    return {r["user_id"]: dict(r) for r in rows}


def notatki(od, do, technik_id=None):
    """Liczba notatek dodanych w okresie — miara aktywności przy zgłoszeniach."""
    granice = granice_dob(od, do)
    filtr, params = ("AND author_id = ?", [technik_id]) if technik_id is not None else ("", [])
    rows = get_db().execute(f"""
        SELECT author_id, COUNT(*) AS c FROM notes
        WHERE created_at >= ? AND created_at < ? {filtr}
        GROUP BY author_id
    """, [*granice, *params]).fetchall()
    return {r["author_id"]: r["c"] for r in rows}

"""Statystyki techników — składanie miar z gotowych liczb.

Warstwa czysta: zapytania są w `app/data/team.py`, tu tylko łączenie wyników
w wiersz technika i porównanie z poprzednim okresem. Miary są opisem
obciążenia i tempa pracy, a nie rankingiem — zespół widzi je bez kolejności
„od najlepszego".
"""

from app.domain.reports import procent, zaokraglij, zmiana_proc


def statystyki_technika(obciazenie, podjecia, rozwiazania, rozwiazania_poprzednio, notatek):
    """Miary jednego technika z wyników zapytań (słowników lub None)."""
    obciazenie = obciazenie or {}
    podjecia = podjecia or {}
    rozwiazania = rozwiazania or {}
    rozwiazanych = rozwiazania.get("rozwiazanych", 0)
    poprzednio = (rozwiazania_poprzednio or {}).get("rozwiazanych", 0)
    z_terminem = rozwiazania.get("z_terminem", 0)
    return {
        "otwartych":                  obciazenie.get("otwartych", 0),
        "otwartych_po_terminie":      obciazenie.get("po_terminie", 0),
        "podjetych":                  podjecia.get("podjetych", 0),
        "sredni_czas_reakcji_h":      zaokraglij(podjecia.get("sredni_czas_reakcji_h")),
        "rozwiazanych":               rozwiazanych,
        "rozwiazanych_poprzednio":    poprzednio,
        "zmiana_proc":                zmiana_proc(rozwiazanych, poprzednio),
        "sredni_czas_rozwiazania_h":  zaokraglij(rozwiazania.get("sredni_czas_h")),
        "rozwiazanych_z_terminem":    z_terminem,
        "w_terminie_sla":             rozwiazania.get("w_terminie", 0),
        "procent_w_terminie_sla":     procent(rozwiazania.get("w_terminie", 0), z_terminem),
        "notatek":                    notatek or 0,
    }


def suma_zespolu(wiersze):
    """Łączne liczby zespołu; średnie czasy ważone liczbą zgłoszeń."""
    def srednia(pole_czasu, pole_liczby):
        wagi = [(w[pole_czasu], w[pole_liczby]) for w in wiersze
                if w[pole_czasu] is not None and w[pole_liczby]]
        razem = sum(n for _, n in wagi)
        return zaokraglij(sum(c * n for c, n in wagi) / razem) if razem else None

    suma = {k: sum(w[k] for w in wiersze) for k in (
        "otwartych", "otwartych_po_terminie", "podjetych", "rozwiazanych",
        "rozwiazanych_poprzednio", "rozwiazanych_z_terminem", "w_terminie_sla", "notatek")}
    suma["zmiana_proc"] = zmiana_proc(suma["rozwiazanych"], suma["rozwiazanych_poprzednio"])
    suma["procent_w_terminie_sla"] = procent(suma["w_terminie_sla"], suma["rozwiazanych_z_terminem"])
    suma["sredni_czas_reakcji_h"] = srednia("sredni_czas_reakcji_h", "podjetych")
    suma["sredni_czas_rozwiazania_h"] = srednia("sredni_czas_rozwiazania_h", "rozwiazanych")
    return suma

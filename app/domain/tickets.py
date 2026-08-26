"""Reguły biznesowe zgłoszeń — cykl życia i wynikające z niego konsekwencje.

Warstwa czysta: bez bazy danych, bez HTTP. Dzięki temu reguły można testować
i czytać w oderwaniu od sposobu ich wywołania.
"""

# Dozwolone przejścia statusów:
#
#     Nowe → W trakcie → Rozwiazane → Zamkniete
#                   ↘ Wstrzymane ↗
#
# Zgłoszenie musi przejść przez obsługę — nie da się zamknąć nowego zgłoszenia
# bez podjęcia go, bo wtedy ścieżka audytu nie pokazywałaby, kto się nim zajął.
TRANSITIONS = {
    "Nowe":       ["W trakcie"],
    "W trakcie":  ["Rozwiazane", "Wstrzymane"],
    "Wstrzymane": ["W trakcie"],
    "Rozwiazane": ["Zamkniete", "W trakcie"],
    "Zamkniete":  [],
}

STATUS_POCZATKOWY = "Nowe"
STATUS_KONCOWY = "Zamkniete"


def dozwolone_przejscia(status: str):
    """Statusy osiągalne z podanego stanu."""
    return TRANSITIONS.get(status, [])


def czy_przejscie_dozwolone(obecny: str, docelowy) -> bool:
    return docelowy in dozwolone_przejscia(obecny)


def czy_podjecie(obecny: str, docelowy: str) -> bool:
    """Czy ta zmiana oznacza podjęcie zgłoszenia przez technika.

    Podjęcie przypisuje zgłoszenie osobie, która zmienia status — o ile nie
    miało jeszcze opiekuna.
    """
    return obecny == STATUS_POCZATKOWY and docelowy == "W trakcie"


def czy_zamkniecie(docelowy: str) -> bool:
    """Czy ta zmiana domyka zgłoszenie (ustawia datę zamknięcia)."""
    return docelowy == STATUS_KONCOWY

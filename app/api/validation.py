"""Walidacja danych wejściowych na granicy HTTP.

Klient może przysłać dowolny JSON, więc typ trzeba sprawdzić, zanim wartość
trafi do `len()` albo do sterownika bazy — inaczej liczba lub obiekt kończą
się nieobsłużonym wyjątkiem i odpowiedzią HTTP 500 zamiast czytelnego 400.
"""

from flask import request


def parametr_calkowity(nazwa, domyslnie, minimum, maksimum):
    """Liczbowy parametr zapytania, przycięty do dozwolonego zakresu.

    Wartości spoza zakresu są przycinane, a nie odrzucane błędem — klient
    prosząc o stronę 9999 dostaje ostatnią istniejącą, co jest użyteczniejsze
    niż komunikat o błędzie.
    """
    surowa = request.args.get(nazwa)
    if surowa is None or surowa == "":
        return domyslnie
    try:
        wartosc = int(surowa)
    except (TypeError, ValueError):
        return domyslnie
    return max(minimum, min(wartosc, maksimum))


def pole_tekstowe(dane, nazwa, maks):
    """Zwraca (wartosc, blad) dla wymaganego pola tekstowego."""
    wartosc = dane.get(nazwa, "")
    if not isinstance(wartosc, str):
        return None, f"Pole '{nazwa}' musi byc tekstem"
    wartosc = wartosc.strip()
    if not wartosc:
        return None, f"Pole '{nazwa}' jest wymagane"
    if len(wartosc) > maks:
        return None, f"Pole '{nazwa}' jest za dlugie (max {maks} znakow)"
    return wartosc, None

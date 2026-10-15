"""Walidacja danych wejściowych na granicy HTTP.

Klient może przysłać dowolny JSON, więc typ trzeba sprawdzić, zanim wartość
trafi do `len()` albo do sterownika bazy — inaczej liczba lub obiekt kończą
się nieobsłużonym wyjątkiem i odpowiedzią HTTP 500 zamiast czytelnego 400.
"""

from datetime import datetime, timezone

from flask import jsonify, request

from app.domain import reports as reguly_raportow


def obiekt_json():
    """Ciało żądania jako słownik — pusty, gdy to nie jest obiekt JSON.

    Poprawny JSON nie musi być obiektem: `[1]` czy `"tekst"` też się
    parsują, a dalszy kod woła na nich `.get()` i kończy się błędem 500.
    Wszystko, co nie jest obiektem, traktujemy jak brak danych.
    """
    dane = request.get_json(silent=True)
    return dane if isinstance(dane, dict) else {}


# Największa liczba mieszcząca się w kolumnie INTEGER SQLite. Python nie ma
# górnej granicy liczb całkowitych, więc większy identyfikator dochodził do
# sterownika bazy i kończył się błędem 500 (OverflowError).
MAX_ID = 2**63 - 1


def okres_z_parametrow():
    """(od, do, odpowiedź błędu albo None) z parametrów `od` i `do`.

    Ta sama walidacja dla raportów klientów i statystyk zespołu — zakres,
    format i granice okresu są w obu miejscach identyczne.
    """
    dzis = datetime.now(timezone.utc).date()
    try:
        od, do = reguly_raportow.okres(request.args.get("od"), request.args.get("do"), dzis)
    except reguly_raportow.BladOkresu as e:
        return None, None, (jsonify({"error": str(e)}), 400)
    return od, do, None


def opis_okresu(od, do):
    pop_od, pop_do = reguly_raportow.poprzedni_okres(od, do)
    return (
        {"od": od.isoformat(), "do": do.isoformat(), "dni": (do - od).days + 1,
         "grupowanie": reguly_raportow.grupowanie(od, do)},
        pop_od, pop_do,
    )


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

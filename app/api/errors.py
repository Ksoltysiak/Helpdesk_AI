"""Obsługa błędów dla ścieżek API.

Klient API musi dostawać JSON także przy błędach — domyślne strony HTML
Flaska łamałyby udokumentowany kontrakt i myliłyby kod błędu z treścią.
"""

from flask import request, jsonify

PREFIKS_API = "/api/"


def _dotyczy_api():
    return request.path.startswith(PREFIKS_API)


def zarejestruj(app):
    def blad_json(kod, komunikat):
        def handler(e):
            if _dotyczy_api():
                return jsonify({"error": komunikat}), kod
            return e
        return handler

    app.register_error_handler(404, blad_json(404, "Nie znaleziono punktu koncowego"))
    app.register_error_handler(405, blad_json(405, "Metoda niedozwolona dla tej sciezki"))
    app.register_error_handler(429, blad_json(429, "Zbyt wiele zadan — sprobuj ponownie pozniej"))

    @app.errorhandler(500)
    def blad_wewnetrzny(_e):
        # Treść wyjątku nigdy nie trafia do klienta — mogłaby zdradzić
        # szczegóły implementacji lub fragmenty danych.
        if _dotyczy_api():
            return jsonify({"error": "Blad wewnetrzny serwera"}), 500
        return "Blad wewnetrzny serwera", 500

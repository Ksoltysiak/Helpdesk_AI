"""Zadania w tle — praca, która nie należy do żadnego żądania HTTP.

Uruchamiane osobnym procesem (`python -m app.zadania`, w Dockerze usługa
`worker`): eskalacja zgłoszeń po terminie SLA i wysyłka e-maili z kolejki
powiadomień. Korzystają z warstw `domain` i `data` tak samo jak warstwa HTTP,
tylko zamiast żądania wyzwala je zegar.
"""

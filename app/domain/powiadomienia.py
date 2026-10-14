"""Reguły powiadomień — kto dowiaduje się o jakim zdarzeniu i jaką treścią.

Warstwa czysta: funkcje dostają dane zgłoszenia (słownik albo wiersz bazy)
i zwracają listę powiadomień do zapisania. O tym, jak powiadomienie dotrze
do człowieka (dzwonek w aplikacji, e-mail), decydują inne warstwy.

Zasada ogólna: nikt nie dostaje powiadomienia o własnej czynności.
"""

TYP_STATUS = "status"
TYP_NOTATKA = "notatka"
TYP_PRZYPISANIE = "przypisanie"
TYP_NOWE_KRYTYCZNE = "nowe_krytyczne"
TYP_ESKALACJA = "eskalacja"

TYPY = (TYP_STATUS, TYP_NOTATKA, TYP_PRZYPISANIE, TYP_NOWE_KRYTYCZNE, TYP_ESKALACJA)

# Nazwy w bazie są bez polskich znaków (wspólne z API); treść powiadomienia
# czyta człowiek, więc dostaje pełną pisownię.
_STATUSY = {"Rozwiazane": "Rozwiązane", "Zamkniete": "Zamknięte"}
_PRIORYTETY = {"Sredni": "Średni"}

# Tytuł w treści jest skracany — powiadomienie ma się mieścić w jednej linii
# dzwonka i w temacie e-maila.
MAKS_TYTUL = 80


def status_pl(status):
    return _STATUSY.get(status, status)


def priorytet_pl(priorytet):
    return _PRIORYTETY.get(priorytet, priorytet)


def opis_zgloszenia(ticket_id, tytul):
    """`#12 „Nie działa VPN”` — tytuł w jednej linii i przycięty.

    Złamania wiersza są zamieniane na spacje: treść trafia też do tematu
    e-maila, a znak nowej linii w nagłówku wiadomości jest niedozwolony.
    """
    tytul = " ".join((tytul or "").split())
    if len(tytul) > MAKS_TYTUL:
        tytul = tytul[:MAKS_TYTUL - 1].rstrip() + "…"
    return f"#{ticket_id} „{tytul}”"


def _powiadomienie(user_id, ticket_id, typ, tresc):
    return {"user_id": user_id, "ticket_id": ticket_id, "typ": typ, "tresc": tresc}


def po_zmianie_statusu(zgloszenie, nowy_status, wykonawca_id):
    """Zgłaszający dowiaduje się o każdej zmianie statusu swojego zgłoszenia."""
    autor = zgloszenie["created_by"]
    if autor == wykonawca_id:
        return []
    opis = opis_zgloszenia(zgloszenie["id"], zgloszenie["title"])
    return [_powiadomienie(autor, zgloszenie["id"], TYP_STATUS,
                           f"Zgłoszenie {opis}: status zmieniony na {status_pl(nowy_status)}")]


def po_notatce(zgloszenie, wewnetrzna, autor_notatki_id):
    """Zgłaszający dostaje powiadomienie tylko o notatce, którą może przeczytać."""
    autor = zgloszenie["created_by"]
    if wewnetrzna or autor == autor_notatki_id:
        return []
    opis = opis_zgloszenia(zgloszenie["id"], zgloszenie["title"])
    return [_powiadomienie(autor, zgloszenie["id"], TYP_NOTATKA,
                           f"Nowa odpowiedź technika w zgłoszeniu {opis}")]


def po_przypisaniu(zgloszenie, nowy_opiekun_id, wykonawca_id):
    """Technik dowiaduje się, że ktoś przekazał mu zgłoszenie.

    Ponowne przypisanie do tej samej osoby niczego nie zmienia, więc też
    nikogo nie powiadamia.
    """
    if nowy_opiekun_id in (wykonawca_id, zgloszenie["assigned_to"]):
        return []
    opis = opis_zgloszenia(zgloszenie["id"], zgloszenie["title"])
    return [_powiadomienie(nowy_opiekun_id, zgloszenie["id"], TYP_PRZYPISANIE,
                           f"Przypisano Ci zgłoszenie {opis} "
                           f"(priorytet {priorytet_pl(zgloszenie['priority'])})")]


def po_utworzeniu(ticket_id, tytul, priorytet, personel_ids):
    """Zgłoszenie krytyczne trafia od razu do całego personelu.

    Przy SLA równym godzinie nie ma czasu czekać, aż ktoś zajrzy na pulpit.
    O zwykłych zgłoszeniach informuje sam pulpit — powiadamianie wszystkich
    techników o każdym z nich zagłuszyłoby te naprawdę pilne.
    """
    if priorytet != "Krytyczny":
        return []
    tresc = f"Nowe zgłoszenie krytyczne {opis_zgloszenia(ticket_id, tytul)}"
    return [_powiadomienie(uid, ticket_id, TYP_NOWE_KRYTYCZNE, tresc) for uid in personel_ids]

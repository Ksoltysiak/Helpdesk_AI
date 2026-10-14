"""Reguły eskalacji zgłoszeń po przekroczeniu terminu SLA.

Dwa stopnie, zgodnie z podziałem ITIL na eskalację funkcjonalną
i hierarchiczną:

    1. Przekroczenie terminu — powiadomienie trafia do opiekuna zgłoszenia,
       a gdy go nie ma, do wszystkich techników: ktoś musi je wziąć.
    2. Zgłoszenie nadal otwarte po upływie kolejnej połowy czasu SLA —
       powiadomienie trafia do administratorów (przełożonych), bo sam zespół
       najwyraźniej sobie z nim nie radzi.

Przykład dla priorytetu Wysoki (SLA 4 h): stopień 1 w chwili przekroczenia
terminu, stopień 2 dwie godziny później.

Eskalacja niczego w zgłoszeniu nie zmienia poza zapamiętaniem stopnia —
nie podnosi priorytetu ani nie przepisuje opiekuna. To decyzje dla ludzi,
system ma tylko dopilnować, żeby właściwe osoby o problemie wiedziały.
"""

from app.domain.ai import SLA_HOURS
from app.domain.powiadomienia import TYP_ESKALACJA, opis_zgloszenia, priorytet_pl

BRAK = 0
STOPIEN_ZESPOL = 1
STOPIEN_PRZELOZONY = 2

# Drugi stopień: po upływie takiej części czasu SLA od przekroczenia terminu.
CZESC_SLA_DO_DRUGIEGO_STOPNIA = 0.5


def stopien_eskalacji(spoznienie_godzin, priorytet):
    """Stopień, który zgłoszenie powinno mieć przy danym opóźnieniu.

    `spoznienie_godzin` < 0 oznacza, że termin jeszcze nie minął.
    Nieznany priorytet dostaje najdłuższy czas SLA — lepiej eskalować później
    niż zasypać przełożonych z powodu błędnych danych.
    """
    if spoznienie_godzin < 0:
        return BRAK
    sla = SLA_HOURS.get(priorytet, max(SLA_HOURS.values()))
    if spoznienie_godzin >= sla * CZESC_SLA_DO_DRUGIEGO_STOPNIA:
        return STOPIEN_PRZELOZONY
    return STOPIEN_ZESPOL


def _czas(godzin):
    if godzin < 1:
        return f"{max(1, round(godzin * 60))} min"
    if godzin >= 10:
        return f"{godzin:.0f} h"
    return f"{godzin:.1f}".removesuffix(".0").replace(".", ",") + " h"


def powiadomienia_eskalacji(zgloszenie, stopien, spoznienie_godzin,
                            technicy_ids, administratorzy_ids):
    """Kogo powiadomić o osiągnięciu danego stopnia i jaką treścią.

    `zgloszenie` musi mieć pola id, title, priority, assigned_to.
    """
    opis = opis_zgloszenia(zgloszenie["id"], zgloszenie["title"])
    priorytet = priorytet_pl(zgloszenie["priority"])

    if stopien == STOPIEN_ZESPOL:
        opiekun = zgloszenie["assigned_to"]
        if opiekun is not None:
            odbiorcy = [opiekun]
            tresc = f"Przekroczony termin SLA: {opis} (priorytet {priorytet})"
        else:
            # Bez techników (mały zespół, sam administrator) zgłoszenie
            # i tak musi do kogoś trafić.
            odbiorcy = list(technicy_ids) or list(administratorzy_ids)
            tresc = (f"Przekroczony termin SLA, zgłoszenie bez opiekuna: {opis} "
                     f"(priorytet {priorytet})")
    elif stopien == STOPIEN_PRZELOZONY:
        odbiorcy = list(administratorzy_ids)
        tresc = (f"Eskalacja: {opis} jest {_czas(spoznienie_godzin)} po terminie SLA "
                 f"(priorytet {priorytet})")
    else:
        return []

    return [{"user_id": uid, "ticket_id": zgloszenie["id"], "typ": TYP_ESKALACJA,
             "tresc": tresc} for uid in dict.fromkeys(odbiorcy)]

"""Eskalacja zgłoszeń po terminie SLA — jeden przebieg."""

import logging

from app.data import audit
from app.data import powiadomienia as repo
from app.data.database import get_db, teraz_utc
from app.domain import eskalacja as reguly

log = logging.getLogger(__name__)


def eskaluj(teraz=None):
    """Podnosi stopień eskalacji zgłoszeń po terminie i powiadamia odbiorców.

    Zwraca liczbę zgłoszeń, których stopień się zmienił. Każde zgłoszenie
    jest zatwierdzane osobno — błąd przy jednym nie cofa pozostałych.

    Zgłoszenie, które od ostatniego przebiegu przeskoczyło o dwa stopnie
    (np. proces roboczy był wyłączony), dostaje powiadomienia obu stopni:
    opiekun też powinien wiedzieć, że jego zgłoszenie trafiło do przełożonych.
    """
    teraz = teraz or teraz_utc()
    technicy, administratorzy = repo.personel()
    db = get_db()
    zmienione = 0

    for t in repo.po_terminie(teraz):
        nowy = reguly.stopien_eskalacji(t["spoznienie"], t["priority"])
        if nowy <= t["eskalacja"]:
            continue
        if not repo.podnies_stopien(t["id"], t["eskalacja"], nowy):
            continue  # inny proces zrobił to pierwszy

        for stopien in range(t["eskalacja"] + 1, nowy + 1):
            repo.dodaj(reguly.powiadomienia_eskalacji(
                t, stopien, t["spoznienie"], technicy, administratorzy))
        audit.zapisz(t["id"], None, audit.AKCJA_ESKALACJA, str(t["eskalacja"]), str(nowy))
        db.commit()
        zmienione += 1
        log.info("Zgloszenie #%s: eskalacja %s -> %s", t["id"], t["eskalacja"], nowy)

    return zmienione

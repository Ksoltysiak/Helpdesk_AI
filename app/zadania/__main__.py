"""Proces roboczy: co `WORKER_INTERWAL` sekund eskalacja SLA i wysyłka e-maili.

    python -m app.zadania

Działa jako osobna usługa, a nie wątek w procesie gunicorna: gunicorn
uruchamia kilka procesów, więc każdy z nich robiłby to samo, a restart
serwera WWW przerywałby wysyłkę w połowie.
"""

import logging
import pathlib
import signal
import threading

from app import config, create_app
from app.zadania import eskalacja, poczta

log = logging.getLogger("app.zadania")


def przebieg(app):
    """Jeden przebieg obu zadań. Błąd jednego nie blokuje drugiego."""
    with app.app_context():
        try:
            eskalacja.eskaluj()
        except Exception:
            log.exception("Eskalacja SLA nie powiodla sie")
        if poczta.wlaczona():
            try:
                poczta.wyslij_zalegle()
            except Exception:
                log.exception("Wysylka e-maili nie powiodla sie")

    if config.WORKER_HEARTBEAT:
        pathlib.Path(config.WORKER_HEARTBEAT).touch()


def petla(app, stop, interwal):
    """Przebiegi aż do ustawienia `stop`. Pierwszy rusza od razu po starcie."""
    while True:
        przebieg(app)
        if stop.wait(interwal):
            return


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    stop = threading.Event()
    # `docker stop` wysyła SIGTERM — kończymy po bieżącym przebiegu zamiast
    # przerywać wysyłkę w połowie.
    for sygnal in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sygnal, lambda *_: stop.set())

    log.info("Proces roboczy: interwal %s s, e-mail %s", config.WORKER_INTERWAL,
             "wlaczony" if poczta.wlaczona() else "wylaczony (brak SMTP_HOST)")
    petla(create_app(), stop, config.WORKER_INTERWAL)


if __name__ == "__main__":
    main()

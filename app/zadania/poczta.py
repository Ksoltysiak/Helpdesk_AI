"""Wysyłka e-maili z kolejki powiadomień.

Wiadomość jest oznaczana jako wysłana od razu po przyjęciu przez serwer
poczty i zatwierdzana pojedynczo: przerwanie procesu w połowie partii nie
spowoduje ponownego wysłania tych, które już wyszły.
"""

import logging
import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage

from app import config
from app.data import powiadomienia as repo
from app.data.database import get_db, teraz_utc

log = logging.getLogger(__name__)

# Bez limitu czasu zawieszony serwer poczty zatrzymałby proces roboczy,
# a z nim także eskalację SLA.
LIMIT_CZASU_SMTP = 15


def wlaczona():
    return bool(config.SMTP_HOST)


def _polacz():
    if config.SMTP_TLS == "ssl":
        smtp = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT,
                                timeout=LIMIT_CZASU_SMTP,
                                context=ssl.create_default_context())
    else:
        smtp = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=LIMIT_CZASU_SMTP)
        if config.SMTP_TLS == "starttls":
            smtp.starttls(context=ssl.create_default_context())
    if config.SMTP_USER:
        smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
    return smtp


def zbuduj_wiadomosc(p):
    """EmailMessage dla wiersza kolejki (tresc, email, name, ticket_id)."""
    msg = EmailMessage()
    msg["From"] = config.SMTP_FROM
    msg["To"] = p["email"]
    msg["Subject"] = f"[HelpDesk] {p['tresc']}"
    tekst = [f"Dzień dobry {p['name']},", "", p["tresc"]]
    if config.APP_URL and p["ticket_id"] is not None:
        tekst += ["", f"Szczegóły: {config.APP_URL}/#zgloszenie-{p['ticket_id']}"]
    tekst += ["", "--", "Wiadomość wysłana automatycznie przez system HelpDesk IT."]
    msg.set_content("\n".join(tekst))
    return msg


def wyslij_zalegle(teraz=None):
    """Wysyła e-maile czekające w kolejce. Zwraca (wysłane, nieudane)."""
    teraz = teraz or teraz_utc()
    od = _przesun(teraz, -config.EMAIL_WAZNOSC_GODZIN)
    kolejka = repo.do_wysylki(od, config.EMAIL_MAX_PROB)
    if not kolejka:
        return 0, 0

    db = get_db()
    try:
        smtp = _polacz()
    except (OSError, smtplib.SMTPException) as e:
        # Serwer niedostępny — każda wiadomość traci jedną próbę, żeby przy
        # trwałej awarii kolejka w końcu przestała być ponawiana.
        log.warning("Brak polaczenia z serwerem poczty: %s", e)
        for p in kolejka:
            repo.oznacz_nieudana_probe(p["id"])
        db.commit()
        return 0, len(kolejka)

    wyslane = nieudane = 0
    try:
        for p in kolejka:
            try:
                smtp.send_message(zbuduj_wiadomosc(p))
            except (OSError, smtplib.SMTPException) as e:
                log.warning("Nie wyslano powiadomienia %s: %s", p["id"], e)
                repo.oznacz_nieudana_probe(p["id"])
                nieudane += 1
            else:
                repo.oznacz_wyslany(p["id"])
                wyslane += 1
            db.commit()
    finally:
        try:
            smtp.quit()
        except (OSError, smtplib.SMTPException):
            pass
    return wyslane, nieudane


def _przesun(znacznik, godzin):
    """Znacznik w formacie SQLite przesunięty o podaną liczbę godzin."""
    chwila = datetime.strptime(znacznik, "%Y-%m-%d %H:%M:%S") + timedelta(hours=godzin)
    return chwila.strftime("%Y-%m-%d %H:%M:%S")

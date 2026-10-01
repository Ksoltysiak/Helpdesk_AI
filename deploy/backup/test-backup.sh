#!/bin/bash
# Test kopii zapasowych na działającym stosie (docker compose up).
#
# Sprawdza cały cykl odtwarzania po awarii, a nie tylko to, że plik kopii
# powstał: kopia → utrata bazy → odtworzenie → aplikacja działa na danych
# z kopii i może dalej zapisywać. Do tego rotację i odrzucenie uszkodzonej
# kopii. Uruchamiany w CI, można go też odpalić lokalnie z katalogu repo.
set -euo pipefail

dc() { docker compose "$@"; }
krok() { echo; echo "== $*"; }
blad() { echo "TEST NIE PRZESZEDL: $*" >&2; exit 1; }

# Zapytania wykonujemy z kontenera aplikacji, jako jej użytkownik — tak jak
# robi to sama aplikacja. Python ma wbudowany moduł sqlite3.
zapytanie() {
    dc exec -T helpdesk python -c \
        "import sqlite3,sys; print(sqlite3.connect('/app/data/helpdesk.db').execute(sys.argv[1]).fetchone()[0])" "$1"
}
liczba_kopii() {
    dc exec -T backup sh -c 'ls -1 /backups/helpdesk-*.db.gz 2>/dev/null | wc -l'
}
czekaj_na_aplikacje() {
    for _ in $(seq 60); do
        curl -sf http://127.0.0.1:8080/api/health >/dev/null && return 0
        sleep 2
    done
    blad "aplikacja nie wstala po odtworzeniu bazy"
}

krok "Dane testowe"
dc exec -T helpdesk python seed.py >/dev/null
zgloszen=$(zapytanie "SELECT count(*) FROM tickets")
[ "$zgloszen" -gt 0 ] || blad "seed nie utworzyl zgloszen"
echo "zgloszen w bazie: $zgloszen"

krok "Kopia na zadanie"
przed=$(liczba_kopii)
dc exec -T backup backup.sh
[ "$(liczba_kopii)" -eq $((przed + 1)) ] || blad "nie powstala nowa kopia"
dc exec -T backup sh -c 'cd /backups && sha256sum -c "$(ls -1 helpdesk-*.db.gz | sort -r | head -n1).sha256"' \
    || blad "suma kontrolna nowej kopii sie nie zgadza"

krok "Kopia nalezy do uzytkownika aplikacji, nie do roota"
dc exec -T backup sh -c 'stat -c %u /backups/$(ls -1 /backups | grep "\.db\.gz$" | sort -r | head -n1)' \
    | grep -qvx 0 || blad "plik kopii nalezy do roota"

krok "Symulowana awaria: utrata pliku bazy"
dc stop helpdesk
dc run --rm --no-deps backup rm -f /data/helpdesk.db /data/helpdesk.db-wal /data/helpdesk.db-shm

krok "Odtworzenie z najnowszej kopii"
dc run --rm --no-deps backup restore.sh latest
dc start helpdesk
czekaj_na_aplikacje

krok "Aplikacja dziala na odtworzonych danych"
po=$(zapytanie "SELECT count(*) FROM tickets")
[ "$po" = "$zgloszen" ] || blad "po odtworzeniu jest $po zgloszen, oczekiwano $zgloszen"
echo "zgloszen po odtworzeniu: $po"

krok "Aplikacja moze zapisywac do odtworzonej bazy"
# Odtworzony plik z niewłaściwym właścicielem dałby się czytać, ale nie
# zapisywać — błąd ujawniłby się dopiero przy pierwszym nowym zgłoszeniu.
dc exec -T helpdesk python -c \
    "import sqlite3; c=sqlite3.connect('/app/data/helpdesk.db'); c.execute('BEGIN IMMEDIATE'); c.rollback()" \
    || blad "odtworzona baza jest tylko do odczytu dla aplikacji"

krok "Rotacja: zostaje tylko BACKUP_KEEP najnowszych kopii"
for _ in 1 2 3; do
    sleep 1   # nazwy kopii maja rozdzielczosc sekundy
    dc exec -T -e BACKUP_KEEP=2 backup backup.sh
done
[ "$(liczba_kopii)" -eq 2 ] || blad "po rotacji jest $(liczba_kopii) kopii, oczekiwano 2"

krok "Uszkodzona kopia jest odrzucana"
dc exec -T backup sh -c '
    cd /backups
    zrodlo=$(ls -1 helpdesk-*.db.gz | sort -r | head -n1)
    cp "$zrodlo" helpdesk-19990101-000000.db.gz
    sed "s/$zrodlo/helpdesk-19990101-000000.db.gz/" "$zrodlo.sha256" > helpdesk-19990101-000000.db.gz.sha256
    printf x >> helpdesk-19990101-000000.db.gz'
dc stop helpdesk
if dc run --rm --no-deps backup restore.sh helpdesk-19990101-000000.db.gz; then
    blad "restore przyjal uszkodzona kopie"
fi
dc start helpdesk
czekaj_na_aplikacje
[ "$(zapytanie "SELECT count(*) FROM tickets")" = "$zgloszen" ] \
    || blad "nieudane odtworzenie naruszylo baze"
dc exec -T backup sh -c 'rm -f /backups/helpdesk-19990101-000000.db.gz*'

echo
echo "Wszystkie testy kopii zapasowych przeszly."

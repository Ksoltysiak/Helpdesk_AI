#!/bin/bash
# Odtwarza bazę z kopii zapasowej.
#
# Użycie:  restore.sh latest | <nazwa pliku kopii> | --list
#          restore.sh --force ...   pomija sprawdzenie, czy aplikacja działa
#
# Aplikacja MUSI być zatrzymana — podmiana pliku pod działającym procesem
# zgubiłaby jego otwarte transakcje. Procedura:
#   docker compose stop helpdesk
#   docker compose run --rm --no-deps backup restore.sh latest
#   docker compose start helpdesk
set -euo pipefail

DB_PATH=${DB_PATH:-/data/helpdesk.db}
BACKUP_DIR=${BACKUP_DIR:-/backups}

log() { echo "[restore $(date '+%F %T')] $*"; }
fail() { log "BLAD: $*" >&2; exit 1; }

# Jak w backup.sh: odtworzony plik musi należeć do użytkownika aplikacji.
if [ "$(id -u)" = 0 ]; then
    wlasciciel=$(stat -c '%u:%g' "$(dirname "$DB_PATH")")
    if [ "$wlasciciel" != "0:0" ]; then
        exec su-exec "$wlasciciel" "$0" "$@"
    fi
fi

force=0
if [ "${1:-}" = "--force" ]; then force=1; shift; fi
cel=${1:-}

if [ "$cel" = "--list" ]; then
    ls -1 "$BACKUP_DIR"/helpdesk-*.db.gz 2>/dev/null | xargs -r -n1 basename | sort -r
    exit 0
fi
[ -n "$cel" ] || fail "podaj 'latest', nazwe kopii albo --list"

if [ "$cel" = "latest" ]; then
    kopia=$(ls -1 "$BACKUP_DIR"/helpdesk-*.db.gz 2>/dev/null | sort -r | head -n1 || true)
    [ -n "$kopia" ] || fail "w $BACKUP_DIR nie ma zadnej kopii"
else
    kopia="$BACKUP_DIR/$(basename "$cel")"
fi
[ -f "$kopia" ] || fail "nie ma pliku $kopia"

# Niepusty plik -wal oznacza, że ktoś ma bazę otwartą (przy zamknięciu
# ostatniego połączenia SQLite scala go z bazą i usuwa). To tylko siatka
# bezpieczeństwa, nie gwarancja: aplikacja otwiera połączenie na czas
# jednego żądania, więc bezczynna aplikacja może nie mieć pliku -wal.
# Zatrzymanie aplikacji przed odtworzeniem pozostaje obowiązkiem operatora.
if [ "$force" = 0 ] && [ -s "$DB_PATH-wal" ]; then
    fail "baza jest w uzyciu (istnieje $DB_PATH-wal). Zatrzymaj aplikacje: docker compose stop helpdesk"
fi

if [ -f "$kopia.sha256" ]; then
    (cd "$BACKUP_DIR" && sha256sum -c --quiet "$(basename "$kopia").sha256") \
        || fail "suma kontrolna sie nie zgadza — plik kopii jest uszkodzony"
else
    log "UWAGA: brak pliku sumy kontrolnej, pomijam weryfikacje sumy"
fi

# Rozpakowujemy obok bazy (ten sam system plików), żeby końcowe `mv`
# było atomowe — baza jest albo stara, albo w całości nowa.
tmp="$(dirname "$DB_PATH")/.restore-$$.db"
trap 'rm -f "$tmp"' EXIT
gunzip -c "$kopia" > "$tmp"

wynik=$(sqlite3 "$tmp" "PRAGMA integrity_check;")
[ "$wynik" = "ok" ] || fail "kopia nie przeszla kontroli spojnosci: $wynik"

# Obecną bazę zostawiamy obok zamiast ją kasować — pomyłkę przy wyborze
# kopii da się wtedy cofnąć.
if [ -f "$DB_PATH" ]; then
    zachowana="$DB_PATH.przed-odtworzeniem-$(date -u '+%Y%m%d-%H%M%S')"
    mv "$DB_PATH" "$zachowana"
    log "dotychczasowa baza zachowana jako $(basename "$zachowana")"
fi
rm -f "$DB_PATH-wal" "$DB_PATH-shm"
mv "$tmp" "$DB_PATH"
trap - EXIT

log "odtworzono z $(basename "$kopia") (zgloszen: $(sqlite3 "$DB_PATH" 'SELECT count(*) FROM tickets;'))"

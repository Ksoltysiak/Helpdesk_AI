#!/bin/bash
# Tworzy spójną kopię bazy SQLite, weryfikuje ją i usuwa najstarsze kopie.
#
# Zmienne:
#   DB_PATH      plik bazy                      (domyślnie /data/helpdesk.db)
#   BACKUP_DIR   katalog kopii                  (domyślnie /backups)
#   BACKUP_KEEP  ile najnowszych kopii zachować (domyślnie 14)
set -euo pipefail

DB_PATH=${DB_PATH:-/data/helpdesk.db}
BACKUP_DIR=${BACKUP_DIR:-/backups}
BACKUP_KEEP=${BACKUP_KEEP:-14}

log() { echo "[backup $(date '+%F %T')] $*"; }
fail() { log "BLAD: $*" >&2; exit 1; }

[ -f "$DB_PATH" ] || fail "brak pliku bazy $DB_PATH"
[[ "$BACKUP_KEEP" =~ ^[1-9][0-9]*$ ]] || fail "BACKUP_KEEP musi byc liczba dodatnia"

# Pracujemy jako właściciel bazy, nie jako root. SQLite w trybie WAL tworzy
# obok bazy pliki -wal i -shm; gdyby utworzył je root, aplikacja (użytkownik
# bez uprawnień roota) nie mogłaby do nich pisać i przestałaby zapisywać dane.
if [ "$(id -u)" = 0 ]; then
    wlasciciel=$(stat -c '%u:%g' "$(dirname "$DB_PATH")")
    if [ "$wlasciciel" != "0:0" ]; then
        mkdir -p "$BACKUP_DIR"
        chown "$wlasciciel" "$BACKUP_DIR"
        exec su-exec "$wlasciciel" "$0" "$@"
    fi
fi

mkdir -p "$BACKUP_DIR"
nazwa="helpdesk-$(date -u '+%Y%m%d-%H%M%S').db"
tmp="$BACKUP_DIR/.tmp-$nazwa"
trap 'rm -f "$tmp" "$tmp.gz"' EXIT

# .backup korzysta z Online Backup API: kopiuje bazę strona po stronie przy
# działającej aplikacji i daje spójny stan — w przeciwieństwie do zwykłego
# `cp`, który przy trybie WAL może skopiować plik bez ostatnich transakcji
# albo w połowie zapisu. Timeout pozwala przeczekać chwilowe blokady.
sqlite3 -cmd ".timeout 10000" "$DB_PATH" ".backup '$tmp'"

# Kopia, której nie da się odtworzyć, jest gorsza niż brak kopii, bo daje
# fałszywe poczucie bezpieczeństwa — dlatego każdą sprawdzamy od razu.
wynik=$(sqlite3 "$tmp" "PRAGMA integrity_check;")
[ "$wynik" = "ok" ] || fail "kopia nie przeszla kontroli spojnosci: $wynik"
zgloszen=$(sqlite3 "$tmp" "SELECT count(*) FROM tickets;")

gzip -9 "$tmp"
# Suma kontrolna wykrywa uszkodzenie pliku już po jego zapisaniu
# (dysk, przenoszenie między serwerami) — sprawdza ją restore.sh.
suma=$(sha256sum "$tmp.gz" | cut -d' ' -f1)
echo "$suma  $nazwa.gz" > "$BACKUP_DIR/$nazwa.gz.sha256"
# Zmiana nazwy jest atomowa: plik helpdesk-*.db.gz albo jest kompletny,
# albo go nie ma. Przerwana kopia nie zostanie wzięta za najnowszą.
mv "$tmp.gz" "$BACKUP_DIR/$nazwa.gz"
trap - EXIT

log "utworzono $nazwa.gz ($(du -h "$BACKUP_DIR/$nazwa.gz" | cut -f1), zgloszen: $zgloszen)"

# Rotacja: nazwy zawierają znacznik czasu, więc sortowanie alfabetyczne
# jest chronologiczne. Usuwamy wszystko poza BACKUP_KEEP najnowszymi.
mapfile -t stare < <(ls -1 "$BACKUP_DIR"/helpdesk-*.db.gz | sort -r | tail -n +"$((BACKUP_KEEP + 1))")
for plik in "${stare[@]}"; do
    rm -f "$plik" "$plik.sha256"
    log "usunieto stara kopie $(basename "$plik")"
done

#!/bin/bash
# Bez argumentów: uruchamia crond z harmonogramem z BACKUP_SCHEDULE.
# Z argumentami: wykonuje podane polecenie (np. restore.sh latest) —
# dzięki temu ten sam obraz służy do jednorazowych operacji.
set -euo pipefail

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

# Wyjście zadania trafia na stdout procesu 1, czyli do `docker compose logs`.
echo "${BACKUP_SCHEDULE} /usr/local/bin/backup.sh > /proc/1/fd/1 2>&1" \
    > /etc/crontabs/root

echo "Harmonogram kopii: '${BACKUP_SCHEDULE}' (${TZ}), przechowywanych kopii: ${BACKUP_KEEP}"
exec crond -f -l 8

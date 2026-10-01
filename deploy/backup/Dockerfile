# Kontener kopii zapasowych bazy SQLite.
#
# Osobny obraz zamiast skryptu w kontenerze aplikacji: kopia ma powstawać
# niezależnie od tego, czy aplikacja działa, a jej harmonogram (cron) nie
# powinien być kolejnym procesem obok gunicorna. Alpine wystarcza — potrzebny
# jest tylko klient sqlite3 (wbudowane polecenie .backup), bash i crond
# z BusyBoxa.
FROM alpine:3.20

RUN apk add --no-cache bash sqlite tzdata su-exec coreutils

COPY backup.sh restore.sh entrypoint.sh /usr/local/bin/

# Na Windowsie git z core.autocrlf=true zamienia końce linii na CRLF, a wtedy
# "#!/bin/bash\r" nie istnieje i kontener nie wystartuje. Normalizujemy
# końce linii przy budowie, więc obraz działa niezależnie od tego, skąd
# zbudowano go z repozytorium.
RUN sed -i 's/\r$//' /usr/local/bin/*.sh \
    && chmod +x /usr/local/bin/*.sh

ENV DB_PATH=/data/helpdesk.db \
    BACKUP_DIR=/backups \
    BACKUP_KEEP=14 \
    BACKUP_SCHEDULE="0 2 * * *" \
    TZ=Europe/Warsaw

ENTRYPOINT ["entrypoint.sh"]

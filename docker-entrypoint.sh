#!/bin/sh
set -e

# init_db() jest idempotentne (CREATE ... IF NOT EXISTS + migracje kolumn),
# wiec uruchamiamy je przy kazdym starcie — dzieki temu istniejaca baza
# dostaje brakujace indeksy i kolumny bez osobnego kroku migracji.
python -c "from app.data.database import init_db; init_db()"

exec "$@"

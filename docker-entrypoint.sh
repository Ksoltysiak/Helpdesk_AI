#!/bin/sh
set -e

# init_db() jest idempotentne (CREATE ... IF NOT EXISTS), wiec uruchamiamy je
# przy kazdym starcie — dzieki temu istniejaca baza dostaje brakujace indeksy
# bez osobnego kroku migracji.
python -c "from db import init_db; init_db()"

exec "$@"

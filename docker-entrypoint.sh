#!/bin/sh
set -e

python -c "from db import init_db, DB_PATH; import os; init_db() if not os.path.exists(DB_PATH) else None"

exec "$@"

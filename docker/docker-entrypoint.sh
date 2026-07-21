#!/bin/sh
set -e

python -c "import sys; sys.path.insert(0, 'backend'); from db import init_db, DB_PATH; import os; init_db() if not os.path.exists(DB_PATH) else None"

exec "$@"

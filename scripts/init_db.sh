#!/usr/bin/env sh
set -eu
python -c "from app.storage.db import init_db; init_db(); print('database initialized')"

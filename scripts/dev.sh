#!/usr/bin/env sh
set -eu
uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-43180}" --reload

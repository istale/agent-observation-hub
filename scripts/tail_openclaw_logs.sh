#!/usr/bin/env sh
set -eu
python -m app.importers.openclaw_importer --path "${1:?log path required}" --follow

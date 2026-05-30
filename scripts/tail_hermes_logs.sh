#!/usr/bin/env sh
set -eu
python -m app.importers.hermes_importer --path "${1:?log path required}" --follow

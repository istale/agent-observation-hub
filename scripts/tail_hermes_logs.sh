#!/usr/bin/env sh
set -eu
python -m app.importers.agent_events.cli --source hermes --path "${1:?log path required}" --follow

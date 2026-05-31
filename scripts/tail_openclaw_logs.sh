#!/usr/bin/env sh
set -eu
python -m app.importers.agent_events.cli --source openclaw --path "${1:?log path required}" --follow

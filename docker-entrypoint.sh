#!/bin/sh
set -e

# Ensure data directory exists for history persistence
mkdir -p /app/data

# Ensure config.yaml exists as a file (web setup wizard populates it)
if [ ! -f /app/config.yaml ]; then
  touch /app/config.yaml
fi

exec python -m uvicorn termmon.main:app --host 0.0.0.0 --port 8084

#!/bin/sh
set -e

# Railway injects the PORT environment variable at runtime. Default to 8080
# if it is not set (e.g. when running the image locally).
PORT="${PORT:-8080}"

exec gunicorn "run:app" --bind "0.0.0.0:${PORT}" --workers 1 --timeout 120

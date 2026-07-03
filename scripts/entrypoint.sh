#!/bin/sh
set -eu

alembic -c backend/alembic.ini upgrade head

exec uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 7999

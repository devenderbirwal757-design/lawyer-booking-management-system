#!/bin/sh
# Compose entrypoint: block until PostgreSQL and Redis accept connections,
# then hand over to the service's own command with its arguments intact.
set -e

python scripts/wait_for_services.py

if [ "$#" -eq 0 ]; then
    echo "docker-entrypoint: no command given" >&2
    exit 1
fi

exec "$@"

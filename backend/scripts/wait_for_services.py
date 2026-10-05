"""Block until PostgreSQL and Redis accept connections.

Used as the container entrypoint gate so the API never boots against a
database that is still starting up. Not needed for local (non-Docker) work.
"""

from __future__ import annotations

import os
import sys
import time

TIMEOUT_SECONDS = int(os.environ.get("WAIT_FOR_SERVICES_TIMEOUT", "60"))


def wait_for_postgres(timeout: int) -> None:
    import psycopg

    dsn = (
        f"host={os.environ.get('DJANGO_DB_HOST', 'db')} "
        f"port={os.environ.get('DJANGO_DB_PORT', '5432')} "
        f"dbname={os.environ.get('DJANGO_DB_NAME', 'lawyer')} "
        f"user={os.environ.get('DJANGO_DB_USER', 'lawyer_app')} "
        f"password={os.environ.get('DJANGO_DB_PASSWORD', '')}"
    )
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=3) as conn:
                conn.execute("SELECT 1")
            return
        except Exception as exc:
            last_error = exc
            time.sleep(1)
    raise SystemExit(f"PostgreSQL not ready after {timeout}s: {last_error}")


def wait_for_redis(timeout: int) -> None:
    import redis

    url = os.environ.get("DJANGO_CELERY_BROKER_URL", "redis://redis:6379/1")
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            client = redis.Redis.from_url(url, socket_connect_timeout=3)
            client.ping()
            return
        except Exception as exc:
            last_error = exc
            time.sleep(1)
    raise SystemExit(f"Redis not ready after {timeout}s: {last_error}")


def main() -> int:
    wait_for_postgres(TIMEOUT_SECONDS)
    wait_for_redis(TIMEOUT_SECONDS)
    print("PostgreSQL and Redis are ready.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

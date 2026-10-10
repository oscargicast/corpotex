"""Postgres advisory locks. One style task at a time (ADR 0019): the worker has 5 slots and the
`style` queue does not limit concurrency by itself."""

import zlib
from contextlib import contextmanager

from django.db import connection

# A constant: Python's hash() changes per process, so it would never lock anything.
STYLE_LOCK_KEY = zlib.crc32(b"corpotex-style")


@contextmanager
def advisory_lock(key: int):
    """Yields True if the lock was acquired. Released on exit; Postgres also releases it if
    the connection dies."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [key])
        acquired = bool(cursor.fetchone()[0])
    try:
        yield acquired
    finally:
        if acquired:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [key])


def style_lock():
    return advisory_lock(STYLE_LOCK_KEY)

"""Populate the demo database with a tiny list of fruits.

Runs once at container start (see Containerfile CMD) before the web app boots.
Idempotent: drops & recreates the table so repeated `compose up` runs are repeatable.

Configuration is via env vars (with safe defaults for use under compose):
  PG_URL  default: postgresql://demo:demo@postgres:5432/demo
"""

from __future__ import annotations

import os
import time
from urllib.parse import urlsplit

import psycopg

PG_URL = os.environ.get("PG_URL", "postgresql://demo:demo@postgres:5432/demo")

FRUITS: list[tuple[str, str, int]] = [
    ("Apple",      "Red, crunchy, ubiquitous.",                89),
    ("Banana",     "Yellow, soft, comes in bunches.",          105),
    ("Cherry",     "Small, sweet, with a pit.",                50),
    ("Date",       "Sticky, very sweet, grows on palms.",      282),
    ("Elderberry", "Tiny, dark, traditionally cooked first.",  73),
    ("Fig",        "Soft, jammy, full of tiny seeds.",         74),
    ("Grape",      "Comes in bunches; also wine.",             69),
    ("Honeydew",   "Pale green melon, very mild.",             36),
    ("Kiwi",       "Fuzzy outside, bright green inside.",      61),
    ("Lemon",      "Yellow, sour, mostly used as juice.",      29),
]


def _redacted_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.password:
        netloc = parts.netloc.replace(f":{parts.password}@", ":***@", 1)
        return parts._replace(netloc=netloc).geturl()
    return url


def connect_with_retry(retries: int = 30, delay: float = 1.0) -> psycopg.Connection:
    # depends_on: service_healthy should make this unnecessary, but keep a
    # short retry loop so the seed step is also runnable standalone.
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return psycopg.connect(PG_URL)
        except psycopg.OperationalError as e:
            last_err = e
            print(
                f"[wait] postgres not reachable yet "
                f"(attempt {attempt}/{retries}): {e}",
                flush=True,
            )
            time.sleep(delay)
    raise RuntimeError(
        f"postgres at {_redacted_url(PG_URL)} never became reachable: {last_err}"
    )


def main() -> None:
    print(f"[seed] connecting to {_redacted_url(PG_URL)}", flush=True)
    with connect_with_retry() as conn, conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS fruits")
        cur.execute(
            """
            CREATE TABLE fruits (
                id           SERIAL PRIMARY KEY,
                name         TEXT NOT NULL UNIQUE,
                description  TEXT NOT NULL,
                calories     INTEGER NOT NULL
            )
            """
        )
        cur.executemany(
            "INSERT INTO fruits (name, description, calories) VALUES (%s, %s, %s)",
            FRUITS,
        )
        conn.commit()
        cur.execute("SELECT count(*) FROM fruits")
        (n,) = cur.fetchone()
        print(f"[seed] loaded {n} fruits", flush=True)


if __name__ == "__main__":
    main()

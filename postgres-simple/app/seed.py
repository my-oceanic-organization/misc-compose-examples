"""Populate the demo database with a tiny list of fruits.

Runs once at container start (see Containerfile CMD) before the web app boots.
Idempotent: drops & recreates the table so repeated `compose up` runs are clean.

Configuration is via env vars (with safe defaults for use under compose):
  POSTGRES_HOST      default: postgres
  POSTGRES_PORT      default: 5432
  POSTGRES_DB        default: demo
  POSTGRES_USER      default: demo
  POSTGRES_PASSWORD  default: demo
"""

from __future__ import annotations

import os
import time

import psycopg

HOST = os.environ.get("POSTGRES_HOST", "postgres")
PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
DB = os.environ.get("POSTGRES_DB", "demo")
USER = os.environ.get("POSTGRES_USER", "demo")
PASSWORD = os.environ.get("POSTGRES_PASSWORD", "demo")

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


def connect_with_retry(retries: int = 30, delay: float = 1.0) -> psycopg.Connection:
    # depends_on: service_healthy should make this unnecessary, but keep a
    # short retry loop so the seed step is also runnable standalone.
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return psycopg.connect(
                host=HOST,
                port=PORT,
                dbname=DB,
                user=USER,
                password=PASSWORD,
            )
        except psycopg.OperationalError as e:
            last_err = e
            print(
                f"[wait] postgres not reachable yet "
                f"(attempt {attempt}/{retries}): {e}",
                flush=True,
            )
            time.sleep(delay)
    raise RuntimeError(f"postgres at {HOST}:{PORT} never became reachable: {last_err}")


def main() -> None:
    print(f"[seed] connecting to {HOST}:{PORT}/{DB} as {USER}", flush=True)
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

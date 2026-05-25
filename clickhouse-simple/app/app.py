"""Minimal ClickHouse demo: insert synthetic events into a MergeTree table and
periodically print an aggregation over the last minute, all in one process.

Configuration is via env vars (with safe defaults for use under compose):
  CLICKHOUSE_HOST          default: clickhouse
  CLICKHOUSE_PORT          default: 8123        (HTTP interface)
  CLICKHOUSE_USER          default: default
  CLICKHOUSE_PASSWORD      default: ""
  CLICKHOUSE_DATABASE      default: default

  INSERT_INTERVAL_SECONDS  default: 1           (one batch per tick)
  INSERT_BATCH_SIZE        default: 50
  REPORT_INTERVAL_SECONDS  default: 5
"""

from __future__ import annotations

import os
import random
import threading
import time
from datetime import datetime, timezone

import clickhouse_connect
from clickhouse_connect.driver.exceptions import OperationalError

HOST = os.environ.get("CLICKHOUSE_HOST", "clickhouse")
PORT = int(os.environ.get("CLICKHOUSE_PORT", "8123"))
USER = os.environ.get("CLICKHOUSE_USER", "default")
PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "")
DATABASE = os.environ.get("CLICKHOUSE_DATABASE", "default")

INSERT_INTERVAL = float(os.environ.get("INSERT_INTERVAL_SECONDS", "1"))
INSERT_BATCH = int(os.environ.get("INSERT_BATCH_SIZE", "50"))
REPORT_INTERVAL = float(os.environ.get("REPORT_INTERVAL_SECONDS", "5"))

EVENT_TYPES = ("click", "view", "purchase", "signup")
TABLE = "events"


def connect():
    return clickhouse_connect.get_client(
        host=HOST,
        port=PORT,
        username=USER,
        password=PASSWORD,
        database=DATABASE,
    )


def wait_for_clickhouse(retries: int = 30, delay: float = 2.0):
    # depends_on: service_healthy should make this unnecessary, but keep a
    # short retry loop so the app is also runnable standalone.
    for attempt in range(1, retries + 1):
        try:
            client = connect()
            client.command("SELECT 1")
            return client
        except (OperationalError, OSError) as e:
            print(
                f"[wait] clickhouse not reachable yet "
                f"(attempt {attempt}/{retries}): {e}",
                flush=True,
            )
            time.sleep(delay)
    raise RuntimeError(f"clickhouse at {HOST}:{PORT} never became reachable")


def ensure_schema(client) -> None:
    client.command(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            ts         DateTime64(3, 'UTC'),
            event_type LowCardinality(String),
            user_id    UInt32,
            value      Float64
        )
        ENGINE = MergeTree
        ORDER BY (event_type, ts)
        """
    )
    print(f"[schema] table {TABLE!r} ready", flush=True)


def insert_loop() -> None:
    client = connect()
    columns = ["ts", "event_type", "user_id", "value"]
    while True:
        now = datetime.now(timezone.utc)
        rows = [
            (
                now,
                random.choice(EVENT_TYPES),
                random.randint(1, 100),
                round(random.uniform(0, 100), 2),
            )
            for _ in range(INSERT_BATCH)
        ]
        client.insert(TABLE, rows, column_names=columns)
        print(f"[insert] +{len(rows)} rows", flush=True)
        time.sleep(INSERT_INTERVAL)


def report_loop() -> None:
    client = connect()
    query = f"""
        SELECT
            event_type,
            count()       AS n,
            round(avg(value), 2) AS avg_value,
            uniqExact(user_id)   AS unique_users
        FROM {TABLE}
        WHERE ts > now() - INTERVAL 1 MINUTE
        GROUP BY event_type
        ORDER BY event_type
    """
    while True:
        time.sleep(REPORT_INTERVAL)
        result = client.query(query)
        print("[report] last 60s by event_type:", flush=True)
        if not result.result_rows:
            print("  (no rows yet)", flush=True)
            continue
        for event_type, n, avg_value, unique_users in result.result_rows:
            print(
                f"  {event_type:<10} n={n:<6} "
                f"avg_value={avg_value:<7} unique_users={unique_users}",
                flush=True,
            )


def main() -> None:
    print(
        f"[boot] clickhouse={HOST}:{PORT} db={DATABASE} "
        f"insert_every={INSERT_INTERVAL}s batch={INSERT_BATCH} "
        f"report_every={REPORT_INTERVAL}s",
        flush=True,
    )
    client = wait_for_clickhouse()
    ensure_schema(client)
    threading.Thread(target=insert_loop, daemon=True).start()
    report_loop()


if __name__ == "__main__":
    main()

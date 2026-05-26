"""Minimal Valkey demo: a "slow" pure-Python function whose results are cached
in Valkey with a short TTL. The main loop picks random keys forever and logs a
clear HIT / MISS line each tick, so the caching behaviour is obvious from the
container logs alone -- no external APIs, no network calls beyond Valkey.

Configuration is via env vars (with safe defaults for use under compose):
  VALKEY_HOST            default: valkey
  VALKEY_PORT            default: 6379
  CACHE_TTL_SECONDS      default: 10     (entries expire, forcing re-MISSes)
  TICK_INTERVAL_SECONDS  default: 1      (delay between lookups)
  SLOW_COMPUTE_SECONDS   default: 2      (how slow a MISS feels)
"""

from __future__ import annotations

import hashlib
import os
import random
import time

import valkey
from valkey.exceptions import ConnectionError as ValkeyConnectionError

HOST = os.environ.get("VALKEY_HOST", "valkey")
PORT = int(os.environ.get("VALKEY_PORT", "6379"))
TTL = int(os.environ.get("CACHE_TTL_SECONDS", "10"))
TICK = float(os.environ.get("TICK_INTERVAL_SECONDS", "1"))
SLOW = float(os.environ.get("SLOW_COMPUTE_SECONDS", "2"))

KEYS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot"]
CACHE_PREFIX = "demo:hash:"


def slow_compute(key: str) -> str:
    """Pretend this is an expensive computation or remote lookup.

    We sleep for SLOW seconds and then return a short hex digest derived from
    the key. The sleep is the whole point: it's what makes the cache pay off.
    """
    time.sleep(SLOW)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def connect_with_retry(retries: int = 30, delay: float = 1.0) -> valkey.Valkey:
    # depends_on: service_healthy should make this unnecessary, but keep a
    # short retry loop so the app is also runnable standalone.
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            client = valkey.Valkey(host=HOST, port=PORT, decode_responses=True)
            client.ping()
            return client
        except ValkeyConnectionError as e:
            last_err = e
            print(
                f"[wait] valkey not reachable yet "
                f"(attempt {attempt}/{retries}): {e}",
                flush=True,
            )
            time.sleep(delay)
    raise RuntimeError(f"valkey at {HOST}:{PORT} never became reachable: {last_err}")


def get_or_compute(client: valkey.Valkey, key: str) -> tuple[str, str, float]:
    """Cache-aside read: returns (value, "HIT"|"MISS", elapsed_seconds)."""
    cache_key = CACHE_PREFIX + key
    t0 = time.perf_counter()
    cached = client.get(cache_key)
    if cached is not None:
        return cached, "HIT", time.perf_counter() - t0

    value = slow_compute(key)
    client.set(cache_key, value, ex=TTL)
    return value, "MISS", time.perf_counter() - t0


def main() -> None:
    print(
        f"[boot] valkey={HOST}:{PORT} ttl={TTL}s "
        f"tick={TICK}s slow_compute={SLOW}s keys={KEYS}",
        flush=True,
    )
    client = connect_with_retry()
    hits = 0
    misses = 0
    while True:
        key = random.choice(KEYS)
        value, kind, elapsed = get_or_compute(client, key)
        if kind == "HIT":
            hits += 1
        else:
            misses += 1
        total = hits + misses
        hit_rate = (hits / total) * 100 if total else 0.0
        print(
            f"[{kind:<4}] key={key:<8} value={value} "
            f"in {elapsed * 1000:7.2f} ms  "
            f"(hits={hits} misses={misses} hit_rate={hit_rate:5.1f}%)",
            flush=True,
        )
        time.sleep(TICK)


if __name__ == "__main__":
    main()

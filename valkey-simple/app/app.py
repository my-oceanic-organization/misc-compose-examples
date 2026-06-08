"""Minimal Valkey demo: a "slow" pure-Python function whose results are cached
in Valkey with a short TTL. A background thread picks random keys forever and
records a clear HIT / MISS event each tick, so the caching behaviour is obvious
from the container logs *and* from a tiny built-in web UI.

The web UI is intentionally trivial: a single static HTML page served from
``index.html`` plus a JSON endpoint that exposes the current stats, the recent
event log, and the currently cached keys with their TTLs. It exists so that
this demo can be shown end-to-end via a PaaS HTTP route without anyone having
to ``docker logs`` or shell in.

Configuration is via env vars (with safe defaults for use under compose):
  VALKEY_URL             default: valkey://valkey:6379
  CACHE_TTL_SECONDS      default: 10     (entries expire, forcing re-MISSes)
  TICK_INTERVAL_SECONDS  default: 1      (delay between lookups)
  SLOW_COMPUTE_SECONDS   default: 2      (how slow a MISS feels)
  HTTP_PORT              default: 8000   (web UI / JSON API)
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import threading
import time
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import valkey
from valkey.exceptions import ConnectionError as ValkeyConnectionError

VALKEY_URL = os.environ.get("VALKEY_URL", "valkey://valkey:6379")
TTL = int(os.environ.get("CACHE_TTL_SECONDS", "10"))
TICK = float(os.environ.get("TICK_INTERVAL_SECONDS", "1"))
SLOW = float(os.environ.get("SLOW_COMPUTE_SECONDS", "2"))
HTTP_PORT = int(os.environ.get("HTTP_PORT", "8000"))

KEYS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot"]
CACHE_PREFIX = "demo:hash:"

INDEX_HTML = (Path(__file__).parent / "index.html").read_bytes()


# ---------------------------------------------------------------------------
# Shared in-process state, written by the worker thread, read by HTTP handlers.
# ---------------------------------------------------------------------------

_state_lock = threading.Lock()
_state: dict[str, Any] = {
    "hits": 0,
    "misses": 0,
    "events": deque(maxlen=50),
    "last_error": None,
}


def _record(kind: str, key: str, value: str, elapsed_ms: float) -> None:
    with _state_lock:
        if kind == "HIT":
            _state["hits"] += 1
        else:
            _state["misses"] += 1
        _state["events"].appendleft(
            {
                "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "kind": kind,
                "key": key,
                "value": value,
                "elapsed_ms": round(elapsed_ms, 3),
            }
        )


# ---------------------------------------------------------------------------
# Cache-aside worker (unchanged behaviour vs the previous version).
# ---------------------------------------------------------------------------


def slow_compute(key: str) -> str:
    """Pretend this is an expensive computation or remote lookup.

    We sleep for SLOW seconds and then return a short hex digest derived from
    the key. The sleep is the whole point: it's what makes the cache pay off.
    """
    time.sleep(SLOW)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def connect_with_retry(retries: int = 30, delay: float = 1.0) -> valkey.Valkey:
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            client = valkey.Valkey.from_url(VALKEY_URL, decode_responses=True)
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
    raise RuntimeError(f"valkey at {VALKEY_URL} never became reachable: {last_err}")


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


def worker_loop(client: valkey.Valkey) -> None:
    while True:
        key = random.choice(KEYS)
        try:
            value, kind, elapsed = get_or_compute(client, key)
        except ValkeyConnectionError as e:
            with _state_lock:
                _state["last_error"] = str(e)
            print(f"[error] {e}", flush=True)
            time.sleep(TICK)
            continue
        _record(kind, key, value, elapsed * 1000)
        with _state_lock:
            total = _state["hits"] + _state["misses"]
            hit_rate = (_state["hits"] / total) * 100 if total else 0.0
            hits, misses = _state["hits"], _state["misses"]
        print(
            f"[{kind:<4}] key={key:<8} value={value} "
            f"in {elapsed * 1000:7.2f} ms  "
            f"(hits={hits} misses={misses} hit_rate={hit_rate:5.1f}%)",
            flush=True,
        )
        time.sleep(TICK)


# ---------------------------------------------------------------------------
# HTTP layer.
# ---------------------------------------------------------------------------


def _snapshot(client: valkey.Valkey) -> dict[str, Any]:
    # Live-query Valkey for the demo:hash:* keys + TTLs so the UI shows the
    # cache state as it actually exists in the server, not just what we think
    # we wrote.
    cache: list[dict[str, Any]] = []
    try:
        for raw in client.scan_iter(match=f"{CACHE_PREFIX}*", count=100):
            ttl = client.ttl(raw)
            val = client.get(raw)
            cache.append(
                {
                    "key": raw.removeprefix(CACHE_PREFIX),
                    "value": val,
                    "ttl": int(ttl) if ttl is not None else None,
                }
            )
        cache.sort(key=lambda r: r["key"])
        live_error = None
    except ValkeyConnectionError as e:
        live_error = str(e)

    with _state_lock:
        total = _state["hits"] + _state["misses"]
        return {
            "config": {
                "url": VALKEY_URL,
                "ttl_seconds": TTL,
                "tick_seconds": TICK,
                "slow_compute_seconds": SLOW,
                "keys": KEYS,
            },
            "stats": {
                "hits": _state["hits"],
                "misses": _state["misses"],
                "total": total,
                "hit_rate": (_state["hits"] / total) if total else 0.0,
            },
            "events": list(_state["events"]),
            "cache": cache,
            "last_error": live_error or _state["last_error"],
        }


def make_handler(client: valkey.Valkey) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, ctype: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - http.server contract
            if self.path == "/" or self.path.startswith("/?"):
                self._send(200, "text/html; charset=utf-8", INDEX_HTML)
            elif self.path == "/healthz":
                self._send(200, "text/plain; charset=utf-8", b"ok\n")
            elif self.path == "/api/state":
                body = json.dumps(_snapshot(client)).encode("utf-8")
                self._send(200, "application/json", body)
            else:
                self._send(404, "text/plain; charset=utf-8", b"not found\n")

        def do_POST(self) -> None:  # noqa: N802 - http.server contract
            if self.path == "/api/flush":
                try:
                    deleted = 0
                    for raw in client.scan_iter(match=f"{CACHE_PREFIX}*", count=100):
                        deleted += client.delete(raw)
                    body = json.dumps({"deleted": deleted}).encode("utf-8")
                    self._send(200, "application/json", body)
                except ValkeyConnectionError as e:
                    body = json.dumps({"error": str(e)}).encode("utf-8")
                    self._send(503, "application/json", body)
            else:
                self._send(404, "text/plain; charset=utf-8", b"not found\n")

        def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
            # Quiet the default per-request stderr log; the worker loop is the
            # interesting log channel for this demo.
            return

    return Handler


def main() -> None:
    print(
        f"[boot] valkey={VALKEY_URL} ttl={TTL}s "
        f"tick={TICK}s slow_compute={SLOW}s keys={KEYS} http_port={HTTP_PORT}",
        flush=True,
    )
    client = connect_with_retry()

    worker = threading.Thread(target=worker_loop, args=(client,), daemon=True)
    worker.start()

    server = ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), make_handler(client))
    print(f"[http] listening on 0.0.0.0:{HTTP_PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

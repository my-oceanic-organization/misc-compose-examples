"""Minimal Kafka consumer: subscribe to a topic and record each message into
shared in-process state. A built-in web UI (single static HTML page) shows the
last N messages, per-partition counters, and the consumer's connection config.

The HTTP layer exists so this demo can be shown end-to-end through a single
PaaS HTTP route without anyone having to ``docker logs`` or shell in.

Configuration via env vars (defaults are compose-friendly):
  KAFKA_BOOTSTRAP_SERVERS  default: kafka:19092
  KAFKA_TOPIC              default: demo
  KAFKA_GROUP_ID           default: demo-group
  KAFKA_AUTO_OFFSET_RESET  default: earliest
  HTTP_PORT                default: 8000

mTLS over SSL is supported out of the box. When the platform substitutes the
in-compose broker for a managed service it injects:
  KAFKA_SECURITY_PROTOCOL  e.g. SSL
  KAFKA_CA_CERT            CA certificate (inline PEM)
  KAFKA_ACCESS_CERT        client certificate (inline PEM)
  KAFKA_ACCESS_KEY         client private key (inline PEM)
  KAFKA_API_VERSION        optional, e.g. 2.6.0
"""

from __future__ import annotations

import atexit
import json
import os
import tempfile
import threading
import time
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from kafka import KafkaConsumer
from kafka.errors import KafkaError

BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:19092")
TOPIC = os.environ.get("KAFKA_TOPIC", "demo")
GROUP_ID = os.environ.get("KAFKA_GROUP_ID", "demo-group")
AUTO_OFFSET_RESET = os.environ.get("KAFKA_AUTO_OFFSET_RESET", "earliest")
SECURITY_PROTOCOL = os.environ.get("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT").upper()
HTTP_PORT = int(os.environ.get("HTTP_PORT", "8000"))

INDEX_HTML = (Path(__file__).parent / "index.html").read_bytes()

# ---------------------------------------------------------------------------
# Shared state.
# ---------------------------------------------------------------------------

_state_lock = threading.Lock()
_state: dict[str, Any] = {
    "connected": False,
    "count": 0,
    "by_partition": {},   # partition -> {"count": int, "last_offset": int}
    "events": deque(maxlen=50),
    "last_error": None,
}


def _record(partition: int, offset: int, value: Any) -> None:
    with _state_lock:
        _state["count"] += 1
        part = _state["by_partition"].setdefault(
            partition, {"count": 0, "last_offset": -1}
        )
        part["count"] += 1
        part["last_offset"] = offset
        _state["events"].appendleft(
            {
                "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "partition": partition,
                "offset": offset,
                "value": value,
            }
        )


# ---------------------------------------------------------------------------
# Kafka consumer thread.
# ---------------------------------------------------------------------------


def _materialize_pem(label: str, pem: str) -> str:
    # Managed Kafka providers hand us the CA / client cert / key as inline PEM
    # strings, but kafka-python wants file paths: write each to a temp file.
    fd, path = tempfile.mkstemp(prefix=f"kafka-{label}-", suffix=".pem")
    with os.fdopen(fd, "w") as fh:
        fh.write(pem)
    atexit.register(lambda p=path: os.path.exists(p) and os.remove(p))
    return path


def security_kwargs() -> dict[str, object]:
    # Local compose talks PLAINTEXT to the in-network broker; nothing to add.
    if SECURITY_PROTOCOL == "PLAINTEXT":
        return {}
    kwargs: dict[str, object] = {"security_protocol": SECURITY_PROTOCOL}
    for env_name, kw in (
        ("KAFKA_CA_CERT", "ssl_cafile"),
        ("KAFKA_ACCESS_CERT", "ssl_certfile"),
        ("KAFKA_ACCESS_KEY", "ssl_keyfile"),
    ):
        pem = os.environ.get(env_name)
        if pem:
            kwargs[kw] = _materialize_pem(env_name.lower(), pem)
    # kafka-python's broker-version auto-probe is unreliable over TLS and
    # raises UnrecognizedBrokerVersion (dpkp/kafka-python#1796); pin it.
    version = os.environ.get("KAFKA_API_VERSION", "2.6.0")
    kwargs["api_version"] = tuple(int(p) for p in version.split("."))
    return kwargs


def connect(retries: int = 30, delay: float = 2.0) -> KafkaConsumer:
    # depends_on: service_healthy should make this loop unnecessary under
    # compose, but keep it so the consumer is also runnable standalone.
    # Catch KafkaError broadly (not just NoBrokersAvailable): a misconfigured
    # TLS/mTLS connection surfaces as UnrecognizedBrokerVersion.
    extra = security_kwargs()
    last_error: KafkaError | None = None
    for attempt in range(1, retries + 1):
        try:
            return KafkaConsumer(
                TOPIC,
                bootstrap_servers=BOOTSTRAP,
                group_id=GROUP_ID,
                auto_offset_reset=AUTO_OFFSET_RESET,
                enable_auto_commit=True,
                value_deserializer=lambda b: json.loads(b.decode("utf-8")),
                **extra,
            )
        except KafkaError as e:
            last_error = e
            print(
                f"[wait] kafka not reachable yet "
                f"({type(e).__name__}; attempt {attempt}/{retries})",
                flush=True,
            )
            time.sleep(delay)
    raise RuntimeError(
        f"kafka at {BOOTSTRAP} never became reachable: {last_error}"
    )


def consume_loop() -> None:
    try:
        consumer = connect()
    except Exception as e:  # noqa: BLE001
        with _state_lock:
            _state["last_error"] = str(e)
        print(f"[error] {e}", flush=True)
        return
    with _state_lock:
        _state["connected"] = True
    for record in consumer:
        _record(record.partition, record.offset, record.value)
        print(
            f"[consume] partition={record.partition} "
            f"offset={record.offset} value={record.value}",
            flush=True,
        )


# ---------------------------------------------------------------------------
# HTTP layer.
# ---------------------------------------------------------------------------


def _snapshot() -> dict[str, Any]:
    with _state_lock:
        return {
            "config": {
                "bootstrap": BOOTSTRAP,
                "topic": TOPIC,
                "group_id": GROUP_ID,
                "auto_offset_reset": AUTO_OFFSET_RESET,
                "security_protocol": SECURITY_PROTOCOL,
            },
            "connected": _state["connected"],
            "count": _state["count"],
            "by_partition": [
                {"partition": p, "count": d["count"], "last_offset": d["last_offset"]}
                for p, d in sorted(_state["by_partition"].items())
            ],
            "events": list(_state["events"]),
            "last_error": _state["last_error"],
        }


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
            body = json.dumps(_snapshot()).encode("utf-8")
            self._send(200, "application/json", body)
        else:
            self._send(404, "text/plain; charset=utf-8", b"not found\n")

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        return


def main() -> None:
    print(
        f"[boot] consumer bootstrap={BOOTSTRAP} topic={TOPIC} "
        f"group={GROUP_ID} offset_reset={AUTO_OFFSET_RESET} "
        f"security={SECURITY_PROTOCOL} http_port={HTTP_PORT}",
        flush=True,
    )

    worker = threading.Thread(target=consume_loop, daemon=True)
    worker.start()

    server = ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), Handler)
    print(f"[http] listening on 0.0.0.0:{HTTP_PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

"""Minimal Kafka producer: send a JSON message to a topic every few seconds.

Configuration via env vars (defaults are compose-friendly):
  KAFKA_BOOTSTRAP_SERVERS  default: kafka:19092
  KAFKA_TOPIC              default: demo
  PRODUCE_INTERVAL_SECONDS default: 2
  KAFKA_NUM_PARTITIONS     default: -1 (use broker default)
  KAFKA_REPLICATION_FACTOR default: -1 (use broker default)

The topic is created at startup if it doesn't exist, since managed brokers
usually disable auto.create.topics.enable.

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
import time
from datetime import datetime, timezone

from kafka import KafkaProducer
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import KafkaError, TopicAlreadyExistsError

BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:19092")
TOPIC = os.environ.get("KAFKA_TOPIC", "demo")
INTERVAL = float(os.environ.get("PRODUCE_INTERVAL_SECONDS", "2"))
SECURITY_PROTOCOL = os.environ.get("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT").upper()
# -1 means "use the broker default" (KIP-464): 1 partition / replica locally,
# whatever the managed cluster mandates (often replication factor >= 2/3).
NUM_PARTITIONS = int(os.environ.get("KAFKA_NUM_PARTITIONS", "-1"))
REPLICATION_FACTOR = int(os.environ.get("KAFKA_REPLICATION_FACTOR", "-1"))


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


def connect(extra: dict[str, object], retries: int = 30, delay: float = 2.0) -> KafkaProducer:
    # depends_on: service_healthy should make this loop unnecessary under
    # compose, but keep it so the producer is also runnable standalone.
    # Catch KafkaError broadly (not just NoBrokersAvailable): a misconfigured
    # TLS/mTLS connection surfaces as UnrecognizedBrokerVersion, and we want a
    # retry + clear message instead of an uncaught crash-loop.
    last_error: KafkaError | None = None
    for attempt in range(1, retries + 1):
        try:
            return KafkaProducer(
                bootstrap_servers=BOOTSTRAP,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
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


def ensure_topic(extra: dict[str, object]) -> None:
    # Managed brokers usually have auto.create.topics.enable=false, so the
    # first send() to a missing topic would block for max_block_ms and then
    # fail. Create it up front (best-effort: a restricted user may not be
    # allowed to, in which case the topic is expected to pre-exist).
    try:
        admin = KafkaAdminClient(bootstrap_servers=BOOTSTRAP, **extra)
    except KafkaError as e:
        print(f"[topic] admin unavailable, skipping ensure ({type(e).__name__})", flush=True)
        return
    try:
        admin.create_topics(
            [NewTopic(TOPIC, num_partitions=NUM_PARTITIONS, replication_factor=REPLICATION_FACTOR)]
        )
        print(f"[topic] created {TOPIC!r}", flush=True)
    except TopicAlreadyExistsError:
        print(f"[topic] {TOPIC!r} already exists", flush=True)
    except KafkaError as e:
        print(f"[topic] could not create {TOPIC!r} ({type(e).__name__}: {e}); continuing", flush=True)
    finally:
        admin.close()


def main() -> None:
    print(
        f"[boot] producer bootstrap={BOOTSTRAP} topic={TOPIC} "
        f"interval={INTERVAL}s security={SECURITY_PROTOCOL}",
        flush=True,
    )
    extra = security_kwargs()
    producer = connect(extra)
    ensure_topic(extra)
    n = 0
    while True:
        msg = {"n": n, "ts": datetime.now(timezone.utc).isoformat()}
        try:
            producer.send(TOPIC, value=msg)
            producer.flush()
            print(f"[produce] -> {msg}", flush=True)
            n += 1
        except KafkaError as e:
            # Log instead of crashing so a transient hiccup doesn't turn into a
            # restart loop (which hides the actual error on most platforms).
            print(f"[error] produce failed ({type(e).__name__}: {e})", flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()

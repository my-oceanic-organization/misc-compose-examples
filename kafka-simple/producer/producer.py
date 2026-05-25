"""Minimal Kafka producer: send a JSON message to a topic every few seconds.

Configuration via env vars (defaults are compose-friendly):
  KAFKA_BOOTSTRAP_SERVERS  default: kafka:19092
  KAFKA_TOPIC              default: demo
  PRODUCE_INTERVAL_SECONDS default: 2
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:19092")
TOPIC = os.environ.get("KAFKA_TOPIC", "demo")
INTERVAL = float(os.environ.get("PRODUCE_INTERVAL_SECONDS", "2"))


def connect(retries: int = 30, delay: float = 2.0) -> KafkaProducer:
    # depends_on: service_healthy should make this loop unnecessary under
    # compose, but keep it so the producer is also runnable standalone.
    for attempt in range(1, retries + 1):
        try:
            return KafkaProducer(
                bootstrap_servers=BOOTSTRAP,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
        except NoBrokersAvailable:
            print(
                f"[wait] kafka not reachable yet (attempt {attempt}/{retries})",
                flush=True,
            )
            time.sleep(delay)
    raise RuntimeError(f"kafka at {BOOTSTRAP} never became reachable")


def main() -> None:
    print(
        f"[boot] producer bootstrap={BOOTSTRAP} topic={TOPIC} interval={INTERVAL}s",
        flush=True,
    )
    producer = connect()
    n = 0
    while True:
        msg = {"n": n, "ts": datetime.now(timezone.utc).isoformat()}
        producer.send(TOPIC, value=msg)
        producer.flush()
        print(f"[produce] -> {msg}", flush=True)
        n += 1
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()

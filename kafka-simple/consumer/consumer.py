"""Minimal Kafka consumer: subscribe to a topic and print each message.

Configuration via env vars (defaults are compose-friendly):
  KAFKA_BOOTSTRAP_SERVERS  default: kafka:19092
  KAFKA_TOPIC              default: demo
  KAFKA_GROUP_ID           default: demo-group
  KAFKA_AUTO_OFFSET_RESET  default: earliest
"""

from __future__ import annotations

import json
import os
import time

from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable

BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:19092")
TOPIC = os.environ.get("KAFKA_TOPIC", "demo")
GROUP_ID = os.environ.get("KAFKA_GROUP_ID", "demo-group")
AUTO_OFFSET_RESET = os.environ.get("KAFKA_AUTO_OFFSET_RESET", "earliest")


def connect(retries: int = 30, delay: float = 2.0) -> KafkaConsumer:
    # depends_on: service_healthy should make this loop unnecessary under
    # compose, but keep it so the consumer is also runnable standalone.
    for attempt in range(1, retries + 1):
        try:
            return KafkaConsumer(
                TOPIC,
                bootstrap_servers=BOOTSTRAP,
                group_id=GROUP_ID,
                auto_offset_reset=AUTO_OFFSET_RESET,
                enable_auto_commit=True,
                value_deserializer=lambda b: json.loads(b.decode("utf-8")),
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
        f"[boot] consumer bootstrap={BOOTSTRAP} topic={TOPIC} "
        f"group={GROUP_ID} offset_reset={AUTO_OFFSET_RESET}",
        flush=True,
    )
    consumer = connect()
    for record in consumer:
        print(
            f"[consume] partition={record.partition} "
            f"offset={record.offset} value={record.value}",
            flush=True,
        )


if __name__ == "__main__":
    main()

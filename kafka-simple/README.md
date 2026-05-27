# kafka-simple

Minimal compose example: an `apache/kafka` broker (KRaft, single-node) plus two
tiny Python apps built from in-repo `Containerfile`s — a **producer** that
publishes a JSON message every couple of seconds and a **consumer** that
subscribes to the same topic. The consumer also exposes a tiny built-in web UI
at <http://localhost:8000> with the last N messages, per-partition counters,
and the connection config. The UI exists so the demo can be shown end-to-end
through a single HTTP route (handy on PaaS platforms) without anyone having to
`docker logs` or shell in.

The point is to have a single `docker compose up` that shows Kafka working
end-to-end with the fewest moving parts possible.

## Layout

```
kafka-simple/
├── docker-compose.yml
├── README.md
├── producer/
│   ├── Containerfile
│   ├── producer.py
│   └── requirements.txt
└── consumer/
    ├── Containerfile
    ├── consumer.py        # consumes + serves a stdlib HTTP UI
    ├── index.html         # single-page UI for the demo
    └── requirements.txt
```

## Run

From this directory:

```bash
podman compose up --build
# or: docker compose up --build
```

Then open <http://localhost:8000> for the consumer's web UI (counts, the last
N messages, per-partition stats). You should also see interleaved log output
like:

```
kafka-simple-producer  | [boot] producer bootstrap=kafka:19092 topic=demo interval=2.0s
kafka-simple-consumer  | [boot] consumer bootstrap=kafka:19092 topic=demo group=demo-group offset_reset=earliest
kafka-simple-producer  | [produce] -> {'n': 0, 'ts': '2026-05-26T...+00:00'}
kafka-simple-consumer  | [consume] partition=0 offset=0 value={'n': 0, 'ts': '2026-05-26T...+00:00'}
kafka-simple-producer  | [produce] -> {'n': 1, 'ts': '...'}
kafka-simple-consumer  | [consume] partition=0 offset=1 value={'n': 1, 'ts': '...'}
```

Stop with Ctrl-C, then clean up:

```bash
podman compose down
```

## Poke at it from the host

The broker also exposes a `PLAINTEXT_HOST` listener on `localhost:9092`, so you
can use any Kafka client (e.g. `kcat`) from the host:

```bash
kcat -b localhost:9092 -t demo -C -o beginning -q
```

Or shell into the broker and use the bundled CLI:

```bash
podman exec -it kafka-simple-broker \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:19092 --topic demo --from-beginning
```

## Configuration

Producer env vars (defaults shown):

| Variable                   | Default       |
| -------------------------- | ------------- |
| `KAFKA_BOOTSTRAP_SERVERS`  | `kafka:19092` |
| `KAFKA_TOPIC`              | `demo`        |
| `PRODUCE_INTERVAL_SECONDS` | `2`           |

Consumer env vars (defaults shown):

| Variable                  | Default       |
| ------------------------- | ------------- |
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka:19092` |
| `KAFKA_TOPIC`             | `demo`        |
| `KAFKA_GROUP_ID`          | `demo-group`  |
| `KAFKA_AUTO_OFFSET_RESET` | `earliest`    |
| `HTTP_PORT`               | `8000`        |

## Notes

- The broker runs in **KRaft mode** (no ZooKeeper) as a single combined
  broker+controller node — fine for demos, not for anything real.
- Producer and consumer are completely independent containers; you can scale
  the consumer with `docker compose up --scale consumer=3` to see Kafka's
  consumer-group partition assignment in action (with the default single
  partition only one replica will actually receive messages — try setting
  `KAFKA_NUM_PARTITIONS` or pre-creating the topic with more partitions).
- `depends_on: condition: service_healthy` makes both apps wait for the
  broker's health check; each app also has a small reconnect loop so it works
  standalone.
- `Containerfile` (not `Dockerfile`) is used to match the rest of this repo;
  `docker-compose.yml` points at it explicitly via `build.dockerfile`.

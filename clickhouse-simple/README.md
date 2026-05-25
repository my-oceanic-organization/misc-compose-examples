# clickhouse-simple

Minimal compose example: the public `clickhouse/clickhouse-server` image plus a
tiny in-repo Python app that continuously inserts synthetic events into a
`MergeTree` table and prints a `GROUP BY` aggregation over the last minute. The
"canonical" ClickHouse demo: fast columnar ingest + analytical aggregations.

## Layout

```
clickhouse-simple/
├── README.md
├── docker-compose.yml      # clickhouse (image) + app (build)
└── app/
    ├── Containerfile       # python:3.12-alpine + clickhouse-connect
    ├── requirements.txt
    └── app.py              # insert loop + report loop
```

## Run

```bash
cd clickhouse-simple
podman compose up --build
# or: docker compose up --build
```

You should see, within ~15s:

```
clickhouse-simple-app  | [boot] clickhouse=clickhouse:8123 db=default ...
clickhouse-simple-app  | [schema] table 'events' ready
clickhouse-simple-app  | [insert] +50 rows
clickhouse-simple-app  | [insert] +50 rows
clickhouse-simple-app  | [report] last 60s by event_type:
clickhouse-simple-app  |   click      n=152    avg_value=48.13   unique_users=78
clickhouse-simple-app  |   purchase   n=147    avg_value=51.02   unique_users=80
clickhouse-simple-app  |   signup     n=151    avg_value=49.87   unique_users=80
clickhouse-simple-app  |   view       n=150    avg_value=50.41   unique_users=82
```

Tear down:

```bash
podman compose down
```

## Poke at the data from the host

The HTTP interface (`8123`) and native TCP (`9000`) are both exposed.

```bash
# HTTP, ad-hoc query:
curl 'http://localhost:8123/?query=SELECT+count()+FROM+events'

# Native client (if you have clickhouse-client installed locally):
clickhouse-client --query 'SELECT event_type, count() FROM events GROUP BY event_type'
```

Or open a shell in the server container:

```bash
podman exec -it clickhouse-simple-server clickhouse-client
```

## Notes

- No volumes are mounted: data is wiped on `down`, which is what you want for
  a repeatable demo.
- `depends_on: condition: service_healthy` plus a `clickhouse-client SELECT 1`
  healthcheck means the app only starts once the server is actually serving
  queries — no flaky startup races.
- The app also has an internal retry loop so it's runnable standalone against
  any reachable ClickHouse (set `CLICKHOUSE_HOST` / `CLICKHOUSE_PORT`).

# valkey-simple

Minimal compose example: the public `valkey/valkey:8-alpine` image plus a tiny
in-repo Python app that demonstrates the **cache-aside** pattern with zero
external dependencies. A deliberately-slow pure-Python function
(`time.sleep(SLOW)` + a SHA-256 digest) is cached in Valkey with a short TTL,
and a forever-loop picks random keys and prints a `HIT` or `MISS` line for
each lookup so the caching behaviour is obvious from the container logs.

## Layout

```
valkey-simple/
├── README.md
├── docker-compose.yml      # valkey (image) + app (build)
└── app/
    ├── Containerfile       # python:3.12-alpine + valkey-py
    ├── requirements.txt
    └── app.py              # cache-aside loop, no external APIs
```

## Run

```bash
cd valkey-simple
podman compose up --build
# or: docker compose up --build
```

You should see, within a few seconds, output like:

```
valkey-simple-app  | [boot] valkey=valkey:6379 ttl=10s tick=1s slow_compute=2s keys=[...]
valkey-simple-app  | [MISS] key=delta    value=8d4f3e... in 2002.41 ms  (hits=0 misses=1 hit_rate=  0.0%)
valkey-simple-app  | [MISS] key=alpha    value=2c26b46... in 2001.88 ms  (hits=0 misses=2 hit_rate=  0.0%)
valkey-simple-app  | [HIT ] key=delta    value=8d4f3e... in    0.41 ms  (hits=1 misses=2 hit_rate= 33.3%)
valkey-simple-app  | [HIT ] key=alpha    value=2c26b46... in    0.32 ms  (hits=2 misses=2 hit_rate= 50.0%)
...
valkey-simple-app  | [MISS] key=alpha    value=2c26b46... in 2002.10 ms  (hits=N misses=N+1 ...)   # TTL expired
```

The `MISS` lines take ~`SLOW_COMPUTE_SECONDS` (~2s by default) because the
slow function runs; the `HIT` lines complete in well under 1ms because the
value comes straight from Valkey. After `CACHE_TTL_SECONDS` (10s by default)
entries expire and you get another `MISS` for that key.

Tear down:

```bash
podman compose down
```

## Poke at the cache from the host

Valkey is exposed on the standard port `6379`. With `valkey-cli` (or `redis-cli`,
since the wire protocol is identical) installed on the host:

```bash
valkey-cli -h localhost -p 6379 KEYS 'demo:hash:*'
valkey-cli -h localhost -p 6379 GET demo:hash:alpha
valkey-cli -h localhost -p 6379 TTL demo:hash:alpha
```

Or open a shell in the server container:

```bash
docker exec -it valkey-simple-server valkey-cli
```

Try `FLUSHALL` while the app is running -- the next tick for every key will be
a `MISS`, then everything goes back to `HIT`s. Fun.

## Configuration

The app reads these env vars (defaults shown):

| Variable                | Default  |
| ----------------------- | -------- |
| `VALKEY_HOST`           | `valkey` |
| `VALKEY_PORT`           | `6379`   |
| `CACHE_TTL_SECONDS`     | `10`     |
| `TICK_INTERVAL_SECONDS` | `1`      |
| `SLOW_COMPUTE_SECONDS`  | `2`      |

## Notes

- No volumes are mounted: data is wiped on `down`, which is what you want for
  a repeatable demo.
- No external network calls of any kind -- the only "slow thing" is a
  `time.sleep` inside a pure-Python function, so the demo is completely
  self-contained.
- `depends_on: condition: service_healthy` plus a `valkey-cli ping` health
  check means the app only starts once Valkey is actually responding.
- `app.py` also has a small reconnect loop so it's runnable standalone
  against any reachable Valkey/Redis (set `VALKEY_HOST` / `VALKEY_PORT`).
- `Containerfile` (not `Dockerfile`) is used to match the rest of this repo;
  `docker-compose.yml` points at it explicitly via `build.dockerfile`.

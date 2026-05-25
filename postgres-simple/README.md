# postgres-simple

Minimal compose example: the public `postgres:17-alpine` image plus a tiny
in-repo Python app that, at container start, **populates** a `fruits` table
and then serves a one-page web "site" rendered straight from those rows --
hand-styled as a faithful homage to Tim Berners-Lee's
[first web page](https://info.cern.ch/hypertext/WWW/TheProject.html)
(no DOCTYPE, no CSS, capital tags, plain hyperlinked text).

## Layout

```
postgres-simple/
├── README.md
├── docker-compose.yml      # postgres (image) + app (build)
└── app/
    ├── Containerfile       # python:3.12-slim + psycopg[binary]
    ├── requirements.txt
    ├── seed.py             # runs once at start; creates+fills `fruits`
    └── app.py              # stdlib HTTP server that reads `fruits` live
```

## Run

```bash
cd postgres-simple
podman compose up --build
# or: docker compose up --build
```

You should see, within a few seconds:

```
postgres-simple-app  | [seed] connecting to postgres:5432/demo as demo
postgres-simple-app  | [seed] loaded 10 fruits
postgres-simple-app  | [boot] postgres=postgres:5432/demo as demo serving on 0.0.0.0:8000
```

Then open <http://localhost:8000> in a browser. You'll get something that
looks like it was written in 1990:

```
THE FRUIT DATABASE

The FruitDataBase is a small hyperlinked catalogue of fruits, served
directly from a PostgreSQL table and rendered in the spirit of the
first web page.

Pick a fruit:
  * Apple
  * Banana
  * Cherry
  ...
```

Each name is a hyperlink to a per-fruit detail page (`/fruits/<id>`), which
is also fetched live from Postgres on every request.

Tear down:

```bash
podman compose down
```

## Poke at the data from the host

Postgres is exposed on the standard port `5432`:

```bash
psql -h localhost -U demo -d demo -c 'SELECT * FROM fruits ORDER BY calories DESC'
# password: demo
```

Or open a shell in the database container:

```bash
podman exec -it postgres-simple-db psql -U demo -d demo
```

## Configuration

The app reads these env vars (defaults shown):

| Variable            | Default     |
| ------------------- | ----------- |
| `POSTGRES_HOST`     | `postgres`  |
| `POSTGRES_PORT`     | `5432`      |
| `POSTGRES_DB`       | `demo`      |
| `POSTGRES_USER`     | `demo`      |
| `POSTGRES_PASSWORD` | `demo`      |
| `HTTP_PORT`         | `8000`      |

## Notes

- The seeding is wired directly into the container's `CMD`:
  `sh -c "python -u seed.py && python -u app.py"`. Restarting the container
  always re-seeds, so the demo is repeatable.
- No volumes are mounted: data is wiped on `down`, which is what you want
  for a repeatable demo.
- `depends_on: condition: service_healthy` plus a `pg_isready` healthcheck
  means the app only starts once Postgres is actually accepting connections.
- `seed.py` also has a small reconnect loop so it works standalone against
  any reachable Postgres (set `POSTGRES_HOST` / `POSTGRES_PORT`).
- `Containerfile` (not `Dockerfile`) is used to match the rest of this repo;
  `docker-compose.yml` points at it explicitly via `build.dockerfile`.

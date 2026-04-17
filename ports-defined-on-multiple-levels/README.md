# ports-defined-on-multiple-levels

A minimal docker/podman compose example to test out different ways to set up ports.
Each service just runs `tail -f /dev/null` on Alpine so it builds and starts quickly without doing anything useful.

## Layout

- `with-expose/Dockerfile` — declares `EXPOSE 3000`
- `without-expose/Dockerfile` — no `EXPOSE` directive
- `docker-compose.yml` — 6 services covering all permutations

## Permutations

| # | Dockerfile `EXPOSE` | Compose override                  | Service name                                   |
|---|---------------------|-----------------------------------|------------------------------------------------|
| 1 | 3000                | none                              | `case1-dockerfile-expose-only`                 |
| 2 | 3000                | `expose: ["1234"]`                | `case2-dockerfile-expose-compose-expose`       |
| 3 | 3000                | `ports: ["2345:3456"]`            | `case3-dockerfile-expose-compose-ports`        |
| 4 | —                   | none                              | `case4-no-expose-no-override`                  |
| 5 | —                   | `expose: ["4567"]`                | `case5-no-expose-compose-expose`               |
| 6 | —                   | `ports: ["5678:6789"]`            | `case6-no-expose-compose-ports`                |

## Usage

```bash
# Build all images
podman compose build
# or: docker compose build

# Start everything detached
podman compose up -d
# or: docker compose up -d

# Tear down
podman compose down
```

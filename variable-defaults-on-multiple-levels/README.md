# variable-defaults-on-multiple-levels

## Layout

- `app/Containerfile` — the app, carrying every env var style
- `docker-compose.yml` — two services, one plain and one overriding everything

## Env vars

In `app/Containerfile`, where the only mechanisms available without `ARG` are an
overridable `ENV` and a shell expansion in `CMD`:

| Style | Example |
|---|---|
| Hardcoded | `ENV APP_NAME="variable-defaults-on-multiple-levels"` |
| Default, overridable | `ENV GREETING="hello from a Containerfile ENV default"` |
| Declared, no usable value | `ENV TENANT_ID=""` |
| In-line default, unset or empty | `${LOG_LEVEL:-info}` in `CMD` |
| In-line default, unset only | `${REGION-eu-north-1}` in `CMD` |
| No default at all | `$TRACE_ID` in `CMD`, never declared |

`LOG_LEVEL`, `REGION` and `TRACE_ID` are never declared with `ENV`. Their only
mention in the whole image is that expansion, which is worth knowing whether the
scanner picks up.

In `docker-compose.yml`, on the `app-with-overrides` service:

| Style | Example |
|---|---|
| Hardcoded | `GREETING: "hello from a hardcoded compose value"` |
| Default, unset or empty | `LOG_LEVEL: "${LOG_LEVEL:-debug}"` |
| Default, unset only | `REGION: "${REGION-eu-west-1}"` |
| No default, declared required | `TENANT_ID: "${TENANT_ID:?tenant id has no default anywhere}"` |
| No default, silently empty | `TRACE_ID: "${TRACE_ID}"` |

## Ports

| Style | Where |
|---|---|
| Default via `ENV` | `ENV APP_PORT=8080` + `EXPOSE ${APP_PORT}` in the Containerfile |
| Default on both sides | `"${HOST_PORT:-18080}:${APP_PORT:-8080}"` on `app` |
| No default on the host side | `"${HOST_PORT_REQUIRED}:8080"` on `app-with-overrides` |
| Hardcoded | the container side of that same mapping, `8080` |

## Image tags

A `FROM` line cannot be varied without an `ARG`, so the Containerfile pins
`alpine:3.23` outright. The remaining place a tag can vary is the `image:` key,
which — because both services also have a `build:` — names the image being built
rather than one to pull:

| Style | Example |
|---|---|
| Hardcoded | `FROM alpine:3.23`, and `image: "variable-defaults-app-with-overrides:hardcoded"` |
| Default | `image: "variable-defaults-app:${APP_TAG:-dev}"` |

## Services

| Service | Port | Variables |
|---|---|---|
| `app` | 18080 | nothing overridden, so every value comes from the Containerfile |
| `app-with-overrides` | 18081 | every compose-side syntax layered on top |

## Usage

`TENANT_ID` is checked when the file is parsed rather than when its service
starts, so every compose command needs it — including ones that touch only the
`app` service:

```bash
export TENANT_ID=acme
export HOST_PORT_REQUIRED=18081

podman compose up --build
# or: docker compose up --build

podman compose down
```

`HOST_PORT`, `APP_PORT`, `APP_TAG`, `LOG_LEVEL`, `REGION`, `GREETING` and
`TRACE_ID` are all optional — exporting them overrides a fallback rather than
supplying a missing value.

Then read back what each service resolved to:

```bash
curl localhost:18080   # app
curl localhost:18081   # app-with-overrides
```

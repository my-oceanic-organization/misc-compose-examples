# very-fast-app

A minimal Alpine-based container that serves a single static page on port 3000 using `busybox httpd`. No packages beyond `busybox-extras` (for the `httpd` applet) and `tini` (so Ctrl-C works), no compilation, builds in seconds.

## Build & run

Podman needs `-f Containerfile` because the file isn't named `Dockerfile`. Pick whichever invocation matches where your shell is.

### From inside `very-fast-app/`

```bash
podman build -f Containerfile -t very-fast-app .
podman run --rm -p 3000:3000 very-fast-app
```

### From the repo root

```bash
podman build -f very-fast-app/Containerfile -t very-fast-app very-fast-app
podman run --rm -p 3000:3000 very-fast-app
```

In another terminal:

```bash
curl localhost:3000
# Hello from very-fast-app
```

Ctrl-C in the `podman run` terminal cleanly stops the container.

## Via compose

A minimal `docker-compose.yml` is included so this example also fits the repo's compose theme. It points at `Containerfile` explicitly via `build.dockerfile`.

```bash
podman compose up --build
# or: docker compose up --build

podman compose down
```


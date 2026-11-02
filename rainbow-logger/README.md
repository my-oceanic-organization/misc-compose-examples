# rainbow-logger

A minimal Alpine container that keeps printing every ANSI color code to stdout, for testing how log output handles colors. Each round prints the 16 basic foreground colors (codes 30-37 and 90-97) in plain and bold, followed by a one-line rainbow. It then prints two 256-color (`38;5;N`) gradients of `█` blocks, one around the hue wheel and one through the grayscale ramp, then sleeps `INTERVAL` seconds (default 2).

The script also runs once during the image build, so build log rendering can be tested too.

## Build & run

```bash
podman build -f Containerfile -t rainbow-logger .
podman run --rm rainbow-logger
```

With Docker BuildKit, step output is collapsed by default. Use `--progress=plain` (and `--no-cache` to force the step to rerun) to see the build-time colors:

```bash
docker build --progress=plain --no-cache -f Containerfile -t rainbow-logger .
```

## Via compose

```bash
podman compose up --build
# or: docker compose up --build
```

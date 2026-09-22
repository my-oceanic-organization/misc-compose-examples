# nginx-simple

The smallest useful compose example in this repo: the public
`nginx:1.27-alpine` image serving a static `hello world` page out of a
bind-mounted directory. Unlike the other examples here there is **no build
step and no app code** — just an image, a port, and a volume.

It also doubles as a fixture for testing what happens when a user points
Aiven at an image it knows nothing about. `nginx` is not one of Aiven's
managed service images (unlike the `kafka`, `postgres`, `valkey`,
`opensearch` and `clickhouse` examples next door), so this is the minimal
"unknown image" case: a valid, popular, entirely ordinary image that no
service mapping will match.

## Layout

```
nginx-simple/
├── README.md
├── docker-compose.yml      # nginx (image only)
└── site/
    └── index.html          # <h1>hello world</h1>
```

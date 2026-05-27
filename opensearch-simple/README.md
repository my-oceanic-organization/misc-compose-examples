# opensearch-simple

Minimal compose example: the public `opensearchproject/opensearch:2` image
(single-node, security plugin off) plus a tiny in-repo Python app that
bulk-indexes a handful of book documents and then loops forever running a
different query (`match`, `term`, `range`, `match_all`) every few seconds and
recording the hits.

The app also serves a tiny built-in web UI at <http://localhost:8000> with the
indexed books, the rolling background searches, and an input box for ad-hoc
`match title:…` queries. The UI exists so the demo can be shown end-to-end
through a single HTTP route (handy on PaaS platforms) without anyone having
to `docker logs` or shell in.

## Run

```bash
cd opensearch-simple
podman compose up --build
# or: docker compose up --build
```

Then open <http://localhost:8000>. You should see, within ~20s of startup,
log output like:

```
opensearch-simple-app  | [boot] url=http://opensearch:9200 index=demo interval=3.0s http_port=8000
opensearch-simple-app  | [index] created 'demo'
opensearch-simple-app  | [index] bulk-loaded 7 books (errors=[])
opensearch-simple-app  | [http] listening on 0.0.0.0:8000
opensearch-simple-app  | [search] match title:wind -> total=1 returned=1
opensearch-simple-app  |     score=1.2450573  'The Name of the Wind' by Patrick Rothfuss (2007)
opensearch-simple-app  | [search] term tags:cyberpunk -> total=2 returned=2
opensearch-simple-app  |     score=1.4021543  'Neuromancer' by William Gibson (1984)
opensearch-simple-app  |     score=1.4021543  'Snow Crash' by Neal Stephenson (1992)
```

OpenSearch itself is also reachable from the host on <http://localhost:9200>.

Tear down:

```bash
podman compose down
```

## Configuration

The app reads these env vars (defaults shown):

| Variable                  | Default                    |
| ------------------------- | -------------------------- |
| `OPENSEARCH_URL`          | `http://opensearch:9200`   |
| `OPENSEARCH_INDEX`        | `demo`                     |
| `SEARCH_INTERVAL_SECONDS` | `3`                        |
| `HTTP_PORT`               | `8000`                     |

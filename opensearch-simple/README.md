# opensearch-simple

Minimal compose example: the public `opensearchproject/opensearch:2` image
(single-node, security plugin off) plus a tiny in-repo Python app that
bulk-indexes a handful of book documents and then loops forever running a
different query (`match`, `term`, `range`, `match_all`) every few seconds and
printing the hits.

## Run

```bash
cd opensearch-simple
podman compose up --build
# or: docker compose up --build
```

You should see, within ~20s:

```
opensearch-simple-app  | [boot] url=http://opensearch:9200 index=demo interval=3.0s
opensearch-simple-app  | [index] created 'demo'
opensearch-simple-app  | [index] bulk-loaded 7 books (errors=[])
opensearch-simple-app  | [search] match title:wind -> total=1 returned=1
opensearch-simple-app  |     score=1.2450573  'The Name of the Wind' by Patrick Rothfuss (2007)
opensearch-simple-app  | [search] term tags:cyberpunk -> total=2 returned=2
opensearch-simple-app  |     score=1.4021543  'Neuromancer' by William Gibson (1984)
opensearch-simple-app  |     score=1.4021543  'Snow Crash' by Neal Stephenson (1992)
```

OpenSearch is also reachable from the host on <http://localhost:9200>.

Tear down:

```bash
podman compose down
```

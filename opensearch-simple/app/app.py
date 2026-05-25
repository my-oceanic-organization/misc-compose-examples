"""Minimal OpenSearch demo: bulk-index a handful of book documents, then loop
forever running a different search query every few seconds and printing the
hits, all in one process.

Configuration is via env vars (with safe defaults for use under compose):
  OPENSEARCH_URL           default: http://opensearch:9200
  OPENSEARCH_INDEX         default: demo
  SEARCH_INTERVAL_SECONDS  default: 3
"""

from __future__ import annotations

import itertools
import os
import time
from typing import Any

from opensearchpy import OpenSearch
from opensearchpy.exceptions import ConnectionError as OSConnectionError
from opensearchpy.exceptions import TransportError
from opensearchpy.helpers import bulk

URL = os.environ.get("OPENSEARCH_URL", "http://opensearch:9200")
INDEX = os.environ.get("OPENSEARCH_INDEX", "demo")
INTERVAL = float(os.environ.get("SEARCH_INTERVAL_SECONDS", "3"))

BOOKS: list[dict[str, Any]] = [
    {"title": "The Hobbit", "author": "J.R.R. Tolkien", "year": 1937, "tags": ["fantasy", "classic"]},
    {"title": "The Lord of the Rings", "author": "J.R.R. Tolkien", "year": 1954, "tags": ["fantasy", "classic"]},
    {"title": "Dune", "author": "Frank Herbert", "year": 1965, "tags": ["sci-fi", "classic"]},
    {"title": "Neuromancer", "author": "William Gibson", "year": 1984, "tags": ["sci-fi", "cyberpunk"]},
    {"title": "Snow Crash", "author": "Neal Stephenson", "year": 1992, "tags": ["sci-fi", "cyberpunk"]},
    {"title": "The Name of the Wind", "author": "Patrick Rothfuss", "year": 2007, "tags": ["fantasy"]},
    {"title": "Project Hail Mary", "author": "Andy Weir", "year": 2021, "tags": ["sci-fi"]},
]

INDEX_BODY: dict[str, Any] = {
    "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
    "mappings": {
        "properties": {
            "title": {"type": "text"},
            "author": {"type": "keyword"},
            "year": {"type": "integer"},
            "tags": {"type": "keyword"},
        }
    },
}


def wait_for_opensearch(client: OpenSearch, retries: int = 30, delay: float = 2.0) -> None:
    # depends_on: service_healthy should make this unnecessary, but keep a
    # short retry loop so the app is also runnable standalone.
    for attempt in range(1, retries + 1):
        try:
            if client.ping():
                return
        except (OSConnectionError, TransportError):
            pass
        print(f"[wait] opensearch not reachable yet (attempt {attempt}/{retries})", flush=True)
        time.sleep(delay)
    raise RuntimeError(f"opensearch at {URL} never became reachable")


def ensure_index(client: OpenSearch) -> None:
    if client.indices.exists(index=INDEX):
        client.indices.delete(index=INDEX)
    client.indices.create(index=INDEX, body=INDEX_BODY)
    print(f"[index] created {INDEX!r}", flush=True)


def load_books(client: OpenSearch) -> None:
    actions = [{"_index": INDEX, "_id": str(i), "_source": b} for i, b in enumerate(BOOKS)]
    success, errors = bulk(client, actions, refresh="wait_for")
    print(f"[index] bulk-loaded {success} books (errors={errors})", flush=True)


def search_loop(client: OpenSearch) -> None:
    queries: list[tuple[str, dict[str, Any]]] = [
        ("match title:wind", {"query": {"match": {"title": "wind"}}}),
        ("term tags:cyberpunk", {"query": {"term": {"tags": "cyberpunk"}}}),
        ("range year>=2000", {"query": {"range": {"year": {"gte": 2000}}}}),
        ("term author:'J.R.R. Tolkien'", {"query": {"term": {"author": "J.R.R. Tolkien"}}}),
        ("match_all", {"query": {"match_all": {}}, "size": 3}),
    ]
    for label, body in itertools.cycle(queries):
        res = client.search(index=INDEX, body=body)
        hits = res["hits"]["hits"]
        total = res["hits"]["total"]["value"]
        print(f"[search] {label} -> total={total} returned={len(hits)}", flush=True)
        for h in hits:
            src = h["_source"]
            print(
                f"    score={h['_score']!s:>5}  "
                f"{src['title']!r} by {src['author']} ({src['year']})",
                flush=True,
            )
        time.sleep(INTERVAL)


def main() -> None:
    print(f"[boot] url={URL} index={INDEX} interval={INTERVAL}s", flush=True)
    client = OpenSearch(hosts=[URL], http_compress=True)
    wait_for_opensearch(client)
    ensure_index(client)
    load_books(client)
    search_loop(client)


if __name__ == "__main__":
    main()

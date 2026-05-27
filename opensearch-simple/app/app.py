"""Minimal OpenSearch demo: bulk-index a handful of book documents, then loop
forever running a different search query every few seconds and recording the
hits. A built-in web UI (single static HTML page) exposes the rotating
searches, the indexed corpus, and lets you try your own ad-hoc match query.

The HTTP layer exists so this demo can be shown end-to-end through a single
PaaS HTTP route without anyone having to ``docker logs`` or shell in.

Configuration is via env vars (with safe defaults for use under compose):
  OPENSEARCH_URL           default: http://opensearch:9200
  OPENSEARCH_INDEX         default: demo
  SEARCH_INTERVAL_SECONDS  default: 3
  HTTP_PORT                default: 8000
"""

from __future__ import annotations

import itertools
import json
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from opensearchpy import OpenSearch
from opensearchpy.exceptions import ConnectionError as OSConnectionError
from opensearchpy.exceptions import TransportError
from opensearchpy.helpers import bulk

URL = os.environ.get("OPENSEARCH_URL", "http://opensearch:9200")
INDEX = os.environ.get("OPENSEARCH_INDEX", "demo")
INTERVAL = float(os.environ.get("SEARCH_INTERVAL_SECONDS", "3"))
HTTP_PORT = int(os.environ.get("HTTP_PORT", "8000"))

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

QUERIES: list[tuple[str, dict[str, Any]]] = [
    ("match title:wind", {"query": {"match": {"title": "wind"}}}),
    ("term tags:cyberpunk", {"query": {"term": {"tags": "cyberpunk"}}}),
    ("range year>=2000", {"query": {"range": {"year": {"gte": 2000}}}}),
    ("term author:'J.R.R. Tolkien'", {"query": {"term": {"author": "J.R.R. Tolkien"}}}),
    ("match_all", {"query": {"match_all": {}}, "size": 3}),
]

INDEX_HTML = (Path(__file__).parent / "index.html").read_bytes()

# ---------------------------------------------------------------------------
# Shared state.
# ---------------------------------------------------------------------------

_state_lock = threading.Lock()
_state: dict[str, Any] = {
    "ready": False,
    "search_count": 0,
    "events": deque(maxlen=20),
    "last_error": None,
}


def _record_search(label: str, took_ms: int, total: int, hits: list[dict[str, Any]]) -> None:
    with _state_lock:
        _state["search_count"] += 1
        _state["events"].appendleft(
            {
                "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "label": label,
                "took_ms": took_ms,
                "total": total,
                "hits": [
                    {
                        "score": h.get("_score"),
                        "title": h["_source"].get("title"),
                        "author": h["_source"].get("author"),
                        "year": h["_source"].get("year"),
                        "tags": h["_source"].get("tags", []),
                    }
                    for h in hits
                ],
            }
        )


# ---------------------------------------------------------------------------
# OpenSearch helpers (unchanged behaviour vs the previous version).
# ---------------------------------------------------------------------------


def wait_for_opensearch(client: OpenSearch, retries: int = 30, delay: float = 2.0) -> None:
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
    for label, body in itertools.cycle(QUERIES):
        try:
            res = client.search(index=INDEX, body=body)
        except (OSConnectionError, TransportError) as e:
            with _state_lock:
                _state["last_error"] = str(e)
            print(f"[error] {e}", flush=True)
            time.sleep(INTERVAL)
            continue
        hits = res["hits"]["hits"]
        total = res["hits"]["total"]["value"]
        _record_search(label, res.get("took", 0), total, hits)
        print(f"[search] {label} -> total={total} returned={len(hits)}", flush=True)
        for h in hits:
            src = h["_source"]
            print(
                f"    score={h['_score']!s:>5}  "
                f"{src['title']!r} by {src['author']} ({src['year']})",
                flush=True,
            )
        time.sleep(INTERVAL)


# ---------------------------------------------------------------------------
# HTTP layer.
# ---------------------------------------------------------------------------


def _snapshot(client: OpenSearch) -> dict[str, Any]:
    doc_count: int | None
    try:
        doc_count = client.count(index=INDEX).get("count")
        live_error = None
    except (OSConnectionError, TransportError) as e:
        doc_count = None
        live_error = str(e)

    with _state_lock:
        return {
            "config": {
                "url": URL,
                "index": INDEX,
                "interval_seconds": INTERVAL,
            },
            "ready": _state["ready"],
            "doc_count": doc_count,
            "search_count": _state["search_count"],
            "books": BOOKS,
            "events": list(_state["events"]),
            "last_error": live_error or _state["last_error"],
        }


def _run_query(client: OpenSearch, q: str) -> dict[str, Any]:
    q = q.strip()
    body: dict[str, Any]
    label: str
    if q:
        body = {"query": {"match": {"title": q}}, "size": 10}
        label = f"match title:{q}"
    else:
        body = {"query": {"match_all": {}}, "size": 10}
        label = "match_all"
    res = client.search(index=INDEX, body=body)
    hits = res["hits"]["hits"]
    return {
        "label": label,
        "took_ms": res.get("took", 0),
        "total": res["hits"]["total"]["value"],
        "hits": [
            {
                "score": h.get("_score"),
                "title": h["_source"].get("title"),
                "author": h["_source"].get("author"),
                "year": h["_source"].get("year"),
                "tags": h["_source"].get("tags", []),
            }
            for h in hits
        ],
    }


def make_handler(client: OpenSearch) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, ctype: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - http.server contract
            parts = urlsplit(self.path)
            if parts.path == "/":
                self._send(200, "text/html; charset=utf-8", INDEX_HTML)
            elif parts.path == "/healthz":
                self._send(200, "text/plain; charset=utf-8", b"ok\n")
            elif parts.path == "/api/state":
                body = json.dumps(_snapshot(client)).encode("utf-8")
                self._send(200, "application/json", body)
            elif parts.path == "/api/search":
                qs = parse_qs(parts.query)
                q = qs.get("q", [""])[0]
                try:
                    result = _run_query(client, q)
                    self._send(200, "application/json", json.dumps(result).encode("utf-8"))
                except (OSConnectionError, TransportError) as e:
                    body = json.dumps({"error": str(e)}).encode("utf-8")
                    self._send(503, "application/json", body)
            else:
                self._send(404, "text/plain; charset=utf-8", b"not found\n")

        def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
            return

    return Handler


def main() -> None:
    print(
        f"[boot] url={URL} index={INDEX} interval={INTERVAL}s http_port={HTTP_PORT}",
        flush=True,
    )
    client = OpenSearch(hosts=[URL], http_compress=True)
    wait_for_opensearch(client)
    ensure_index(client)
    load_books(client)
    with _state_lock:
        _state["ready"] = True

    worker = threading.Thread(target=search_loop, args=(client,), daemon=True)
    worker.start()

    server = ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), make_handler(client))
    print(f"[http] listening on 0.0.0.0:{HTTP_PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

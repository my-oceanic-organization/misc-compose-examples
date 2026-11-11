"""Small app used three ways from compose, depending on which URLs are set:

  app_underscore  PG_URL only      talks to Postgres at my_service
  app-hyphen      VALKEY_URL only  talks to Valkey at my-service
  app_both        both

Each tick writes a row to Postgres and/or increments a Valkey counter, then
serves a one-page view of what this process can see.

Configuration is via env vars:
  APP_NAME               default: app
  PG_URL                 unset means this process does not use Postgres
  VALKEY_URL             unset means this process does not use Valkey
  TICK_INTERVAL_SECONDS  default: 2
  HTTP_PORT              default: 8000
"""

from __future__ import annotations

import html
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

import psycopg
import valkey
from valkey.exceptions import ConnectionError as ValkeyConnectionError

APP_NAME = os.environ.get("APP_NAME", "app")
PG_URL = os.environ.get("PG_URL", "").strip()
VALKEY_URL = os.environ.get("VALKEY_URL", "").strip()
TICK = float(os.environ.get("TICK_INTERVAL_SECONDS", "2"))
HTTP_PORT = int(os.environ.get("HTTP_PORT", "8000"))

_state_lock = threading.Lock()
_state: dict[str, Any] = {
    "pg_count": None,
    "vk_count": None,
    "last_error": None,
    "events": deque(maxlen=20),
}


def _redacted_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url)
    if parts.password:
        netloc = parts.netloc.replace(f":{parts.password}@", ":***@", 1)
        return parts._replace(netloc=netloc).geturl()
    return url


def _host(url: str) -> str:
    if not url:
        return ""
    return urlsplit(url).hostname or url


def _record(backend: str, detail: str) -> None:
    with _state_lock:
        _state["events"].appendleft(
            {
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "backend": backend,
                "detail": detail,
            }
        )


def connect_postgres(retries: int = 30, delay: float = 1.0) -> psycopg.Connection:
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            conn = psycopg.connect(PG_URL)
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ticks (
                        id      bigserial PRIMARY KEY,
                        source  text NOT NULL,
                        seen_at timestamptz NOT NULL DEFAULT now()
                    )
                    """
                )
            return conn
        except psycopg.Error as e:
            last_err = e
            print(
                f"[wait] postgres not reachable yet "
                f"(attempt {attempt}/{retries}): {e}",
                flush=True,
            )
            time.sleep(delay)
    raise RuntimeError(
        f"postgres at {_redacted_url(PG_URL)} never became reachable: {last_err}"
    )


def connect_valkey(retries: int = 30, delay: float = 1.0) -> valkey.Valkey:
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            client = valkey.Valkey.from_url(VALKEY_URL, decode_responses=True)
            client.ping()
            return client
        except ValkeyConnectionError as e:
            last_err = e
            print(
                f"[wait] valkey not reachable yet "
                f"(attempt {attempt}/{retries}): {e}",
                flush=True,
            )
            time.sleep(delay)
    raise RuntimeError(
        f"valkey at {_redacted_url(VALKEY_URL)} never became reachable: {last_err}"
    )


def tick_postgres(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO ticks (source) VALUES (%s)", (APP_NAME,))
        cur.execute("SELECT count(*) FROM ticks WHERE source = %s", (APP_NAME,))
        count = int(cur.fetchone()[0])
    with _state_lock:
        _state["pg_count"] = count
        _state["last_error"] = None
    _record("postgres", f"{_host(PG_URL)} count={count}")
    print(f"[postgres] host={_host(PG_URL)} source={APP_NAME} count={count}", flush=True)


def tick_valkey(client: valkey.Valkey) -> None:
    key = f"demo:ticks:{APP_NAME}"
    count = int(client.incr(key))
    with _state_lock:
        _state["vk_count"] = count
        _state["last_error"] = None
    _record("valkey", f"{_host(VALKEY_URL)} count={count}")
    print(f"[valkey] host={_host(VALKEY_URL)} key={key} count={count}", flush=True)


def worker_loop(conn: psycopg.Connection | None, client: valkey.Valkey | None) -> None:
    while True:
        try:
            if conn is not None:
                tick_postgres(conn)
            if client is not None:
                tick_valkey(client)
        except (psycopg.Error, ValkeyConnectionError) as e:
            with _state_lock:
                _state["last_error"] = str(e)
            print(f"[error] {e}", flush=True)
        time.sleep(TICK)


def render() -> str:
    with _state_lock:
        pg_count = _state["pg_count"]
        vk_count = _state["vk_count"]
        last_error = _state["last_error"]
        events = list(_state["events"])

    def row(label: str, configured: bool, host: str, count: int | None) -> str:
        if not configured:
            detail = "not configured"
        elif count is None:
            detail = f"{html.escape(host)} (waiting)"
        else:
            detail = f"{html.escape(host)} count={count}"
        return f"<TR><TD>{label}</TD><TD>{detail}</TD></TR>"

    event_rows = "\n".join(
        "<TR><TD>{ts}</TD><TD>{backend}</TD><TD>{detail}</TD></TR>".format(
            ts=html.escape(event["ts"]),
            backend=html.escape(event["backend"]),
            detail=html.escape(event["detail"]),
        )
        for event in events
    ) or "<TR><TD COLSPAN=3>no ticks yet</TD></TR>"
    error = (
        f"<P>Last error: <CODE>{html.escape(last_error)}</CODE></P>"
        if last_error
        else ""
    )
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="2">
<title>{html.escape(APP_NAME)}</title>
</head>
<body>
<h1>{html.escape(APP_NAME)}</h1>
<p>This process talks to whichever of the conflicting service names it was given.</p>
<table border="1" cellpadding="4">
{row("postgres", bool(PG_URL), _host(PG_URL), pg_count)}
{row("valkey", bool(VALKEY_URL), _host(VALKEY_URL), vk_count)}
</table>
{error}
<h2>Recent ticks</h2>
<table border="1" cellpadding="4">
<TR><TH>time</TH><TH>backend</TH><TH>detail</TH></TR>
{event_rows}
</table>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _write(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (stdlib API)
        path = urlsplit(self.path).path
        if path in ("/", "/index.html"):
            self._write(200, render().encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/healthz":
            self._write(200, b"ok\n", "text/plain; charset=utf-8")
            return
        self._write(404, b"not found\n", "text/plain; charset=utf-8")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return


def main() -> None:
    if not PG_URL and not VALKEY_URL:
        raise SystemExit("set PG_URL and/or VALKEY_URL")

    print(
        f"[boot] app={APP_NAME} "
        f"postgres={_redacted_url(PG_URL) or '-'} "
        f"valkey={_redacted_url(VALKEY_URL) or '-'} "
        f"serving on 0.0.0.0:{HTTP_PORT}",
        flush=True,
    )
    conn = connect_postgres() if PG_URL else None
    client = connect_valkey() if VALKEY_URL else None

    worker = threading.Thread(target=worker_loop, args=(conn, client), daemon=True)
    worker.start()

    server = ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), Handler)
    print(f"[http] listening on 0.0.0.0:{HTTP_PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

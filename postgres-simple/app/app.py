"""Minimal Postgres demo: a stdlib HTTP server that, on every request, reads
rows from the `fruits` table and renders them as a Tim-Berners-Lee-vintage
HTML page (no doctype, no CSS, capital tags, plain hyperlinked text).

Pair with seed.py, which populates the table at container start.

Configuration is via env vars (with safe defaults for use under compose):
  PG_URL     default: postgresql://demo:demo@postgres:5432/demo
  HTTP_PORT  default: 8000
"""

from __future__ import annotations

import html
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import psycopg

PG_URL = os.environ.get("PG_URL", "postgresql://demo:demo@postgres:5432/demo")

HTTP_PORT = int(os.environ.get("HTTP_PORT", "8000"))


def fetch_fruits() -> list[tuple[int, str, str, int]]:
    with psycopg.connect(PG_URL) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, description, calories FROM fruits ORDER BY name"
        )
        return cur.fetchall()


def fetch_fruit(fruit_id: int) -> tuple[int, str, str, int] | None:
    with psycopg.connect(PG_URL) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, description, calories FROM fruits WHERE id = %s",
            (fruit_id,),
        )
        return cur.fetchone()


def render_index(fruits: list[tuple[int, str, str, int]]) -> str:
    items = "\n".join(
        f'<LI><A HREF="/fruits/{fid}">{html.escape(name)}</A>'
        for fid, name, _desc, _cals in fruits
    )
    return f"""<HEADER>
<TITLE>The Fruit Database</TITLE>
<NEXTID N="1">
</HEADER>
<BODY>
<H1>The Fruit Database</H1>
The FruitDataBase is a small hyperlinked catalogue of fruits, served
directly from a <A HREF="https://www.postgresql.org/">PostgreSQL</A>
table and rendered in the spirit of the
<A HREF="https://info.cern.ch/hypertext/WWW/TheProject.html">first web page</A>.
<P>
Pick a fruit:
<UL>
{items}
</UL>
<P>
See also: <A HREF="/about">About this page</A>.
</BODY>
"""


def render_fruit(fruit: tuple[int, str, str, int]) -> str:
    _fid, name, desc, cals = fruit
    return f"""<HEADER>
<TITLE>{html.escape(name)} -- The Fruit Database</TITLE>
</HEADER>
<BODY>
<H1>{html.escape(name)}</H1>
{html.escape(desc)}
<P>
Approximately <B>{cals}</B> kcal per 100 g.
<P>
<A HREF="/">Back to the index</A>.
</BODY>
"""


def render_about() -> str:
    return """<HEADER>
<TITLE>About -- The Fruit Database</TITLE>
</HEADER>
<BODY>
<H1>About</H1>
This page is part of the <CODE>postgres-simple</CODE> compose example.
The HTML is intentionally pre-HTML 2.0 in style: no DOCTYPE, no CSS, no
JavaScript, capital tags, and only the elements one might have used in
late 1990 -- only the data is fetched live from Postgres on every request.
<P>
<A HREF="/">Back to the index</A>.
</BODY>
"""


def render_not_found(path: str) -> str:
    return f"""<HEADER>
<TITLE>Not Found</TITLE>
</HEADER>
<BODY>
<H1>Not Found</H1>
No document exists at <CODE>{html.escape(path)}</CODE>.
<P>
<A HREF="/">Back to the index</A>.
</BODY>
"""


class Handler(BaseHTTPRequestHandler):
    def _write(self, status: int, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802 (stdlib API)
        path = urlsplit(self.path).path
        try:
            if path in ("/", "/index.html"):
                self._write(200, render_index(fetch_fruits()))
                return
            if path == "/about":
                self._write(200, render_about())
                return
            if path.startswith("/fruits/"):
                try:
                    fruit_id = int(path[len("/fruits/"):])
                except ValueError:
                    self._write(404, render_not_found(path))
                    return
                fruit = fetch_fruit(fruit_id)
                if fruit is None:
                    self._write(404, render_not_found(path))
                    return
                self._write(200, render_fruit(fruit))
                return
            self._write(404, render_not_found(path))
        except psycopg.Error as e:
            self._write(
                500,
                f"<H1>Database Error</H1><PRE>{html.escape(str(e))}</PRE>",
            )

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        print(f"[http] {self.address_string()} - {format % args}", flush=True)


def _redacted_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.password:
        netloc = parts.netloc.replace(f":{parts.password}@", ":***@", 1)
        return parts._replace(netloc=netloc).geturl()
    return url


def main() -> None:
    print(
        f"[boot] postgres={_redacted_url(PG_URL)} "
        f"serving on 0.0.0.0:{HTTP_PORT}",
        flush=True,
    )
    server = ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()

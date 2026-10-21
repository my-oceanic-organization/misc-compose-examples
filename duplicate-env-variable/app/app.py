"""Small app that shows which env var values the process actually received.

It is used twice from compose, each service defining the same variables more
than once (inside `environment:`, or across `env_file` and `environment:`).

Configuration is via env vars:
  APP_NAME   default: app
  GREETING   default: unset
  LOG_LEVEL  default: unset
  REGION     default: unset
  HTTP_PORT  default: 8000
"""

from __future__ import annotations

import html
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP_NAME = os.environ.get("APP_NAME", "app")
HTTP_PORT = int(os.environ.get("HTTP_PORT", "8000"))
VARS = ("GREETING", "LOG_LEVEL", "REGION")


def render() -> str:
    rows = "\n".join(
        "<TR><TD>{name}</TD><TD>{value}</TD></TR>".format(
            name=name,
            value=html.escape(os.environ.get(name) or "(unset)"),
        )
        for name in VARS
    )
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{html.escape(APP_NAME)}</title>
</head>
<body>
<h1>{html.escape(APP_NAME)}</h1>
<p>Values this process received after compose resolved the duplicates.</p>
<table border="1" cellpadding="4">
<tr><th>Variable</th><th>Value</th></tr>
{rows}
</table>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = render().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} {format % args}", flush=True)


def main() -> None:
    print(f"{APP_NAME} listening on :{HTTP_PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()

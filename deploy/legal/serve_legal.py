"""Serve the two public legal pages at exact paths (/privacy, /terms) with HTTP 200.

Static, read-only, bound to 127.0.0.1. No APEX application routes are touched.
"""
import argparse
import functools
import http.server
from pathlib import Path

PAGES = {"/privacy": "privacy/index.html", "/privacy/": "privacy/index.html",
         "/terms": "terms/index.html", "/terms/": "terms/index.html"}


class LegalHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        target = PAGES.get(self.path.split("?", 1)[0])
        if target is None:
            self.send_error(404, "Not found")
            return
        page = Path(self.directory) / target
        data = page.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_HEAD(self):
        self.do_GET()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True)
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    handler = functools.partial(LegalHandler, directory=args.directory)
    with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()

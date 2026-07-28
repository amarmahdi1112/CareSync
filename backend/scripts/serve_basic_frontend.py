"""Serve the sealed CareSync production frontend with SPA route fallback."""

from __future__ import annotations

import argparse
import functools
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


class SpaHandler(SimpleHTTPRequestHandler):
    """Serve real assets and fall back to index.html for client-side routes."""

    def send_head(self):  # type: ignore[no-untyped-def]
        requested = urlsplit(self.path).path
        translated = Path(self.translate_path(requested))
        if requested != "/" and not translated.exists():
            self.path = "/index.html"
        return super().send_head()

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5174)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    if root.is_symlink() or not root.is_dir() or not (root / "index.html").is_file():
        parser.error("frontend root must contain index.html")
    os.chdir(root)
    handler = functools.partial(SpaHandler, directory=str(root))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

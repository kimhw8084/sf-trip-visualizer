"""Serve the local map with HTTP byte ranges for PMTiles; no network dependency."""

import argparse
import mimetypes
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RangeHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        path = Path(self.translate_path(self.path))
        if not path.is_file():
            return super().send_head()
        requested = self.headers.get("Range", "")
        if not requested.startswith("bytes="):
            return super().send_head()
        try:
            start_text, end_text = requested[6:].split("-", 1)
            size = path.stat().st_size
            start = int(start_text)
            end = int(end_text) if end_text else size - 1
            if start < 0 or end < start or start >= size:
                raise ValueError
            end = min(end, size - 1)
        except ValueError:
            self.send_error(416, "Invalid byte range")
            return None
        file = path.open("rb")
        file.seek(start)
        self._range_remaining = end - start + 1
        self.send_response(206)
        self.send_header("Content-Type", mimetypes.guess_type(str(path))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(self._range_remaining))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        return file

    def copyfile(self, source, outputfile):
        remaining = getattr(self, "_range_remaining", None)
        if remaining is None:
            return super().copyfile(source, outputfile)
        while remaining:
            chunk = source.read(min(65536, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--directory", default=str(ROOT / ".build" / "modular"))
    args = parser.parse_args()
    directory = str(Path(args.directory).resolve())
    if not Path(directory).is_dir():
        raise SystemExit(f"Generated modular build is missing: {directory}; run scripts/pipeline.py fast first.")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(RangeHandler, directory=directory))
    print(f"Map ready at http://127.0.0.1:{args.port}/index.html from {directory}", flush=True)
    server.serve_forever()

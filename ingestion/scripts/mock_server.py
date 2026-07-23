"""Local stand-in for the Elexon API, for fast debug iteration.

Serves the same JSON as the test fixtures on every request, regardless
of path or query params -- it's not trying to be a faithful mock of the
whole API, just something verify_live_schema.py (or ElexonClient
pointed at --base-url http://127.0.0.1:8765) can hit without touching
the real network or waiting on a real day's data.

Usage (run from anywhere -- paths are resolved relative to this file,
not your current directory):

    python3 scripts/mock_server.py
    python3 scripts/mock_server.py --port 9000

Leave it running in a spare terminal, then point the VS Code
"verify_live_schema (against a local mock server)" launch config, or
`--base-url http://127.0.0.1:<port>`, at it.
"""

from __future__ import annotations

import argparse
import http.server
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures"


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (http.server's naming convention)
        if "system-prices" in self.path:
            fixture_name = "elexon_system_prices.json"
        elif "FUELHH" in self.path:
            fixture_name = "elexon_fuel_hh.json"
        else:
            self.send_response(404)
            self.end_headers()
            return

        body = (FIXTURES / fixture_name).read_text()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        # Quiet by default -- flip this to the default behaviour
        # (call super().log_message) if you want request logging.
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    server = http.server.HTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Mock Elexon server on http://127.0.0.1:{args.port} (Ctrl+C to stop)")
    print(f"Serving fixtures from {FIXTURES}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()

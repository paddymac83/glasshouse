"""Entry point for `glasshouse-api` -- runs the dev server via uvicorn."""

from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run("glasshouse_api.main:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()

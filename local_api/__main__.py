"""Local HTTP API for TradingAgents Report (OSS)."""

from __future__ import annotations

import argparse


def main() -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit(
            'The API extra is required: pip install ".[api]" '
            f"({type(exc).__name__}: {exc})"
        ) from exc

    parser = argparse.ArgumentParser(description="Self-hosted research HTTP API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run("local_api.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()

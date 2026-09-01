"""Local stdio MCP for TradingAgents Report (OSS)."""


def main() -> None:
    try:
        from mcp_server.server import run
    except ImportError as exc:
        raise SystemExit(
            'The MCP extra is required: pip install ".[mcp]" '
            f"({type(exc).__name__}: {exc})"
        ) from exc
    run()


if __name__ == "__main__":
    main()

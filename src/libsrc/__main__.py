import argparse
import logging

from libsrc.config import load_config

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(prog="libsrc", description="Library source code MCP server")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="Start the MCP server")
    serve_parser.add_argument(
        "--port", type=int, default=None,
        help="Port to listen on (overrides config file, default: 7890)",
    )

    subparsers.add_parser("cleanup", help="Run worktree cleanup")

    args = parser.parse_args()

    if args.command == "serve":
        from fastmcp.utilities.logging import configure_logging

        # Use FastMCP's rich logging for all loggers
        configure_logging(level="INFO", logger=logging.getLogger())
        logging.getLogger("httpx").setLevel(logging.WARNING)
        # Route uvicorn through root logger (rich handler) instead of its own
        for uv_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            uv_logger = logging.getLogger(uv_name)
            uv_logger.handlers.clear()
            uv_logger.propagate = True

        config = load_config()
        if args.port is not None:
            config.port = args.port

        # Run worktree cleanup on startup
        from libsrc.worktree_tracker import WorktreeTracker

        tracker = WorktreeTracker()
        removed = tracker.cleanup()
        if removed:
            logger.info("Startup cleanup: removed %d expired worktree(s)", len(removed))

        from libsrc.server import create_server

        server = create_server(config)
        try:
            server.run(
                transport="streamable-http",
                host=config.host,
                port=config.port,
                show_banner=False,
                uvicorn_config={
                    "log_config": None,  # prevent uvicorn from overriding our logging
                    "timeout_graceful_shutdown": 1,
                },
            )
        except KeyboardInterrupt:
            pass

    elif args.command == "cleanup":
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )

        from libsrc.worktree_tracker import WorktreeTracker

        tracker = WorktreeTracker()
        removed = tracker.cleanup()
        if removed:
            for p in removed:
                print(f"Removed: {p}")
            print(f"Cleaned up {len(removed)} worktree(s)")
        else:
            print("No expired worktrees to clean up")


if __name__ == "__main__":
    main()

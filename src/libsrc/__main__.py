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
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        logging.getLogger("httpx").setLevel(logging.WARNING)

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
        logger.info("Starting libsrc MCP server on http://%s:%d/mcp", config.host, config.port)
        server.run(transport="streamable-http", host=config.host, port=config.port, show_banner=False)

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

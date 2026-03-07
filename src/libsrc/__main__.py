import argparse

from libsrc.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser(prog="libsrc", description="Library source code MCP server")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("serve", help="Start the MCP server")
    subparsers.add_parser("cleanup", help="Run worktree cleanup")

    args = parser.parse_args()

    if args.command == "serve":
        config = load_config()
        from libsrc.server import create_server

        server = create_server(config)
        server.run(transport="streamable-http", host=config.host, port=config.port)

    elif args.command == "cleanup":
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

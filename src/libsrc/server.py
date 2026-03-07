from fastmcp import FastMCP

from libsrc.config import Config


def create_server(config: Config) -> FastMCP:
    mcp = FastMCP("libsrc")

    @mcp.tool
    def get_library_sources(
        project_dir: str,
        library_name: str | None = None,
        transitive: bool = False,
    ) -> str:
        """Resolve project dependencies and provide local source code paths for inspection.

        This tool auto-detects the build system (Maven, Gradle, Poetry, uv) by scanning
        files in the given project directory, resolves dependencies, and can clone and
        check out the source code of matching libraries.

        Args:
            project_dir: Absolute path to the project root directory.
            library_name: Optional substring filter. When omitted, returns the full
                dependency listing without cloning. When specified, performs a substring
                match against full library identifiers (e.g. "hibernate" matches
                "org.hibernate:hibernate-core:6.4.1") and clones/checks out matching
                libraries, returning local filesystem paths to their source code.
            transitive: Whether to include transitive dependencies. Defaults to False
                (direct dependencies only). The library_name filter applies to
                transitives as well when enabled.

        Returns:
            When library_name is omitted: a listing of all resolved dependencies.
            When library_name is specified: matched libraries with local worktree paths
            to their version-specific source code, or status messages if source could
            not be resolved.
        """
        return "Not yet implemented"

    return mcp

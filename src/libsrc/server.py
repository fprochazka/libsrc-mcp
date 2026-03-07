import logging
from pathlib import Path

from fastmcp import FastMCP

from libsrc.cache import DependencyCache
from libsrc.config import Config
from libsrc.ecosystems import Ecosystem, detect_ecosystems
from libsrc.git import GitManager
from libsrc.models import Dependency
from libsrc.source_resolver import SourceResolver
from libsrc.worktree_tracker import WorktreeTracker

logger = logging.getLogger(__name__)


def create_server(config: Config) -> FastMCP:
    mcp = FastMCP("libsrc")

    # Create shared instances (reused across all tool calls)
    dep_cache = DependencyCache()
    source_resolver = SourceResolver(config)
    git_manager = GitManager(config)
    worktree_tracker = WorktreeTracker()

    # NOTE: source_resolver._close() should ideally be called on server shutdown
    # to close the httpx client. FastMCP does not currently expose a shutdown hook,
    # so the client will be closed when the process exits.

    @mcp.tool
    async def get_library_sources(
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
        # 1. Validate project_dir
        project_path = Path(project_dir)
        if not project_path.exists():
            return f"Error: project directory does not exist: {project_dir}"
        if not project_path.is_dir():
            return f"Error: path is not a directory: {project_dir}"

        # 2. Detect ecosystems
        ecosystems = detect_ecosystems(project_path)
        if not ecosystems:
            return (
                f"No supported build system detected in {project_dir}.\n"
                "Supported: Maven (pom.xml), Gradle (build.gradle / build.gradle.kts), "
                "Poetry (pyproject.toml + poetry.lock), uv (pyproject.toml + uv.lock)."
            )

        # 3. For each ecosystem: discover build files, check cache, resolve deps
        all_deps: list[Dependency] = []
        deps_by_ecosystem: dict[str, list[Dependency]] = {}

        for ecosystem in ecosystems:
            eco_name = type(ecosystem).__name__.replace("Ecosystem", "").lower()
            try:
                build_files = ecosystem.discover_build_files(project_path)

                # Check cache
                cached = dep_cache.get(project_path, build_files)
                if cached is not None:
                    eco_deps = cached
                    logger.info("Using cached dependencies for %s (%s)", eco_name, project_dir)
                else:
                    # Resolve dependencies
                    eco_deps = await ecosystem.resolve_dependencies(project_path)
                    # Save to cache
                    dep_cache.put(project_path, build_files, eco_deps)
                    logger.info(
                        "Resolved %d dependencies for %s (%s)",
                        len(eco_deps), eco_name, project_dir,
                    )

                all_deps.extend(eco_deps)
                deps_by_ecosystem[eco_name] = eco_deps
            except Exception:
                logger.exception("Failed to resolve dependencies for %s", eco_name)
                deps_by_ecosystem[eco_name] = []

        # 4. If library_name is None: return listing
        if library_name is None:
            return _format_listing(deps_by_ecosystem, transitive)

        # 5. If library_name is specified: filter, resolve sources, clone
        return await _resolve_and_clone(
            all_deps, library_name, transitive,
            source_resolver, git_manager, worktree_tracker, config,
        )

    async def _resolve_and_clone(
        deps: list[Dependency],
        library_name: str,
        transitive: bool,
        resolver: SourceResolver,
        git: GitManager,
        tracker: WorktreeTracker,
        cfg: Config,
    ) -> str:
        """Filter deps by library_name, resolve sources, clone repos, create worktrees."""
        # Filter by transitive flag
        if not transitive:
            filtered = [d for d in deps if d.is_direct]
        else:
            filtered = list(deps)

        # Substring match on full identifier string
        matches = [
            d for d in filtered
            if library_name.lower() in f"{d.identifier}:{d.version}".lower()
        ]

        if not matches:
            if not transitive:
                return (
                    f"No dependencies matching '{library_name}' found among direct dependencies.\n"
                    "Tip: use transitive=True to also search transitive dependencies."
                )
            return f"No dependencies matching '{library_name}' found."

        # Deduplicate by (repo_url, version) to handle monorepos
        results: list[str] = []
        seen_worktrees: dict[str, Path] = {}  # (repo_url, version) -> worktree_path

        for dep in matches:
            dep_id = f"{dep.identifier}:{dep.version}"
            try:
                source = await resolver.resolve(dep)

                if source is None:
                    results.append(
                        f"{dep_id} -> Source repository not found. "
                        "Try searching for -sources.jar or inspecting .venv/ directory."
                    )
                    continue

                # Untrusted host warning
                warning = ""
                if not source.trusted:
                    warning = f" [WARNING: source hosted on untrusted host '{source.hosting}']"

                # Check if we already have a worktree for this repo+version
                cache_key = f"{source.repo_url}|{dep.version}"
                if cache_key in seen_worktrees:
                    worktree_path = seen_worktrees[cache_key]
                    results.append(f"{dep_id} -> {worktree_path}{warning}")
                    continue

                # Clone or fetch
                clone_path = await git.clone_or_fetch(source.repo_url)

                # Extract artifact_id for Maven/Gradle tag matching
                artifact_id: str | None = None
                if dep.ecosystem.lower() in ("maven", "gradle") and ":" in dep.identifier:
                    artifact_id = dep.identifier.split(":")[-1]

                # Create worktree
                worktree_path = await git.create_worktree(clone_path, dep.version, artifact_id)

                if worktree_path is not None:
                    tracker.touch(worktree_path)
                    seen_worktrees[cache_key] = worktree_path
                    results.append(f"{dep_id} -> {worktree_path}{warning}")
                else:
                    results.append(
                        f"{dep_id} -> Cloned to {clone_path} but no matching version tag found.{warning}"
                    )

            except Exception as e:
                logger.exception("Failed to resolve source for %s", dep_id)
                results.append(f"{dep_id} -> Error: {e}")

        return "\n".join(results)

    def _format_listing(deps_by_ecosystem: dict[str, list[Dependency]], transitive: bool) -> str:
        """Format the dependency listing when no library_name is specified."""
        lines: list[str] = []
        lines.append("No library name specified. Libraries will only be cloned when a name is provided.")
        lines.append(f"Detected ecosystem(s): {', '.join(deps_by_ecosystem.keys())}")
        lines.append("")

        for eco_name, eco_deps in deps_by_ecosystem.items():
            if not transitive:
                display_deps = [d for d in eco_deps if d.is_direct]
            else:
                display_deps = eco_deps

            lines.append(f"{eco_name} ({len(display_deps)} dependencies):")
            for dep in display_deps:
                lines.append(f"  {dep.identifier}:{dep.version}")

            if not display_deps:
                lines.append("  (none)")
            lines.append("")

        if not transitive:
            lines.append(
                "Note: only showing direct dependencies. "
                "Use transitive=True to include transitive dependencies."
            )

        return "\n".join(lines)

    return mcp

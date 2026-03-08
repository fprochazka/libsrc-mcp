import asyncio
import fcntl
import logging
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from libsrc.config import Config

logger = logging.getLogger(__name__)


class _FileLock:
    """Async context manager for file-based locking using fcntl.flock."""

    def __init__(self, lock_path: Path) -> None:
        self._lock_path = lock_path
        self._fd: int | None = None

    async def __aenter__(self) -> None:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = open(self._lock_path, "w")  # noqa: SIM115
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, fcntl.flock, self._fd.fileno(), fcntl.LOCK_EX)

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        if self._fd is not None:
            fcntl.flock(self._fd.fileno(), fcntl.LOCK_UN)
            self._fd.close()
            self._fd = None


class GitManager:
    """Handles cloning repos and creating version-specific worktrees."""

    def __init__(self, config: Config) -> None:
        self.config = config

    def _clone_path_for_url(self, repo_url: str) -> Path:
        """Derive the local clone path from a normalized https URL.

        repo_url is like https://github.com/owner/repo
        Returns: <config.output_dir>/<hostname>/<owner>/<repo>
        """
        parsed = urlparse(repo_url)
        host = parsed.hostname or "unknown"
        path_parts = [p for p in parsed.path.strip("/").split("/") if p]
        if len(path_parts) >= 2:
            owner, repo = path_parts[0], path_parts[1]
        else:
            # Fallback for unusual URLs
            owner = path_parts[0] if path_parts else "unknown"
            repo = "unknown"
        return self.config.output_dir / host / owner / repo

    async def clone_or_fetch(self, repo_url: str) -> Path:
        """Clone a repo or fetch if already cloned. Returns the clone path.

        repo_url is a normalized https URL like https://github.com/owner/repo.
        Clone target: <config.output_dir>/<hostname>/<owner>/<repo>

        Uses file-based locking to prevent concurrent operations on the same repo.
        """
        clone_path = self._clone_path_for_url(repo_url)
        lock_path = clone_path.parent / f"{clone_path.name}.lock"

        async with _FileLock(lock_path):
            if clone_path.is_dir() and (clone_path / ".git").exists():
                logger.info("Fetching updates for %s", repo_url)
                proc = await asyncio.create_subprocess_exec(
                    "git",
                    "-C",
                    str(clone_path),
                    "fetch",
                    "--all",
                    "--tags",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    logger.warning(
                        "git fetch failed for %s (rc=%d): %s",
                        clone_path,
                        proc.returncode,
                        stderr.decode().strip(),
                    )
            else:
                logger.info("Cloning %s into %s", repo_url, clone_path)
                clone_path.parent.mkdir(parents=True, exist_ok=True)
                proc = await asyncio.create_subprocess_exec(
                    "git",
                    "clone",
                    repo_url,
                    str(clone_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    msg = stderr.decode().strip()
                    logger.error(
                        "git clone failed for %s (rc=%d): %s",
                        repo_url,
                        proc.returncode,
                        msg,
                    )
                    raise RuntimeError(f"git clone failed: {msg}")

        return clone_path

    async def create_worktree(
        self, clone_path: Path, version: str, artifact_id: str | None = None
    ) -> Path | None:
        """Create a git worktree for a specific version. Returns worktree path.

        Worktree path: <clone_path>.versions/<version>
        If worktree already exists, just return the path.

        Returns None if no matching tag is found.
        """
        worktree_path = clone_path.parent / f"{clone_path.name}.versions" / version

        if worktree_path.is_dir():
            logger.debug("Worktree already exists: %s", worktree_path)
            return worktree_path

        tag = self._find_best_tag(clone_path, version, artifact_id)
        if tag is None:
            logger.warning(
                "No matching tag found for version %s in %s",
                version,
                clone_path,
            )
            return None

        lock_path = clone_path.parent / f"{clone_path.name}.lock"

        async with _FileLock(lock_path):
            # Re-check after acquiring lock (another process may have created it)
            if worktree_path.is_dir():
                return worktree_path

            worktree_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info("Creating worktree at %s for tag %s", worktree_path, tag)

            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                str(clone_path),
                "worktree",
                "add",
                "--detach",
                str(worktree_path),
                tag,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                msg = stderr.decode().strip()
                # Check if it failed because worktree already exists
                if "already exists" in msg.lower():
                    logger.debug("Worktree already exists (race): %s", worktree_path)
                    return worktree_path
                logger.error(
                    "git worktree add failed (rc=%d): %s",
                    proc.returncode,
                    msg,
                )
                return None

        return worktree_path

    # Well-known release qualifiers that some projects (e.g. Hibernate, Spring)
    # append to Maven/Gradle version strings but omit from git tags.
    _RELEASE_QUALIFIERS = (".Final", ".RELEASE", ".GA", "-Final", "-RELEASE", "-GA")

    def _find_best_tag(
        self, clone_path: Path, version: str, artifact_id: str | None = None
    ) -> str | None:
        """Find the best matching git tag for a version string.

        Check patterns in order (first with the original version, then with
        well-known release qualifiers like .Final / .RELEASE / .GA stripped):
        1. Exact: v{version}
        2. Exact: {version}
        3. Exact: release-{version}
        4. Exact: {artifact_id}-{version} (if artifact_id provided)
        5. Fuzzy: any tag ending with the version string
        6. Fuzzy: closest match containing the version string
        """
        try:
            result = subprocess.run(
                ["git", "-C", str(clone_path), "tag", "-l"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                logger.warning(
                    "git tag -l failed in %s: %s", clone_path, result.stderr.strip()
                )
                return None
        except FileNotFoundError:
            logger.error("git executable not found")
            return None

        all_tags = [t.strip() for t in result.stdout.splitlines() if t.strip()]
        if not all_tags:
            logger.debug("No tags found in %s", clone_path)
            return None

        # Build list of version strings to try: original first, then with
        # release qualifiers stripped (e.g. "6.6.39.Final" -> "6.6.39").
        versions_to_try = [version]
        for qualifier in self._RELEASE_QUALIFIERS:
            if version.endswith(qualifier):
                stripped = version[: -len(qualifier)]
                if stripped and stripped not in versions_to_try:
                    versions_to_try.append(stripped)

        tag_set = set(all_tags)

        for ver in versions_to_try:
            # 1-4: Exact matches in priority order
            exact_candidates = [
                f"v{ver}",
                ver,
                f"release-{ver}",
            ]
            if artifact_id:
                exact_candidates.append(f"{artifact_id}-{ver}")

            for candidate in exact_candidates:
                if candidate in tag_set:
                    logger.debug("Found exact tag match: %s", candidate)
                    return candidate

            # 5: Any tag ending with the version string
            suffix_matches = [t for t in all_tags if t.endswith(ver)]
            if suffix_matches:
                # Prefer shorter tags (closer match)
                suffix_matches.sort(key=len)
                logger.debug("Found suffix tag match: %s", suffix_matches[0])
                return suffix_matches[0]

            # 6: Any tag containing the version string
            contains_matches = [t for t in all_tags if ver in t]
            if contains_matches:
                # Prefer shorter tags (closer match)
                contains_matches.sort(key=len)
                logger.debug("Found contains tag match: %s", contains_matches[0])
                return contains_matches[0]

        return None

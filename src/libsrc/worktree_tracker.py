import json
import logging
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class WorktreeTracker:
    """Tracks last-access times for worktrees and handles cleanup."""

    def __init__(self) -> None:
        self._tracker_file = Path.home() / ".cache" / "libsrc" / "worktree-access.json"

    def touch(self, worktree_path: Path) -> None:
        """Update last-access timestamp for a worktree."""
        data = self._load()
        data[str(worktree_path)] = time.time()
        self._save(data)

    def cleanup(self, max_age_days: int = 7) -> list[Path]:
        """Remove worktrees not accessed for more than max_age_days.

        Returns list of removed worktree paths.
        For each expired worktree:
        1. Find the parent git repo (worktree_path is like <repo>.versions/<version>)
        2. Run: git -C <repo_path> worktree remove <worktree_path>
        3. Remove from tracker
        """
        data = self._load()
        if not data:
            return []

        now = time.time()
        max_age_seconds = max_age_days * 86400
        removed: list[Path] = []
        to_remove_keys: list[str] = []

        for path_str, timestamp in data.items():
            if now - timestamp > max_age_seconds:
                worktree_path = Path(path_str)
                to_remove_keys.append(path_str)
                removed.append(worktree_path)

                # Derive the repo path from the worktree path.
                # Worktree is at <repo>.versions/<version>, so the .versions dir
                # parent is the directory containing <repo>.versions/, and repo
                # is that name without .versions suffix.
                repo_path = self._repo_path_from_worktree(worktree_path)
                if repo_path is None:
                    logger.warning(
                        "Cannot determine repo path for worktree %s, skipping git removal",
                        worktree_path,
                    )
                    continue

                try:
                    result = subprocess.run(
                        [
                            "git",
                            "-C",
                            str(repo_path),
                            "worktree",
                            "remove",
                            "--force",
                            str(worktree_path),
                        ],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if result.returncode != 0:
                        logger.warning(
                            "git worktree remove failed for %s (rc=%d): %s",
                            worktree_path,
                            result.returncode,
                            result.stderr.strip(),
                        )
                except FileNotFoundError:
                    logger.error("git executable not found")

        # Remove expired entries from tracker regardless of git command success
        for key in to_remove_keys:
            data.pop(key, None)

        if to_remove_keys:
            self._save(data)

        return removed

    @staticmethod
    def _repo_path_from_worktree(worktree_path: Path) -> Path | None:
        """Derive the git repo clone path from a worktree path.

        Worktree path is like: <parent>/<repo>.versions/<version>
        Repo path is: <parent>/<repo>
        """
        versions_dir = worktree_path.parent  # <parent>/<repo>.versions
        versions_dir_name = versions_dir.name  # <repo>.versions
        if not versions_dir_name.endswith(".versions"):
            return None
        repo_name = versions_dir_name[: -len(".versions")]
        return versions_dir.parent / repo_name

    def _load(self) -> dict[str, float]:
        """Load tracker data: {path_str: timestamp}."""
        if not self._tracker_file.is_file():
            return {}
        try:
            return json.loads(self._tracker_file.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load worktree tracker: %s", e)
            return {}

    def _save(self, data: dict[str, float]) -> None:
        """Save tracker data."""
        try:
            self._tracker_file.parent.mkdir(parents=True, exist_ok=True)
            self._tracker_file.write_text(json.dumps(data, indent=2))
        except OSError as e:
            logger.warning("Failed to save worktree tracker: %s", e)

import hashlib
import json
import logging
from dataclasses import asdict
from pathlib import Path

from libsrc.models import Dependency

logger = logging.getLogger(__name__)


class DependencyCache:
    """Cache for resolved dependency lists, keyed by project dir and build file contents."""

    def __init__(self) -> None:
        self._cache_base = Path.home() / ".cache" / "libsrc" / "deps"

    def _cache_dir(self, project_dir: Path) -> Path:
        """Return the cache directory for a specific project."""
        resolved = str(project_dir.resolve())
        dir_hash = hashlib.sha256(resolved.encode()).hexdigest()
        dir_name = f"{dir_hash}-{project_dir.name}"
        return self._cache_base / dir_name

    def _content_hash(self, build_files: list[Path]) -> str:
        """Compute SHA256 hash of sorted concatenated build file contents."""
        hasher = hashlib.sha256()
        for path in sorted(build_files):
            try:
                hasher.update(path.read_bytes())
            except (OSError, IOError) as e:
                logger.warning("Failed to read %s for cache hash: %s", path, e)
        return hasher.hexdigest()

    def get(
        self, project_dir: Path, build_files: list[Path]
    ) -> list[Dependency] | None:
        """Load cached dependencies if available and valid."""
        if not build_files:
            return None

        cache_dir = self._cache_dir(project_dir)
        content_hash = self._content_hash(build_files)
        cache_file = cache_dir / f"{content_hash}.json"

        if not cache_file.is_file():
            return None

        try:
            data = json.loads(cache_file.read_text())
            return [
                Dependency(
                    ecosystem=d["ecosystem"],
                    identifier=d["identifier"],
                    version=d["version"],
                    scope=d.get("scope"),
                    is_direct=d.get("is_direct", True),
                )
                for d in data
            ]
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Failed to load cache file %s: %s", cache_file, e)
            return None

    def put(
        self, project_dir: Path, build_files: list[Path], deps: list[Dependency]
    ) -> None:
        """Save resolved dependencies to cache."""
        if not build_files:
            return

        cache_dir = self._cache_dir(project_dir)
        content_hash = self._content_hash(build_files)
        cache_file = cache_dir / f"{content_hash}.json"

        cache_dir.mkdir(parents=True, exist_ok=True)
        data = [asdict(d) for d in deps]
        cache_file.write_text(json.dumps(data, indent=2))

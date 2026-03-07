from abc import ABC, abstractmethod
from pathlib import Path

from libsrc.models import Dependency


class Ecosystem(ABC):
    """Abstract base class for build system ecosystem handlers."""

    @abstractmethod
    def discover_build_files(self, project_dir: Path) -> list[Path]:
        """Find all relevant build/lock files for cache invalidation."""
        ...

    @abstractmethod
    async def resolve_dependencies(self, project_dir: Path) -> list[Dependency]:
        """Resolve dependencies, returning list of Dependency objects."""
        ...


def detect_ecosystems(project_dir: Path) -> list[Ecosystem]:
    """Scan direct files in project_dir to determine build system(s).

    Returns a list of detected Ecosystem instances. Multiple ecosystems
    may be detected in polyglot repositories.
    """
    from libsrc.ecosystems.gradle import GradleEcosystem
    from libsrc.ecosystems.maven import MavenEcosystem
    from libsrc.ecosystems.poetry import PoetryEcosystem
    from libsrc.ecosystems.uv import UvEcosystem

    ecosystems: list[Ecosystem] = []

    # Maven: pom.xml
    if (project_dir / "pom.xml").is_file():
        ecosystems.append(MavenEcosystem())

    # Gradle: build.gradle or build.gradle.kts
    if (project_dir / "build.gradle").is_file() or (project_dir / "build.gradle.kts").is_file():
        ecosystems.append(GradleEcosystem())

    has_pyproject = (project_dir / "pyproject.toml").is_file()

    # Poetry: pyproject.toml + poetry.lock
    if has_pyproject and (project_dir / "poetry.lock").is_file():
        ecosystems.append(PoetryEcosystem())

    # uv: pyproject.toml + uv.lock
    if has_pyproject and (project_dir / "uv.lock").is_file():
        ecosystems.append(UvEcosystem())

    return ecosystems

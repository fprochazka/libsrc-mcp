import asyncio
import logging
import re
import tomllib
from pathlib import Path

from libsrc.ecosystems import Ecosystem
from libsrc.models import Dependency

logger = logging.getLogger(__name__)


def _normalize_name(name: str) -> str:
    """Normalize a Python package name for comparison (PEP 503)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _parse_direct_dep_names_from_pyproject(pyproject: dict) -> set[str]:
    """Extract direct dependency names from pyproject.toml data."""
    direct_names: set[str] = set()

    # Poetry legacy: [tool.poetry.dependencies]
    poetry_deps = pyproject.get("tool", {}).get("poetry", {}).get("dependencies", {})
    for name in poetry_deps:
        if name.lower() == "python":
            continue
        direct_names.add(_normalize_name(name))

    # Poetry legacy groups: [tool.poetry.group.<name>.dependencies]
    poetry_groups = pyproject.get("tool", {}).get("poetry", {}).get("group", {})
    for group_data in poetry_groups.values():
        group_deps = group_data.get("dependencies", {})
        for name in group_deps:
            direct_names.add(_normalize_name(name))

    # PEP 621: [project].dependencies (Poetry 2.0+)
    project_deps = pyproject.get("project", {}).get("dependencies", [])
    for dep_str in project_deps:
        match = re.match(r"^([A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?)", dep_str)
        if match:
            direct_names.add(_normalize_name(match.group(1)))

    # PEP 621: [project.optional-dependencies]
    optional_deps = pyproject.get("project", {}).get("optional-dependencies", {})
    for group_deps in optional_deps.values():
        for dep_str in group_deps:
            match = re.match(r"^([A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?)", dep_str)
            if match:
                direct_names.add(_normalize_name(match.group(1)))

    return direct_names


class PoetryEcosystem(Ecosystem):
    """Handler for Poetry-managed Python projects (pyproject.toml + poetry.lock)."""

    def discover_build_files(self, project_dir: Path) -> list[Path]:
        files: list[Path] = []
        pyproject = project_dir / "pyproject.toml"
        if pyproject.is_file():
            files.append(pyproject)
        poetry_lock = project_dir / "poetry.lock"
        if poetry_lock.is_file():
            files.append(poetry_lock)
        return files

    async def resolve_dependencies(self, project_dir: Path) -> list[Dependency]:
        poetry_lock = project_dir / "poetry.lock"
        if poetry_lock.is_file():
            return self._parse_lock_file(project_dir, poetry_lock)
        return await self._fallback_poetry_show(project_dir)

    def _parse_lock_file(self, project_dir: Path, poetry_lock: Path) -> list[Dependency]:
        with open(poetry_lock, "rb") as f:
            lock_data = tomllib.load(f)

        # Parse pyproject.toml for direct dependency names
        pyproject_path = project_dir / "pyproject.toml"
        direct_names: set[str] = set()
        if pyproject_path.is_file():
            with open(pyproject_path, "rb") as f:
                pyproject = tomllib.load(f)
            direct_names = _parse_direct_dep_names_from_pyproject(pyproject)

        deps: list[Dependency] = []
        packages = lock_data.get("package", [])
        for pkg in packages:
            name = pkg.get("name", "")
            version = pkg.get("version", "")

            is_direct = _normalize_name(name) in direct_names

            deps.append(
                Dependency(
                    ecosystem="poetry",
                    identifier=name,
                    version=version,
                    is_direct=is_direct,
                )
            )

        return deps

    async def _fallback_poetry_show(self, project_dir: Path) -> list[Dependency]:
        """Fallback: run `poetry show` and parse output."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "poetry",
                "show",
                cwd=str(project_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
        except FileNotFoundError:
            raise RuntimeError(
                "Dependencies cannot be resolved because poetry is not installed "
                "and the project does not have a poetry.lock file."
            )

        if proc.returncode != 0:
            raise RuntimeError(
                f"poetry show failed (exit code {proc.returncode}): {stderr.decode().strip()}"
            )

        output = stdout.decode()
        deps: list[Dependency] = []
        # poetry show output: name    version   description
        # Each line is a flat list of all installed packages
        for line in output.strip().splitlines():
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0]
                version = parts[1]
                deps.append(
                    Dependency(
                        ecosystem="poetry",
                        identifier=name,
                        version=version,
                        is_direct=False,  # Can't reliably determine from flat list
                    )
                )

        return deps

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

    # [project].dependencies — list of PEP 508 strings
    project_deps = pyproject.get("project", {}).get("dependencies", [])
    for dep_str in project_deps:
        # PEP 508: name followed by extras/version/markers
        match = re.match(r"^([A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?)", dep_str)
        if match:
            direct_names.add(_normalize_name(match.group(1)))

    # [project.optional-dependencies]
    optional_deps = pyproject.get("project", {}).get("optional-dependencies", {})
    for group_deps in optional_deps.values():
        for dep_str in group_deps:
            match = re.match(r"^([A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?)", dep_str)
            if match:
                direct_names.add(_normalize_name(match.group(1)))

    # [dependency-groups] (PEP 735)
    dep_groups = pyproject.get("dependency-groups", {})
    for group_deps in dep_groups.values():
        for item in group_deps:
            if isinstance(item, str):
                match = re.match(r"^([A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?)", item)
                if match:
                    direct_names.add(_normalize_name(match.group(1)))
            # dict entries like {include-group = "..."} are group includes, skip them

    return direct_names


class UvEcosystem(Ecosystem):
    """Handler for uv-managed Python projects (pyproject.toml + uv.lock)."""

    def discover_build_files(self, project_dir: Path) -> list[Path]:
        files: list[Path] = []
        pyproject = project_dir / "pyproject.toml"
        if pyproject.is_file():
            files.append(pyproject)
        uv_lock = project_dir / "uv.lock"
        if uv_lock.is_file():
            files.append(uv_lock)
        return files

    async def resolve_dependencies(self, project_dir: Path) -> list[Dependency]:
        uv_lock = project_dir / "uv.lock"
        if uv_lock.is_file():
            return self._parse_lock_file(project_dir, uv_lock)
        return await self._fallback_uv_tree(project_dir)

    def _parse_lock_file(self, project_dir: Path, uv_lock: Path) -> list[Dependency]:
        with open(uv_lock, "rb") as f:
            lock_data = tomllib.load(f)

        # Parse pyproject.toml for direct dependency names
        pyproject_path = project_dir / "pyproject.toml"
        direct_names: set[str] = set()
        if pyproject_path.is_file():
            with open(pyproject_path, "rb") as f:
                pyproject = tomllib.load(f)
            direct_names = _parse_direct_dep_names_from_pyproject(pyproject)

        # Also get the project's own name so we can skip it
        project_name = None
        if pyproject_path.is_file():
            project_name = pyproject.get("project", {}).get("name")
            if project_name:
                project_name = _normalize_name(project_name)

        deps: list[Dependency] = []
        packages = lock_data.get("package", [])
        for pkg in packages:
            name = pkg.get("name", "")
            version = pkg.get("version", "")

            # Skip the project itself (workspace/virtual source)
            source = pkg.get("source", {})
            if isinstance(source, dict) and (
                source.get("virtual") is not None
                or source.get("workspace") is not None
                or source.get("editable") is not None
            ):
                continue

            # Also skip if the name matches the project name
            if project_name and _normalize_name(name) == project_name:
                continue

            is_direct = _normalize_name(name) in direct_names

            deps.append(
                Dependency(
                    ecosystem="uv",
                    identifier=name,
                    version=version,
                    is_direct=is_direct,
                )
            )

        return deps

    async def _fallback_uv_tree(self, project_dir: Path) -> list[Dependency]:
        """Fallback: run `uv tree --depth 1` and parse output."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "uv",
                "tree",
                "--depth",
                "1",
                cwd=str(project_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
        except FileNotFoundError:
            raise RuntimeError(
                "Dependencies cannot be resolved because uv is not installed "
                "and the project does not have a uv.lock file."
            )

        if proc.returncode != 0:
            raise RuntimeError(
                f"uv tree failed (exit code {proc.returncode}): {stderr.decode().strip()}"
            )

        output = stdout.decode()
        deps: list[Dependency] = []
        # uv tree --depth 1 output looks like:
        # project-name v0.1.0
        # ├── dep-a v1.2.3
        # ├── dep-b v2.0.0
        # │   └── transitive v0.5.0
        # The first line is the project itself, direct deps at first indent level
        lines = output.strip().splitlines()
        for line in lines[1:]:  # skip project root line
            # Direct deps: lines starting with tree chars at first level
            # Match lines like: ├── name v1.2.3  or  └── name v1.2.3
            match = re.match(r"^[├└]── (\S+)\s+v(\S+)", line)
            if match:
                name = match.group(1)
                version = match.group(2)
                deps.append(
                    Dependency(
                        ecosystem="uv",
                        identifier=name,
                        version=version,
                        is_direct=True,
                    )
                )
                continue

            # Transitive deps at second level (depth 1 means we see them listed)
            match = re.match(r"^[│ ]\s+[├└]── (\S+)\s+v(\S+)", line)
            if match:
                name = match.group(1)
                version = match.group(2)
                deps.append(
                    Dependency(
                        ecosystem="uv",
                        identifier=name,
                        version=version,
                        is_direct=False,
                    )
                )

        return deps

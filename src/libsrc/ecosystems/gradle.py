import asyncio
import logging
import re
import shutil
from pathlib import Path

from libsrc.ecosystems import Ecosystem
from libsrc.models import Dependency

logger = logging.getLogger(__name__)

# Directories to skip when searching for Gradle build files
_SKIP_DIRS = {".gradle", "build", ".git", "node_modules", ".idea"}

# File names to discover
_BUILD_FILES = {"build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"}


class GradleEcosystem(Ecosystem):
    """Handler for Gradle-based Java/Kotlin projects."""

    def discover_build_files(self, project_dir: Path) -> list[Path]:
        """Find all Gradle build files in the project tree."""
        files: list[Path] = []
        self._find_gradle_files(project_dir, files)

        # Also check for version catalog
        version_catalog = project_dir / "gradle" / "libs.versions.toml"
        if version_catalog.is_file():
            files.append(version_catalog)

        return sorted(files)

    def _find_gradle_files(self, directory: Path, results: list[Path]) -> None:
        try:
            entries = sorted(directory.iterdir())
        except PermissionError:
            return

        for entry in entries:
            if entry.is_file() and entry.name in _BUILD_FILES:
                results.append(entry)
            elif entry.is_dir() and entry.name not in _SKIP_DIRS:
                self._find_gradle_files(entry, results)

    async def resolve_dependencies(self, project_dir: Path) -> list[Dependency]:
        wrapper = self._find_wrapper(project_dir)

        proc = await asyncio.create_subprocess_exec(
            wrapper,
            "dependencies",
            "--configuration",
            "runtimeClasspath",
            "-q",
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(
                f"Gradle dependencies failed (exit code {proc.returncode}): "
                f"{stderr.decode().strip()}"
            )

        output = stdout.decode()
        return self._parse_dependency_tree(output)

    def _find_wrapper(self, project_dir: Path) -> str:
        """Find Gradle wrapper or system Gradle."""
        gradlew = project_dir / "gradlew"
        if gradlew.is_file():
            return str(gradlew)

        if shutil.which("gradle"):
            return "gradle"

        raise RuntimeError(
            "Dependencies cannot be resolved because gradle is not installed "
            "and the project does not include gradlew."
        )

    def _parse_dependency_tree(self, output: str) -> list[Dependency]:
        """Parse the text output of `gradle dependencies --configuration runtimeClasspath`.

        Lines look like:
            +--- org.springframework:spring-core:5.3.9
            |    +--- org.springframework:spring-jcl:5.3.9
            |    \\--- org.springframework:spring-jcl:5.3.9
            \\--- com.google.guava:guava:31.1-jre
            +--- com.example:lib:1.0 -> 2.0
            +--- com.example:lib:1.0 -> 2.0 (*)
            +--- com.example:lib (n)
            +--- com.example:lib:{strictly 1.0} -> 1.0 (c)
        """
        deps: list[Dependency] = []
        seen: set[str] = set()

        # Pattern to match dependency lines
        # Groups: (indent_chars)(group:name:requested_version)(optional -> resolved_version)(optional markers)
        dep_pattern = re.compile(
            r"^([\s|]*)[+\\]--- "  # indentation + branch marker
            r"(\S+)"               # group:name or group:name:version
            r"(?: -> (\S+))?"      # optional version override
            r"(?: \(.*\))?"        # optional markers like (*), (c), (n)
            r"\s*$"
        )

        for line in output.splitlines():
            match = dep_pattern.match(line)
            if not match:
                continue

            indent = match.group(1)
            coordinate = match.group(2)
            resolved_version_override = match.group(3)

            # Skip constraints (c) and unresolved (n)
            if "(n)" in line or "(c)" in line:
                continue

            # Parse the coordinate: group:name:version or group:name
            parts = coordinate.split(":")
            if len(parts) < 2:
                continue

            group = parts[0]
            name = parts[1]
            identifier = f"{group}:{name}"

            # Determine version
            if resolved_version_override:
                version = resolved_version_override
            elif len(parts) >= 3:
                version = parts[2]
                # Handle version ranges like {strictly 1.0}
                if version.startswith("{"):
                    continue  # skip constraint-only entries
            else:
                continue  # no version available

            # Determine depth: count indentation level
            # Each level is typically 5 chars: "|    " or "     "
            # First level deps have indent like "" (empty)
            # Calculate depth by looking at the indentation
            indent_str = indent.replace("|", " ")
            depth = len(indent_str) // 5  # each nesting level adds ~5 chars

            is_direct = depth == 0

            # Deduplicate
            dedup_key = f"{identifier}:{version}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            deps.append(
                Dependency(
                    ecosystem="gradle",
                    identifier=identifier,
                    version=version,
                    is_direct=is_direct,
                )
            )

        return deps

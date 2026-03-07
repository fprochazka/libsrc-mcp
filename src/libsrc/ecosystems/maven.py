import asyncio
import json
import logging
import shutil
import tempfile
from pathlib import Path

from libsrc.ecosystems import Ecosystem
from libsrc.models import Dependency

logger = logging.getLogger(__name__)

# Directories to skip when searching for pom.xml files
_SKIP_DIRS = {"target", ".git", "node_modules", ".idea", ".mvn", "build"}


class MavenEcosystem(Ecosystem):
    """Handler for Maven-based Java projects (pom.xml)."""

    def discover_build_files(self, project_dir: Path) -> list[Path]:
        """Recursively find all pom.xml files in the project tree."""
        pom_files: list[Path] = []
        self._find_pom_files(project_dir, pom_files)
        return sorted(pom_files)

    def _find_pom_files(self, directory: Path, results: list[Path]) -> None:
        try:
            entries = sorted(directory.iterdir())
        except PermissionError:
            return

        for entry in entries:
            if entry.is_file() and entry.name == "pom.xml":
                results.append(entry)
            elif entry.is_dir() and entry.name not in _SKIP_DIRS:
                self._find_pom_files(entry, results)

    async def resolve_dependencies(self, project_dir: Path) -> list[Dependency]:
        wrapper = self._find_wrapper(project_dir)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmpfile = tmp.name

        try:
            proc = await asyncio.create_subprocess_exec(
                wrapper,
                "dependency:tree",
                f"-DoutputType=json",
                f"-DoutputFile={tmpfile}",
                "-DappendOutput=true",
                cwd=str(project_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                raise RuntimeError(
                    f"Maven dependency:tree failed (exit code {proc.returncode}): "
                    f"{stderr.decode().strip()}"
                )

            # Read and parse the JSON output
            output_path = Path(tmpfile)
            if not output_path.is_file() or output_path.stat().st_size == 0:
                raise RuntimeError(
                    "Maven dependency:tree produced no output file. "
                    "Ensure maven-dependency-plugin 3.7.0+ is available."
                )

            content = output_path.read_text()
            roots = self._parse_concatenated_json(content)

            deps: list[Dependency] = []
            seen: set[str] = set()
            for root in roots:
                self._collect_dependencies(root, deps, seen, is_root=True)

            return deps

        finally:
            Path(tmpfile).unlink(missing_ok=True)

    def _find_wrapper(self, project_dir: Path) -> str:
        """Find Maven wrapper or system Maven."""
        mvnw = project_dir / "mvnw"
        if mvnw.is_file():
            return str(mvnw)

        if shutil.which("mvn"):
            return "mvn"

        raise RuntimeError(
            "Dependencies cannot be resolved because mvn is not installed "
            "and the project does not include mvnw."
        )

    def _parse_concatenated_json(self, content: str) -> list[dict]:
        """Parse potentially concatenated JSON objects from Maven output.

        When -DappendOutput=true is used in multi-module projects, Maven
        concatenates multiple JSON root objects in the same file.
        """
        roots: list[dict] = []
        decoder = json.JSONDecoder()
        content = content.strip()
        pos = 0
        while pos < len(content):
            # Skip whitespace between JSON objects
            while pos < len(content) and content[pos] in " \t\n\r":
                pos += 1
            if pos >= len(content):
                break
            try:
                obj, end_pos = decoder.raw_decode(content, pos)
                roots.append(obj)
                pos = end_pos
            except json.JSONDecodeError:
                # Try to skip past any garbage between JSON objects
                next_brace = content.find("{", pos + 1)
                if next_brace == -1:
                    break
                pos = next_brace

        return roots

    def _collect_dependencies(
        self,
        node: dict,
        deps: list[Dependency],
        seen: set[str],
        is_root: bool = False,
    ) -> None:
        """Recursively collect dependencies from Maven JSON tree."""
        group_id = node.get("groupId", "")
        artifact_id = node.get("artifactId", "")
        version = node.get("version", "")
        scope = node.get("scope")

        identifier = f"{group_id}:{artifact_id}"

        if not is_root:
            # Use identifier:version as dedup key
            dedup_key = f"{identifier}:{version}"
            if dedup_key not in seen:
                seen.add(dedup_key)
                deps.append(
                    Dependency(
                        ecosystem="maven",
                        identifier=identifier,
                        version=version,
                        scope=scope,
                        is_direct=False,  # will be corrected below
                    )
                )

        children = node.get("children", [])
        for child in children:
            child_group = child.get("groupId", "")
            child_artifact = child.get("artifactId", "")
            child_version = child.get("version", "")
            child_scope = child.get("scope")
            child_id = f"{child_group}:{child_artifact}"
            child_dedup = f"{child_id}:{child_version}"

            if child_dedup not in seen:
                seen.add(child_dedup)
                deps.append(
                    Dependency(
                        ecosystem="maven",
                        identifier=child_id,
                        version=child_version,
                        scope=child_scope,
                        is_direct=is_root,  # direct children of root are direct deps
                    )
                )

            # Recurse into children of this child
            for grandchild in child.get("children", []):
                self._collect_dependencies(grandchild, deps, seen, is_root=False)

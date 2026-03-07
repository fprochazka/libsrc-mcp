from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Dependency:
    ecosystem: str
    identifier: str
    version: str
    scope: str | None = None
    is_direct: bool = True


@dataclass
class ResolvedSource:
    repo_url: str
    hosting: str
    trusted: bool
    clone_path: Path | None = None
    worktree_path: Path | None = None


@dataclass
class LibraryResult:
    dependency: Dependency
    source: ResolvedSource | None = None
    messages: list[str] = field(default_factory=list)

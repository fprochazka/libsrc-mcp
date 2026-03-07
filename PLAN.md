# libsrc - Implementation Plan

## Project Structure

```
libsrc/
├── pyproject.toml
├── src/
│   └── libsrc/
│       ├── __init__.py
│       ├── __main__.py              # CLI entry: `uvx libsrc serve`
│       ├── server.py                # FastMCP server setup, tool registration
│       ├── config.py                # Config loading (~/.config/libsrc/config.yml)
│       ├── cache.py                 # Dependency resolution cache + deps.dev cache
│       ├── models.py                # Shared data models (Dependency, ResolvedDep, etc.)
│       ├── git.py                   # Git clone, fetch, worktree, tag matching, locking
│       ├── source_resolver.py       # deps.dev API + registry-specific SCM lookup
│       ├── ecosystems/
│       │   ├── __init__.py          # Ecosystem detection + base class
│       │   ├── maven.py             # Maven pom.xml / mvn dependency:tree
│       │   ├── gradle.py            # Gradle build.gradle / gradlew dependencies
│       │   ├── poetry.py            # Poetry pyproject.toml + poetry.lock
│       │   └── uv.py                # uv pyproject.toml + uv.lock
│       └── worktree_tracker.py      # Last-access tracking + cleanup
├── systemd/
│   └── libsrc.service              # Systemd user unit file
├── tests/
│   └── ...
├── SPEC.md
├── PLAN.md
└── docs/
    └── *.md                         # Research documents
```

## Implementation Phases

### Phase 1: Project Skeleton + Config + MCP Server

**Files:** `pyproject.toml`, `__init__.py`, `__main__.py`, `server.py`, `config.py`, `models.py`

1. Set up `pyproject.toml`:
   - Package name: `libsrc`
   - Python: `>=3.11`
   - Dependencies: `fastmcp`, `pyyaml`, `httpx` (for deps.dev/registry APIs)
   - Entry point: `[project.scripts] libsrc = "libsrc.__main__:main"`

2. `config.py`:
   - Load `~/.config/libsrc/config.yml`
   - Defaults: `output_dir: ~/devel/libs/`, `port: 7890`, `trusted_hosts: [github.com, gitlab.com]`, `deps_dev_cache_ttl: 24`
   - Expand `~` in paths

3. `models.py`:
   - `Dependency` dataclass: ecosystem, identifier (group/artifact/name), version, scope, is_direct
   - `ResolvedSource` dataclass: repo_url, hosting, trusted, clone_path, worktree_path
   - `LibraryResult` dataclass: dependency, source, status_messages

4. `server.py`:
   - FastMCP server with HTTP transport
   - Register `get_library_sources` tool
   - Tool implementation skeleton that calls into ecosystem + source resolver modules

5. `__main__.py`:
   - `libsrc serve` command (start MCP server)
   - `libsrc cleanup` command (manual worktree cleanup)

### Phase 2: Ecosystem Detection + Dependency Resolution

**Files:** `ecosystems/__init__.py`, `ecosystems/maven.py`, `ecosystems/gradle.py`, `ecosystems/poetry.py`, `ecosystems/uv.py`, `cache.py`

1. `ecosystems/__init__.py`:
   - `detect_ecosystem(project_dir) -> list[Ecosystem]` — scan direct files in dir
   - Abstract base class `Ecosystem`:
     - `discover_build_files(project_dir) -> list[Path]` — find all relevant files (for cache invalidation)
     - `resolve_dependencies(project_dir) -> list[Dependency]`

2. `ecosystems/poetry.py`:
   - Check for `poetry.lock` → parse TOML directly (`[[package]]` entries)
   - Fallback: run `poetry show --tree` and parse output
   - Extract: name, version, is_direct (from `pyproject.toml` [tool.poetry.dependencies] or [project] dependencies)

3. `ecosystems/uv.py`:
   - Check for `uv.lock` → parse TOML directly (`[[package]]` entries)
   - Fallback: run `uv tree` and parse output
   - Extract: name, version, source, is_direct

4. `ecosystems/maven.py`:
   - Discover all `pom.xml` files in project tree
   - Find wrapper: `mvnw` > `mvn`
   - Run: `mvnw dependency:tree -DoutputType=json -DoutputFile=<tmpfile>`
   - For multi-module: use `-DappendOutput=true` and handle concatenated JSON
   - Parse JSON output into `Dependency` objects

5. `ecosystems/gradle.py`:
   - Discover all `build.gradle` / `build.gradle.kts` files
   - Find wrapper: `gradlew` > `gradle`
   - Run: `gradlew dependencies --configuration runtimeClasspath`
   - Parse text output (indentation-based tree, `->` for version overrides)
   - Extract: group, name, resolved version, is_direct (top-level = direct)

6. `cache.py`:
   - `DependencyCache`:
     - Key: `sha256(project_dir)-basename` / `sha256(contents of all build files).json`
     - Load/save resolved dependency lists
   - `DepsDevCache`:
     - Key: `ecosystem/package/version.json`
     - TTL-based expiry

### Phase 3: Source Repository Discovery

**Files:** `source_resolver.py`

1. `SourceResolver` class:
   - `resolve(dependency: Dependency) -> ResolvedSource | None`

2. **deps.dev lookup** (first):
   - `GET https://api.deps.dev/v3/systems/{SYSTEM}/packages/{name}/versions/{version}`
   - System mapping: Maven → `MAVEN`, PyPI → `PYPI`
   - Extract `links` array, look for `SOURCE_REPO` label
   - Cache response

3. **Maven fallback**:
   - Download POM: `https://repo1.maven.org/maven2/{groupPath}/{artifact}/{version}/{artifact}-{version}.pom`
   - Parse `<scm><url>` or `<scm><connection>` (strip `scm:git:` prefix)

4. **PyPI fallback**:
   - `GET https://pypi.org/pypi/{name}/{version}/json`
   - Check `info.project_urls` keys: `Source`, `Source Code`, `Repository`, `Code`, `GitHub`, `Homepage`
   - Normalize: extract `github.com/owner/repo` or `gitlab.com/owner/repo` from URL

5. **Heuristics** (last resort):
   - Maven groupId `com.github.{user}` or `io.github.{user}` → `github.com/{user}/{artifactId}`
   - Package name → GitHub search (maybe skip for v1)

6. **Trusted host check**: compare extracted hosting against config whitelist

### Phase 4: Git Clone + Worktree Management

**Files:** `git.py`, `worktree_tracker.py`

1. `git.py` — `GitManager` class:
   - `clone_or_fetch(repo_url) -> Path`:
     - Parse URL to `<output_dir>/<hostname>/<owner>/<repo>`
     - If exists: `git fetch --all`
     - If not: `git clone <url> <path>`
     - File-based locking per repo path (use `fcntl.flock` or a `.lock` file)
   - `create_worktree(clone_path, version) -> Path`:
     - Target: `<clone_path>.versions/<version>`
     - If worktree already exists, return it
     - Find best matching tag: `git tag -l` → match against patterns: `v{version}`, `{version}`, `release-{version}`, `{artifactId}-{version}`, then closest match
     - `git worktree add <path> <tag>`
     - File-based locking per clone path

2. `worktree_tracker.py`:
   - JSON file at `~/.cache/libsrc/worktree-access.json`
   - Track: `{worktree_path: last_access_timestamp}`
   - Update on every tool response
   - `cleanup(max_age_days=7)`:
     - Find worktrees older than threshold
     - `git worktree remove <path>`
     - Remove from tracker

### Phase 5: Wire Everything Together

**Files:** `server.py` (update)

1. Implement the full `get_library_sources` tool logic:
   - Load config
   - Detect ecosystem(s) in `project_dir`
   - Check dependency cache → resolve if miss → save to cache
   - If `library_name` is None: return dependency listing with message
   - If `library_name` is specified:
     - Filter dependencies by substring match on full identifier
     - Respect `transitive` flag
     - For each match: resolve source → clone/fetch → create worktree → track access
     - Return results with paths and status messages
   - Handle errors gracefully (tool not installed, source not found, untrusted host)

### Phase 6: Systemd + Polish

**Files:** `systemd/libsrc.service`, README updates

1. Systemd user unit:
   ```ini
   [Unit]
   Description=libsrc - Library Source Code MCP Server
   After=network.target

   [Service]
   Type=simple
   ExecStart=%h/.local/bin/libsrc serve
   Restart=on-failure
   RestartSec=5

   [Install]
   WantedBy=default.target
   ```

2. Startup cleanup: run worktree cleanup on server start

3. Basic README with usage instructions

## Key Dependencies

- `fastmcp` — MCP server framework
- `pyyaml` — config file parsing
- `httpx` — HTTP client for deps.dev and registry APIs

## Notes

- All subprocess calls (mvn, gradle, poetry, uv, git) should use `asyncio.create_subprocess_exec` for non-blocking execution
- File locking for git operations: simple `.lock` file with `fcntl.flock`
- Tag matching: try exact patterns first, then fall back to fuzzy/closest match using version string similarity
- Gradle text parsing: each line has indentation (3 chars per level: `+--- `, `|    `, `\--- `), version conflict shown as `1.0 -> 1.1`

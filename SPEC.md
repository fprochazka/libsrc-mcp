# libsrc - Specification

## Overview

**`libsrc`** — a tool installable via `uv`, runnable via `uvx`, that starts an MCP server (built with FastMCP) exposing tools for AI agents to resolve project dependencies and provide local source code paths for inspection.

The primary value: the agent calls one tool and gets back paths to cloned, version-checked-out source code of project dependencies — handling registry lookup, git clone, and worktree creation automatically.

**Python version:** 3.11+ (for `tomllib` in stdlib).

## MCP Transport

- **HTTP** (streamable) — single long-running daemon process that multiple agents connect to
- Avoids stdio's problem of starting separate processes per agent connection
- Default port configurable in `config.yml`

## MCP Tools

### `get_library_sources(project_dir, library_name?, transitive?)`

- `project_dir` — path to the project root directory; the tool auto-detects the build system by scanning direct files in the directory
- `library_name` — optional; when omitted, resolves dependencies and returns a listing (no cloning); when specified, performs a substring match against the full library identifier (e.g. `hibernate` matches `org.hibernate:hibernate-core:6.4.1`) and clones/checks out matching libraries
- `transitive` — optional boolean, default `false`; controls whether transitive dependencies are included; the `library_name` filter also applies to transitives when enabled

**Response when `library_name` is omitted:**
- A message explaining that no library name was given and libraries will only be cloned when a name is specified
- The full list of resolved dependencies (identifier + version) for the agent to browse

**Response when `library_name` is specified:**
- A list of matched packages, each containing:
  - package identifier (ecosystem-specific: `groupId:artifactId:version` for Maven/Gradle, `name==version` for Python)
  - path to the version-specific worktree directory (or `null` if source could not be found)
  - status/warning messages (e.g. "source hosted on untrusted host", "source repository not found in registry metadata")

Design goal: **one tool call, no chaining required.** The agent gets everything it needs in a single invocation. The `library_name` substring matches against the full identifier string, giving the agent flexibility.

## Supported Ecosystems

- **Java**: Maven (`pom.xml`), Gradle (`build.gradle`, `build.gradle.kts`)
- **Python**: Poetry (`pyproject.toml` + `poetry.lock`), uv (`pyproject.toml` + `uv.lock`)

**Not supported:** plain pip / `requirements.txt` (no reliable version resolution without a lock file or detectable venv). Users should migrate to uv or Poetry.

Architecture should be designed to allow adding more ecosystems later.

## Behavior

### 1. Ecosystem Detection

Scan direct files in `project_dir` to determine the build system:
- `pom.xml` → Maven
- `build.gradle` or `build.gradle.kts` → Gradle
- `pyproject.toml` + `poetry.lock` → Poetry
- `pyproject.toml` + `uv.lock` → uv

If multiple ecosystems are detected (polyglot repo), search all of them for the given `library_name`. In practice, polyglot repos usually have separate subdirs per language, so the caller would point to the specific subdir.

### 2. Dependency Resolution

**Prefer lock files when available, fall back to CLI tools:**

| Ecosystem | Lock File (preferred) | CLI Fallback |
|-----------|----------------------|--------------|
| Maven | — | `mvnw dependency:tree -DoutputType=json` (or `mvn` if no wrapper) |
| Gradle | — | `gradlew dependencies` (or `gradle` if no wrapper) |
| Poetry | `poetry.lock` (parse TOML directly) | `poetry show --tree` |
| uv | `uv.lock` (parse TOML directly) | `uv tree` |

**Build tool wrapper preference:** `mvnw` > `mvn`, `gradlew` > `gradle`.

If the required build tool is not installed and no wrapper exists, the tool response should say: "Dependencies cannot be resolved because [tool] is not installed and the project does not include [wrapper]."

**Gradle text output parsing:** Gradle has no built-in JSON output. Parsing the text output of `gradle dependencies` is not ideal but manageable — the format is well-structured with clear indentation and conflict resolution markers (`->` for version overrides).

**Discovered build files:** The tool must discover all relevant build files in the project (all `pom.xml` files for multi-module Maven, all `build.gradle` files for multi-module Gradle, etc.) for both resolution and cache invalidation purposes.

### 3. Source Repository Discovery

Layered approach:

1. **deps.dev API** (first) — best unified source across ecosystems. Returns `SOURCE_REPO` links with provenance indicators. Cache responses locally.
2. **Registry-specific fallback:**
   - Maven: download POM from Maven Central, parse `<scm><url>` / `<scm><connection>`
   - PyPI: JSON API at `https://pypi.org/pypi/{name}/{version}/json`, check `project_urls` keys (`Source`, `Repository`, `Code`, `Homepage`)
3. **Heuristics:** Maven groupId patterns (`com.github.*`, `io.github.*`), package name → repo name matching

When source cannot be found: the tool response should clearly state this. The AI agent can then look for `-sources.jar`, inspect `.venv/` directories, or decompile classes on its own.

### 4. Library Identifier Formats

- **Maven/Gradle**: `groupId:artifactId:version` (plus optional classifier/type)
- **Python (Poetry/uv)**: `name==version`
- Package name normalization: handle PyPI's case-insensitive, hyphen/underscore equivalence (search for multiple variants or normalize before matching)

### 5. Clone and Worktree Management

**Cloning:**
- Full clones (not shallow) — the user builds up a local cache over time; full history needed for worktree checkout of arbitrary tags
- Clone into `<output_dir>/<hostname>/<owner>/<repo>` (same structure as `git-libs-clone`)
- Before looking for tags, always `git fetch` to ensure we have the latest

**Worktree creation:**
- Path structure: `<lib-clone-path>.versions/<version>`
- Enables parallel agents to inspect different versions without checkout conflicts
- Worktree checkout targets the best-matching git tag for the version

**Version tag matching:**
- Search `git tag -l` for the version
- Common patterns: `v1.2.3`, `1.2.3`, `release-1.2.3`, `artifactId-1.2.3`
- Use the closest match — better than nothing

**Monorepo handling:** Multiple Maven artifacts may map to the same repo+version. Clone once, create one worktree, return the same path for all matching artifacts.

### 6. Worktree Lifecycle

- Track last-access time per worktree in a JSON file (updated each time the tool returns the path)
- Cleanup: remove worktrees not accessed for more than 1 week
- Cleanup can run periodically (e.g., on server startup or as a background task)

### 7. Concurrency

Single MCP server process, but filesystem operations (clone, worktree creation) need to be atomic. Use file-based locking to prevent concurrent clone/worktree operations on the same repository.

## Caching

### Dependency Resolution Cache

- Location: `~/.cache/libsrc/<sanitized-project-path>/<content-hash>.json`
- `sanitized-project-path` = `sha256(absolute_normalized_project_dir)-sanitized_project_dir_basename`
- `content-hash` = checksum of the contents of all discovered build/lock files in the project
- This handles both committed and uncommitted changes — any file modification invalidates the cache

### deps.dev API Cache

- Cache deps.dev responses locally to avoid redundant API calls
- Cache key: ecosystem + package identifier + version
- TTL: reasonable expiry (e.g., 24 hours or configurable)

## Trusted Hosting

- Whitelist of trusted git hostings for cloning
- Default: `github.com`, `gitlab.com`
- Configurable in `config.yml`
- When a library's source is hosted on an untrusted host, the tool response must communicate this clearly

## Configuration

Config file: `~/.config/libsrc/config.yml`

```yaml
# Directory where library sources are cloned
output_dir: ~/devel/libs/

# HTTP server port
port: 7890

# Whitelist of trusted git hostings
trusted_hosts:
  - github.com
  - gitlab.com

# deps.dev cache TTL in hours
deps_dev_cache_ttl: 24
```

## Installation and Deployment

### Quick start
```bash
uvx libsrc serve
```

### Systemd service
A systemd unit file should be provided for users who want the server running as a daemon:
```
~/.config/systemd/user/libsrc.service
```

## Reference Implementations

- FastMCP framework: `/home/fprochazka/devel/libs/github.com/PrefectHQ/fastmcp`
- git-libs-clone script: `~/.config/gitconfig/bin/git-libs-clone` (base behavior for cloning)

## Research Documents

Detailed research on each ecosystem's dependency resolution is in `docs/`:
- `docs/maven-dependencies.md`
- `docs/gradle-dependencies.md`
- `docs/poetry-dependencies.md`
- `docs/uv-dependencies.md`
- `docs/pip-dependencies.md`
- `docs/deps-dev-api.md`

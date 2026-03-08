# libsrc

An MCP server that resolves project dependencies and provides local source code paths for AI agent inspection. It auto-detects the build system, resolves dependencies, looks up source repositories, clones them, and checks out the correct version as a git worktree -- all in a single tool call.

## Supported Ecosystems

- **Java**: Maven (`pom.xml`), Gradle (`build.gradle`, `build.gradle.kts`)
- **Python**: Poetry (`pyproject.toml` + `poetry.lock`), uv (`pyproject.toml` + `uv.lock`)

Plain pip / `requirements.txt` is not supported (no reliable version resolution without a lock file).

## Installation

```bash
# Install as a tool
uv tool install libsrc-mcp

# Or run directly without installing
uvx libsrc-mcp serve

# Auto-register in detected AI coding tools
libsrc-mcp install
```

### Auto-install into AI tools

`libsrc-mcp install` detects installed AI coding tools and adds the MCP server to their configs. Supported: Claude Code, Cursor, Windsurf, Codex CLI, Gemini CLI, JetBrains Junie, VS Code Copilot. Skips tools that aren't installed or already configured.

```bash
libsrc-mcp install
libsrc-mcp install --port 8080  # if using a non-default port
```

## Configuration

Create `~/.config/libsrc/config.yml` (all fields optional):

```yaml
# Directory where library sources are cloned (default: ~/devel/libs/)
output_dir: ~/devel/libs/

# HTTP server port (default: 7890)
port: 7890

# Trusted git hostings for cloning (default: github.com, gitlab.com)
trusted_hosts:
  - github.com
  - gitlab.com

# deps.dev API cache TTL in hours (default: 24)
deps_dev_cache_ttl: 24
```

## Usage

### Start the server

```bash
libsrc-mcp serve
libsrc-mcp serve --port 8080
```

### Systemd service (Linux)

```bash
mkdir -p ~/.config/systemd/user
cp systemd/libsrc-mcp.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now libsrc-mcp
```

### Worktree cleanup

Worktrees not accessed for 7+ days are cleaned up automatically on server startup. Manual cleanup:

```bash
libsrc-mcp cleanup
```

## MCP Tool: `get_library_sources`

| Parameter | Type | Description |
|-----------|------|-------------|
| `project_dir` | `string` | Absolute path to the project root directory. Build system is auto-detected. |
| `library_name` | `string?` | Substring filter against full identifier (e.g. `"hibernate"` matches `org.hibernate:hibernate-core:6.4.1`). When omitted, lists dependencies without cloning. |
| `transitive` | `bool` | Include transitive dependencies (default: `false`). |

**Without `library_name`:** returns the dependency listing for discovery.
**With `library_name`:** resolves source repos, clones, creates version worktrees, returns local paths.

## How It Works

### Dependency Resolution

Lock files are preferred when available, CLI tools are the fallback:

| Ecosystem | Lock File (preferred) | CLI Fallback |
|-----------|----------------------|--------------|
| Maven | — | `mvnw dependency:tree -DoutputType=json` |
| Gradle | — | `gradlew dependencies --configuration runtimeClasspath` |
| Poetry | `poetry.lock` (TOML) | `poetry show --tree` |
| uv | `uv.lock` (TOML) | `uv tree` |

Build tool wrappers are preferred: `mvnw` > `mvn`, `gradlew` > `gradle`.

### Source Repository Discovery

Layered approach (first match wins):

1. **deps.dev API** -- Google's unified package-to-repo mapping (Maven, PyPI, npm, Go, etc.). Responses are cached locally.
2. **Registry fallback** -- Maven Central POM `<scm>` element; PyPI JSON API `project_urls`.
3. **Heuristics** -- Maven groupId patterns (`com.github.*`), package name matching.

### Clone and Worktree Management

- Full clones into `<output_dir>/<hostname>/<owner>/<repo>`
- `git fetch --all --tags` before each tag lookup
- Version worktrees at `<clone_path>.versions/<version>` (enables parallel agents on different versions)
- Tag matching: tries `v{ver}`, `{ver}`, `release-{ver}`, `{artifact}-{ver}`, suffix/contains fallback
- Strips release qualifiers (`.Final`, `.RELEASE`, `.GA`) for projects that omit them from tags
- Monorepo dedup: same repo+version = one worktree shared across artifacts
- File-based locking (`fcntl.flock`) for concurrent safety

### Caching

- **Dependency cache**: `~/.cache/libsrc/deps/` keyed by content hash of all build/lock files (invalidates on any file change)
- **deps.dev cache**: `~/.cache/libsrc/depsdev/` with configurable TTL
- **Worktree tracker**: `~/.cache/libsrc/worktree-access.json` for LRU cleanup

## MCP Client Configuration

### Claude Code

```bash
claude mcp add libsrc --transport http http://127.0.0.1:7890/mcp
```

### VS Code Copilot (`.vscode/mcp.json`)

```json
{
  "servers": {
    "libsrc": { "type": "http", "url": "http://127.0.0.1:7890/mcp" }
  }
}
```

### Other tools

```json
{
  "mcpServers": {
    "libsrc": { "type": "http", "url": "http://127.0.0.1:7890/mcp" }
  }
}
```

See `docs/mcp-auto-install.md` for tool-specific config details (Cursor, Windsurf, Gemini CLI, Codex CLI, Cline, Continue.dev, JetBrains Junie).

## Releasing

1. Bump the version in `pyproject.toml`
2. Commit and tag: `git tag v<version>`
3. Push the tag: `git push origin v<version>`

The `publish.yml` GitHub Action builds and publishes to PyPI automatically via trusted publishing.

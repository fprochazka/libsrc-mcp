# libsrc

An MCP server that resolves project dependencies and provides local source code paths for AI agent inspection. It auto-detects the build system (Maven, Gradle, Poetry, uv), resolves dependencies, looks up source repositories, and clones/checks out the correct version -- all in a single tool call.

## Installation

```bash
# Install as a tool
uv tool install libsrc

# Or run directly without installing
uvx libsrc serve
```

## Configuration

Create `~/.config/libsrc/config.yml`:

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

All fields are optional and have sensible defaults.

## Usage

### Start the server

```bash
libsrc serve
```

Override the port:

```bash
libsrc serve --port 8080
```

### Systemd service (Linux)

Copy the unit file and enable it:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/libsrc.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now libsrc
```

Check status:

```bash
systemctl --user status libsrc
journalctl --user -u libsrc -f
```

### Manual worktree cleanup

Remove worktrees that haven't been accessed in the last 7 days:

```bash
libsrc cleanup
```

## MCP Client Configuration

Point your MCP client at the server's streamable HTTP endpoint.

### Claude Code

```bash
claude mcp add libsrc --transport http http://127.0.0.1:7890/mcp
```

### Generic MCP client (JSON config)

```json
{
  "mcpServers": {
    "libsrc": {
      "type": "http",
      "url": "http://127.0.0.1:7890/mcp"
    }
  }
}
```

## Available Tools

### `get_library_sources`

Resolve project dependencies and provide local source code paths.

| Parameter | Type | Description |
|-----------|------|-------------|
| `project_dir` | `string` | Absolute path to the project root directory. The build system is auto-detected. |
| `library_name` | `string?` | Optional substring filter. When omitted, lists all dependencies. When specified, clones matching libraries and returns local paths. |
| `transitive` | `bool` | Include transitive dependencies (default: `false`). |

**Examples:**

- List all direct dependencies: `get_library_sources(project_dir="/path/to/project")`
- Clone a specific library: `get_library_sources(project_dir="/path/to/project", library_name="hibernate")`
- Search transitives too: `get_library_sources(project_dir="/path/to/project", library_name="slf4j", transitive=true)`

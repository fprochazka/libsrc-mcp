# MCP Auto-Installation Research

How to programmatically register an MCP server into popular AI coding tools.

## Tool-by-Tool Configuration

### 1. Claude Code CLI

**Config paths:**
- Local (per-project, private): `~/.claude.json` (keyed under project path)
- Project (team-shared, VCS): `.mcp.json` at project root
- User (global): `~/.claude.json` (top-level `mcpServers`)

**Detection:** `which claude` or `~/.claude.json` exists

**HTTP config:**
```json
{
  "mcpServers": {
    "libsrc": {
      "type": "streamable-http",
      "url": "http://127.0.0.1:7890/mcp"
    }
  }
}
```

**CLI alternative (no file editing):**
```bash
claude mcp add --transport http libsrc http://127.0.0.1:7890/mcp
```

### 2. Claude Desktop

**Config paths:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: not officially supported

**Detection:** Config directory existence

**HTTP config (requires mcp-remote proxy — Desktop only supports stdio natively):**
```json
{
  "mcpServers": {
    "libsrc": {
      "command": "npx",
      "args": ["mcp-remote", "http://127.0.0.1:7890/mcp"]
    }
  }
}
```

### 3. Cursor IDE

**Config paths:**
- Global: `~/.cursor/mcp.json`
- Project: `.cursor/mcp.json`

**Detection:** `~/.cursor/` directory

**HTTP config (requires mcp-remote proxy):**
```json
{
  "mcpServers": {
    "libsrc": {
      "command": "npx",
      "args": ["mcp-remote", "http://127.0.0.1:7890/mcp"]
    }
  }
}
```

### 4. VS Code with GitHub Copilot

**Config paths:**
- Linux: `~/.config/Code/User/mcp.json`
- macOS: `~/Library/Application Support/Code/User/mcp.json`
- Windows: `%APPDATA%\Code\User\mcp.json`
- Workspace: `.vscode/mcp.json`
- Insiders: replace `Code` with `Code - Insiders`

**Detection:** Config directory existence

**HTTP config (note: uses `"servers"` not `"mcpServers"`, and `"http"` not `"streamable-http"`):**
```json
{
  "servers": {
    "libsrc": {
      "type": "http",
      "url": "http://127.0.0.1:7890/mcp"
    }
  }
}
```

### 5. Windsurf IDE

**Config paths:**
- macOS/Linux: `~/.codeium/windsurf/mcp_config.json`
- Windows: `%USERPROFILE%\.codeium\windsurf\mcp_config.json`

**Detection:** `~/.codeium/windsurf/` directory

**HTTP config (note: uses `"serverUrl"` not `"url"`):**
```json
{
  "mcpServers": {
    "libsrc": {
      "serverUrl": "http://127.0.0.1:7890/mcp"
    }
  }
}
```

### 6. Cline (VS Code Extension)

**Config paths (extension ID: `saoudrizwan.claude-dev`):**
- Linux/VS Code: `~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`
- Linux/Cursor: `~/.config/Cursor/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`
- macOS/VS Code: `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`
- Windows/VS Code: `%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json`

**Detection:** `saoudrizwan.claude-dev` under globalStorage

**HTTP config (note: uses camelCase `"streamableHttp"`):**
```json
{
  "mcpServers": {
    "libsrc": {
      "url": "http://127.0.0.1:7890/mcp",
      "type": "streamableHttp",
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

### 7. Continue.dev

**Config paths:**
- Global: `~/.continue/config.yaml`
- Workspace MCP: `.continue/mcpServers/*.yaml`

**Detection:** `~/.continue/` directory

**YAML config (preferred):**
```yaml
mcpServers:
  - name: libsrc
    type: streamable-http
    url: http://127.0.0.1:7890/mcp
```

**Also accepts Claude Desktop JSON format in `.continue/mcpServers/`.**

### 8. Google Gemini CLI

**Config paths:**
- Global: `~/.gemini/settings.json`
- Project: `.gemini/settings.json`

**Detection:** `which gemini` or `~/.gemini/` directory

**HTTP config (note: uses `"httpUrl"` not `"url"`):**
```json
{
  "mcpServers": {
    "libsrc": {
      "httpUrl": "http://127.0.0.1:7890/mcp"
    }
  }
}
```

### 9. JetBrains IDEs (Junie)

**Config paths:**
- Global: `~/.junie/mcp/mcp.json`
- Project: `.junie/mcp/mcp.json`

**Detection:** `~/.junie/` directory or `~/.config/JetBrains/`

**HTTP config:**
```json
{
  "mcpServers": {
    "libsrc": {
      "url": "http://127.0.0.1:7890/mcp"
    }
  }
}
```

### 10. OpenAI Codex CLI

**Config paths (TOML!):**
- Global: `~/.codex/config.toml`
- Project: `.codex/config.toml`

**Detection:** `which codex` or `~/.codex/` directory

**HTTP config (TOML format):**
```toml
[mcp_servers.libsrc]
url = "http://127.0.0.1:7890/mcp"
```

## Transport Type Quick Reference

| Tool | Root key | HTTP field | HTTP type value |
|---|---|---|---|
| Claude Code | `mcpServers` | `url` | `"streamable-http"` |
| Claude Desktop | `mcpServers` | n/a (proxy) | n/a |
| Cursor | `mcpServers` | n/a (proxy) | n/a |
| VS Code Copilot | `servers` | `url` | `"http"` |
| Windsurf | `mcpServers` | `serverUrl` | implicit |
| Cline | `mcpServers` | `url` | `"streamableHttp"` |
| Continue.dev | `mcpServers` (YAML list) | `url` | `"streamable-http"` |
| Gemini CLI | `mcpServers` | `httpUrl` | implicit |
| JetBrains/Junie | `mcpServers` | `url` | implicit |
| Codex CLI | `mcp_servers` (TOML) | `url` | implicit |

## Key Observations

- Every tool has a slightly different config format — no true standard
- Claude Desktop and Cursor don't support HTTP natively, require `mcp-remote` proxy
- VS Code uses `"servers"` (not `"mcpServers"`) and `"http"` (not `"streamable-http"`)
- Windsurf uses `"serverUrl"`, Gemini uses `"httpUrl"` — everyone else uses `"url"`
- Codex is the only TOML-based config
- Continue.dev prefers YAML
- Cline uses camelCase `"streamableHttp"`

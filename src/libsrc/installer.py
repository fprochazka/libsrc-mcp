"""Auto-installer for libsrc MCP server into AI coding tool configurations."""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path


def _load_json(path: Path) -> dict:
    """Load a JSON file, returning empty dict if missing or empty."""
    if not path.is_file():
        return {}
    text = path.read_text().strip()
    if not text:
        return {}
    return json.loads(text)


def _save_json(path: Path, data: dict) -> None:
    """Save dict as pretty-printed JSON, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def _install_json_tool(
    *,
    name: str,
    config_path: Path,
    detect_path: Path,
    root_key: str,
    entry: dict,
) -> None:
    """Generic installer for JSON-based tool configs."""
    if not detect_path.exists():
        return

    data = _load_json(config_path)
    servers = data.get(root_key, {})

    if "libsrc" in servers:
        print(f"  [ok] {name}: already configured")
        return

    servers["libsrc"] = entry
    data[root_key] = servers
    _save_json(config_path, data)
    print(f"  [+]  {name}: installed")


def _install_claude_code(url: str) -> None:
    _install_json_tool(
        name="Claude Code",
        config_path=Path("~/.claude.json").expanduser(),
        detect_path=Path("~/.claude.json").expanduser(),
        root_key="mcpServers",
        entry={"type": "http", "url": url},
    )


def _install_cursor(url: str) -> None:
    _install_json_tool(
        name="Cursor",
        config_path=Path("~/.cursor/mcp.json").expanduser(),
        detect_path=Path("~/.cursor").expanduser(),
        root_key="mcpServers",
        entry={"command": "npx", "args": ["mcp-remote", url]},
    )


def _install_windsurf(url: str) -> None:
    _install_json_tool(
        name="Windsurf",
        config_path=Path("~/.codeium/windsurf/mcp_config.json").expanduser(),
        detect_path=Path("~/.codeium/windsurf").expanduser(),
        root_key="mcpServers",
        entry={"serverUrl": url},
    )


def _install_gemini(url: str) -> None:
    _install_json_tool(
        name="Gemini CLI",
        config_path=Path("~/.gemini/settings.json").expanduser(),
        detect_path=Path("~/.gemini").expanduser(),
        root_key="mcpServers",
        entry={"httpUrl": url},
    )


def _install_junie(url: str) -> None:
    _install_json_tool(
        name="JetBrains Junie",
        config_path=Path("~/.junie/mcp/mcp.json").expanduser(),
        detect_path=Path("~/.junie").expanduser(),
        root_key="mcpServers",
        entry={"url": url},
    )


def _install_vscode_copilot(url: str) -> None:
    if sys.platform == "darwin":
        config_dir = Path("~/Library/Application Support/Code/User").expanduser()
    else:
        config_dir = Path("~/.config/Code/User").expanduser()

    _install_json_tool(
        name="VS Code Copilot",
        config_path=config_dir / "mcp.json",
        detect_path=config_dir,
        root_key="servers",
        entry={"type": "http", "url": url},
    )


def _install_codex(url: str) -> None:
    """Install into OpenAI Codex CLI (TOML config)."""
    codex_dir = Path("~/.codex").expanduser()
    if not codex_dir.exists():
        return

    config_path = codex_dir / "config.toml"

    # Check if already configured
    if config_path.is_file():
        text = config_path.read_text()
        if text.strip():
            data = tomllib.loads(text)
            if "libsrc" in data.get("mcp_servers", {}):
                print("  [ok] Codex CLI: already configured")
                return
    else:
        text = ""

    # Append the TOML section
    section = f'\n[mcp_servers.libsrc]\nurl = "{url}"\n'
    config_path.write_text(text.rstrip("\n") + "\n" + section)
    print("  [+]  Codex CLI: installed")


def install_mcp(url: str) -> None:
    """Detect installed AI tools and add libsrc MCP server to their configs."""
    print(f"Installing libsrc MCP server ({url})...\n")

    _install_claude_code(url)
    _install_cursor(url)
    _install_windsurf(url)
    _install_codex(url)
    _install_gemini(url)
    _install_junie(url)
    _install_vscode_copilot(url)

    print()
    print("Done.")

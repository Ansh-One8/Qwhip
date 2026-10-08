"""
One-click setup helpers, so nobody has to edit files or type commands:

  Claude Desktop   add/remove qwhip in Claude Desktop's config (MCP), with a backup first
  Browsers         find Chrome/Brave/Edge, open their extensions page, locate our extension folder
"""

import json
import os
import shutil
import subprocess
import sys
import winreg
from datetime import datetime
from pathlib import Path

APP_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


# ---------------------------------------------------------------- Claude Desktop

def claude_config_path():
    """Where Claude Desktop keeps claude_desktop_config.json, or None if it isn't installed."""
    appdata = Path(os.environ.get("APPDATA", ""))
    candidates = [appdata / "Claude"]
    # The Microsoft Store version keeps its files in a per-app folder instead.
    packages = Path(os.environ.get("LOCALAPPDATA", "")) / "Packages"
    if packages.exists():
        candidates += [p / "LocalCache" / "Roaming" / "Claude" for p in packages.glob("Claude_*")]
    for folder in candidates:
        if folder.is_dir():
            return folder / "claude_desktop_config.json"
    return None


def mcp_server_entry():
    """How Claude Desktop should start our MCP server."""
    if getattr(sys, "frozen", False):  # packaged: qwhip-mcp.exe sits next to qwhip.exe
        return {"command": str(APP_DIR / "qwhip-mcp.exe"), "args": []}
    # From source: the venv's python.exe (a console program; MCP talks over stdin/stdout).
    python = Path(sys.executable).with_name("python.exe")
    return {"command": str(python), "args": [str(APP_DIR / "mcp_server.py")]}


def _read_config(path):
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except ValueError:
        # Never overwrite a file we can't understand; the user might lose settings.
        raise RuntimeError(f"{path.name} isn't valid JSON, so qwhip won't touch it. "
                           "Fix or delete it, then try again.")


def _write_config(path, config):
    if path.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copyfile(path, path.with_name(f"claude_desktop_config.backup-{stamp}.json"))
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def claude_desktop_status():
    """'missing' (Claude Desktop not installed), 'connected', 'outdated' or 'not connected'."""
    path = claude_config_path()
    if path is None:
        return "missing"
    try:
        entry = _read_config(path).get("mcpServers", {}).get("qwhip")
    except RuntimeError:
        return "not connected"
    if entry is None:
        return "not connected"
    # e.g. the app was moved or reinstalled somewhere else
    return "connected" if entry.get("command") == mcp_server_entry()["command"] else "outdated"


def connect_claude_desktop():
    """Add (or update) qwhip in Claude Desktop's config. Raises RuntimeError with a readable message."""
    path = claude_config_path()
    if path is None:
        raise RuntimeError("Claude Desktop doesn't seem to be installed (no Claude settings folder found).")
    config = _read_config(path)
    servers = config.get("mcpServers") or {}
    servers["qwhip"] = mcp_server_entry()
    config["mcpServers"] = servers
    _write_config(path, config)


def disconnect_claude_desktop():
    path = claude_config_path()
    if path is None:
        return
    config = _read_config(path)
    if "qwhip" in config.get("mcpServers", {}):
        del config["mcpServers"]["qwhip"]
        _write_config(path, config)


# ---------------------------------------------------------------- browsers

# name: (exe registered under App Paths, URL of its extensions page)
BROWSERS = {
    "Chrome": ("chrome.exe", "chrome://extensions"),
    "Brave": ("brave.exe", "brave://extensions"),
    "Edge": ("msedge.exe", "edge://extensions"),
}


def installed_browsers():
    """{'Chrome': 'C:\\...\\chrome.exe', ...} for the browsers found on this PC."""
    found = {}
    for name, (exe, _) in BROWSERS.items():
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(hive, rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{exe}") as key:
                    path = winreg.QueryValue(key, None)
                if path and Path(path).exists():
                    found[name] = path
                    break
            except OSError:
                continue
    return found


def open_extensions_page(browser_name, browser_path):
    # chrome:// pages can't be opened like normal links, but the browser accepts them
    # as a start-up argument.
    subprocess.Popen([browser_path, BROWSERS[browser_name][1]])


def extension_folder():
    return APP_DIR / "extension"

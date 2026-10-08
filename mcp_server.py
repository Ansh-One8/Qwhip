"""
Step 8: MCP server — lets Claude (Claude Code, Claude Desktop, ...) read your sessions.

MCP ("Model Context Protocol") is a standard way to give an AI app extra tools.
Claude starts this script itself, talks to it over stdin/stdout, and can call:

  get_latest_session()      the newest session: notes + screenshots
  list_sessions()           recent sessions with their ids
  get_session(session_id)   one specific session

So you can just type: "look at my qwhip screenshots and tell me what's wrong".

This script only READS session folders. It doesn't need the tray app to be running.

Important: stdout is the channel to Claude, so this file must never print().
"""

import os
from datetime import datetime
from pathlib import Path

from mcp.server.mcpserver import Image, MCPServer
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QImage

from session import DEFAULT_ROOT, Session, SessionStore

# Claude downsizes big images anyway; sending them smaller saves time and tokens.
MAX_EDGE = 1568
ROOT = Path(os.environ.get("QWHIP_SESSIONS_DIR", DEFAULT_ROOT))

server = MCPServer(
    name="qwhip",
    instructions=(
        "qwhip holds screenshot sessions the user captured on their screen, each screenshot "
        "with a short note and the window it came from. When the user mentions their "
        "screenshots, captures, qwhip, or 'what I just showed you', call get_latest_session."
    ),
)


def _png_bytes(path):
    image = QImage(str(path))
    if image.isNull():
        raise ValueError(f"Could not read {path.name}")
    if max(image.width(), image.height()) > MAX_EDGE:
        image = image.scaled(MAX_EDGE, MAX_EDGE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


def _session_content(session, max_screenshots):
    """Text header, then for each shot: a text line (number, note, window) + the image."""
    shots = session.shots[:max_screenshots]
    started = datetime.fromisoformat(session.created_at).strftime("%Y-%m-%d %H:%M")
    header = f"qwhip session {session.folder.name} (started {started}), {len(session)} screenshot(s)."
    if len(session) > len(shots):
        header += f" Showing the first {len(shots)}."
    if not shots:
        return [header + " It is empty."]

    content = [header]
    for number, shot in enumerate(shots, start=1):
        line = f"Screenshot {number}: {shot.note or '(no note)'}"
        if shot.window_title:
            line += f"  [window: {shot.window_title}]"
        content.append(line)
        content.append(Image(data=_png_bytes(session.image_path(shot)), format="png"))
    return content


@server.tool(structured_output=False)
def get_latest_session(max_screenshots: int = 10):
    """Get the user's most recent qwhip screenshot session: each screenshot with its note."""
    session = SessionStore(ROOT).latest()
    if session is None:
        return "No qwhip sessions yet. The user can capture screenshots with Ctrl+Alt+S."
    return _session_content(session, max(1, max_screenshots))


@server.tool(structured_output=False)
def list_sessions(limit: int = 10):
    """List recent qwhip sessions (newest first) with their ids, sizes and first note."""
    folders = sorted((p for p in ROOT.glob("*") if (p / "session.json").exists()), reverse=True)
    if not folders:
        return "No qwhip sessions yet."
    lines = []
    for folder in folders[:max(1, limit)]:
        session = Session.load(folder)
        first_note = next((s.note for s in session.shots if s.note), "")
        lines.append(f"{folder.name}  ·  {len(session)} screenshot(s)"
                     + (f"  ·  \"{first_note}\"" if first_note else ""))
    return "\n".join(lines)


@server.tool(structured_output=False)
def get_session(session_id: str, max_screenshots: int = 10):
    """Get one qwhip session by its id (the folder name shown by list_sessions)."""
    folder = ROOT / session_id
    # Only plain folder names inside the sessions directory, nothing like "..\\..\\secret".
    if Path(session_id).name != session_id or not (folder / "session.json").exists():
        return f"No session with id '{session_id}'. Use list_sessions to see valid ids."
    return _session_content(Session.load(folder), max(1, max_screenshots))


if __name__ == "__main__":
    server.run()  # stdio: Claude starts this process and talks over stdin/stdout

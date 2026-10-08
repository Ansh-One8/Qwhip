"""
Step 3: Sessions.

A session is one folder holding your screenshots plus a session.json:

  %LOCALAPPDATA%\\qwhip\\sessions\\2026-10-08_17-45-12\\
      shot_001.png
      shot_002.png
      session.json   <- order, notes, window titles, times

Why LOCALAPPDATA and not your project/OneDrive folder? Screenshots can contain
private stuff; LOCALAPPDATA stays on this PC and is not synced to the cloud.

The panel (Step 5) will need to redraw when a session changes, so Session has a
tiny "subscribe" mechanism: anyone can register a function that gets called
after every change.
"""

import json
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

DEFAULT_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "qwhip" / "sessions"
TRASH = ".trash"  # deleted screenshots wait here so they can be undone


@dataclass
class Shot:
    id: int
    filename: str
    note: str = ""
    window_title: str = ""
    created_at: str = ""


class Session:
    def __init__(self, folder, shots=None, next_id=1, created_at=None):
        self.folder = Path(folder)
        self.shots = shots or []
        self._next_id = next_id  # ever-increasing, so deleting a shot never reuses a filename
        self.created_at = created_at or datetime.now().isoformat(timespec="seconds")
        self._listeners = []
        self._removed = []  # (position, shot) of deleted shots, newest last, for undo

    # ---- loading / saving ----
    @classmethod
    def load(cls, folder):
        data = json.loads((Path(folder) / "session.json").read_text(encoding="utf-8"))
        return cls(
            folder,
            shots=[Shot(**s) for s in data["shots"]],
            next_id=data["next_id"],
            created_at=data["created_at"],
        )

    def save(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        data = {
            "created_at": self.created_at,
            "next_id": self._next_id,
            "shots": [asdict(s) for s in self.shots],
        }
        # Write to a temp file, then swap it in: if the app crashes mid-write,
        # the old session.json is still intact.
        tmp = self.folder / "session.json.tmp"
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.folder / "session.json")

    # ---- change notifications ----
    def subscribe(self, callback):
        """callback() is called after every change (add, note, move, remove)."""
        self._listeners.append(callback)

    def unsubscribe(self, callback):
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _changed(self):
        self.save()
        for callback in self._listeners:
            callback()

    # ---- editing ----
    def add_shot(self, image, window_title=""):
        """image: anything with .save(path), e.g. a QImage from capture.py."""
        self.folder.mkdir(parents=True, exist_ok=True)
        shot = Shot(
            id=self._next_id,
            filename=f"shot_{self._next_id:03d}.png",
            window_title=window_title,
            created_at=datetime.now().isoformat(timespec="seconds"),
        )
        if not image.save(str(self.folder / shot.filename)):
            raise OSError(f"Could not save {shot.filename}")
        self._next_id += 1
        self.shots.append(shot)
        self._changed()
        return shot

    def get(self, shot_id):
        for shot in self.shots:
            if shot.id == shot_id:
                return shot
        raise KeyError(shot_id)

    def image_path(self, shot):
        return self.folder / shot.filename

    def set_note(self, shot_id, note):
        self.get(shot_id).note = note.strip()
        self._changed()

    def move(self, shot_id, delta):
        """Move a shot up (delta=-1) or down (delta=+1) in the order."""
        i = self.shots.index(self.get(shot_id))
        j = max(0, min(len(self.shots) - 1, i + delta))
        if i != j:
            self.shots.insert(j, self.shots.pop(i))
            self._changed()

    def remove(self, shot_id):
        """Delete a shot. Its PNG moves to .trash/ so undo_remove() can bring it back."""
        shot = self.get(shot_id)
        position = self.shots.index(shot)
        self.shots.remove(shot)
        trash = self.folder / TRASH
        trash.mkdir(exist_ok=True)
        if self.image_path(shot).exists():
            os.replace(self.image_path(shot), trash / shot.filename)
        self._removed.append((position, shot))
        self._changed()

    def can_undo(self):
        return bool(self._removed)

    def undo_remove(self):
        """Bring back the most recently deleted shot, in its old position."""
        if not self._removed:
            return None
        position, shot = self._removed.pop()
        trashed = self.folder / TRASH / shot.filename
        if trashed.exists():
            os.replace(trashed, self.image_path(shot))
        self.shots.insert(min(position, len(self.shots)), shot)
        self._changed()
        return shot

    def empty_trash(self):
        """Permanently delete trashed screenshots (no more undo for them)."""
        self._removed = []
        shutil.rmtree(self.folder / TRASH, ignore_errors=True)

    def __len__(self):
        return len(self.shots)


class SessionStore:
    """Finds, creates and resumes sessions under one root folder."""

    def __init__(self, root=DEFAULT_ROOT):
        self.root = Path(root)

    def _folders(self):
        if not self.root.exists():
            return []
        # Folder names are timestamps, so sorting by name = sorting by time.
        return sorted(p for p in self.root.iterdir() if (p / "session.json").exists())

    def latest(self):
        """Most recent session, or None if there are none yet."""
        folders = self._folders()
        return Session.load(folders[-1]) if folders else None

    def new_session(self):
        name = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        folder = self.root / name
        n = 2
        while folder.exists():  # two sessions in the same second
            folder = self.root / f"{name}_{n}"
            n += 1
        session = Session(folder)
        session.save()
        return session

    def current(self):
        """Resume the latest session (so restarting the app loses nothing), or start one."""
        session = self.latest() or self.new_session()
        session.empty_trash()  # undo only lasts while the app is running
        return session


if __name__ == "__main__":
    # Manual test: each Ctrl+Alt+S capture is added to the current session.
    import signal
    import sys

    from PySide6.QtWidgets import QApplication

    from capture import RegionCapture
    from hotkeys import HotkeyManager

    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    session = SessionStore().current()
    print(f"Session folder: {session.folder}  ({len(session)} shots so far)", flush=True)

    capture = RegionCapture()

    def on_captured(image, title):
        shot = session.add_shot(image, title)
        print(f"added #{len(session)}: {shot.filename}  window: {title!r}", flush=True)

    capture.captured.connect(on_captured)

    hotkeys = HotkeyManager({"capture": "ctrl+alt+s"})
    hotkeys.triggered.connect(lambda name: capture.start())
    app.aboutToQuit.connect(hotkeys.stop)
    hotkeys.start()

    print("Press Ctrl+Alt+S to add screenshots. Ctrl+C here to quit.", flush=True)
    sys.exit(app.exec())

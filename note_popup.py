"""
Step 4: Note popup.

Right after a capture, a small box appears next to the mouse:

   ┌──────────────────────────────────────────────┐
   │ [thumb]  #3 · Chrome - localhost:3000        │
   │          [ What's this? ___________________ ]│
   │          Enter = save · Esc = skip           │
   └──────────────────────────────────────────────┘

  Enter      -> save the note
  Esc        -> skip (no note)
  click away -> save whatever you typed (so you never lose text)

It emits `finished(text)`, where text is "" if skipped.
"""

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

THUMB_SIZE = (120, 72)

STYLE = """
#card {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(52, 86, 190, 245), stop:0.55 rgba(26, 34, 70, 248), stop:1 rgba(16, 20, 40, 250));
    border: 1px solid rgba(255, 255, 255, 60); border-radius: 14px;
}
QLabel { color: #eef2ff; font-size: 12px; background: transparent; font-family: "Segoe UI Variable", "Segoe UI"; }
#hint { color: rgba(238, 242, 255, 140); font-size: 11px; }
QLineEdit {
    background: rgba(0, 0, 0, 80); color: #ffffff; border: 1px solid rgba(255, 255, 255, 50);
    border-radius: 8px; padding: 6px 8px; font-size: 13px; min-width: 280px;
}
QLineEdit:focus { border-color: rgba(140, 180, 255, 230); }
"""


class _NoteEdit(QLineEdit):
    """Text box that tells the popup when Esc is pressed or focus is lost."""

    escape = Signal()
    focus_lost = Signal()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.escape.emit()
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.focus_lost.emit()


class NotePopup(QWidget):
    finished = Signal(str)

    def __init__(self, number, image, window_title=""):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)  # lets the card have rounded corners
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setStyleSheet(STYLE)
        self._done = False

        thumb = QLabel()
        thumb.setPixmap(QPixmap.fromImage(image).scaled(
            *THUMB_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        title = window_title if len(window_title) <= 45 else window_title[:44] + "…"
        header = QLabel(f"<b>#{number}</b>" + (f" · {title}" if title else ""))

        self.edit = _NoteEdit()
        self.edit.setPlaceholderText("What's this?")
        self.edit.returnPressed.connect(lambda: self._finish(self.edit.text()))
        self.edit.escape.connect(lambda: self._finish(""))
        self.edit.focus_lost.connect(lambda: self._finish(self.edit.text()))

        hint = QLabel("Enter = save · Esc = skip")
        hint.setObjectName("hint")

        right = QVBoxLayout()
        right.addWidget(header)
        right.addWidget(self.edit)
        right.addWidget(hint)

        card = QFrame()
        card.setObjectName("card")
        row = QHBoxLayout(card)
        row.setContentsMargins(10, 10, 10, 10)
        row.addWidget(thumb)
        row.addLayout(right)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)

    def open_near_cursor(self):
        self.adjustSize()
        pos = QCursor.pos() + QPoint(16, 16)
        # Keep the popup fully on the screen the mouse is on.
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        x = min(max(pos.x(), area.left()), area.right() - self.width())
        y = min(max(pos.y(), area.top()), area.bottom() - self.height())
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.edit.setFocus()

    def commit(self):
        """Save what's typed and close (used if a new capture starts while open)."""
        self._finish(self.edit.text())

    def _finish(self, text):
        if self._done:  # Enter then focus-loss would otherwise fire twice
            return
        self._done = True
        self.finished.emit(text.strip())
        try:
            self.close()
        except RuntimeError:
            pass  # the app is quitting and Qt already destroyed this window


if __name__ == "__main__":
    # Manual test: capture -> popup -> note saved into the current session.
    import signal
    import sys

    from PySide6.QtWidgets import QApplication

    from capture import RegionCapture
    from hotkeys import HotkeyManager
    from session import SessionStore

    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    session = SessionStore().current()
    print(f"Session folder: {session.folder}  ({len(session)} shots so far)", flush=True)
    capture = RegionCapture()
    state = {"popup": None}

    def start_capture():
        if state["popup"]:
            state["popup"].commit()  # finish the previous note first
        capture.start()

    def on_captured(image, title):
        shot = session.add_shot(image, title)
        popup = NotePopup(len(session), image, title)

        def on_note(text):
            session.set_note(shot.id, text)
            state["popup"] = None
            print(f"#{len(session)} {shot.filename}: note={text!r}", flush=True)

        popup.finished.connect(on_note)
        state["popup"] = popup
        popup.open_near_cursor()

    capture.captured.connect(on_captured)

    hotkeys = HotkeyManager({"capture": "ctrl+alt+s"})
    hotkeys.triggered.connect(lambda name: start_capture())
    app.aboutToQuit.connect(hotkeys.stop)
    hotkeys.start()

    print("Press Ctrl+Alt+S, capture, then type a note. Ctrl+C here to quit.", flush=True)
    sys.exit(app.exec())

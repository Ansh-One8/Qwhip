"""
Step 5: Session panel.

   ┌─ qwhip ─────────────────────────────────────────────────────────┐
   │ Session · Oct 08, 17:45 · 3 shots      [Open folder] [New] [⚙]  │
   │ ┌─────────────────────────────────────────────────────────────┐ │
   │ │ 1 [thumb]  VS Code - qwhip                      [↑][↓][✕]   │ │
   │ │           [ the error in the terminal______ ]               │ │
   │ └─────────────────────────────────────────────────────────────┘ │
   │ No Claude tab is open.                        [Open Claude] [×] │  <- notices
   │ Deleted #3 "old note"                                  [Undo]   │  <- after ✕
   │ [x] Auto-send       Send to [Claude ▾] [Send]        [Copy all] │
   └─────────────────────────────────────────────────────────────────┘

The panel never changes files itself; it calls Session methods
(set_note / move / remove / undo_remove), and the Session notifies the panel back.
So the panel always shows what's really on disk.

Rows are kept per shot id and reused (not rebuilt from scratch) so that
clicking ↑ while typing a note doesn't destroy the button under your mouse.
"""

import os
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

import targets
from theme import make_glass

THUMB_SIZE = (160, 100)
UNDO_SECONDS = 10


class _ShotRow(QFrame):
    def __init__(self, panel, shot):
        super().__init__()
        self.setObjectName("row")
        self.shot_id = shot.id

        self.num = QLabel()
        self.num.setObjectName("num")

        thumb = QLabel()
        pixmap = QPixmap(str(panel.session.image_path(shot)))
        thumb.setPixmap(pixmap.scaled(*THUMB_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        thumb.setFixedSize(*THUMB_SIZE)
        thumb.setAlignment(Qt.AlignCenter)

        window = QLabel(shot.window_title or "—")
        window.setObjectName("window")
        window.setToolTip(shot.window_title)
        window.setMaximumWidth(260)

        self.note = QLineEdit(shot.note)
        self.note.setPlaceholderText("Add a note…")
        self.note.editingFinished.connect(lambda: self._save_note(panel.session))
        self.note.returnPressed.connect(self.note.clearFocus)

        buttons = QHBoxLayout()
        for text, tip, action in (
            ("↑", "Move up", lambda: panel.session.move(self.shot_id, -1)),
            ("↓", "Move down", lambda: panel.session.move(self.shot_id, +1)),
            ("✕", "Delete this screenshot (you can undo)", lambda: panel.delete_shot(self.shot_id)),
        ):
            button = QPushButton(text)
            button.setObjectName("small")
            button.setToolTip(tip)
            button.clicked.connect(action)
            buttons.addWidget(button)

        top = QHBoxLayout()
        top.addWidget(window, 1)
        top.addLayout(buttons)

        right = QVBoxLayout()
        right.addLayout(top)
        right.addWidget(self.note)
        right.addStretch()

        layout = QHBoxLayout(self)
        layout.addWidget(self.num, 0, Qt.AlignTop)
        layout.addWidget(thumb)
        layout.addLayout(right, 1)

    def _save_note(self, session):
        try:
            if self.note.text().strip() != session.get(self.shot_id).note:
                session.set_note(self.shot_id, self.note.text())
        except KeyError:
            pass  # the shot was just deleted

    def update_from(self, number, shot):
        self.num.setText(str(number))
        # Don't overwrite what the user is typing right now.
        if not self.note.hasFocus() and self.note.text() != shot.note:
            self.note.setText(shot.note)


class SessionPanel(QWidget):
    new_session_requested = Signal()
    copy_all_requested = Signal()
    send_to_browser_requested = Signal()
    settings_requested = Signal()
    autosend_toggled = Signal(bool)
    target_changed = Signal(str)

    def __init__(self, session):
        super().__init__()
        self.setWindowTitle("qwhip")
        self.resize(680, 680)
        surface, self.glass = make_glass(self)
        self.session = None
        self._rows = {}  # shot id -> _ShotRow

        # ---- top bar ----
        self.header = QLabel()
        open_button = QPushButton("Open folder")
        open_button.clicked.connect(lambda: os.startfile(self.session.folder))
        new_button = QPushButton("New session")
        new_button.setToolTip("Start a fresh, empty session (the current one stays saved)")
        new_button.clicked.connect(self.new_session_requested)
        settings_button = QPushButton("⚙")
        settings_button.setToolTip("Settings")
        settings_button.clicked.connect(self.settings_requested)

        top = QHBoxLayout()
        top.addWidget(self.header, 1)
        top.addWidget(open_button)
        top.addWidget(new_button)
        top.addWidget(settings_button)

        # ---- list of shots ----
        self.empty = QLabel()
        self.empty.setObjectName("empty")
        self.empty.setAlignment(Qt.AlignCenter)

        self.list_layout = QVBoxLayout()
        self.list_layout.setSpacing(8)
        container = QWidget()
        column = QVBoxLayout(container)
        column.setContentsMargins(0, 0, 4, 0)
        column.addWidget(self.empty)
        column.addLayout(self.list_layout)
        column.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)

        # ---- notice bar (e.g. "No Claude tab is open") ----
        self.notice = QFrame()
        self.notice.setObjectName("notice")
        self.notice_label = QLabel()
        self.notice_label.setWordWrap(True)
        self.notice_button = QPushButton()
        self._notice_action = None
        self.notice_button.clicked.connect(self._run_notice_action)
        close_notice = QPushButton("×")
        close_notice.setObjectName("small")
        close_notice.clicked.connect(self.hide_notice)
        notice_row = QHBoxLayout(self.notice)
        notice_row.setContentsMargins(12, 6, 6, 6)
        notice_row.addWidget(self.notice_label, 1)
        notice_row.addWidget(self.notice_button)
        notice_row.addWidget(close_notice)
        self.notice.hide()

        # ---- undo bar (hidden until something is deleted) ----
        self.undo_bar = QFrame()
        self.undo_bar.setObjectName("undo")
        self.undo_label = QLabel()
        undo_button = QPushButton("Undo")
        undo_button.setToolTip("Bring the screenshot back (Ctrl+Z)")
        undo_button.clicked.connect(self.undo_delete)
        undo_row = QHBoxLayout(self.undo_bar)
        undo_row.setContentsMargins(12, 4, 6, 4)
        undo_row.addWidget(self.undo_label, 1)
        undo_row.addWidget(undo_button)
        self.undo_bar.hide()
        self._undo_timer = QTimer(self)
        self._undo_timer.setSingleShot(True)
        self._undo_timer.timeout.connect(self.undo_bar.hide)
        QShortcut(QKeySequence.Undo, self, activated=self.undo_delete)

        # ---- bottom bar ----
        self.autosend_box = QCheckBox("Auto-send")
        self.autosend_box.setToolTip("Send every new screenshot to the chosen AI right after you write its note")
        self.autosend_box.toggled.connect(self.autosend_toggled)
        self.target_combo = QComboBox()
        self.target_combo.setToolTip("Which AI chat (open in your browser) receives the screenshots")
        for key in targets.TARGETS:
            self.target_combo.addItem(targets.name(key), key)
        self.target_combo.currentIndexChanged.connect(
            lambda: self.target_changed.emit(self.target_combo.currentData()))
        self.send_button = QPushButton("Send")
        self.send_button.setToolTip("Attach every screenshot to the AI chat open in your browser")
        self.send_button.clicked.connect(self.send_to_browser_requested)
        self.copy_button = QPushButton("Copy all")
        self.copy_button.setObjectName("primary")
        self.copy_button.clicked.connect(self.copy_all_requested)

        bottom = QHBoxLayout()
        bottom.addWidget(self.autosend_box)
        bottom.addStretch()
        bottom.addWidget(QLabel("Send to"))
        bottom.addWidget(self.target_combo)
        bottom.addWidget(self.send_button)
        bottom.addSpacing(8)
        bottom.addWidget(self.copy_button)

        layout = QVBoxLayout(surface)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.addLayout(top)
        layout.addWidget(scroll, 1)
        layout.addWidget(self.notice)
        layout.addWidget(self.undo_bar)
        layout.addLayout(bottom)

        self.set_hotkey_hints("Ctrl+Alt+S", "Ctrl+Alt+C")
        self.set_session(session)

    # ---- outside updates ----
    def set_session(self, session):
        """Show a different session (e.g. after 'New session')."""
        if self.session:
            self.session.unsubscribe(self.refresh)
        for row in self._rows.values():
            self._drop(row)
        self._rows = {}
        self.undo_bar.hide()
        self.session = session
        session.subscribe(self.refresh)
        self.refresh()

    def set_autosend(self, enabled):
        """Update the checkbox without re-announcing the change."""
        self.autosend_box.blockSignals(True)
        self.autosend_box.setChecked(enabled)
        self.autosend_box.blockSignals(False)

    def set_target(self, key):
        self.target_combo.blockSignals(True)
        self.target_combo.setCurrentIndex(list(targets.TARGETS).index(key))
        self.target_combo.blockSignals(False)

    def set_hotkey_hints(self, capture, copy_all):
        self.empty.setText(f"No screenshots yet.\nPress {capture} to capture.")
        self.copy_button.setToolTip(f"Put every screenshot + note on the clipboard ({copy_all}), "
                                    "then paste anywhere with Ctrl+V")

    # ---- notices ----
    def show_notice(self, text, action_text=None, action=None):
        self.notice_label.setText(text)
        self._notice_action = action
        self.notice_button.setText(action_text or "")
        self.notice_button.setVisible(bool(action_text))
        self.notice.show()

    def hide_notice(self):
        self.notice.hide()

    def _run_notice_action(self):
        if self._notice_action:
            self._notice_action()
        self.hide_notice()

    # ---- delete / undo ----
    def delete_shot(self, shot_id):
        number = [s.id for s in self.session.shots].index(shot_id) + 1
        note = self.session.get(shot_id).note
        self.session.remove(shot_id)
        label = f"Deleted #{number}" + (f" “{note[:40]}”" if note else "")
        self.undo_label.setText(label)
        self.undo_bar.show()
        self._undo_timer.start(UNDO_SECONDS * 1000)

    def undo_delete(self):
        if self.session.undo_remove():
            if not self.session.can_undo():
                self.undo_bar.hide()
            else:
                self.undo_label.setText("Restored. Undo again for the one before.")
                self._undo_timer.start(UNDO_SECONDS * 1000)

    # ---- drawing ----
    def refresh(self):
        """Make the rows match the session: add new, remove deleted, fix order."""
        ids = [shot.id for shot in self.session.shots]
        for shot_id in list(self._rows):
            if shot_id not in ids:
                self._drop(self._rows.pop(shot_id))
        for number, shot in enumerate(self.session.shots, start=1):
            row = self._rows.get(shot.id)
            if row is None:
                row = self._rows[shot.id] = _ShotRow(self, shot)
            self.list_layout.insertWidget(number - 1, row)  # also moves existing rows into place
            row.update_from(number, shot)

        count = len(self.session)
        started = datetime.fromisoformat(self.session.created_at).strftime("%b %d, %H:%M")
        self.header.setText(f"<b>Session</b> · {started} · {count} shot{'s' if count != 1 else ''}")
        self.empty.setVisible(count == 0)
        self.copy_button.setEnabled(count > 0)
        self.send_button.setEnabled(count > 0)

    def show_status(self, text, ms=2000):
        """Briefly show a message on the Copy button, e.g. 'Copied 3 ✓'."""
        self.copy_button.setText(text)
        QTimer.singleShot(ms, lambda: self.copy_button.setText("Copy all"))

    def _drop(self, row):
        # Remove from the screen right away; Qt frees the memory a moment later.
        row.hide()
        self.list_layout.removeWidget(row)
        row.deleteLater()

    def toggle(self):
        if self.isVisible() and self.isActiveWindow():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()


if __name__ == "__main__":
    # The full app (capture -> note -> panel -> copy all) now lives in main.py.
    import sys

    from main import main

    sys.exit(main())

"""
Settings window.

   Hotkeys            Capture / Show panel / Copy all            [Reset to defaults]
   Send to            AI: [Claude ▾]   [ ] Auto-send each capture   [x] Caption strip
   Browser extension  ● Connected  /  ○ Not detected yet
                      1. [Open extensions page in: Chrome ▾]
                      2. Turn on "Developer mode" (top right)
                      3. "Load unpacked" -> pick this folder   [Copy folder path] [Show folder]
   Claude Desktop     ● Connected          [Connect] / [Disconnect]
   System             [ ] Start qwhip when Windows starts
                                                                  [Cancel] [Save]

Hotkeys/send/system changes are applied on Save through an `apply` function (from
main.py); if that fails (e.g. a hotkey is taken) the error is shown and nothing is lost.
The extension and Claude Desktop buttons act immediately: they're one-off setup actions.
"""

import copy
import os

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout, QKeySequenceEdit,
    QLabel, QPushButton, QVBoxLayout,
)

import integrations
import targets
from hotkeys import parse_hotkey
from theme import make_glass

DEFAULT_SETTINGS = {
    "hotkeys": {"capture": "ctrl+alt+s", "panel": "ctrl+alt+p", "copy_all": "ctrl+alt+c"},
    "target": targets.DEFAULT_TARGET,
    "autosend": False,
    "captions": True,
}
HOTKEY_LABELS = {"capture": "Capture", "panel": "Show panel", "copy_all": "Copy all"}


def with_defaults(settings):
    """Fill in anything missing (e.g. settings.json from an older version)."""
    merged = copy.deepcopy(DEFAULT_SETTINGS)
    for key, value in settings.items():
        if key not in merged:
            continue  # drop settings that no longer exist
        if isinstance(value, dict):
            merged[key].update(value)
        else:
            merged[key] = value
    if merged["target"] not in targets.TARGETS:
        merged["target"] = targets.DEFAULT_TARGET
    return merged


def to_qt(combo):
    """'ctrl+alt+s' -> QKeySequence('Ctrl+Alt+S')"""
    parts = ["Meta" if p == "win" else p.capitalize() for p in combo.split("+")]
    return QKeySequence("+".join(parts))


def from_qt(sequence):
    """QKeySequence('Ctrl+Alt+S') -> 'ctrl+alt+s' (our format)"""
    text = sequence.toString(QKeySequence.PortableText).lower()
    return text.replace("meta", "win")


def _status(label, ok, text):
    label.setObjectName("ok" if ok else "bad")
    label.setText(("● " if ok else "○ ") + text)
    label.style().unpolish(label)  # re-apply the stylesheet for the new object name
    label.style().polish(label)


class SettingsDialog(QDialog):
    def __init__(self, settings, startup_enabled, apply, extension_connected=lambda: False, parent=None):
        """apply(new_settings, startup_enabled) -> error message, or None if it worked.
        extension_connected() -> True if the browser extension has talked to qwhip recently."""
        super().__init__(parent)
        self.setWindowTitle("qwhip settings")
        self.setMinimumWidth(520)
        surface, self.glass = make_glass(self)
        self._apply = apply
        self._extension_connected = extension_connected
        settings = with_defaults(settings)

        # ---- hotkeys ----
        self.key_edits = {}
        hotkey_form = QFormLayout()
        for name, label in HOTKEY_LABELS.items():
            edit = QKeySequenceEdit(to_qt(settings["hotkeys"][name]))
            edit.setMaximumSequenceLength(1)  # one combo, not a sequence of several
            self.key_edits[name] = edit
            hotkey_form.addRow(label, edit)
        reset = QPushButton("Reset to defaults")
        reset.clicked.connect(self._reset_hotkeys)
        hint = QLabel("Click a box, then press the new combination, e.g. Ctrl+Alt+S.")
        hint.setObjectName("hint")
        hotkey_box = QGroupBox("Hotkeys")
        hotkey_layout = QVBoxLayout(hotkey_box)
        hotkey_layout.addLayout(hotkey_form)
        hotkey_layout.addWidget(hint)
        hotkey_layout.addWidget(reset)

        # ---- send to ----
        self.target_combo = QComboBox()
        for key in targets.TARGETS:
            self.target_combo.addItem(targets.name(key), key)
        self.target_combo.setCurrentIndex(list(targets.TARGETS).index(settings["target"]))
        self.autosend_box = QCheckBox("Auto-send each capture")
        self.autosend_box.setChecked(settings["autosend"])
        self.captions_box = QCheckBox("Add caption strip (number + note) to images")
        self.captions_box.setChecked(settings["captions"])
        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("AI chat:"))
        target_row.addWidget(self.target_combo)
        target_row.addStretch()
        send_box = QGroupBox("Send to")
        send_layout = QVBoxLayout(send_box)
        send_layout.addLayout(target_row)
        send_layout.addWidget(self.autosend_box)
        send_layout.addWidget(self.captions_box)

        # ---- browser extension setup ----
        self.extension_status = QLabel()
        browsers = integrations.installed_browsers()
        self.browser_combo = QComboBox()
        for name, path in browsers.items():
            self.browser_combo.addItem(name, path)
        open_page = QPushButton("Open extensions page")
        open_page.setEnabled(bool(browsers))
        open_page.clicked.connect(self._open_extensions_page)
        step1 = QHBoxLayout()
        step1.addWidget(QLabel("1."))
        step1.addWidget(open_page)
        step1.addWidget(QLabel("in"))
        step1.addWidget(self.browser_combo)
        step1.addStretch()
        copy_path = QPushButton("Copy folder path")
        copy_path.setToolTip(str(integrations.extension_folder()))
        copy_path.clicked.connect(self._copy_extension_path)
        show_folder = QPushButton("Show folder")
        show_folder.clicked.connect(lambda: os.startfile(integrations.extension_folder()))
        step3 = QHBoxLayout()
        step3.addWidget(QLabel("3. Click <b>Load unpacked</b> and choose the qwhip extension folder:"))
        step3.addStretch()
        step3_buttons = QHBoxLayout()
        step3_buttons.addSpacing(18)
        step3_buttons.addWidget(copy_path)
        step3_buttons.addWidget(show_folder)
        step3_buttons.addStretch()
        extension_hint = QLabel("Tip: in the folder picker, paste the copied path into the address bar.")
        extension_hint.setObjectName("hint")
        extension_box = QGroupBox("Browser extension (for Send to browser)")
        extension_layout = QVBoxLayout(extension_box)
        extension_layout.addWidget(self.extension_status)
        extension_layout.addLayout(step1)
        extension_layout.addWidget(QLabel("2. Turn on <b>Developer mode</b> (switch in the top-right corner)"))
        extension_layout.addLayout(step3)
        extension_layout.addLayout(step3_buttons)
        extension_layout.addWidget(extension_hint)

        # ---- Claude Desktop ----
        self.claude_status = QLabel()
        self.claude_button = QPushButton()
        self.claude_button.clicked.connect(self._toggle_claude_desktop)
        claude_row = QHBoxLayout()
        claude_row.addWidget(self.claude_status, 1)
        claude_row.addWidget(self.claude_button)
        claude_hint = QLabel("Lets Claude Desktop read your sessions: ask it “look at my qwhip screenshots”.")
        claude_hint.setObjectName("hint")
        claude_hint.setWordWrap(True)
        claude_box = QGroupBox("Claude Desktop app")
        claude_layout = QVBoxLayout(claude_box)
        claude_layout.addLayout(claude_row)
        claude_layout.addWidget(claude_hint)

        # ---- system ----
        self.startup_box = QCheckBox("Start qwhip when Windows starts")
        self.startup_box.setChecked(startup_enabled)
        system_box = QGroupBox("System")
        QVBoxLayout(system_box).addWidget(self.startup_box)

        # ---- buttons ----
        self.error = QLabel()
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        self.error.hide()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.setObjectName("primary")
        save.setDefault(True)
        save.clicked.connect(self._save)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(save)

        layout = QVBoxLayout(surface)
        for widget in (hotkey_box, send_box, extension_box, claude_box, system_box, self.error):
            layout.addWidget(widget)
        layout.addLayout(buttons)

        # Live status: e.g. turns green the moment the extension is loaded.
        self._refresh_status()
        self._timer = QTimer(self, interval=1000, timeout=self._refresh_status)
        self._timer.start()

    # ---- status ----
    def _refresh_status(self):
        if self._extension_connected():
            _status(self.extension_status, True, "Connected: the extension is talking to qwhip")
        else:
            _status(self.extension_status, False, "Not detected yet. Set it up below, then open an AI chat tab.")
        state = integrations.claude_desktop_status()
        texts = {
            "connected": "Connected",
            "outdated": "Connected to an older copy of qwhip: click Reconnect",
            "not connected": "Not connected",
            "missing": "Claude Desktop isn't installed",
        }
        _status(self.claude_status, state == "connected", texts[state])
        self.claude_button.setText({"connected": "Disconnect", "outdated": "Reconnect"}.get(state, "Connect"))
        self.claude_button.setEnabled(state != "missing")

    # ---- actions ----
    def _open_extensions_page(self):
        integrations.open_extensions_page(self.browser_combo.currentText(), self.browser_combo.currentData())

    def _copy_extension_path(self):
        QGuiApplication.clipboard().setText(str(integrations.extension_folder()))
        self._show_message("Folder path copied.", ok=True)

    def _toggle_claude_desktop(self):
        try:
            if integrations.claude_desktop_status() == "connected":
                integrations.disconnect_claude_desktop()
                self._show_message("Disconnected. Restart Claude Desktop to apply.", ok=True)
            else:
                integrations.connect_claude_desktop()
                self._show_message("Connected! Fully quit Claude Desktop (tray icon → Quit) and reopen it.",
                                   ok=True)
        except (RuntimeError, OSError) as e:
            self._show_message(str(e), ok=False)
        self._refresh_status()

    def _show_message(self, text, ok):
        self.error.setObjectName("ok" if ok else "error")
        self.error.style().unpolish(self.error)
        self.error.style().polish(self.error)
        self.error.setText(text)
        self.error.show()

    def _reset_hotkeys(self):
        for name, edit in self.key_edits.items():
            edit.setKeySequence(to_qt(DEFAULT_SETTINGS["hotkeys"][name]))

    # ---- save ----
    def values(self):
        return {
            "hotkeys": {name: from_qt(edit.keySequence()) for name, edit in self.key_edits.items()},
            "target": self.target_combo.currentData(),
            "autosend": self.autosend_box.isChecked(),
            "captions": self.captions_box.isChecked(),
        }

    def validate(self, values):
        """Return an error message, or None if the hotkeys are usable."""
        combos = values["hotkeys"]
        for name, combo in combos.items():
            if not combo:
                return f"{HOTKEY_LABELS[name]}: please set a key combination."
            try:
                mods, _ = parse_hotkey(combo)
            except ValueError:
                return (f"{HOTKEY_LABELS[name]}: '{combo}' isn't supported. "
                        "Use a letter, digit or F1-F24 with modifiers.")
            if not mods & 0x000F:  # no ctrl/alt/shift/win -> would block normal typing
                return f"{HOTKEY_LABELS[name]}: add Ctrl, Alt, Shift or Win, so normal typing still works."
        if len(set(combos.values())) < len(combos):
            return "Two actions use the same hotkey."
        return None

    def _save(self):
        values = self.values()
        error = self.validate(values) or self._apply(values, self.startup_box.isChecked())
        if error:
            self._show_message(error, ok=False)
        else:
            self.accept()

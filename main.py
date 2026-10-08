"""
Step 7: The app.

Ties everything together and lives in the system tray (bottom-right, near the clock).

  Ctrl+Alt+S   capture a screenshot (+ note popup)
  Ctrl+Alt+P   show / hide the session panel
  Ctrl+Alt+C   copy the whole session -> paste anywhere with Ctrl+V
  (all three can be changed in Settings)

  Left-click the tray icon = show/hide the panel. Right-click = menu.

  Browser (needs the qwhip extension; set it up in Settings):
    "Send to [Claude ▾]"   attach the whole session to that AI chat open in your browser
    "Auto-send"            every capture is attached right after you write its note

Run without a console window:   pythonw main.py
"""

import ctypes
import json
import os
import signal
import sys

from PySide6.QtCore import QLockFile, QRectF, Qt, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

import startup
import targets
from bridge import Bridge
from capture import RegionCapture
from export import caption_image, copy_session, summary_text
from hotkeys import HotkeyManager
from note_popup import NotePopup
from panel import SessionPanel
from session import DEFAULT_ROOT, SessionStore
from settings_dialog import SettingsDialog, with_defaults

SETTINGS_FILE = DEFAULT_ROOT.parent / "settings.json"


def pretty(combo):
    """'ctrl+alt+s' -> 'Ctrl+Alt+S' for menus and messages."""
    return "+".join(part.capitalize() for part in combo.split("+"))


def make_icon(size=64):
    """Draw the tray icon in code: two stacked 'screenshots' (no image file needed)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size / 64, size / 64)  # the shapes below are drawn on a 64x64 grid
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#8bb4ff"))
    p.drawRoundedRect(QRectF(16, 6, 42, 34), 7, 7)  # back card
    p.setBrush(QColor("#2f6feb"))
    p.drawRoundedRect(QRectF(6, 20, 46, 38), 8, 8)  # front card
    p.setBrush(QColor("white"))
    p.drawEllipse(QRectF(21, 31, 16, 16))           # camera lens
    p.end()
    return QIcon(pixmap)


class QwhipApp:
    def __init__(self, store=None, register_hotkeys=True, bridge=None, settings_file=SETTINGS_FILE):
        self.store = store or SessionStore()
        self.settings_file = settings_file
        first_run = not self.settings_file.exists()
        self.settings = with_defaults(self._load_settings())
        self.capture = RegionCapture()
        self.panel = SessionPanel(self.store.current())
        self.popup = None
        self._actions = {"capture": self.start_capture, "panel": self.panel.toggle, "copy_all": self.copy_all}

        self.bridge = bridge or Bridge()
        try:
            self.bridge.start()
            self.bridge_ok = True
        except OSError:  # port already used by some other program
            self.bridge_ok = False

        self.capture.captured.connect(self.on_captured)
        self.panel.new_session_requested.connect(self.new_session)
        self.panel.copy_all_requested.connect(self.copy_all)
        self.panel.send_to_browser_requested.connect(self.send_session_to_browser)
        self.panel.settings_requested.connect(self.open_settings)
        self.panel.autosend_toggled.connect(self.set_autosend)
        self.panel.target_changed.connect(self.set_target)
        self.panel.set_autosend(self.settings["autosend"])
        self.panel.set_target(self.settings["target"])

        icon = make_icon()
        self.panel.setWindowIcon(icon)
        self.tray = QSystemTrayIcon(icon)
        self.tray.setToolTip("qwhip — screenshot sessions for AI")
        self._update_hotkey_labels()
        self.tray.activated.connect(self._on_tray_click)
        self._message_action = None  # what clicking the last notification does
        self.tray.messageClicked.connect(lambda: self._message_action and self._message_action())
        self.tray.show()
        if not self.bridge_ok:
            self.notify("Browser bridge unavailable",
                        "Port 47831 is in use, so sending to the browser won't work.")

        if first_run:
            # Welcome a new user: show the panel and point them at the one-time setup.
            self._save_settings()
            keys = self.settings["hotkeys"]
            self.panel.show_notice(
                f"Welcome to qwhip! Press {pretty(keys['capture'])} to capture. To send screenshots "
                "straight into Claude, ChatGPT, Gemini or DeepSeek, set up the browser extension once.",
                "Set up", self.open_settings)
            self.show_panel()

        self.hotkeys = None
        if register_hotkeys:
            self.hotkeys, failed = self._register_hotkeys(self.settings["hotkeys"])
            keys = self.settings["hotkeys"]
            if failed:
                self.notify("Some hotkeys are taken by another app",
                            ", ".join(failed) + " won't work. Change them in Settings.")
            else:
                self.notify("qwhip is running", f"{pretty(keys['capture'])} to capture · "
                                                f"{pretty(keys['copy_all'])} to copy all")

    # ---- settings (remembered between restarts) ----
    def _load_settings(self):
        try:
            return json.loads(self.settings_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_settings(self):
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        self.settings_file.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")

    def _register_hotkeys(self, combos):
        manager = HotkeyManager(combos)
        manager.triggered.connect(lambda name: self._actions[name]())
        failed = manager.start()
        return manager, failed

    def _update_hotkey_labels(self):
        keys = self.settings["hotkeys"]
        self.panel.set_hotkey_hints(pretty(keys["capture"]), pretty(keys["copy_all"]))
        self.tray.setContextMenu(self._build_menu())

    def open_settings(self):
        extension_connected = self.bridge.extension_seen if self.bridge_ok else (lambda: False)
        dialog = SettingsDialog(self.settings, startup.is_enabled(), self.apply_settings, extension_connected)
        dialog.setWindowIcon(self.tray.icon())
        dialog.exec()

    def apply_settings(self, new, start_with_windows):
        """Called by the Settings dialog. Returns an error message, or None on success."""
        if new["hotkeys"] != self.settings["hotkeys"] and self.hotkeys:
            self.hotkeys.stop()
            manager, failed = self._register_hotkeys(new["hotkeys"])
            if failed:
                manager.stop()
                self.hotkeys, _ = self._register_hotkeys(self.settings["hotkeys"])  # put the old ones back
                return f"Already used by another app: {', '.join(failed)}. Pick a different combination."
            self.hotkeys = manager

        if start_with_windows != startup.is_enabled():
            try:
                startup.set_enabled(start_with_windows)
            except OSError as e:
                return f"Couldn't change the Windows startup setting: {e}"

        self.settings.update(new)
        self._save_settings()
        self.panel.set_autosend(new["autosend"])
        self.panel.set_target(new["target"])
        self._update_hotkey_labels()
        return None

    # ---- tray ----
    def _build_menu(self):
        keys = self.settings["hotkeys"]
        menu = QMenu()

        def add(text, slot):
            action = QAction(text, menu)
            action.triggered.connect(slot)
            menu.addAction(action)

        add(f"Capture\t{pretty(keys['capture'])}", self.start_capture)
        add(f"Show session\t{pretty(keys['panel'])}", self.show_panel)
        add(f"Copy all\t{pretty(keys['copy_all'])}", self.copy_all)
        menu.addSeparator()
        add("Send session to browser", self.send_session_to_browser)
        self.autosend_action = QAction("Auto-send each capture", menu)
        self.autosend_action.setCheckable(True)
        self.autosend_action.setChecked(self.settings["autosend"])
        self.autosend_action.toggled.connect(self.set_autosend)
        menu.addAction(self.autosend_action)
        menu.addSeparator()
        add("New session", self.new_session)
        add("Open sessions folder", lambda: os.startfile(self.store.root))
        add("Settings…", self.open_settings)
        menu.addSeparator()
        add("Quit", QApplication.quit)

        self._menu = menu  # keep a reference so Python doesn't garbage-collect it
        return menu

    def _on_tray_click(self, reason):
        if reason == QSystemTrayIcon.Trigger:  # plain left click
            self.panel.toggle()

    def notify(self, title, message, on_click=None):
        self._message_action = on_click
        self.tray.showMessage(title, message, QSystemTrayIcon.Information, 4000)

    # ---- actions ----
    def start_capture(self):
        if self.popup:
            self.popup.commit()  # finish the previous note first
        self.capture.start()

    def on_captured(self, image, window_title):
        session = self.panel.session
        shot = session.add_shot(image, window_title)
        popup = NotePopup(len(session), image, window_title)

        def on_note(text):
            self.popup = None
            if not any(s.id == shot.id for s in session.shots):  # deleted meanwhile
                return
            session.set_note(shot.id, text)
            if self.settings["autosend"]:
                current = session.get(shot.id)
                number = session.shots.index(current) + 1
                self._send_to_browser(session, [current], f"{number}. {text}\n" if text else "")

        popup.finished.connect(on_note)
        self.popup = popup
        popup.open_near_cursor()

    def show_panel(self):
        self.panel.show()
        self.panel.raise_()
        self.panel.activateWindow()

    def copy_all(self):
        if self.popup:
            self.popup.commit()  # include the note you were just typing
        count = copy_session(self.panel.session, captions=self.settings["captions"])
        if count:
            self.panel.show_status(f"Copied {count} ✓")
            self.notify(f"Copied {count} screenshot{'s' if count != 1 else ''}",
                        "Paste into your AI chat with Ctrl+V")
        else:
            self.panel.show_status("Nothing to copy")
            self.notify("Nothing to copy", f"Take a screenshot first with "
                                           f"{pretty(self.settings['hotkeys']['capture'])}")

    def new_session(self):
        if len(self.panel.session) > 0:  # don't pile up empty sessions
            self.panel.session.empty_trash()
            self.panel.set_session(self.store.new_session())
        self.notify("New session started", "Your previous session is still saved")

    # ---- browser (Step 9) ----
    def set_autosend(self, enabled):
        if enabled == self.settings["autosend"]:
            return
        self.settings["autosend"] = enabled
        self._save_settings()
        # Keep the panel checkbox and the tray menu item in sync.
        self.panel.set_autosend(enabled)
        self.autosend_action.blockSignals(True)
        self.autosend_action.setChecked(enabled)
        self.autosend_action.blockSignals(False)
        if enabled:
            self.notify("Auto-send is on", f"Each capture will be attached to your open "
                                           f"{targets.name(self.settings['target'])} tab.")

    def set_target(self, key):
        self.settings["target"] = key
        self._save_settings()
        self.panel.hide_notice()

    def send_session_to_browser(self):
        if self.popup:
            self.popup.commit()
        session = self.panel.session
        if len(session) == 0:
            self.notify("Nothing to send", "Take a screenshot first.")
            return
        self._send_to_browser(session, session.shots, summary_text(session), focus=True)

    def _send_to_browser(self, session, shots, text, focus=False):
        if not self.bridge_ok:
            self.notify("Browser bridge unavailable", "Port 47831 is in use by another program.")
            return
        images = []
        for shot in shots:
            number = session.shots.index(shot) + 1
            image = QImage(str(session.image_path(shot)))
            if self.settings["captions"]:
                image = caption_image(image, number, shot.note, shot.window_title)
            images.append((number, image))
        key = self.settings["target"]
        name, site, chat_url = targets.name(key), targets.host(key), targets.url(key)
        if focus:
            # Let the browser bring its tab to the front (Windows only allows that if the
            # app you're using, us, says it's OK).
            ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
        self.bridge.send(site, images, text, focus=focus)

        def open_chat():
            QDesktopServices.openUrl(QUrl(chat_url))

        if not self.bridge.extension_seen():
            self.panel.show_notice("The qwhip browser extension isn't connected yet. "
                                   "Set it up once in Settings.", "Set up", self.open_settings)
            self.notify("Browser extension not connected", "Open qwhip Settings to set it up.",
                        on_click=self.open_settings)
        elif not self.bridge.tab_open(site):
            self.panel.show_notice(f"No {name} tab is open. Open one within 2 minutes and the "
                                   f"screenshots will appear there.", f"Open {name}", open_chat)
            self.notify(f"No {name} tab is open", f"Click here to open {name}. "
                        "The screenshots will be attached there.", on_click=open_chat)
        else:
            self.panel.hide_notice()
            self.panel.show_status(f"Sent to {name} ✓")

    def shutdown(self):
        if self.hotkeys:
            self.hotkeys.stop()
        if self.bridge_ok:
            self.bridge.stop()
        self.tray.hide()


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)  # Ctrl+C in the terminal quits immediately
    app = QApplication(sys.argv)
    app.setApplicationName("qwhip")
    app.setQuitOnLastWindowClosed(False)  # closing the panel just hides it; the tray keeps running
    if "--check" in sys.argv:
        return 0  # used by the build script: "everything imports and Qt starts"

    # Only one copy may run: a second one couldn't register the hotkeys anyway.
    DEFAULT_ROOT.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(DEFAULT_ROOT.parent / "qwhip.lock"))
    if not lock.tryLock(100):
        QMessageBox.information(None, "qwhip", "qwhip is already running — look for its icon in the tray.")
        return 0

    qwhip = QwhipApp()
    app.aboutToQuit.connect(qwhip.shutdown)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

"""
Step 1: Global hotkeys.

Asks Windows to notify us when a key combo (e.g. Ctrl+Alt+S) is pressed,
even when our app is not the focused window.

How it works:
  1. A background thread calls RegisterHotKey() for each combo.
  2. That thread then waits in a loop for Windows messages (GetMessage).
  3. When a WM_HOTKEY message arrives, we emit a Qt signal.
  4. The Qt signal safely hands the event to the main (GUI) thread.
"""

import ctypes
import threading
from ctypes import wintypes

from PySide6.QtCore import QObject, Signal

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# Tell ctypes the exact argument types of the Windows functions we call.
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

# Modifier flags and message ids from the Windows API docs.
MODIFIERS = {"ctrl": 0x0002, "alt": 0x0001, "shift": 0x0004, "win": 0x0008}
MOD_NOREPEAT = 0x4000  # holding the keys down fires only once
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012


def parse_hotkey(text):
    """Turn 'ctrl+alt+s' into (modifier_flags, virtual_key_code)."""
    mods = MOD_NOREPEAT
    key = None
    for part in text.lower().replace(" ", "").split("+"):
        if part in MODIFIERS:
            mods |= MODIFIERS[part]
        elif len(part) == 1 and part.isalnum():
            key = ord(part.upper())  # 'A'-'Z' and '0'-'9' are their ASCII codes
        elif part.startswith("f") and part[1:].isdigit() and 1 <= int(part[1:]) <= 24:
            key = 0x70 + int(part[1:]) - 1  # F1 = 0x70
        else:
            raise ValueError(f"Unknown key '{part}' in hotkey '{text}'")
    if key is None:
        raise ValueError(f"Hotkey '{text}' has no main key")
    return mods, key


class HotkeyManager(QObject):
    """Listens for global hotkeys and emits `triggered(name)` when one is pressed."""

    triggered = Signal(str)

    def __init__(self, hotkeys):
        """hotkeys: dict like {"capture": "ctrl+alt+s", "panel": "ctrl+alt+p"}"""
        super().__init__()
        self._hotkeys = {name: parse_hotkey(combo) for name, combo in hotkeys.items()}
        self._combos = hotkeys
        self._thread = None
        self._thread_id = None
        self._failed = []

    def start(self):
        """Start listening. Returns a list of hotkeys that could not be registered."""
        ready = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(ready,), daemon=True)
        self._thread.start()
        ready.wait()  # wait until registration is done so we can report failures
        return self._failed

    def stop(self):
        if self._thread_id:
            # Wake up the GetMessage loop so the thread can exit cleanly.
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(timeout=2)

    def _run(self, ready):
        # Hotkeys must be registered and unregistered in the same thread
        # that reads the messages.
        self._thread_id = kernel32.GetCurrentThreadId()
        ids = {}
        for hotkey_id, (name, (mods, key)) in enumerate(self._hotkeys.items(), start=1):
            if user32.RegisterHotKey(None, hotkey_id, mods, key):
                ids[hotkey_id] = name
            else:
                # Usually means another app already owns this combo.
                self._failed.append(f"{name} ({self._combos[name]})")
        ready.set()

        msg = wintypes.MSG()
        # GetMessage blocks until a message arrives; returns 0 on WM_QUIT.
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and msg.wParam in ids:
                self.triggered.emit(ids[msg.wParam])

        for hotkey_id in ids:
            user32.UnregisterHotKey(None, hotkey_id)


if __name__ == "__main__":
    # Quick manual test: run this file, press the hotkeys, watch the output.
    import signal
    import sys

    from PySide6.QtWidgets import QApplication

    signal.signal(signal.SIGINT, signal.SIG_DFL)  # let Ctrl+C in the terminal quit

    app = QApplication(sys.argv)
    manager = HotkeyManager({
        "capture": "ctrl+alt+s",
        "panel": "ctrl+alt+p",
        "copy_all": "ctrl+alt+c",
    })
    manager.triggered.connect(lambda name: print(f"hotkey pressed: {name}", flush=True))
    app.aboutToQuit.connect(manager.stop)

    failed = manager.start()
    if failed:
        print("Could not register (already used by another app?):", ", ".join(failed))
    print("Listening... press Ctrl+Alt+S, Ctrl+Alt+P or Ctrl+Alt+C. Ctrl+C here to quit.", flush=True)
    sys.exit(app.exec())

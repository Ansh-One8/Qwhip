"""
Start qwhip when Windows starts.

Windows launches every program listed under this registry key when you sign in:
    HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
(It's the same list as Task Manager -> Startup apps.)

We add or remove one value named "qwhip". Nothing else in the registry is touched,
and it's only for your user account (HKEY_CURRENT_USER), no admin rights needed.
"""

import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "qwhip"


def launch_command():
    """The command Windows should run at sign-in."""
    if getattr(sys, "frozen", False):  # running as the packaged qwhip.exe
        return f'"{sys.executable}"'
    # Running from source: use pythonw.exe (no console window) next to python.exe.
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    main_py = Path(__file__).resolve().with_name("main.py")
    return f'"{pythonw}" "{main_py}"'


def is_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
            return True
    except FileNotFoundError:
        return False


def set_enabled(enabled):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass  # already off

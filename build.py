"""
Build a shareable qwhip for Windows:

    python build.py

Result (in the project's release/ folder):
    qwhip-windows.zip      the app folder zipped: qwhip.exe, qwhip-mcp.exe, extension/, README.txt
    qwhip-setup.exe        the installer (only if Inno Setup 6 is installed)

The build itself happens in %LOCALAPPDATA%\qwhip-build, outside OneDrive, because
OneDrive locks and uploads the hundreds of MB of files a build produces.

Nobody needs Python installed to use any of these.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

VERSION = "0.3.0"
ROOT = Path(__file__).resolve().parent
BUILD = Path(os.environ.get("LOCALAPPDATA", ROOT)) / "qwhip-build"
DIST = BUILD / "dist" / "qwhip"   # the finished app folder
RELEASE = ROOT / "release"        # what you share

README = f"""qwhip {VERSION} — screenshot sessions for AI
==========================================

Start qwhip.exe. It lives in the system tray (click the ^ near the clock).

  Ctrl+Alt+S   capture a screenshot and add a note
  Ctrl+Alt+P   show the session panel
  Ctrl+Alt+C   copy everything -> paste into any AI chat with Ctrl+V

In the panel, "Send to [Claude / ChatGPT / Gemini / DeepSeek]" attaches all your
screenshots straight into that AI chat in your browser.

Everything else is set up from the panel's gear button (Settings), no files to edit:
  * Browser extension: 3 guided clicks (needed for "Send to")
  * Claude Desktop: one "Connect" button
  * Hotkeys, start with Windows, captions

Your screenshots stay on your PC in %LOCALAPPDATA%\\qwhip\\sessions.
"""


def run(*args):
    print(">", " ".join(str(a) for a in args), flush=True)
    subprocess.run(args, cwd=ROOT, check=True)


def find_inno_setup():
    candidates = [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    ]
    found = shutil.which("iscc")
    return Path(found) if found else next((c for c in candidates if c.exists()), None)


def main():
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--workpath", BUILD / "work", "--distpath", BUILD / "dist", "qwhip.spec")

    shutil.rmtree(DIST / "extension", ignore_errors=True)
    shutil.copytree(ROOT / "extension", DIST / "extension")
    (DIST / "README.txt").write_text(README, encoding="utf-8")

    # Smoke test: does the packaged app start (imports + Qt) without errors?
    run(DIST / "qwhip.exe", "--check")

    RELEASE.mkdir(exist_ok=True)
    archive = shutil.make_archive(str(RELEASE / "qwhip-windows"), "zip", DIST.parent, "qwhip")
    print(f"\nApp folder: {DIST}")
    print(f"Zip:        {archive} ({Path(archive).stat().st_size / 1_000_000:.0f} MB)")

    iscc = find_inno_setup()
    if iscc is None:
        print("Installer:  skipped (Inno Setup 6 not found: winget install JRSoftware.InnoSetup)")
        return
    run(iscc, f"/DAppVersion={VERSION}", f"/DSourceDir={DIST}", f"/DOutputDir={RELEASE}", "/Qp", "installer.iss")
    setup = RELEASE / "qwhip-setup.exe"
    print(f"Installer:  {setup} ({setup.stat().st_size / 1_000_000:.0f} MB)")


if __name__ == "__main__":
    main()

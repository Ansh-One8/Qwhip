<p align="center">
  <img src="extension/icon128.png" width="96" alt="qwhip icon">
</p>

<h1 align="center">qwhip</h1>

<p align="center"><b>Screenshot sessions for AI.</b><br>
Capture several screenshots, add a one-line note to each, and send them all to Claude, ChatGPT, Gemini or DeepSeek in a single message.</p>

<p align="center">
  <a href="../../releases/latest"><b>⬇ Download for Windows</b></a>
</p>

---

<!-- Add a short demo GIF here: capture → note → Send. It's the best way to show what qwhip does. -->

## Why

Explaining a bug or a UI problem to an AI usually takes several screenshots, plus words that say what each one shows. Without a tool for it, the loop looks like this: snip, switch to the chat, paste, type, switch back, snip again…

qwhip turns that into one flow:

1. Press **Ctrl+Alt+S** and drag a box. A small popup asks *"What's this?"*. Type a note and press Enter.
2. Repeat as many times as you need.
3. Click **Send**. Every screenshot, numbered and captioned with its note, appears in your AI chat, ready for you to review and send.

## Features

- **Fast capture.** A global hotkey works from any app. Drag to select an area, or click for the full screen. Multi-monitor and display scaling (125%, 150%…) are handled.
- **A note on every screenshot.** Notes are added as text *and* drawn onto the image, so the AI always knows what it's looking at.
- **Window context for free.** qwhip records which window each screenshot came from (e.g. *Chrome – localhost:3000*).
- **Send to any AI chat.** Choose **Claude, ChatGPT, Gemini or DeepSeek**. qwhip attaches the screenshots to the chat open in your browser, but never presses Send for you.
- **Auto-send mode.** Each new screenshot goes to the chat right after you write its note.
- **Copy all.** Puts every screenshot on the clipboard at once, so a single **Ctrl+V** attaches them all in almost any app.
- **Claude Desktop integration (MCP).** Connect with one click, then ask Claude *"look at my qwhip screenshots"*.
- **Session panel.** Reorder shots, edit notes, delete them (with undo), and start new sessions.
- **Helpful messages.** If no tab of your chosen AI is open, qwhip tells you and offers to open one.
- **Frosted-glass interface** on Windows 11.
- **Private by default.** Everything stays on your PC. qwhip has no account, no cloud and no tracking.

## Install

1. Download **`qwhip-setup.exe`** from the [latest release](../../releases/latest) and run it.
   > Windows may show *"Windows protected your PC"* because the app isn't code-signed yet. Click **More info → Run anyway**.
2. qwhip starts and opens its panel with a welcome message. It lives in the **system tray**: click the **^** next to the clock.

Prefer not to install? Download **`qwhip-windows.zip`**, extract it anywhere, and run `qwhip.exe`.

## Set up sending to your AI (one time, about 1 minute)

To send screenshots straight into a chat, qwhip uses a small browser extension that works in Chrome, Brave and Edge. qwhip walks you through it:

1. In the qwhip panel, click **⚙ Settings**, then go to **Browser extension**.
2. Click **Open extensions page**, then turn on **Developer mode** (top-right corner).
3. Click **Load unpacked** and choose the qwhip extension folder. **Copy folder path** in Settings puts its location on your clipboard.

When it works, Settings shows **● Connected**. Open your AI chat in the browser, refreshing it if it was already open, and you're done.

## Using qwhip

| Shortcut | What it does |
|---|---|
| **Ctrl+Alt+S** | Capture a screenshot, then add a note (Enter = save, Esc = skip) |
| **Ctrl+Alt+P** | Show or hide the session panel |
| **Ctrl+Alt+C** | Copy every screenshot to the clipboard. Paste anywhere with Ctrl+V |
| **Ctrl+Z** (in the panel) | Undo the last delete |

You can change every shortcut in **Settings**.

In the panel:
- **Send to [Claude ▾] → Send** attaches the whole session to that AI's chat in your browser and brings the tab to the front.
- **Auto-send** sends each new screenshot as soon as you've written its note.
- **New session** starts fresh. Old sessions stay saved.

### Claude Desktop

In **Settings → Claude Desktop app**, click **Connect**, then fully quit Claude Desktop (tray icon → Quit) and reopen it. Now you can ask Claude Desktop things like:

> *"Look at my latest qwhip screenshots and tell me why the login button doesn't work."*

Claude reads the session directly, with every screenshot, note and window title. No copy-paste needed.

## Privacy

- Screenshots are saved only on your PC, in `%LOCALAPPDATA%\qwhip\sessions`.
- Nothing is uploaded anywhere. Screenshots only reach an AI when *you* click Send, use Copy all, or ask Claude Desktop to read them.
- The browser extension talks only to the qwhip app on your own computer (`127.0.0.1`), and only on the AI chat sites listed above. Other websites can't read your screenshots.
- Unsent screenshots expire from the send queue after 2 minutes, so nothing old pops into a chat later.

## Uninstall

**Windows Settings → Apps → qwhip → Uninstall.** Your saved screenshots are kept. Delete `%LOCALAPPDATA%\qwhip` if you want them gone too. Remove the extension from your browser's extensions page.

---

## For developers

### Run from source

Requires **Python 3.12+** on **Windows 10/11**.

```powershell
git clone <this repo>
cd qwhip
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

Load the extension from the `extension/` folder (see *Set up sending to your AI* above).

### Build the installer

```powershell
python build.py
```

This produces `release/qwhip-windows.zip`, plus `release/qwhip-setup.exe` if [Inno Setup 6](https://jrsoftware.org/isdl.php) is installed. The build runs in `%LOCALAPPDATA%\qwhip-build`.

### How it works

```
 hotkey ──► capture overlay ──► note popup ──► session (PNG files + session.json)
                                                     │
              ┌──────────────────┬───────────────────┼────────────────────┐
              ▼                  ▼                   ▼                    ▼
          Copy all          Send to browser      Claude Desktop        Panel
   (files on clipboard)   (local bridge ──►    (MCP server reads   (reorder, notes,
                          browser extension)    session folders)     delete/undo)
```

| File | Purpose |
|---|---|
| `main.py` | The app: tray icon, wires everything together |
| `hotkeys.py` | Global hotkeys (Windows `RegisterHotKey`) |
| `capture.py` | Fullscreen region-selection overlay |
| `note_popup.py` | The "What's this?" note box |
| `session.py` | Sessions on disk, with undo |
| `panel.py` | Session panel window |
| `export.py` | Caption strips + multi-file clipboard |
| `bridge.py` | Local server the browser extension connects to |
| `extension/` | Browser extension (Manifest V3) |
| `mcp_server.py` | MCP server for Claude Desktop |
| `settings_dialog.py` | Settings window |
| `integrations.py` | Claude Desktop connect, browser detection |
| `theme.py` | Windows 11 Acrylic "glass" look |
| `startup.py` | Start with Windows |
| `targets.py` | Supported AI chat sites |

### Known limitations

- **Windows only** for now.
- **Gemini and DeepSeek** support is new. If screenshots don't attach there, please open an issue.
- The extension is loaded in Developer mode until it's published on the Chrome Web Store.
- The installer isn't code-signed yet, so Windows shows a warning on first run.

## Contributing

Issues and pull requests are welcome. If something doesn't work on your setup, please include your Windows version, browser, and the AI site you were sending to.

## License

<!-- Choose a license (e.g. MIT) and add a LICENSE file. -->

"""
Step 9 (app side): the bridge between qwhip and the browser extension.

Every open AI chat tab (claude.ai, chatgpt.com, ...) keeps ONE request open to us:
"wake me up when there's something for <my site>". We answer as soon as a batch for
that site arrives, or after ~20 s with "nothing" (then the tab simply asks again).

  qwhip app ──send(site=claude.ai)──► outbox ──► the waiting claude.ai tab gets it at once

Why long requests instead of asking every second? Chrome slows down timers in tabs
that are hidden behind other windows (to about once a minute), but it doesn't slow
down a request that's already waiting. So delivery is instant even then, and we
always know which AI tabs are open: those with a waiting request.

Safety:
  * Listens on 127.0.0.1 only: other computers on your network can't reach it.
  * Requires a custom "X-Qwhip" header. Web pages can't send custom headers to
    another site without permission (a CORS "preflight") which we never grant,
    so a random website can't read your screenshots. Only the extension can.
  * Checks the Host header, which blocks "DNS rebinding" tricks.
  * Port opened in exclusive mode, so no other program can listen on it too.
  * Batches expire after 2 minutes, so an old screenshot never pops into a chat later.
"""

import base64
import json
import socket
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PySide6.QtCore import QBuffer, QByteArray, QIODevice

PORT = 47831
EXPIRE_SECONDS = 120
WAIT_SECONDS = 20       # how long a tab's request is held open when there's nothing to send
VISIBLE_HEAD_START = 1  # seconds a visible tab gets to claim a batch before a background tab may


class _ExclusiveServer(ThreadingHTTPServer):
    """On Windows, SO_REUSEADDR lets a second program listen on the same port.
    Ask for exclusive use instead, so nobody else can sit on our port."""

    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows only
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def image_to_base64_png(image):
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return base64.b64encode(bytes(data)).decode("ascii")


class Bridge:
    def __init__(self, port=PORT, wait_seconds=WAIT_SECONDS):
        self.port = port
        self.wait_seconds = wait_seconds
        self._outbox = deque()
        # One lock + condition: the HTTP threads wait on it, send() wakes them up.
        self._changed = threading.Condition()
        self._waiting = {}     # site -> number of tabs waiting right now
        self._last_seen = {}   # site -> time a tab of that site last talked to us
        self._server = None
        self._stopping = False

    # ---- called by the qwhip app ----
    def start(self):
        self._server = _ExclusiveServer(("127.0.0.1", self.port), self._make_handler())
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def stop(self):
        if self._server:
            with self._changed:
                self._stopping = True
                self._outbox.clear()
                self._changed.notify_all()  # release every waiting tab
            self._server.shutdown()
            self._server.server_close()

    def tab_open(self, site, within=3):
        """Is a tab of this site (e.g. 'claude.ai') open with the extension running?"""
        with self._changed:
            return self._waiting.get(site, 0) > 0 or time.time() - self._last_seen.get(site, 0) < within

    def extension_seen(self, within=30):
        """Has the extension talked to us recently (from any site)?"""
        with self._changed:
            recent = max(self._last_seen.values(), default=0)
            return any(self._waiting.values()) or time.time() - recent < within

    def send(self, site, images, text, focus=False):
        """Queue one batch for one site.

        images: list of (number, QImage), attached together as screenshot_<number>.png
        text:   typed into the chat box after the images
        focus:  bring that browser tab to the front after attaching
        """
        batch = {
            "site": site,
            "created": time.time(),
            "text": text,
            "focus": focus,
            "images": [{"name": f"screenshot_{i}.png", "data": image_to_base64_png(img)}
                       for i, img in images],
        }
        with self._changed:
            self._outbox.append(batch)
            self._changed.notify_all()

    # ---- called from the HTTP threads ----
    def _wait_for_batch(self, site, visible):
        deadline = time.time() + self.wait_seconds
        with self._changed:
            self._waiting[site] = self._waiting.get(site, 0) + 1
            try:
                while not self._stopping:
                    self._last_seen[site] = time.time()
                    batch, retry_in = self._take(site, visible)
                    if batch:
                        return batch
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        return None
                    self._changed.wait(min(remaining, retry_in))
                return None
            finally:
                self._waiting[site] -= 1
                self._last_seen[site] = time.time()

    def _take(self, site, visible):
        """(batch, None) if one is ready for this tab, else (None, seconds until worth re-checking)."""
        now = time.time()
        while self._outbox and now - self._outbox[0]["created"] >= EXPIRE_SECONDS:
            self._outbox.popleft()  # too old: drop it
        for batch in self._outbox:
            if batch["site"] != site:
                continue
            age = now - batch["created"]
            if visible or age >= VISIBLE_HEAD_START:  # a visible tab of the same site goes first
                self._outbox.remove(batch)
                return batch, None
            return None, VISIBLE_HEAD_START - age
        return None, self.wait_seconds

    def _make_handler(self):
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                # Always read the whole request first; replying before that makes
                # Windows reset the connection.
                try:
                    length = min(int(self.headers.get("Content-Length") or 0), 10_000)
                except ValueError:
                    length = 0
                body = self.rfile.read(length)
                if self.headers.get("Host") not in {f"127.0.0.1:{bridge.port}", f"localhost:{bridge.port}"} \
                        or self.headers.get("X-Qwhip") != "1":
                    self.send_error(403)
                    return
                if self.path != "/api/next":
                    self.send_error(404)
                    return
                try:
                    info = json.loads(body or b"{}")
                    site, visible = str(info.get("site", "")), bool(info.get("visible", True))
                except (ValueError, AttributeError):
                    site, visible = "", True

                batch = bridge._wait_for_batch(site, visible) if site else None
                if batch is None:
                    self.send_response(204)  # "nothing for you right now, ask again"
                    self.end_headers()
                    return
                data = json.dumps(batch).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass  # keep quiet (pythonw has no console)

        return Handler

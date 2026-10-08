"""
Step 2: Region capture.

When started:
  1. Remember which window was active (free context for the AI later).
  2. Take a picture of every monitor BEFORE showing anything.
  3. Cover each monitor with a fullscreen overlay showing that picture, dimmed.
  4. The user drags a rectangle -> that area is shown un-dimmed.
  5. On mouse release, crop the picture and emit `captured(image, window_title)`.

  Click without dragging = capture that whole monitor.
  Esc or right-click = cancel.

Display scaling: on a 150% screen, Qt coordinates are "logical" (smaller) but the
picture has real pixels (bigger). So when cropping we multiply by the screen's
devicePixelRatio (1.5) to get the right pixels.
"""

import ctypes

from PySide6.QtCore import QObject, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

MIN_DRAG = 5  # smaller than this (in px) counts as a click, not a drag


def active_window_title():
    """Title of the window the user was looking at, e.g. 'Inbox - Gmail - Google Chrome'."""
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


class _Overlay(QWidget):
    """Fullscreen dimmed picture of one monitor where the user drags a box."""

    def __init__(self, controller, screen, pixmap):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self._controller = controller
        self._pixmap = pixmap
        self._dpr = pixmap.devicePixelRatio()
        self._start = None
        self._end = None

        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)
        self.setGeometry(screen.geometry())

    def _selection(self):
        """Selected area in logical coordinates (decimals, for precision at 125%/150%)."""
        if self._start is None:
            return QRectF()
        return QRectF(self._start, self._end).normalized()

    def _to_pixels(self, rect):
        """Logical rect -> rect in the pixmap's real pixels."""
        d = self._dpr
        left, top = round(rect.left() * d), round(rect.top() * d)
        right, bottom = round(rect.right() * d), round(rect.bottom() * d)
        return QRect(left, top, right - left, bottom - top)

    # ---- drawing ----
    def paintEvent(self, event):
        p = QPainter(self)
        p.drawPixmap(0, 0, self._pixmap)
        p.fillRect(self.rect(), QColor(0, 0, 0, 110))  # dim everything

        sel = self._selection()
        if sel.width() > 0 and sel.height() > 0:
            # Re-draw the selected area un-dimmed, then a border around it.
            p.drawPixmap(sel, self._pixmap, QRectF(self._to_pixels(sel)))
            p.setPen(QPen(QColor(80, 160, 255), 2))
            p.drawRect(sel)

            # Size label (in real pixels, since that's the image size you'll get).
            px = self._to_pixels(sel)
            label = f"{px.width()} × {px.height()}"
            label_pos = sel.topLeft() + QPointF(0, -6) if sel.top() > 20 else sel.bottomLeft() + QPointF(0, 16)
            p.setPen(Qt.white)
            p.drawText(label_pos, label)
        else:
            p.setPen(Qt.white)
            p.drawText(self.rect().adjusted(0, 30, 0, 0), Qt.AlignHCenter | Qt.AlignTop,
                       "Drag to capture  ·  Click for full screen  ·  Esc to cancel")

    # ---- mouse / keyboard ----
    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self._controller.cancel()
        elif event.button() == Qt.LeftButton:
            self._start = self._end = event.position()
            self.update()

    def mouseMoveEvent(self, event):
        if self._start is not None:
            self._end = event.position()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or self._start is None:
            return
        sel = self._selection()
        if sel.width() < MIN_DRAG or sel.height() < MIN_DRAG:
            image = self._pixmap.toImage()  # a click = whole monitor
        else:
            image = self._pixmap.copy(self._to_pixels(sel)).toImage()
        image.setDevicePixelRatio(1.0)  # save at real pixel size
        self._controller.finish(image)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._controller.cancel()


class RegionCapture(QObject):
    """Shows overlays on all monitors. Emits `captured(QImage, window_title)` or `cancelled()`."""

    captured = Signal(object, str)
    cancelled = Signal()

    def __init__(self):
        super().__init__()
        self._overlays = []
        self._window_title = ""

    def is_active(self):
        return bool(self._overlays)

    def start(self):
        if self.is_active():
            return  # already capturing; ignore a second hotkey press

        self._window_title = active_window_title()

        # Grab every screen first, so our own overlays aren't in the picture.
        shots = []
        for screen in QGuiApplication.screens():
            pixmap = screen.grabWindow(0)
            pixmap.setDevicePixelRatio(screen.devicePixelRatio())
            shots.append((screen, pixmap))

        cursor_screen = QGuiApplication.screenAt(QCursor.pos())
        for screen, pixmap in shots:
            overlay = _Overlay(self, screen, pixmap)
            overlay.show()
            self._overlays.append(overlay)
            if screen is cursor_screen:
                # Give keyboard focus to the monitor under the mouse so Esc works.
                overlay.raise_()
                overlay.activateWindow()

    def finish(self, image):
        self._close_all()
        self.captured.emit(image, self._window_title)

    def cancel(self):
        self._close_all()
        self.cancelled.emit()

    def _close_all(self):
        for overlay in self._overlays:
            overlay.close()
        self._overlays = []


if __name__ == "__main__":
    # Manual test: Ctrl+Alt+S starts a capture, each result is saved to test_captures/.
    import signal
    import sys
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from hotkeys import HotkeyManager

    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # closing the overlay must not quit the app

    out_dir = Path("test_captures")
    out_dir.mkdir(exist_ok=True)
    capture = RegionCapture()

    def on_captured(image, title):
        path = out_dir / f"shot_{len(list(out_dir.glob('*.png'))) + 1}.png"
        image.save(str(path))
        print(f"saved {path}  ({image.width()}x{image.height()})  window: {title!r}", flush=True)

    capture.captured.connect(on_captured)
    capture.cancelled.connect(lambda: print("cancelled", flush=True))

    hotkeys = HotkeyManager({"capture": "ctrl+alt+s"})
    hotkeys.triggered.connect(lambda name: capture.start())
    app.aboutToQuit.connect(hotkeys.stop)
    hotkeys.start()

    print("Press Ctrl+Alt+S, then drag a box (or click for full screen). Ctrl+C here to quit.", flush=True)
    sys.exit(app.exec())

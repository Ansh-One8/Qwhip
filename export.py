"""
Step 6: "Copy all" — put a whole session on the clipboard for one Ctrl+V.

Three things happen:

1. Captioned copies. Each screenshot gets a strip on top with its number, note
   and window title, saved to <session>/export/screenshot_1.png, ...
   The note is *inside the image*, so it reaches the AI even if a chat app
   ignores pasted text. Originals are never modified.

       ┌───────────────────────────────────────────┐
       │ #2  login button does nothing             │
       │     Chrome - localhost:3000               │
       ├───────────────────────────────────────────┤
       │            (your screenshot)              │
       └───────────────────────────────────────────┘

2. Files on the clipboard. We put the PNGs on the clipboard as a *file list*
   (Windows format CF_HDROP), the same thing Explorer does when you copy files.
   Chat apps that accept pasted files attach all of them at once.

3. Text on the clipboard too, as a numbered summary:
       Here are 3 screenshots:
       1. the error in the terminal  [Terminal]
       2. login button does nothing  [Chrome - localhost:3000]
"""

import shutil

from PySide6.QtCore import QMimeData, QRect, Qt, QUrl
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QImage, QPainter

MIN_WIDTH = 480  # tiny crops get padded so the caption stays readable

CAPTION_BG = QColor("#1f2329")
CAPTION_TEXT = QColor("#e6edf3")
CAPTION_DIM = QColor("#8b949e")
ACCENT = QColor("#4c8dff")


def caption_image(image, number, note, window_title):
    """Return a new image: caption strip on top + the screenshot below."""
    width = max(image.width(), MIN_WIDTH)
    font_px = max(16, min(30, width // 55))  # scale text with image size
    pad = font_px // 2 + 4

    note_font = QFont("Segoe UI")
    note_font.setPixelSize(font_px)
    title_font = QFont("Segoe UI")
    title_font.setPixelSize(max(12, int(font_px * 0.7)))
    num_font = QFont("Segoe UI")
    num_font.setPixelSize(font_px)
    num_font.setBold(True)

    num_text = f"#{number}"
    num_width = QFontMetrics(num_font).horizontalAdvance(num_text) + pad
    text_left = pad + num_width
    text_width = width - text_left - pad

    note_text = note or "(no note)"
    note_rect = QFontMetrics(note_font).boundingRect(
        QRect(0, 0, text_width, 10_000), Qt.TextWordWrap, note_text)
    title_height = QFontMetrics(title_font).height() if window_title else 0
    strip_height = pad + note_rect.height() + (4 + title_height if window_title else 0) + pad

    out = QImage(width, strip_height + image.height(), QImage.Format_RGB32)
    out.fill(QColor("#0d1117"))  # background for the padding of narrow images
    p = QPainter(out)
    p.setRenderHint(QPainter.TextAntialiasing)
    p.fillRect(0, 0, width, strip_height, CAPTION_BG)
    p.fillRect(0, strip_height - 3, width, 3, ACCENT)  # separator line

    p.setFont(num_font)
    p.setPen(ACCENT)
    p.drawText(QRect(pad, pad, num_width, note_rect.height()), Qt.AlignLeft | Qt.AlignTop, num_text)

    p.setFont(note_font)
    p.setPen(CAPTION_TEXT if note else CAPTION_DIM)
    p.drawText(QRect(text_left, pad, text_width, note_rect.height()),
               Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, note_text)

    if window_title:
        p.setFont(title_font)
        p.setPen(CAPTION_DIM)
        title = QFontMetrics(title_font).elidedText(window_title, Qt.ElideRight, text_width)
        p.drawText(QRect(text_left, pad + note_rect.height() + 4, text_width, title_height),
                   Qt.AlignLeft | Qt.AlignTop, title)

    p.drawImage(0, strip_height, image)
    p.end()
    return out


def summary_text(session):
    lines = [f"Here {'is' if len(session) == 1 else 'are'} {len(session)} "
             f"screenshot{'' if len(session) == 1 else 's'}:"]
    for number, shot in enumerate(session.shots, start=1):
        line = f"{number}. {shot.note or '(no note)'}"
        if shot.window_title:
            line += f"  [{shot.window_title}]"
        lines.append(line)
    return "\n".join(lines)


def export_session(session, captions=True):
    """Write the files to <session>/export/ and return (list_of_paths, summary_text)."""
    out_dir = session.folder / "export"
    if out_dir.exists():
        shutil.rmtree(out_dir)  # only ever contains files we generated
    out_dir.mkdir(parents=True)

    paths = []
    for number, shot in enumerate(session.shots, start=1):
        source = session.image_path(shot)
        target = out_dir / f"screenshot_{number}.png"
        if captions:
            image = QImage(str(source))
            if image.isNull():
                raise OSError(f"Could not read {source}")
            caption_image(image, number, shot.note, shot.window_title).save(str(target))
        else:
            shutil.copyfile(source, target)
        paths.append(target)
    return paths, summary_text(session)


def copy_to_clipboard(paths, text):
    mime = QMimeData()
    # File URLs -> Qt turns these into CF_HDROP (a file list) on Windows.
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    # Tell apps it's a "copy" (not a cut/move), exactly like Explorer does.
    mime.setData('application/x-qt-windows-mime;value="Preferred DropEffect"',
                 (1).to_bytes(4, "little"))
    mime.setText(text)
    QGuiApplication.clipboard().setMimeData(mime)


def copy_session(session, captions=True):
    """Export + copy. Returns how many screenshots were copied."""
    if len(session) == 0:
        return 0
    paths, text = export_session(session, captions)
    copy_to_clipboard(paths, text)
    return len(paths)

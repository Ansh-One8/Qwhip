// Runs inside the AI chat sites (claude.ai, chatgpt.com, gemini.google.com, chat.deepseek.com).
// It keeps one request open to the qwhip app ("wake me up when there's something for this
// site") and attaches whatever arrives to the chat box. It never presses Send.

const RETRY_MS = 3000; // when the qwhip app isn't running, check again this often

// The chat box on each site; the generic ones at the end are a fallback.
const COMPOSERS = [
  'div.ProseMirror[contenteditable="true"]', // claude.ai, chatgpt.com
  "#prompt-textarea",                        // chatgpt.com (older layout)
  'rich-textarea [contenteditable="true"]',  // gemini.google.com
  "textarea#chat-input",                     // chat.deepseek.com
  '[contenteditable="true"]',
  "textarea",
];

let connected = null; // last known state, so we only log when it changes
console.log("[qwhip] extension loaded on this page");

function findComposer() {
  for (const selector of COMPOSERS) {
    const element = document.querySelector(selector);
    if (element) return element;
  }
  return null;
}

function base64ToFile(b64, name) {
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  return new File([bytes], name, { type: "image/png" });
}

function attachFiles(composer, files) {
  const transfer = new DataTransfer();
  files.forEach((file) => transfer.items.add(file));

  // 1) Pretend the user pasted the files: the same path as Ctrl+V.
  composer.focus();
  const paste = new ClipboardEvent("paste", { clipboardData: transfer, bubbles: true, cancelable: true });
  composer.dispatchEvent(paste);
  if (paste.defaultPrevented) {
    console.log("[qwhip] attached via paste");
    return true; // the site handled it
  }

  // 2) Fallback: hand the files to the site's own hidden "upload file" input.
  const input = document.querySelector('input[type="file"]');
  if (input) {
    input.files = transfer.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
    console.log("[qwhip] attached via file input");
    return true;
  }
  return false;
}

function typeText(composer, text) {
  composer.focus();
  if (composer instanceof HTMLTextAreaElement) {
    composer.setSelectionRange(composer.value.length, composer.value.length);
  } else {
    // Move the cursor to the end of the editor.
    const selection = window.getSelection();
    selection.selectAllChildren(composer);
    selection.collapseToEnd();
  }
  // Insert like real typing so the site's editor notices.
  document.execCommand("insertText", false, text);
}

function deliver(batch) {
  const composer = findComposer();
  if (!composer) {
    console.warn("[qwhip] Could not find the chat box on this page.");
    return;
  }
  const files = batch.images.map((img) => base64ToFile(img.data, img.name));
  if (files.length && !attachFiles(composer, files)) {
    console.warn("[qwhip] This page did not accept the screenshots.");
  }
  if (batch.text) {
    // Give the site a moment to process the attachments before typing.
    setTimeout(() => typeText(composer, batch.text), 300);
  }
  if (batch.focus) chrome.runtime.sendMessage({ type: "focus" });
}

function poll() {
  if (!chrome.runtime?.id) return; // the extension was reloaded/removed: this old script stops
  try {
    chrome.runtime.sendMessage({ type: "poll", visible: document.visibilityState === "visible" }, (response) => {
      if (chrome.runtime.lastError || !response) {
        setTimeout(poll, RETRY_MS);
        return;
      }
      if (response.connected !== connected) {
        connected = response.connected;
        console.log(connected ? "[qwhip] connected to the qwhip app"
                              : "[qwhip] qwhip app not reachable (is it running?)");
      }
      if (response.batch) {
        console.log(`[qwhip] received ${response.batch.images.length} screenshot(s)`);
        deliver(response.batch);
      }
      // Connected: ask again right away (the app holds the request until there's news).
      setTimeout(poll, connected ? 100 : RETRY_MS);
    });
  } catch (e) {
    // "Extension context invalidated": the extension was reloaded; this old script stops.
  }
}

poll();

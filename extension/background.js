// Runs in the extension itself (not inside any web page).
// Chat pages ask us to wait for screenshots from the qwhip app; we're allowed to talk
// to 127.0.0.1:47831 because of "host_permissions" in manifest.json. A normal web page isn't.

const QWHIP_URL = "http://127.0.0.1:47831/api/next";

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const tab = sender.tab;
  if (!tab) return;

  if (message.type === "poll") {
    // Which site is asking. Taken from Chrome (sender.tab), not from the page, so a page can't lie.
    const site = tab.url ? new URL(tab.url).hostname : "";
    fetch(QWHIP_URL, {
      method: "POST",
      headers: { "X-Qwhip": "1", "Content-Type": "application/json" },
      body: JSON.stringify({ site, visible: message.visible }),
    })
      .then((response) => {
        if (response.status === 200) return response.json().then((batch) => ({ batch, connected: true }));
        if (response.status === 204) return { batch: null, connected: true };
        return { batch: null, connected: false }; // unexpected answer: treat as not connected
      })
      .catch(() => ({ batch: null, connected: false })) // qwhip app not running
      .then(sendResponse);
    return true; // "I'll answer later" (the fetch is asynchronous)
  }

  if (message.type === "focus") {
    // Bring the tab that just received screenshots to the front.
    chrome.tabs.update(tab.id, { active: true });
    chrome.windows.update(tab.windowId, { focused: true });
  }
});

"""The AI chat sites qwhip can send screenshots to (through the browser extension)."""

# key: (display name, hostname the extension reports, URL to open a new chat)
TARGETS = {
    "claude": ("Claude", "claude.ai", "https://claude.ai/new"),
    "chatgpt": ("ChatGPT", "chatgpt.com", "https://chatgpt.com/"),
    "gemini": ("Gemini", "gemini.google.com", "https://gemini.google.com/app"),
    "deepseek": ("DeepSeek", "chat.deepseek.com", "https://chat.deepseek.com/"),
}
DEFAULT_TARGET = "claude"


def name(key):
    return TARGETS[key][0]


def host(key):
    return TARGETS[key][1]


def url(key):
    return TARGETS[key][2]

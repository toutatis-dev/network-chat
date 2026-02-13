import os

CONFIG_FILE = "chat_config.json"
LOCAL_CHAT_ROOT = ".local_chat"
AI_CONFIG_FILE = os.path.join(LOCAL_CHAT_ROOT, "ai_config.json")
LOCAL_ROOMS_ROOT = os.path.join(LOCAL_CHAT_ROOT, "rooms")
AI_DM_ROOM = "ai-dm"
MEMORY_DIR_NAME = "memory"
MEMORY_GLOBAL_FILE = "global.jsonl"
DEFAULT_PATH = None
DEFAULT_ROOM = "general"
MAX_MESSAGES = 200
LOCK_TIMEOUT_SECONDS = 2.0
LOCK_MAX_ATTEMPTS = 20
LOCK_BACKOFF_BASE_SECONDS = 0.05
LOCK_BACKOFF_MAX_SECONDS = 0.5
MAX_PRESENCE_ID_LENGTH = 64
CLIENT_ID_LENGTH = 12
PRESENCE_REFRESH_INTERVAL_SECONDS = 1.0
AI_HTTP_TIMEOUT_SECONDS = 45
AI_RETRY_BACKOFF_SECONDS = 1.2
EVENT_SCHEMA_VERSION = 1
EVENT_ALLOWED_TYPES = (
    "chat",
    "me",
    "system",
    "ai_prompt",
    "ai_response",
)
MONITOR_POLL_INTERVAL_MIN_SECONDS = 0.2
MONITOR_POLL_INTERVAL_MAX_SECONDS = 1.5
MONITOR_POLL_INTERVAL_ACTIVE_SECONDS = 0.35

THEMES = {
    "default": {
        "chat-area": "bg:#000000 #ffffff",
        "input-area": "bg:#222222 #ffffff",
        "sidebar": "bg:#111111 #88ff88",
        "frame.label": "bg:#0000aa #ffffff bold",
        "status": "bg:#004400 #ffffff",
        "completion-menu": "bg:#333333 #ffffff",
        "completion-menu.completion.current": "bg:#00aaaa #000000",
        "search-match": "bg:#333300 #ffff66",
        "mention": "fg:#ffaf00 bold",
        "timestamp": "fg:#888888",
    },
    "nord": {
        "chat-area": "bg:#2E3440 #D8DEE9",
        "input-area": "bg:#3B4252 #ECEFF4",
        "sidebar": "bg:#434C5E #8FBCBB",
        "frame.label": "bg:#5E81AC #ECEFF4 bold",
        "status": "bg:#A3BE8C #2E3440",
        "completion-menu": "bg:#4C566A #ECEFF4",
        "completion-menu.completion.current": "bg:#88C0D0 #2E3440",
        "search-match": "bg:#5e81ac #eceff4",
        "mention": "fg:#ebcb8b bold",
        "timestamp": "fg:#81a1c1",
    },
    "matrix": {
        "chat-area": "bg:#000000 #00FF00",
        "input-area": "bg:#001100 #00DD00",
        "sidebar": "bg:#001100 #00FF00",
        "frame.label": "bg:#003300 #00FF00 bold",
        "status": "bg:#004400 #ffffff",
        "completion-menu": "bg:#002200 #00FF00",
        "completion-menu.completion.current": "bg:#00FF00 #000000",
        "search-match": "bg:#003300 #aaffaa",
        "mention": "fg:#ffffff bold",
        "timestamp": "fg:#66cc66",
    },
    "solarized-dark": {
        "chat-area": "bg:#002b36 #839496",
        "input-area": "bg:#073642 #93a1a1",
        "sidebar": "bg:#073642 #2aa198",
        "frame.label": "bg:#268bd2 #fdf6e3 bold",
        "status": "bg:#859900 #fdf6e3",
        "completion-menu": "bg:#073642 #93a1a1",
        "completion-menu.completion.current": "bg:#2aa198 #002b36",
        "search-match": "bg:#586e75 #fdf6e3",
        "mention": "fg:#cb4b16 bold",
        "timestamp": "fg:#93a1a1",
    },
    "monokai": {
        "chat-area": "bg:#272822 #F8F8F2",
        "input-area": "bg:#3E3D32 #F8F8F2",
        "sidebar": "bg:#272822 #A6E22E",
        "frame.label": "bg:#F92672 #F8F8F2 bold",
        "status": "bg:#66D9EF #272822",
        "completion-menu": "bg:#3E3D32 #F8F8F2",
        "completion-menu.completion.current": "bg:#FD971F #272822",
        "search-match": "bg:#49483e #f8f8f2",
        "mention": "fg:#fd971f bold",
        "timestamp": "fg:#a59f85",
    },
}

COLORS = [
    "green",
    "cyan",
    "magenta",
    "yellow",
    "blue",
    "red",
    "white",
    "brightgreen",
    "brightcyan",
    "brightmagenta",
    "brightyellow",
    "brightblue",
    "brightred",
]

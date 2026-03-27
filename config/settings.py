"""
config/settings.py
──────────────────
Loads and validates all environment variables required by the agent.
"""

import os
import json
import logging
from dotenv import load_dotenv

# Load .env file if present (local development)
load_dotenv()

logger = logging.getLogger(__name__)


def _require(key: str) -> str:
    """Return env var value or raise if missing."""
    value = os.environ.get(key, "").strip()
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{key}' is missing or empty. "
            "Check your .env file or GitHub Actions secrets."
        )
    return value


# ── Google Drive ─────────────────────────────────────────────
def get_service_account_info() -> dict:
    """Parse the service account JSON from the environment variable."""
    raw = _require("GOOGLE_SERVICE_ACCOUNT_JSON")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON. "
            "Ensure you paste the full service account key as a single-line JSON string."
        ) from exc


DRIVE_FOLDER_ID: str = _require("GOOGLE_DRIVE_FOLDER_ID")

# ── YouTube OAuth2 ───────────────────────────────────────────
YOUTUBE_CLIENT_ID: str = _require("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET: str = _require("YOUTUBE_CLIENT_SECRET")
YOUTUBE_REFRESH_TOKEN: str = _require("YOUTUBE_REFRESH_TOKEN")

# ── AI API ────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "").strip()
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "").strip()
NVIDIA_API_KEY: str = os.environ.get("NVIDIA_API_KEY", "").strip()
NVIDIA_BASE_URL: str = os.environ.get(
    "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
)
NVIDIA_MODEL: str = os.environ.get("NVIDIA_MODEL", "nvidia/nemotron-3-super-120b-a12b")

if not any([ANTHROPIC_API_KEY, OPENAI_API_KEY, NVIDIA_API_KEY]):
    raise EnvironmentError(
        "At least one AI API key must be set: ANTHROPIC_API_KEY, OPENAI_API_KEY, or NVIDIA_API_KEY."
    )

# Priority: NVIDIA -> Anthropic -> OpenAI
if NVIDIA_API_KEY:
    AI_PROVIDER = "nvidia"
elif ANTHROPIC_API_KEY:
    AI_PROVIDER = "anthropic"
else:
    AI_PROVIDER = "openai"

# ── Telegram ─────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID: str = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
TELEGRAM_GROUP_CHAT_ID: str = os.environ.get(
    "TELEGRAM_GROUP_CHAT_ID", "-1003769042674"
).strip()

TELEGRAM_ENABLED: bool = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
if not TELEGRAM_ENABLED:
    logger.warning(
        "Telegram notifications disabled — TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set."
    )

# ── Misc ──────────────────────────────────────────────────────
# Supported video extensions
VIDEO_EXTENSIONS: tuple = (".mp4", ".mov", ".avi", ".mkv", ".webm")

# Temp download directory
TMP_DIR: str = os.environ.get("TMP_DIR", "/tmp/yt_seo_agent")

# IST timezone
IST_TIMEZONE: str = "Asia/Kolkata"

# GitHub Auth (for state persistence in Actions)
GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", "").strip()
GITHUB_REPO: str = os.environ.get("GITHUB_REPOSITORY", "").strip()
STATE_FILE_PATH: str = os.environ.get("STATE_FILE_PATH", "state/upload_state.json")

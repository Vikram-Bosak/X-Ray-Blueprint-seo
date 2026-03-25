"""
src/telegram_notifier.py
────────────────────────
Send Telegram notifications after upload success or failure.
Uses Telegram Bot API with HTML formatting.
"""

import logging
import os
import sys
from datetime import datetime
from typing import Optional

import requests
import pytz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

logger = logging.getLogger(__name__)


def _get_ist_time() -> str:
    """Return current time formatted as IST (Asia/Kolkata)."""
    ist = pytz.timezone(settings.IST_TIMEZONE)
    now_ist = datetime.now(ist)
    return now_ist.strftime("%d %b %Y, %I:%M:%S %p IST")


def _send_telegram_message(text: str, parse_mode: str = "HTML") -> bool:
    """
    Send a message via Telegram Bot API.

    Returns True on success, False on failure.
    """
    if not settings.TELEGRAM_ENABLED:
        logger.info("Telegram notifications disabled — skipping message")
        return True

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": settings.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
    }

    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        logger.info("Telegram message sent to chat %s", settings.TELEGRAM_CHAT_ID)
        return True
    except requests.exceptions.RequestException as exc:
        logger.error("Failed to send Telegram message: %s", exc)
        return False


def send_success_notification(
    title: str,
    video_url: str,
    tags: list,
    file_name: str,
    slot_info: dict = None,
    next_video: str = None,
    next_slot_info: dict = None,
) -> bool:
    """
    Send a success notification after a successful YouTube upload.
    Format includes video URL, slot timing, next upload info.
    """
    if slot_info is None:
        slot_info = {
            "id": "?",
            "label": "Unknown",
            "ist_time": _get_ist_time(),
            "us_time": "Unknown",
            "uploads_today": 0
        }

    slot_id = slot_info.get("id", "?")
    slot_label = slot_info.get("label", "Unknown")
    ist_ts = slot_info.get("ist_time", _get_ist_time())
    us_ts = slot_info.get("us_time", "Unknown")
    count = slot_info.get("uploads_today", 0)

    # Build next upload info
    next_info = ""
    if next_slot_info:
        next_time = next_slot_info.get("ist_time", "Unknown")
        next_us = next_slot_info.get("us_time", "")
        next_info = f"\n📌 <b>Next Upload:</b> {next_time} ({next_us})"
        if next_video:
            next_info += f"\n📹 <b>Next Video:</b> {next_video[:50]}{'...' if len(next_video) > 50 else ''}"
    elif next_video:
        next_info = f"\n📹 <b>Next Video:</b> {next_video[:50]}{'...' if len(next_video) > 50 else ''}"

    message = f"""
✅ <b>VIDEO PUBLISHED!</b>

📹 <b>Title:</b> {title}
🔗 <b>Link:</b> <a href="{video_url}">Watch on YouTube</a>

⏰ <b>Upload Slot:</b> Slot {slot_id} — {slot_label}
🕐 <b>IST Time:</b> {ist_ts}
🌎 <b>US Time:</b> {us_ts}

📊 <b>Today's Uploads:</b> {count}/5
📁 <b>Drive File:</b> Moved to PROCESSED ✅{next_info}

━━━━━━━━━━━━━━━━━━━━━━━━━━
🎬 The 3D Breakdown Bot
"""

    return _send_telegram_message(message)


def send_failure_notification(
    file_name: str,
    error_message: str,
    step: str,
) -> bool:
    """
    Send a failure notification if the upload or any critical step fails.
    """
    timestamp = _get_ist_time()

    # Truncate error message if too long
    error_short = error_message[:500] if len(error_message) > 500 else error_message

    message = f"""
❌ <b>UPLOAD FAILED!</b>

📁 <b>File:</b> {file_name}
⚠️ <b>Failed Step:</b> {step}

🕐 <b>Time:</b> {timestamp}

📝 <b>Error:</b>
<pre>{error_short}</pre>

⚠️ <b>Drive file NOT deleted</b> — will retry next run

━━━━━━━━━━━━━━━━━━━━━━━━━━
🎬 The 3D Breakdown Bot
"""

    return _send_telegram_message(message)

"""
src/scheduler.py
─────────────────
Upload scheduling logic for the YouTube Shorts SEO Agent.

Handles:
- IST slot window detection (6 slots targeting US peak hours)
- Daily counter management (max 5 uploads/day)
- Within-slot randomization (human-like upload timing)
- State persistence via upload_state.json (committed back to GitHub)
- Daily reset at midnight IST
"""

import json
import logging
import os
import random
import sys
from datetime import datetime, timedelta, date

import pytz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

IST = pytz.timezone("Asia/Kolkata")
US_ET = pytz.timezone("America/New_York")

MAX_UPLOADS_PER_DAY = 5

# Slot definitions (IST). "end": "00:00" means midnight (next calendar day in IST).
SLOT_WINDOWS = {
    "1": {"start": "18:00", "end": "19:00", "label": "US Morning"},
    "2": {"start": "20:00", "end": "21:00", "label": "US Mid-Morning"},
    "3": {"start": "23:00", "end": "00:00", "label": "US Lunch"},
    "4": {"start": "01:00", "end": "02:00", "label": "US Afternoon"},
    "5": {"start": "03:00", "end": "04:00", "label": "US Evening"},
    "6": {"start": "05:30", "end": "07:30", "label": "US Prime Time"},
}

# No-upload zone: 04:00–18:00 IST (US audience sleeping/at work)
# This is enforced implicitly — slots only cover 18:00–07:30 IST.

DEFAULT_STATE = {
    "date_ist": "2000-01-01",   # forced reset on first run
    "uploads_today": 0,
    "slots_used": [],
    "last_upload_ist": None,
    "slot_windows": SLOT_WINDOWS,
}


# ── State I/O ──────────────────────────────────────────────────────────────────

def load_state(path: str) -> dict:
    """
    Load upload_state.json from disk. Performs a daily reset if the stored
    date differs from today (IST). Creates the file (with defaults) if absent.
    """
    today_ist = _today_ist_str()

    if not os.path.exists(path):
        logger.info("State file not found — initialising fresh state at: %s", path)
        state = dict(DEFAULT_STATE)
        state["date_ist"] = today_ist
        os.makedirs(os.path.dirname(path), exist_ok=True)
        save_state(state, path)
        return state

    with open(path, "r", encoding="utf-8") as fh:
        state = json.load(fh)

    # Daily reset: if stored date != today IST, wipe counter/slots
    if state.get("date_ist") != today_ist:
        logger.info(
            "New IST day detected (%s → %s). Resetting upload counter.",
            state.get("date_ist"), today_ist
        )
        state["date_ist"] = today_ist
        state["uploads_today"] = 0
        state["slots_used"] = []
        state["last_upload_ist"] = None
        save_state(state, path)

    return state


def save_state(state: dict, path: str) -> None:
    """Persist state dict to disk as JSON."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    logger.debug("State saved to %s", path)


# ── Slot Logic ─────────────────────────────────────────────────────────────────

def get_active_slot(now_ist: datetime) -> tuple[str | None, dict | None]:
    """
    Return (slot_id, slot_dict) if we are currently inside a slot window,
    or (None, None) if not.

    Handles:
    - Normal slots (start < end hour, same day)
    - Midnight-crossing slot 3 (23:00 → 00:00 treated as 24:00)
    """
    current_time_str = now_ist.strftime("%H:%M")

    for slot_id, slot in SLOT_WINDOWS.items():
        start = slot["start"]
        end = slot["end"]

        if end == "00:00":
            # Midnight crossing: slot runs from start until midnight
            if _time_str_ge(current_time_str, start):
                logger.debug("In slot %s (%s→midnight): now=%s", slot_id, start, current_time_str)
                return slot_id, slot
        elif _time_str_lt(start, end):
            # Normal intra-day slot
            if _time_str_ge(current_time_str, start) and _time_str_lt(current_time_str, end):
                logger.debug("In slot %s (%s→%s): now=%s", slot_id, start, end, current_time_str)
                return slot_id, slot

    return None, None


def can_upload(state: dict, slot_id: str) -> tuple[bool, str]:
    """
    Check all gating conditions.

    Returns (True, "") if upload is allowed,
    or (False, reason_string) if blocked.
    """
    if state["uploads_today"] >= MAX_UPLOADS_PER_DAY:
        return False, f"Daily upload limit ({MAX_UPLOADS_PER_DAY}) reached. Skipping."

    if slot_id in state["slots_used"]:
        return False, f"Slot {slot_id} already used today. Skipping."

    return True, ""


def compute_upload_time(slot: dict, now_ist: datetime) -> datetime:
    """
    Compute a randomised target upload time within the slot window.

    Strategy:
    - Each agent run picks random_offset = randint(0, 55) minutes from slot_start.
    - The random seed is based on (date + slot_id) so the same random time is
      chosen consistently across the multiple 15-min triggers within one slot.
    """
    start_h, start_m = map(int, slot["start"].split(":"))

    # Deterministic random per (date, slot) so all triggers in same slot agree
    today = now_ist.strftime("%Y-%m-%d")
    slot_label = slot["label"]
    seed = hash(f"{today}-{slot_label}") % (2**31)
    rng = random.Random(seed)
    
    # Within-slot randomization (0-55 mins)
    offset_minutes = rng.randint(0, 55)

    # Build slot_start_dt in IST
    # Special handling for slots where IST date might be different than 'today'
    # Actually, we just use the 'now_ist' and set the hours.
    # If it's a 23:00 slot, and now_ist is 23:15, slot_start is 23:00 today.
    # If it's a 01:00 slot, and now_ist is 01:15, slot_start is 01:00 today.
    slot_start_dt = now_ist.replace(
        hour=start_h, minute=start_m, second=0, microsecond=0
    )
    
    upload_dt = slot_start_dt + timedelta(minutes=offset_minutes)
    return upload_dt


def mark_uploaded(state: dict, slot_id: str, now_ist: datetime) -> dict:
    """Update state after a successful upload."""
    state["uploads_today"] = state.get("uploads_today", 0) + 1
    slots_used = state.get("slots_used", [])
    if slot_id not in slots_used:
        slots_used.append(slot_id)
    state["slots_used"] = slots_used
    state["last_upload_ist"] = now_ist.strftime("%H:%M")
    return state


# ── GitHub State Commit ────────────────────────────────────────────────────────

def commit_state_to_github(local_path: str) -> bool:
    """
    Commit upload_state.json back to the GitHub repo so state persists
    between Actions runs.

    Uses GITHUB_TOKEN (auto-injected by Actions) and GITHUB_REPOSITORY
    (format: "owner/repo", also auto-injected).

    Returns True on success, False on failure (non-fatal).
    """
    token = settings.GITHUB_TOKEN
    repo = settings.GITHUB_REPO   # e.g. "myuser/youtube-seo-agent"
    state_file_path = settings.STATE_FILE_PATH  # e.g. "state/upload_state.json"

    if not token or not repo:
        logger.warning(
            "GITHUB_TOKEN or GITHUB_REPOSITORY not set — state will not be persisted to repo. "
            "This is normal during local development."
        )
        return False

    try:
        import base64
        import requests

        api_url = f"https://api.github.com/repos/{repo}/contents/{state_file_path}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
        }

        # Get current file SHA (required for update)
        get_resp = requests.get(api_url, headers=headers, timeout=15)
        sha = None
        if get_resp.status_code == 200:
            sha = get_resp.json().get("sha")

        # Read local file content
        with open(local_path, "rb") as fh:
            content_b64 = base64.b64encode(fh.read()).decode()

        payload = {
            "message": "chore: update upload state [skip ci]",
            "content": content_b64,
        }
        if sha:
            payload["sha"] = sha

        put_resp = requests.put(api_url, headers=headers, json=payload, timeout=15)
        if put_resp.status_code in (200, 201):
            logger.info("State file committed to GitHub: %s", state_file_path)
            return True
        else:
            logger.error(
                "GitHub commit failed: %s %s", put_resp.status_code, put_resp.text[:200]
            )
            return False

    except Exception as exc:
        logger.error("Failed to commit state to GitHub: %s", exc)
        return False


# ── Helpers ────────────────────────────────────────────────────────────────────

def now_ist() -> datetime:
    """Return timezone-aware current datetime in IST."""
    return datetime.now(IST)


def ist_to_et(dt_ist: datetime) -> str:
    """Convert an IST datetime to US Eastern Time string."""
    dt_et = dt_ist.astimezone(US_ET)
    return dt_et.strftime("%d %b %Y, %I:%M %p ET")


def _today_ist_str() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def get_next_slot_info(state: dict, now_ist: datetime) -> dict | None:
    """
    Get information about the next available upload slot.
    Returns dict with slot_id, label, start_time, ist_time, us_time or None if no slots available today.
    """
    current_time_str = now_ist.strftime("%H:%M")
    current_minutes = _to_minutes(current_time_str)
    uploads_today = state.get("uploads_today", 0)
    slots_used = state.get("slots_used", [])
    
    if uploads_today >= MAX_UPLOADS_PER_DAY:
        return None
    
    # Find next available slot
    all_slots = []
    for slot_id, slot in SLOT_WINDOWS.items():
        if slot_id in slots_used:
            continue
        
        start_minutes = _to_minutes(slot["start"])
        end_minutes = _to_minutes(slot["end"]) if slot["end"] != "00:00" else 1440  # midnight
        
        # If slot hasn't started yet
        if start_minutes > current_minutes:
            all_slots.append((start_minutes, slot_id, slot))
        # If we're in a slot that's not used yet
        elif current_minutes <= end_minutes and slot_id not in slots_used:
            # This slot is current - but we just used it, so find next
            pass
    
    # If no future slots today, check tomorrow's first slot
    if not all_slots:
        # Return first slot info for tomorrow
        first_slot = list(SLOT_WINDOWS.items())[0]
        return {
            "slot_id": first_slot[0],
            "label": first_slot[1]["label"],
            "start_time": first_slot[1]["start"],
            "ist_time": f"Tomorrow {first_slot[1]['start']} IST",
            "us_time": _get_us_time(first_slot[1]["start"]),
        }
    
    # Return next slot
    next_slot = sorted(all_slots)[0]
    slot_id, slot = next_slot[2], next_slot[2]
    return {
        "slot_id": next_slot[1],
        "label": slot["label"],
        "start_time": slot["start"],
        "ist_time": f"Today {slot['start']} IST",
        "us_time": _get_us_time(slot["start"]),
    }


def _get_us_time(ist_time: str) -> str:
    """Convert IST time to US EST time string."""
    h, m = map(int, ist_time.split(":"))
    ist_dt = datetime.now(IST).replace(hour=h, minute=m, second=0, microsecond=0)
    try:
        et_dt = ist_dt.astimezone(US_ET)
        return et_dt.strftime("%I:%M %p EST")
    except:
        return f"{ist_time} IST"


def _to_minutes(time_str: str) -> int:
    """Convert 'HH:MM' string to total minutes since midnight."""
    h, m = map(int, time_str.split(":"))
    return h * 60 + m


def _time_str_lt(a: str, b: str) -> bool:
    return _to_minutes(a) < _to_minutes(b)


def _time_str_ge(a: str, b: str) -> bool:
    return _to_minutes(a) >= _to_minutes(b)

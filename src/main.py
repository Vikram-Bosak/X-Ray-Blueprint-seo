"""
src/main.py
────────────
Entry point for the YouTube Shorts SEO Agent.
Orchestrates all steps: Drive scan → Download → SEO → YouTube upload → Drive delete → Email.
"""

import logging
import os
import sys
import traceback
import time
from datetime import datetime

import pytz

# Add project root to path so config/ is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from src.drive_handler import (
    get_oldest_video,
    download_video,
    delete_file,
    list_video_files,
)
from src.seo_generator import generate_seo_metadata
from src.youtube_uploader import upload_video
from src.telegram_notifier import send_success_notification, send_failure_notification
from src.scheduler import (
    load_state,
    save_state,
    get_active_slot,
    can_upload,
    mark_uploaded,
    now_ist,
    commit_state_to_github,
    compute_upload_time,
    ist_to_et,
    get_next_slot_info,
)


# ── Logging setup ─────────────────────────────────────────────────────────────
def setup_logging():
    ist = pytz.timezone(settings.IST_TIMEZONE)

    class ISTFormatter(logging.Formatter):
        def formatTime(self, record, datefmt=None):
            dt = datetime.fromtimestamp(record.created, tz=ist)
            return dt.strftime("%Y-%m-%d %H:%M:%S IST")

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        ISTFormatter("[%(asctime)s] %(levelname)-8s %(name)s — %(message)s")
    )
    logging.basicConfig(level=logging.INFO, handlers=[handler])


logger = logging.getLogger("main")


# ── Main Agent Logic ──────────────────────────────────────────────────────────
def run_agent():
    setup_logging()

    # ── LOCK MECHANISM ─────────────────────────────────────────────────────────
    # Prevent parallel runs (important for local execution)
    lock_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent.lock"
    )
    if os.path.exists(lock_file):
        # Check if the lock is stale (older than 30 minutes)
        lock_age = time.time() - os.path.getmtime(lock_file)
        if lock_age < 1800:
            logger.warning(
                "Another instance of the agent is already running (lock file exists). Exiting."
            )
            return
        else:
            logger.warning("Stale lock file found (>30 min). Overriding.")

    with open(lock_file, "w") as f:
        f.write(str(os.getpid()))

    file_info = None
    local_path = None
    upload_succeeded = False

    try:
        logger.info("=" * 60)
        logger.info("YouTube Shorts SEO Agent — Starting Run")
        logger.info("=" * 60)

        current_ist = now_ist()
        state_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "state",
            "upload_state.json",
        )

        # ── STEP 0: Check Scheduler (Skip if BYPASS_SCHEDULER is True) ──────────
        if os.environ.get("BYPASS_SCHEDULER", "").lower() == "true":
            logger.info(
                "[STEP 0] ! BYPASS_SCHEDULER is active. Overriding IST slots for testing."
            )
            slot_id, slot_info = (
                "TEST",
                {"label": "Manual Test", "start": "00:00", "end": "23:59"},
            )
        else:
            logger.info(
                "[STEP 0] Checking scheduler status (IST: %s)...",
                current_ist.strftime("%H:%M"),
            )
            state = load_state(state_path)

            slot_id, slot_info = get_active_slot(current_ist)
            if not slot_id:
                logger.info("Not currently in an upload slot window. Sleeping.")
                return

            allowed, reason = can_upload(state, slot_id)
            if not allowed:
                logger.info(reason)
                return

            # ── Within-Slot Randomization ─────────────────────────────────────
            target_dt = compute_upload_time(slot_info, current_ist)

            if current_ist < target_dt:
                diff_seconds = (target_dt - current_ist).total_seconds()
                if diff_seconds > 300:  # 5 minutes
                    # Check if we're already past the target but within slot
                    slot_end_h, slot_end_m = map(int, slot_info["end"].split(":"))
                    slot_end_dt = current_ist.replace(
                        hour=slot_end_h, minute=slot_end_m, second=0, microsecond=0
                    )

                    # If target passed but still within slot - upload immediately
                    if target_dt <= current_ist and current_ist < slot_end_dt:
                        logger.info(
                            "Slot %s — Target time %s passed but within slot. Proceeding now.",
                            slot_id,
                            target_dt.strftime("%H:%M"),
                        )
                    else:
                        logger.info(
                            "Slot %s — Target time %s is >5 mins away (now %s). Skipping run.",
                            slot_id,
                            target_dt.strftime("%H:%M"),
                            current_ist.strftime("%H:%M"),
                        )
                        return
                else:
                    logger.info(
                        "Slot %s — Target time %s is close (in %.1f min). Waiting...",
                        slot_id,
                        target_dt.strftime("%H:%M"),
                        diff_seconds / 60,
                    )
                    time.sleep(diff_seconds)
                    current_ist = now_ist()  # Update current time after sleep
            else:
                logger.info(
                    "Slot %s — Target time %s already passed (now %s). Proceeding.",
                    slot_id,
                    target_dt.strftime("%H:%M"),
                    current_ist.strftime("%H:%M"),
                )

        logger.info("Active Slot: %s (%s)", slot_id, slot_info["label"])

        # ── STEP 1: Scan Google Drive ─────────────────────────────────────────
        logger.info(
            "[STEP 1] Scanning Google Drive folder: %s", settings.DRIVE_FOLDER_ID
        )
        file_info = get_oldest_video(settings.DRIVE_FOLDER_ID)

        if file_info is None:
            logger.info("No videos found in Drive folder. Exiting gracefully.")
            return

        file_name = file_info["name"]
        file_id = file_info["id"]
        file_size = int(file_info.get("size", 0))
        logger.info(
            "Selected file: '%s' | ID: %s | Size: %.2f MB",
            file_name,
            file_id,
            file_size / (1024 * 1024),
        )

        # ── STEP 2: Download Video ────────────────────────────────────────────
        logger.info("[STEP 2] Downloading video from Google Drive...")
        local_path = download_video(file_id, file_name)
        logger.info("Download complete: %s", local_path)

        # ── STEP 3: Generate SEO Metadata ────────────────────────────────────
        logger.info("[STEP 3] Generating SEO metadata via AI...")
        metadata = generate_seo_metadata(file_name)
        logger.info("Title: %s", metadata["title"])
        logger.info(
            "Tags (%d): %s",
            len(metadata["tags"]),
            ", ".join(metadata["tags"][:5]) + "...",
        )

        # ── STEP 4: Upload to YouTube ─────────────────────────────────────────
        logger.info("[STEP 4] Uploading to YouTube...")
        result = upload_video(local_path, metadata)
        video_id = result["video_id"]
        video_url = result["video_url"]
        logger.info("YouTube upload successful! URL: %s", video_url)
        upload_succeeded = True

        # ── STEP 5: Delete from Google Drive ─────────────────────────────────
        logger.info("[STEP 5] Deleting '%s' from Google Drive...", file_name)
        deleted = delete_file(file_id, file_name)
        if deleted:
            logger.info("Drive file deleted successfully.")
        else:
            logger.warning(
                "Drive file deletion failed (non-critical). Will retry next run."
            )

        # ── STEP 5.5: Update Scheduler State ────────────────────────────────
        if os.environ.get("BYPASS_SCHEDULER", "").lower() != "true":
            state = mark_uploaded(state, slot_id, current_ist)
            save_state(state, state_path)
            commit_state_to_github(state_path)

        # ── STEP 6: Send Telegram Notification ───────────────────────────────
        logger.info("[STEP 6] Sending Telegram notification...")

        # Get next slot info
        next_slot = (
            get_next_slot_info(state, current_ist) if "state" in locals() else None
        )

        # Get next video name
        next_file = get_oldest_video(settings.DRIVE_FOLDER_ID)
        next_video_name = next_file["name"] if next_file else None

        # Get video counts
        all_drive_files = list_video_files(settings.DRIVE_FOLDER_ID)
        pending_videos = len(
            [f for f in all_drive_files if not f["name"].startswith("✅ DONE")]
        )

        # Get processed count from PROCESSED folder
        processed_videos = 0
        try:
            from src.drive_handler import _get_drive_service

            service = _get_drive_service()
            processed_folder_id = "1ONZ8c2QMFOWiYtnwdOg4Oko7sEcVyl-X"
            processed = (
                service.files()
                .list(
                    q=f'"{processed_folder_id}" in parents and trashed=false',
                    fields="files(id)",
                )
                .execute()
            )
            processed_videos = len(processed.get("files", []))
        except:
            processed_videos = 0

        send_success_notification(
            title=metadata["title"],
            video_url=video_url,
            tags=metadata["tags"],
            file_name=file_name,
            slot_info={
                "id": slot_id,
                "label": slot_info["label"],
                "ist_time": current_ist.strftime("%d %b %Y, %I:%M %p IST"),
                "us_time": ist_to_et(current_ist),
                "uploads_today": state["uploads_today"] if "state" in locals() else 0,
            },
            next_video=next_video_name,
            next_slot_info=next_slot,
            pending_videos=pending_videos,
            processed_videos=processed_videos,
        )

        logger.info("=" * 60)
        logger.info("Agent run COMPLETE. Video: %s", video_url)
        logger.info("=" * 60)

    except Exception as exc:
        error_msg = traceback.format_exc()
        logger.error("Agent encountered a fatal error:\n%s", error_msg)

        # Determine which step failed
        if file_info is None:
            step = "STEP 1: Drive Scan"
        elif local_path is None:
            step = "STEP 2: Drive Download"
        elif not upload_succeeded:
            step = "STEP 3/4: SEO Generation / YouTube Upload"
        else:
            step = "STEP 5/6: Drive Deletion / Email"

        fn = file_info["name"] if file_info else "unknown"

        # Send failure email (best effort — don't crash if email fails)
        try:
            send_failure_notification(
                file_name=fn,
                error_message=str(exc),
                step=step,
            )
        except Exception as email_exc:
            logger.error("Additionally, failure email could not be sent: %s", email_exc)

        # IMPORTANT: Do NOT delete Drive file on upload failure
        if not upload_succeeded:
            logger.info("Drive file '%s' was NOT deleted (upload did not succeed).", fn)

        sys.exit(1)

    finally:
        # ── LOCK CLEANUP ───────────────────────────────────────────────────
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
            except Exception:
                pass

        # Always clean up temp downloaded file
        if local_path and os.path.exists(local_path):
            try:
                os.remove(local_path)
                logger.debug("Temp file cleaned up: %s", local_path)
            except Exception:
                pass


if __name__ == "__main__":
    run_agent()

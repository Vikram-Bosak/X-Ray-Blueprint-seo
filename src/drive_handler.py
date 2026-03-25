"""
src/drive_handler.py
─────────────────────
Google Drive helper: list, download, and delete video files.
Uses a Service Account (no interactive OAuth required in CI/CD).
"""

import io
import os
import logging
from datetime import datetime
from typing import Optional

import pytz
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]


def _get_drive_service():
    """Build and return an authenticated Google Drive API service."""
    info = settings.get_service_account_info()
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def list_video_files(folder_id: str) -> list[dict]:
    """
    List all video files in a Drive folder, sorted by creation date (oldest first).

    Returns a list of dicts: [{id, name, mimeType, createdTime, size}, ...]
    """
    service = _get_drive_service()

    # Build MIME type filter for common video extensions
    mime_types = [
        "video/mp4",
        "video/quicktime",
        "video/x-msvideo",
        "video/x-matroska",
        "video/webm",
        "video/mpeg",
        "application/octet-stream",  # sometimes Drive uses this for .mp4
    ]
    mime_query = " or ".join(f"mimeType='{m}'" for m in mime_types)

    query = (
        f"'{folder_id}' in parents "
        f"and trashed=false "
        f"and ({mime_query})"
    )

    files = []
    page_token = None

    try:
        while True:
            response = (
                service.files()
                .list(
                    q=query,
                    spaces="drive",
                    fields="nextPageToken, files(id, name, mimeType, createdTime, size)",
                    orderBy="createdTime asc",
                    pageToken=page_token,
                )
                .execute()
            )
            files.extend(response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
    except Exception as exc:
        logger.error("Failed to list Drive files: %s", exc)
        raise

    logger.info("Found %d video file(s) in Drive folder %s", len(files), folder_id)
    return files


def get_oldest_video(folder_id: str) -> Optional[dict]:
    """Return the oldest video file in the folder, or None if folder is empty."""
    files = list_video_files(folder_id)

    # Filter out already processed files (marked with DONE)
    video_files = [
        f for f in files
        if not f["name"].startswith("✅ DONE")
        and not f["name"].startswith("DONE -")
        and (any(f["name"].lower().endswith(ext) for ext in settings.VIDEO_EXTENSIONS)
             or f["mimeType"].startswith("video/"))
    ]

    if not video_files:
        return None

    # Already sorted oldest-first by the API, but let's double-check
    video_files.sort(key=lambda f: f.get("createdTime", ""))
    return video_files[0]


def download_video(file_id: str, file_name: str) -> str:
    """
    Download a Drive file to the local temp directory.

    Returns the local file path.
    """
    service = _get_drive_service()
    os.makedirs(settings.TMP_DIR, exist_ok=True)
    local_path = os.path.join(settings.TMP_DIR, file_name)

    logger.info("Downloading Drive file '%s' (ID: %s) to %s", file_name, file_id, local_path)

    try:
        request = service.files().get_media(fileId=file_id)
        buffer = io.FileIO(local_path, mode="wb")
        downloader = MediaIoBaseDownload(buffer, request, chunksize=10 * 1024 * 1024)

        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                percent = int(status.progress() * 100)
                logger.debug("Download progress: %d%%", percent)

        buffer.close()
    except Exception as exc:
        logger.error("Failed to download file '%s': %s", file_name, exc)
        if os.path.exists(local_path):
            os.remove(local_path)
        raise

    size_mb = os.path.getsize(local_path) / (1024 * 1024)
    logger.info("Downloaded '%s' — %.2f MB", file_name, size_mb)
    return local_path


PROCESSED_FOLDER_ID = "1ONZ8c2QMFOWiYtnwdOg4Oko7sEcVyl-X"  # PROCESSED folder


def delete_file(file_id: str, file_name: str) -> bool:
    """
    Move processed file to PROCESSED folder in Google Drive.
    This keeps the main folder clean and tracks processed videos.

    Returns True on success, False on failure.
    """
    service = _get_drive_service()
    
    # Try to move file to processed folder
    try:
        # First try to remove from current parent and add to new parent
        file = service.files().get(fileId=file_id, fields='parents').execute()
        previous_parents = ",".join(file.get('parents', []))
        
        service.files().update(
            fileId=file_id,
            removeParents=previous_parents,
            addParents=PROCESSED_FOLDER_ID,
            body={'name': file_name}  # Keep original name
        ).execute()
        
        logger.info("Moved '%s' to PROCESSED folder (ID: %s)", file_name, file_id)
        return True
    except Exception as exc:
        logger.warning("Failed to move to PROCESSED folder: %s", exc)
    
    # Fallback: Try to rename if move fails
    try:
        new_name = f"✅ DONE - {file_name}"
        service.files().update(fileId=file_id, body={"name": new_name}).execute()
        logger.info("Renamed '%s' to '%s'", file_name, new_name)
        return True
    except Exception as exc:
        logger.error("Failed to process '%s': %s", file_name, exc)
        return False

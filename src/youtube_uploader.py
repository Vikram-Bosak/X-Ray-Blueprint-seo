"""
src/youtube_uploader.py
────────────────────────
Upload a video file to YouTube using the Data API v3 (OAuth2 with refresh token).
Handles resumable uploads, quota checks, and status verification.
"""

import json
import logging
import os
import sys
import time

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

logger = logging.getLogger(__name__)

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
                  "https://www.googleapis.com/auth/youtube"]

# YouTube API resumable upload chunk size: 50 MB
CHUNK_SIZE = 50 * 1024 * 1024

# Retry settings for transient errors
MAX_RETRIES = 5
RETRIABLE_STATUS_CODES = {500, 502, 503, 504}
RETRIABLE_EXCEPTIONS = (ConnectionError, TimeoutError)


def _get_youtube_service():
    """Build an authenticated YouTube API service using OAuth2 refresh token."""
    creds = Credentials(
        token=None,
        refresh_token=settings.YOUTUBE_REFRESH_TOKEN,
        client_id=settings.YOUTUBE_CLIENT_ID,
        client_secret=settings.YOUTUBE_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=YOUTUBE_SCOPES,
    )
    # Refresh the access token
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def check_quota(service) -> bool:
    """
    Perform a lightweight API call to confirm the quota is not exhausted.
    YouTube's write quota is 10,000 units/day; a video upload costs 1,600 units.
    We can't directly read quota, so we do a read call to check connectivity.
    Returns True if quota appears fine, False on quota exceeded errors.
    """
    try:
        service.channels().list(part="snippet", mine=True).execute()
        return True
    except HttpError as exc:
        if exc.resp.status == 403:
            reason = ""
            try:
                body = json.loads(exc.content)
                reason = body["error"]["errors"][0].get("reason", "")
            except Exception:
                pass
            if "quotaExceeded" in reason or "dailyLimitExceeded" in reason:
                logger.error("YouTube API daily quota exceeded. Try again tomorrow.")
                return False
        logger.warning("Quota check call failed (non-quota error): %s", exc)
        return True  # Assume OK for non-quota errors
    except Exception as exc:
        logger.warning("Quota check failed unexpectedly: %s", exc)
        return True


def upload_video(local_path: str, metadata: dict) -> dict:
    """
    Upload a video to YouTube as a Short.

    Parameters
    ----------
    local_path : str
        Path to the local video file.
    metadata : dict
        SEO metadata with keys: title, description, tags, category_id, default_language.

    Returns
    -------
    dict with keys: video_id, video_url, title
    Raises on failure.
    """
    service = _get_youtube_service()

    # Quota check before upload
    if not check_quota(service):
        raise RuntimeError("YouTube daily upload quota has been exceeded.")

    title = metadata["title"]
    description = metadata["description"]
    tags = metadata.get("tags", [])
    category_id = metadata.get("category_id", "22")
    default_language = metadata.get("default_language", "en")
    
    # Clean tags for YouTube API
    # YouTube doesn't allow: special chars, tags starting with numbers, too short, too long
    import re
    clean_tags = []
    
    # Fallback safe tags if AI generates bad tags
    fallback_tags = [
        "coin", "swallow", "digestive", "body", "3D", "animation",
        "science", "medical", "anatomy", "educational", "shorts"
    ]
    
    for t in tags:
        # Convert to string and clean
        t_str = str(t).strip()
        # Remove all special characters, keep only letters and spaces
        t_clean = re.sub(r'[^a-zA-Z\s]', '', t_str)
        # Split and take first word if contains multiple words
        t_clean = t_clean.split()[0] if t_clean.split() else ""
        # Limit to 24 chars
        t_clean = t_clean[:24]
        # Skip if too short or starts with number
        if t_clean and len(t_clean) >= 3 and not t_clean[0].isdigit():
            if t_clean.lower() not in [ct.lower() for ct in clean_tags]:
                clean_tags.append(t_clean)
    
    # If no valid tags, use fallback
    if not clean_tags:
        clean_tags = fallback_tags[:10]
    
    tags = clean_tags[:35]

    # Ensure #Shorts is in the title for YouTube to classify as a Short
    if "#Shorts" not in title and "#shorts" not in title:
        # Append if short enough, otherwise prepend to description
        if len(title) + 8 <= 100:
            title = title + " #Shorts"
        else:
            description = "#Shorts #YouTubeShorts\n\n" + description

    body = {
        "snippet": {
            "title": str(title)[:100],
            "description": str(description)[:5000],
            "tags": tags[:500] if isinstance(tags, list) else [],
            "categoryId": str(category_id),
            "defaultLanguage": str(default_language),
            "defaultAudioLanguage": str(default_language),
        },
        "status": {
            "privacyStatus": "public",  # Ensure video is published immediately
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        local_path,
        mimetype="video/*",
        resumable=True,
        chunksize=CHUNK_SIZE,
    )

    insert_request = service.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )

    logger.info("Starting YouTube upload: '%s'", title)
    response = _resumable_upload(insert_request)

    video_id = response["id"]
    video_url = f"https://youtube.com/shorts/{video_id}"
    logger.info("Upload complete! Video ID: %s | URL: %s", video_id, video_url)

    return {
        "video_id": video_id,
        "video_url": video_url,
        "title": title,
    }


def _resumable_upload(insert_request):
    """
    Execute a resumable upload with exponential back-off retry on transient errors.
    """
    response = None
    error = None
    retry = 0

    while response is None:
        try:
            status, response = insert_request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                logger.info("Upload progress: %d%%", pct)
        except HttpError as exc:
            if exc.resp.status in RETRIABLE_STATUS_CODES:
                error = exc
            else:
                raise
        except RETRIABLE_EXCEPTIONS as exc:
            error = exc

        if error:
            retry += 1
            if retry > MAX_RETRIES:
                logger.error("Max retries exceeded during upload.")
                raise error
            wait = 2 ** retry
            logger.warning("Transient error on upload (attempt %d/%d): %s. Retrying in %ds...",
                           retry, MAX_RETRIES, error, wait)
            time.sleep(wait)
            error = None

    return response

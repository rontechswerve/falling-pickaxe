import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests
from dateutil import parser

from config import config

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"

logger = logging.getLogger(__name__)

session = requests.Session()
seen_comments = set()


def _access_token() -> Optional[str]:
    token = config.get("INSTAGRAM_ACCESS_TOKEN")
    if not token:
        logger.warning("INSTAGRAM_ACCESS_TOKEN is not set; Instagram Live polling is disabled.")
        return None
    return token


def _get(url: str, params: Dict[str, str]) -> Optional[Dict]:
    token = _access_token()
    if not token:
        return None

    try:
        response = session.get(url, params={**params, "access_token": token}, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        logger.error("Instagram API request failed: %s", exc)
    return None


def get_live_media_for_user(user_id: str) -> List[Dict]:
    """Return all live or recently live media for the Instagram user."""
    if not user_id:
        return []

    data = _get(
        f"{GRAPH_API_BASE}/{user_id}/live_media",
        {"fields": "id,status,title,ingest_streams"},
    )
    return data.get("data", []) if data else []


def get_live_media(live_media_id: str) -> Optional[Dict]:
    """Retrieve metadata for a single live media/broadcast."""
    if not live_media_id:
        return None

    data = _get(
        f"{GRAPH_API_BASE}/{live_media_id}",
        {"fields": "id,status,title,ingest_streams"},
    )
    return data if data else None


def get_active_live_media(user_id: str) -> Optional[Dict]:
    """Return the first active live media for the given user, if any."""
    live_media_list = get_live_media_for_user(user_id)
    for media in live_media_list:
        status = (media.get("status") or "").lower()
        if status in {"live", "active", "inprogress", "in_progress"}:
            detailed = get_live_media(media.get("id"))
            return detailed or media
    return None


def get_live_comment_stream_id(live_media: Dict) -> Optional[str]:
    """Instagram Live comments are keyed by the live media ID itself."""
    if not live_media:
        return None
    return live_media.get("id")


def get_new_live_comments(live_media_id: str) -> List[Dict]:
    """Fetch and return new Instagram Live comments that haven't been seen yet."""
    if not live_media_id:
        return []

    data = _get(
        f"{GRAPH_API_BASE}/{live_media_id}/live_comments",
        {"fields": "id,text,from{id,username,profile_picture_url},created_time"},
    )
    if not data or "data" not in data:
        return []

    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"ig_chat_{datetime.today().strftime('%Y-%m-%d')}.txt"

    messages: List[Dict] = []
    for item in data.get("data", []):
        comment_id = item.get("id")
        if not comment_id or comment_id in seen_comments:
            continue

        seen_comments.add(comment_id)

        author_info = item.get("from", {}) or {}
        timestamp_raw = item.get("created_time")
        timestamp = (
            parser.parse(timestamp_raw).strftime("%Y-%m-%d %H:%M:%S")
            if timestamp_raw
            else datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        )

        display_name = author_info.get("username") or author_info.get("id") or "Unknown"
        message_text = item.get("text") or ""

        log_message = f"[{timestamp}] {display_name}: {message_text}"
        with open(log_file, "a+", encoding="utf-8") as chat_file:
            chat_file.write(log_message + "\n")

        messages.append(
            {
                "timestamp": timestamp,
                "author": display_name,
                "author_channel_id": author_info.get("id") or display_name,
                "profile_image_url": author_info.get("profile_picture_url"),
                "message": message_text,
                "sc_details": None,
                "ss_details": None,
            }
        )

    return messages

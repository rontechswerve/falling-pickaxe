import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from dateutil import parser

from config import config

GRAPH_API_BASE = "https://graph.facebook.com/v24.0"

logger = logging.getLogger(__name__)

session = requests.Session()
seen_comments = set()
profile_picture_cache: Dict[str, Optional[str]] = {}


def _is_placeholder(value: Optional[str]) -> bool:
    if not value:
        return True
    return str(value).startswith("YOUR_") or str(value).endswith("_OPTIONAL")


def is_configured(value: Optional[str]) -> bool:
    """Return True when the provided config string is non-empty and not a placeholder."""
    return not _is_placeholder(value)


def _access_token() -> Optional[str]:
    token = config.get("INSTAGRAM_ACCESS_TOKEN")
    if not token or _is_placeholder(token):
        logger.warning("INSTAGRAM_ACCESS_TOKEN is not set; Instagram Live polling is disabled.")
        return None
    return token


token_invalidated = False


def _get(url: str, params: Dict[str, str]) -> Optional[Dict]:
    global token_invalidated

    token = _access_token()
    if not token:
        return None

    if token_invalidated:
        logger.warning("Skipping Instagram Graph call because the access token is invalid or expired.")
        return None

    params_with_token = {**params, "access_token": token}

    try:
        response = session.get(url, params=params_with_token, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as exc:
        message = exc.response.text if exc.response is not None else str(exc)
        error_json: Dict[str, Dict] = {}
        try:
            error_json = exc.response.json() if exc.response is not None else {}
        except Exception:  # noqa: BLE001 - best-effort parse for diagnostics only
            error_json = {}

        error_info = error_json.get("error") or {}
        code = error_info.get("code")
        subcode = error_info.get("error_subcode")
        if code == 190:
            token_invalidated = True
            logger.error(
                "Instagram access token is invalid or expired (code %s, subcode %s). "
                "Refresh the token via Instagram Login / Facebook Graph and update INSTAGRAM_ACCESS_TOKEN.",
                code,
                subcode,
            )
        logger.error("Instagram API request failed: %s :: %s", exc, message)
    except requests.RequestException as exc:
        logger.error("Instagram API request failed: %s", exc)

    return None


def _get_with_field_fallback(url: str, field_variants: List[str]) -> Optional[Dict]:
    """Try the provided field lists in order, stopping once data is returned.

    Some Graph node types omit fields like `status` (e.g., ShadowIGMedia). To avoid
    fatal errors when callers provide a specific live media ID, we progressively
    degrade to slimmer field sets so we can still fetch usable data.
    """

    for fields in field_variants:
        data = _get(url, {"fields": fields})
        if data:
            return data
        if token_invalidated:
            break

    logger.error("Unable to fetch %s with any provided field set: %s", url, field_variants)
    return None


def _get_edge_variant(base_url: str, edges: List[str], params: Dict[str, str]) -> Optional[Dict]:
    """Try multiple edge names on the same base node until one returns data."""

    for edge in edges:
        data = _get(f"{base_url}/{edge}", params)
        if data:
            return data
        if token_invalidated:
            break

    logger.error("Unable to fetch %s with any provided edge: %s", base_url, edges)
    return None


def _resolve_first_available(data: Dict, keys: List[str]) -> Optional[Tuple[str, Dict]]:
    """Find the first populated field from keys and return its id along with the raw object."""

    for key in keys:
        candidate = data.get(key) or {}
        if isinstance(candidate, dict) and candidate.get("id"):
            return candidate.get("id"), candidate
    return None


def get_profile_picture_url(user_id: str) -> Optional[str]:
    """Best-effort lookup for a user's profile picture, with basic caching."""

    if not user_id:
        return None

    if user_id in profile_picture_cache:
        return profile_picture_cache[user_id]

    data = _get(f"{GRAPH_API_BASE}/{user_id}", {"fields": "profile_picture_url,username"})
    if data and data.get("profile_picture_url"):
        profile_picture_cache[user_id] = data.get("profile_picture_url")
        return profile_picture_cache[user_id]

    profile_picture_cache[user_id] = None
    return None


def get_instagram_user_from_page(page_id: str) -> Tuple[Optional[str], Optional[Dict]]:
    """Discover the IG user linked to a Facebook Page (business/creator or shadow IG user)."""

    if not page_id:
        return None, None

    data = _get(
        f"{GRAPH_API_BASE}/{page_id}",
        {
            "fields": ",".join(
                [
                    "instagram_business_account{id,ig_id,username}",
                    "instagram_professional_account{id,ig_id,username}",
                    "connected_instagram_account{id,ig_id,username}",
                    "shadow_ig_user{id,ig_id,username}",
                ]
            )
        },
    )

    if not data:
        return None, None

    resolution = _resolve_first_available(
        data,
        [
            "instagram_business_account",
            "instagram_professional_account",
            "connected_instagram_account",
            "shadow_ig_user",
        ],
    )

    if resolution:
        return resolution[0], resolution[1]

    logger.warning(
        "Facebook Page %s did not return a linked Instagram account (business/professional/connected/shadow).",
        page_id,
    )
    return None, data


def get_live_media_for_user(user_id: str) -> List[Dict]:
    """Return all live or recently live media for the Instagram user."""
    if not user_id or _is_placeholder(user_id):
        return []

    data = _get_with_field_fallback(
        f"{GRAPH_API_BASE}/{user_id}/live_media",
        [
            "id,status,title,ingest_streams",
            "id,live_status,title,ingest_streams",
            "id,title",
            "id",
        ],
    )
    return data.get("data", []) if data else []


def discover_user_id() -> Tuple[Optional[str], Optional[Dict]]:
    """Resolve an Instagram user ID using config hints (user id, Facebook Page, or shadow IG user)."""

    configured_user = config.get("INSTAGRAM_USER_ID")
    if configured_user and not _is_placeholder(configured_user):
        return configured_user, {"source": "configured_user"}

    shadow_user = config.get("INSTAGRAM_SHADOW_USER_ID")
    if shadow_user and not _is_placeholder(shadow_user):
        return shadow_user, {"source": "shadow_user"}

    page_id = config.get("FACEBOOK_PAGE_ID")
    if page_id and not _is_placeholder(page_id):
        user_id, raw = get_instagram_user_from_page(page_id)
        if user_id:
            return user_id, {"source": "page_lookup", "details": raw}

    return None, None


def get_live_media(live_media_id: str) -> Optional[Dict]:
    """Retrieve metadata for a single live media/broadcast."""
    if not live_media_id or _is_placeholder(live_media_id):
        return None

    data = _get_with_field_fallback(
        f"{GRAPH_API_BASE}/{live_media_id}",
        [
            "id,status,title,ingest_streams",
            "id,live_status,title,ingest_streams",
            "id,title",
            "id",
        ],
    )
    return data if data else None


def get_active_live_media(user_id: str) -> Optional[Dict]:
    """Return the first active live media for the given user, if any."""
    live_media_list = get_live_media_for_user(user_id)
    if live_media_list:
        statuses = ", ".join(
            [
                f"{media.get('id')}: {media.get('status')}" for media in live_media_list
                if media.get("id")
            ]
        )
        logger.info("Found live_media entries for user %s: %s", user_id, statuses)
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

    data = _get_edge_variant(
        f"{GRAPH_API_BASE}/{live_media_id}",
        ["live_comments", "comments"],
        {"fields": "id,text,from{id,username},created_time"},
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
        author_id = author_info.get("id")
        timestamp_raw = item.get("created_time")
        timestamp = (
            parser.parse(timestamp_raw).strftime("%Y-%m-%d %H:%M:%S")
            if timestamp_raw
            else datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        )

        display_name = author_info.get("username") or author_info.get("id") or "Unknown"
        message_text = item.get("text") or ""
        profile_image_url = author_info.get("profile_picture_url") or get_profile_picture_url(author_id)

        log_message = f"[{timestamp}] {display_name}: {message_text}"
        with open(log_file, "a+", encoding="utf-8") as chat_file:
            chat_file.write(log_message + "\n")

        messages.append(
            {
                "timestamp": timestamp,
                "author": display_name,
                "author_channel_id": author_id or display_name,
                "profile_image_url": profile_image_url,
                "message": message_text,
                "sc_details": None,
                "ss_details": None,
            }
        )

    return messages

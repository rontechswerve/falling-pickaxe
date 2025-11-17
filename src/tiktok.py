import asyncio
import importlib
import logging
import sys
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def is_configured(value: Optional[str]) -> bool:
    """Return True when the provided value is non-empty and not a placeholder."""
    if value is None:
        return False
    value_str = str(value).strip()
    return bool(value_str) and not value_str.upper().startswith("YOUR_")


if TYPE_CHECKING:  # pragma: no cover - import only for type checkers
    from TikTokLive import TikTokLiveClient
    from TikTokLive.events import CommentEvent, ConnectEvent, GiftEvent


class TikTokChatBridge:
    """Bridge TikTok Live events into in-game chat command queues."""

    def __init__(
        self,
        unique_id: str,
        tnt_queue: List[Dict],
        superchat_queue: List[Dict],
        fast_slow_queue: List[Dict],
        big_queue: List[Dict],
        pickaxe_queue: List[Dict],
        mega_tnt_queue: List[Dict],
    ) -> None:
        TikTokLiveClient, CommentEvent, ConnectEvent, GiftEvent = _load_tiktoklive()

        self.unique_id = unique_id
        self.tnt_queue = tnt_queue
        self.superchat_queue = superchat_queue
        self.fast_slow_queue = fast_slow_queue
        self.big_queue = big_queue
        self.pickaxe_queue = pickaxe_queue
        self.mega_tnt_queue = mega_tnt_queue
        self.client = TikTokLiveClient(unique_id=unique_id, process_initial_data=False)
        self._register_handlers(CommentEvent, ConnectEvent, GiftEvent)

    def _register_handlers(self, CommentEvent, ConnectEvent, GiftEvent) -> None:
        @self.client.on("connect")
        async def _on_connect(_: ConnectEvent) -> None:
            logger.info("Connected to TikTok Live as %s (room %s)", self.unique_id, self.client.room_id)

        @self.client.on("comment")
        async def _on_comment(event: CommentEvent) -> None:
            display_name = event.user.nickname or event.user.uniqueId or "Unknown"
            author_id = str(event.user.userId or event.user.uniqueId or display_name)
            message = event.comment or ""
            profile_image_url = _extract_avatar(event)

            payload = {
                "author_id": author_id,
                "display_name": display_name,
                "message": message,
                "profile_image_url": profile_image_url,
            }

            logger.info("Queued TNT for chat message from %s", display_name)
            text_lower = message.lower()
            highlight = "tnt" if "tnt" in text_lower else None
            self.tnt_queue.append({**payload, "highlight": highlight})

            if "megatnt" in text_lower:
                logger.info("Added %s to MegaTNT queue (keyword)", display_name)
                self.mega_tnt_queue.append({**payload, "highlight": "megatnt"})

            if "fast" in text_lower and author_id not in [entry.get("author_id") for entry in self.fast_slow_queue]:
                self.fast_slow_queue.append({"author_id": author_id, "display_name": display_name, "choice": "Fast"})
                logger.info("Added %s to Fast/Slow queue (Fast)", display_name)
            elif "slow" in text_lower and author_id not in [entry.get("author_id") for entry in self.fast_slow_queue]:
                self.fast_slow_queue.append({"author_id": author_id, "display_name": display_name, "choice": "Slow"})
                logger.info("Added %s to Fast/Slow queue (Slow)", display_name)

            if "big" in text_lower and author_id not in [entry.get("author_id") for entry in self.big_queue]:
                self.big_queue.append({"author_id": author_id, "display_name": display_name})
                logger.info("Added %s to Big queue", display_name)

            pickaxe_map = {
                "wood": "wooden_pickaxe",
                "stone": "stone_pickaxe",
                "iron": "iron_pickaxe",
                "gold": "golden_pickaxe",
                "diamond": "diamond_pickaxe",
                "netherite": "netherite_pickaxe",
            }
            for key, pickaxe_type in pickaxe_map.items():
                if key in text_lower and author_id not in [entry.get("author_id") for entry in self.pickaxe_queue]:
                    self.pickaxe_queue.append({
                        "author_id": author_id,
                        "display_name": display_name,
                        "pickaxe_type": pickaxe_type,
                    })
                    logger.info("Added %s to Pickaxe queue (%s)", display_name, pickaxe_type)
                    break

        @self.client.on("gift")
        async def _on_gift(event: GiftEvent) -> None:
            display_name = event.user.nickname or event.user.uniqueId or "Unknown"
            author_id = str(event.user.userId or event.user.uniqueId or display_name)
            profile_image_url = _extract_avatar(event)
            gift_name = None
            try:
                gift_name = event.gift.extended_gift.name  # type: ignore[attr-defined]
            except Exception:
                gift_name = getattr(event.gift, "name", None)

            message = f"Gift: {gift_name or 'TikTok gift'}"
            payload = {
                "author_id": author_id,
                "display_name": display_name,
                "message": message,
                "profile_image_url": profile_image_url,
                "highlight": "megatnt",
            }
            logger.info("Added %s to Superchat MegaTNT queue (gift)", display_name)
            self.superchat_queue.append(payload)

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        asyncio.run_coroutine_threadsafe(self.client.start(), loop)


def _extract_avatar(event: object) -> Optional[str]:
    user = getattr(event, "user", None)
    if user is None:
        return None
    profile_picture = getattr(user, "profilePicture", None)
    if profile_picture is None:
        return None
    avatar_url = getattr(profile_picture, "avatar_url", None)
    if avatar_url:
        return avatar_url
    urls = getattr(profile_picture, "urls", None)
    if urls:
        try:
            return urls[0]
        except Exception:
            return None
    return None


def _load_tiktoklive() -> Tuple[object, object, object, object]:
    """Import TikTokLive lazily so Python 3.9 users see a friendly message."""

    if sys.version_info < (3, 10):
        raise RuntimeError(
            "TikTok chat control requires Python 3.10+ because the TikTokLive "
            "library uses modern type syntax. Please upgrade your Python interpreter "
            "or disable CHAT_CONTROL."
        )

    try:
        tiktoklive_module = importlib.import_module("TikTokLive")
        events_module = importlib.import_module("TikTokLive.events")
        TikTokLiveClient = getattr(tiktoklive_module, "TikTokLiveClient")
        CommentEvent = getattr(events_module, "CommentEvent")
        ConnectEvent = getattr(events_module, "ConnectEvent")
        GiftEvent = getattr(events_module, "GiftEvent")
        return TikTokLiveClient, CommentEvent, ConnectEvent, GiftEvent
    except TypeError as exc:
        raise RuntimeError(
            "TikTokLive failed to import due to Python version incompatibility. "
            "Use Python 3.10+ or pin TikTokLive to a version that supports older interpreters."
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            "TikTokLive dependency is not available. Run `pip install TikTokLive` or disable CHAT_CONTROL."
        ) from exc


def start_tiktok_bridge(
    unique_id: str,
    tnt_queue: List[Dict],
    superchat_queue: List[Dict],
    fast_slow_queue: List[Dict],
    big_queue: List[Dict],
    pickaxe_queue: List[Dict],
    mega_tnt_queue: List[Dict],
    loop: asyncio.AbstractEventLoop,
) -> Optional[TikTokChatBridge]:
    try:
        bridge = TikTokChatBridge(
            unique_id,
            tnt_queue,
            superchat_queue,
            fast_slow_queue,
            big_queue,
            pickaxe_queue,
            mega_tnt_queue,
        )
        bridge.start(loop)
        return bridge
    except RuntimeError as exc:
        logger.error(str(exc))
        return None

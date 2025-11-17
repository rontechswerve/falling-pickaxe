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
    from TikTokLive.client.client import TikTokLiveClient
    from TikTokLive.client.logger import LogLevel
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
        (
            TikTokLiveClient,
            CommentEvent,
            ConnectEvent,
            GiftEvent,
            DisconnectEvent,
            LiveEndEvent,
            LogLevel,
        ) = _load_tiktoklive()

        self.unique_id = unique_id
        self.tnt_queue = tnt_queue
        self.superchat_queue = superchat_queue
        self.fast_slow_queue = fast_slow_queue
        self.big_queue = big_queue
        self.pickaxe_queue = pickaxe_queue
        self.mega_tnt_queue = mega_tnt_queue
        self._client_factory = lambda: TikTokLiveClient(unique_id=unique_id)
        self.client = self._client_factory()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._future: Optional[asyncio.Future] = None
        self._health_task: Optional[asyncio.Future] = None
        self._restart_pending: bool = False
        self._last_comment_time: Optional[float] = None
        self._last_gift_time: Optional[float] = None
        # Surface the TikTokLive client's own debug logs for troubleshooting.
        try:
            self.client.logger.setLevel(LogLevel.DEBUG.value)
        except Exception:
            self.client.logger.setLevel(logging.DEBUG)
        logger.debug("TikTokLive client created for @%s", unique_id)
        self._register_handlers(CommentEvent, ConnectEvent, GiftEvent, DisconnectEvent, LiveEndEvent)

    def _register_handlers(self, CommentEvent, ConnectEvent, GiftEvent, DisconnectEvent, LiveEndEvent) -> None:
        logger.debug("Registering TikTokLive handlers for connect/comment/gift events")

        @self.client.on(ConnectEvent)
        async def _on_connect(_: ConnectEvent) -> None:
            logger.info("Connected to TikTok Live as %s (room %s)", self.unique_id, self.client.room_id)
            logger.debug("Connection details: state=%s room_info=%s", getattr(self.client, "connected", None), getattr(self.client, "room_info", None))

        # Log disconnects to help diagnose dropped sessions or offline rooms.
        if DisconnectEvent:
            @self.client.on(DisconnectEvent)
            async def _on_disconnect(event):  # type: ignore[no-untyped-def]
                logger.warning(
                    "Disconnected from TikTok Live (room %s); reason=%s", getattr(event, "room_id", "?"), getattr(event, "reason", "unknown")
                )

        # Report when the stream ends so users know why comments stopped flowing.
        if LiveEndEvent:
            @self.client.on(LiveEndEvent)
            async def _on_live_end(event):  # type: ignore[no-untyped-def]
                logger.warning(
                    "TikTok Live ended for @%s (room %s); event=%s", self.unique_id, getattr(event, "room_id", "?"), event
                )

        @self.client.on(CommentEvent)
        async def _on_comment(event: CommentEvent) -> None:
            logger.debug("Received TikTok comment event: %s", event)
            self._last_comment_time = asyncio.get_running_loop().time()
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

            print(f"TikTok chat: {display_name} -> {message}")
            logger.info("Queued TNT for chat message from %s", display_name)
            logger.debug("Queues now: tnt=%d mega=%d fast/slow=%d big=%d pickaxe=%d", len(self.tnt_queue), len(self.mega_tnt_queue), len(self.fast_slow_queue), len(self.big_queue), len(self.pickaxe_queue))
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

        @self.client.on(GiftEvent)
        async def _on_gift(event: GiftEvent) -> None:
            logger.debug("Received TikTok gift event: %s", event)
            self._last_gift_time = asyncio.get_running_loop().time()
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
            print(f"TikTok gift from {display_name}: {gift_name or 'TikTok gift'}")
            logger.info("Added %s to Superchat MegaTNT queue (gift)", display_name)
            logger.debug("Superchat queue size now %d", len(self.superchat_queue))
            self.superchat_queue.append(payload)

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        logger.debug("Starting TikTokLive client for @%s in background loop", self.unique_id)
        self._loop = loop

        if self._health_task is None:
            self._health_task = asyncio.run_coroutine_threadsafe(self._log_health(), loop)

        self._start_client()

    def _start_client(self) -> None:
        if self._loop is None:
            return

        if getattr(self.client, "connected", False):
            logger.debug("TikTokLive client already connected; skipping start")
            return

        logger.info("Starting TikTokLive connection to @%s", self.unique_id)
        self._future = asyncio.run_coroutine_threadsafe(self.client.start(), self._loop)
        self._future.add_done_callback(self._on_future_done)

    def _on_future_done(self, fut: asyncio.Future) -> None:
        try:
            fut.result()
        except Exception as exc:  # pragma: no cover - troubleshooting aid
            if exc.__class__.__name__ == "UserOfflineError":
                logger.error(
                    "TikTokLive reported @%s offline or room closed. Ensure the stream is live and the unique_id is correct.",
                    self.unique_id,
                )
                self._reset_client()
                self._schedule_restart("offline or room closed")
            elif exc.__class__.__name__ == "AlreadyConnectedError":
                logger.warning("TikTokLive client reported an existing connection; resetting client before retry")
                self._reset_client()
                self._schedule_restart("recover from duplicate connection")
            else:
                logger.error("TikTokLive client stopped with error: %s", exc, exc_info=exc)
                self._reset_client()
                self._schedule_restart("error")
        else:
            logger.warning("TikTokLive client stopped without error; stream may have ended.")
            self._reset_client()
            self._schedule_restart("stream ended")

    def _schedule_restart(self, reason: str, delay_seconds: int = 15) -> None:
        if self._loop is None or self._restart_pending:
            return

        self._restart_pending = True
        logger.info("Reconnecting to TikTok Live in %ds (%s)", delay_seconds, reason)

        def _do_restart() -> None:
            self._restart_pending = False
            self._start_client()

        self._loop.call_later(delay_seconds, _do_restart)

    def _reset_client(self) -> None:
        """Dispose of the current client and create a fresh one before reconnecting."""
        try:
            if getattr(self.client, "connected", False) and self._loop is not None:
                self._loop.call_soon_threadsafe(lambda: asyncio.ensure_future(self.client.stop()))
        except Exception:
            logger.debug("Failed to stop TikTokLive client during reset", exc_info=True)

        (
            TikTokLiveClient,
            CommentEvent,
            ConnectEvent,
            GiftEvent,
            DisconnectEvent,
            LiveEndEvent,
            LogLevel,
        ) = _load_tiktoklive()

        self.client = self._client_factory()
        try:
            self.client.logger.setLevel(LogLevel.DEBUG.value)
        except Exception:
            self.client.logger.setLevel(logging.DEBUG)

        self._register_handlers(CommentEvent, ConnectEvent, GiftEvent, DisconnectEvent, LiveEndEvent)

    async def _log_health(self) -> None:
        """Periodically log connection state and queue sizes while running."""
        while True:
            try:
                await asyncio.sleep(15)
                logger.info(
                    "TikTokLive health: connected=%s room_id=%s queued tnt=%d mega=%d fast/slow=%d big=%d pickaxe=%d last_comment=%s last_gift=%s",
                    getattr(self.client, "connected", None),
                    getattr(self.client, "room_id", None),
                    len(self.tnt_queue),
                    len(self.mega_tnt_queue),
                    len(self.fast_slow_queue),
                    len(self.big_queue),
                    len(self.pickaxe_queue),
                    f"{self._last_comment_time:.1f}" if self._last_comment_time else "never",
                    f"{self._last_gift_time:.1f}" if self._last_gift_time else "never",
                )
            except Exception as exc:  # pragma: no cover - debug helper
                logger.error("Health logger crashed: %s", exc, exc_info=exc)
                return


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


def _load_tiktoklive() -> Tuple[object, object, object, object, Optional[object], Optional[object], object]:
    """Import TikTokLive lazily so Python 3.9 users see a friendly message."""

    if sys.version_info < (3, 10):
        raise RuntimeError(
            "TikTok chat control requires Python 3.10+ because the TikTokLive "
            "library uses modern type syntax. Please upgrade your Python interpreter "
            "or disable CHAT_CONTROL."
        )

    try:
        client_module = importlib.import_module("TikTokLive.client.client")
        events_module = importlib.import_module("TikTokLive.events")
        logger_module = importlib.import_module("TikTokLive.client.logger")
        TikTokLiveClient = getattr(client_module, "TikTokLiveClient")
        CommentEvent = getattr(events_module, "CommentEvent")
        ConnectEvent = getattr(events_module, "ConnectEvent")
        GiftEvent = getattr(events_module, "GiftEvent")
        DisconnectEvent = getattr(events_module, "DisconnectEvent", None)
        LiveEndEvent = getattr(events_module, "LiveEndEvent", None)
        LogLevel = getattr(logger_module, "LogLevel")
        return (
            TikTokLiveClient,
            CommentEvent,
            ConnectEvent,
            GiftEvent,
            DisconnectEvent,
            LiveEndEvent,
            LogLevel,
        )
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

import asyncio
import importlib
import logging
import sys
from collections import deque
from typing import TYPE_CHECKING, Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def is_configured(value: Optional[str]) -> bool:
    """Return True when the provided value is non-empty and not a placeholder."""
    if value is None:
        return False
    value_str = str(value).strip()
    return bool(value_str) and not value_str.upper().startswith("YOUR_")


class _SeenCache:
    """Track recently seen event keys with bounded memory usage."""

    def __init__(self, maxlen: int = 2000) -> None:
        self._maxlen = maxlen
        self._items: Deque[str] = deque()
        self._index: set[str] = set()

    def add(self, key: str) -> bool:
        """Return True if the key was newly added; False if already present."""

        if key in self._index:
            return False

        self._index.add(key)
        self._items.append(key)

        if len(self._items) > self._maxlen:
            oldest = self._items.popleft()
            self._index.discard(oldest)

        return True




if TYPE_CHECKING:  # pragma: no cover - import only for type checkers
    from TikTokLive.client.client import TikTokLiveClient
    from TikTokLive.client.logger import LogLevel
    from TikTokLive.events import CommentEvent, ConnectEvent, GiftEvent, LikeEvent


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
        *,
        auto_reconnect: bool = False,
    ) -> None:
        (
            TikTokLiveClient,
            CommentEvent,
            ConnectEvent,
            GiftEvent,
            LikeEvent,
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
        self._client_factory = lambda: _create_tiktok_client(TikTokLiveClient, unique_id)
        self.client = self._client_factory()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._future: Optional[asyncio.Future] = None
        self._health_task: Optional[asyncio.Future] = None
        self._restart_pending: bool = False
        self._last_comment_time: Optional[float] = None
        self._last_gift_time: Optional[float] = None
        self._auto_reconnect = auto_reconnect
        self._backoff_attempts: int = 0
        self._seen_comment_ids: _SeenCache = _SeenCache()
        self._seen_gift_ids: _SeenCache = _SeenCache()
        self._seen_like_ids: _SeenCache = _SeenCache()
        self._like_counters: Dict[str, int] = {}
        # Surface the TikTokLive client's own debug logs for troubleshooting.
        try:
            self.client.logger.setLevel(LogLevel.DEBUG.value)
        except Exception:
            self.client.logger.setLevel(logging.DEBUG)
        logger.debug("TikTokLive client created for @%s", unique_id)
        self._register_handlers(CommentEvent, ConnectEvent, GiftEvent, LikeEvent, DisconnectEvent, LiveEndEvent)

    def _register_handlers(self, CommentEvent, ConnectEvent, GiftEvent, LikeEvent, DisconnectEvent, LiveEndEvent) -> None:
        logger.debug("Registering TikTokLive handlers for connect/comment/gift events")

        @self.client.on(ConnectEvent)
        async def _on_connect(_: ConnectEvent) -> None:
            self._backoff_attempts = 0
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

        async def _handle_comment(event: CommentEvent) -> None:
            logger.debug("Received TikTok comment event: %s", event)
            self._last_comment_time = asyncio.get_running_loop().time()
            comment_key = _event_key(event)
            if comment_key and not self._seen_comment_ids.add(comment_key):
                logger.debug("Skipping duplicate comment with key %s", comment_key)
                return
            display_name = _display_name(event)
            author_id = _author_id(event)
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
            logger.debug(
                "Queues now: tnt=%d mega=%d fast/slow=%d big=%d pickaxe=%d",
                len(self.tnt_queue),
                len(self.mega_tnt_queue),
                len(self.fast_slow_queue),
                len(self.big_queue),
                len(self.pickaxe_queue),
            )
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
                    self.pickaxe_queue.append(
                        {
                            "author_id": author_id,
                            "display_name": display_name,
                            "pickaxe_type": pickaxe_type,
                        }
                    )
                    logger.info("Added %s to Pickaxe queue (%s)", display_name, pickaxe_type)
                    break

        async def _handle_gift(event: GiftEvent) -> None:
            logger.debug("Received TikTok gift event: %s", event)
            self._last_gift_time = asyncio.get_running_loop().time()
            gift_key = _event_key(event)
            if gift_key and not self._seen_gift_ids.add(gift_key):
                logger.debug("Skipping duplicate gift with key %s", gift_key)
                return
            display_name = _display_name(event)
            author_id = _author_id(event)
            profile_image_url = _extract_avatar(event)
            gift_name = None
            try:
                gift_name = event.gift.extended_gift.name  # type: ignore[attr-defined]
            except Exception:
                gift_name = getattr(event.gift, "name", None)

            raw_quantity = (
                getattr(event, "repeat_count", None)
                or getattr(event, "count", None)
                or getattr(event.gift, "repeat_count", None)
                or getattr(event.gift, "count", None)
            )
            try:
                quantity = max(int(raw_quantity), 1) if raw_quantity is not None else 1
            except Exception:
                quantity = 1

            raw_coins = getattr(event.gift, "diamond_count", None) or getattr(event, "diamond_count", None)
            try:
                coin_value = int(raw_coins) if raw_coins is not None else None
            except Exception:
                coin_value = None

            message = f"Gift: {gift_name or 'TikTok gift'}"
            base_payload = {
                "author_id": author_id,
                "display_name": display_name,
                "message": message,
                "profile_image_url": profile_image_url,
                "priority": "gift",
            }

            tnt_to_enqueue = 0
            mega_to_enqueue = 0

            if coin_value is not None:
                if coin_value > 50:
                    mega_to_enqueue = 10
                    logger.info("%s gifted >50 coins; queueing %d MegaTNT", display_name, mega_to_enqueue)
                elif coin_value > 1:
                    tnt_to_enqueue = 5
                    mega_to_enqueue = 5
                    logger.info(
                        "%s gifted >1 coin; queueing %d TNT and %d MegaTNT", display_name, tnt_to_enqueue, mega_to_enqueue
                    )
                else:
                    tnt_to_enqueue = 10
                    logger.info("%s gifted 1 coin; queueing %d TNT", display_name, tnt_to_enqueue)
            elif quantity > 1:
                tnt_to_enqueue = 5
                mega_to_enqueue = 5
                logger.info(
                    "%s gifted multiple items (x%s); queueing %d TNT and %d MegaTNT", display_name, quantity, tnt_to_enqueue, mega_to_enqueue
                )
            else:
                tnt_to_enqueue = 10
                logger.info("%s gifted once; queueing %d TNT", display_name, tnt_to_enqueue)

            if tnt_to_enqueue:
                self.tnt_queue.append({**base_payload, "highlight": "tnt", "count": tnt_to_enqueue})
                logger.debug("TNT queue size now %d", len(self.tnt_queue))

            if mega_to_enqueue:
                self.mega_tnt_queue.append({**base_payload, "highlight": "megatnt", "count": mega_to_enqueue})
                logger.debug("MegaTNT queue size now %d", len(self.mega_tnt_queue))

            print(f"TikTok gift from {display_name}: {gift_name or 'TikTok gift'}")

        async def _handle_like(event) -> None:  # type: ignore[no-untyped-def]
            if LikeEvent is None:
                return

            logger.debug("Received TikTok like event: %s", event)
            like_key = _event_key(event)
            if like_key and not self._seen_like_ids.add(like_key):
                logger.debug("Skipping duplicate like with key %s", like_key)
                return

            display_name = _display_name(event)
            author_id = _author_id(event)
            profile_image_url = _extract_avatar(event)
            raw_like_count = getattr(event, "likeCount", None) or getattr(event, "like_count", None) or 1
            try:
                like_count = int(raw_like_count)
            except Exception:
                like_count = 1

            self._like_counters[author_id] = self._like_counters.get(author_id, 0) + max(like_count, 1)
            bundles = self._like_counters[author_id] // 5
            self._like_counters[author_id] %= 5

            if bundles <= 0:
                return

            for _ in range(bundles):
                payload = {
                    "author_id": author_id,
                    "display_name": display_name,
                    "message": "Likes x5",
                    "profile_image_url": profile_image_url,
                    "highlight": "megatnt",
                }
                self.mega_tnt_queue.append(payload)
                logger.info("Added MegaTNT for %s after 5 likes", display_name)
                logger.debug("MegaTNT queue size now %d", len(self.mega_tnt_queue))

        # Register both typed and string-based listeners so we catch proto and string events.
        self.client.add_listener(CommentEvent, _handle_comment)
        self.client.add_listener("comment", _handle_comment)
        self.client.add_listener(GiftEvent, _handle_gift)
        self.client.add_listener("gift", _handle_gift)
        if LikeEvent is not None:
            self.client.add_listener(LikeEvent, _handle_like)
        self.client.add_listener("like", _handle_like)

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
            elif exc.__class__.__name__ == "SignAPIError" or "SIGN_NOT_200" in str(exc):
                delay = self._next_backoff_delay()
                logger.error("TikTokLive Sign API error; retrying in %ds: %s", delay, exc, exc_info=exc)
                self._reset_client()
                self._schedule_restart("sign api error", delay_seconds=delay)
            else:
                logger.error("TikTokLive client stopped with error: %s", exc, exc_info=exc)
                self._reset_client()
                self._schedule_restart("error")
        else:
            logger.warning("TikTokLive client stopped without error; stream may have ended.")
            self._reset_client()
            self._schedule_restart("stream ended")

    def _schedule_restart(self, reason: str, delay_seconds: int = 15) -> None:
        if not self._auto_reconnect:
            logger.info("Auto-reconnect disabled; not restarting after stop (%s)", reason)
            return

        if self._loop is None or self._restart_pending:
            return

        self._restart_pending = True
        logger.info("Reconnecting to TikTok Live in %ds (%s)", delay_seconds, reason)

        def _do_restart() -> None:
            self._restart_pending = False
            self._start_client()

        self._loop.call_later(delay_seconds, _do_restart)

    def _next_backoff_delay(self, base_seconds: int = 5, max_seconds: int = 60) -> int:
        """Return the next exponential backoff delay for reconnect attempts."""

        self._backoff_attempts += 1
        delay = base_seconds * (2 ** (self._backoff_attempts - 1))
        return min(delay, max_seconds)

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
            LikeEvent,
            DisconnectEvent,
            LiveEndEvent,
            LogLevel,
        ) = _load_tiktoklive()

        self.client = self._client_factory()
        try:
            self.client.logger.setLevel(LogLevel.DEBUG.value)
        except Exception:
            self.client.logger.setLevel(logging.DEBUG)

        self._register_handlers(CommentEvent, ConnectEvent, GiftEvent, LikeEvent, DisconnectEvent, LiveEndEvent)

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


def _create_tiktok_client(TikTokLiveClient, unique_id: str):
    """Build a TikTokLive client while disabling history playback when possible."""

    try:
        # process_initial_data=False prevents replaying historical messages on reconnect,
        # which reduces duplicate chat/gift processing.
        return TikTokLiveClient(unique_id=unique_id, process_initial_data=False)
    except TypeError:
        logger.debug("TikTokLiveClient lacks process_initial_data; using defaults")
        return TikTokLiveClient(unique_id=unique_id)


def _event_key(event: object) -> Optional[str]:
    """Return a best-effort stable identifier to deduplicate TikTok events."""

    # Prefer explicit message IDs, then any cursor or client-generated IDs.
    attr_names = [
        "msg_id",
        "msgId",
        "message_id",
        "messageId",
        "event_id",
        "eventId",
        "id",
        "cursor",
        "client_msg_id",
        "clientMsgId",
        "log_id",
        "logId",
        "create_time",
        "createTime",
        "timestamp",
    ]

    for name in attr_names:
        value = getattr(event, name, None)
        if value:
            return str(value)

    base_message = getattr(event, "base_message", None)
    if base_message:
        for name in attr_names:
            value = getattr(base_message, name, None)
            if value:
                return str(value)

    # Fallback: synthesize a key from user + content so repeated history replays are ignored.
    try:
        author = _author_id(event)
    except Exception:
        author = None

    if hasattr(event, "comment"):
        comment_text = getattr(event, "comment", "") or ""
        create_time = getattr(event, "create_time", None) or getattr(event, "timestamp", None)
        return f"comment:{author}:{comment_text}:{create_time}" if author or comment_text else None

    gift = getattr(event, "gift", None)
    if gift is not None:
        gift_id = getattr(gift, "id", None) or getattr(gift, "gift_id", None)
        gift_name = getattr(gift, "name", None)
        create_time = getattr(event, "create_time", None) or getattr(event, "timestamp", None)
        return f"gift:{author}:{gift_id or gift_name}:{create_time}" if (author or gift_id or gift_name) else None

    return None


def _display_name(event: object) -> str:
    user = getattr(event, "user", None)
    candidates = [
        getattr(user, "nickname", None) if user else None,
        getattr(user, "uniqueId", None) if user else None,
        getattr(user, "unique_id", None) if user else None,
        getattr(user, "username", None) if user else None,
    ]
    for name in candidates:
        if name:
            return str(name)
    return "Unknown"


def _author_id(event: object) -> str:
    user = getattr(event, "user", None)
    candidates = [
        getattr(user, "userId", None) if user else None,
        getattr(user, "user_id", None) if user else None,
        getattr(user, "id", None) if user else None,
        getattr(user, "uid", None) if user else None,
        getattr(user, "uniqueId", None) if user else None,
        getattr(user, "unique_id", None) if user else None,
    ]
    for value in candidates:
        if value:
            return str(value)
    return _display_name(event)


def _load_tiktoklive() -> Tuple[object, object, object, object, Optional[object], Optional[object], Optional[object], object]:
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
        LikeEvent = getattr(events_module, "LikeEvent", None)
        LogLevel = getattr(logger_module, "LogLevel")
        return (
            TikTokLiveClient,
            CommentEvent,
            ConnectEvent,
            GiftEvent,
            LikeEvent,
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
    *,
    auto_reconnect: bool = False,
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
            auto_reconnect=auto_reconnect,
        )
        bridge.start(loop)
        return bridge
    except RuntimeError as exc:
        logger.error(str(exc))
        return None

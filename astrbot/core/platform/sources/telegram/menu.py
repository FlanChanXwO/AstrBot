import inspect
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from astrbot.core.message.message_event_result import MessageChain

from .components import (
    TELEGRAM_CALLBACK_DATA_MAX_BYTES,
    SupportsTelegramButton,
    TelegramForceReply,
    TelegramInlineButton,
    TelegramInlineKeyboard,
    TelegramText,
)

TELEGRAM_MENU_CALLBACK_PREFIX = "tgm"

TelegramMenuState = dict[str, Any]
TelegramMenuRender = Callable[["TelegramMenuContext"], Any]
TelegramMenuInputParser = Callable[[str, "TelegramMenuContext"], Any]
TelegramMenuInputSuccessHandler = Callable[[Any, "TelegramMenuContext"], Any]
TelegramMenuInputErrorText = str | Callable[[Exception], str]


@runtime_checkable
class TelegramMenuStateStore(Protocol):
    """Storage backend for Telegram menu state."""

    async def save(
        self,
        token: str,
        snapshot: "TelegramMenuSnapshot",
        *,
        expires_at: float | None = None,
    ) -> None: ...

    async def load(self, token: str) -> "TelegramMenuSnapshot | None": ...

    async def delete(self, token: str) -> None: ...

    async def cleanup(self) -> None: ...

    async def save_pending_input(
        self,
        key: str,
        pending_input: "TelegramMenuPendingInput",
        *,
        expires_at: float | None = None,
    ) -> None: ...

    async def load_pending_input(
        self,
        key: str,
    ) -> "TelegramMenuPendingInput | None": ...

    async def delete_pending_input(self, key: str) -> None: ...


@dataclass
class TelegramMenuSnapshot:
    """Stored navigation state for one Telegram menu message."""

    state: TelegramMenuState
    stack: list[TelegramMenuState] = field(default_factory=list)


@dataclass
class TelegramMenuPendingInput:
    """Stored input state for one user waiting to submit one field."""

    token: str
    field: str
    prompt: str
    placeholder: str | None = None
    action: str = ""
    cancel_action: str = "cancel_input"


@dataclass
class _StoredTelegramMenuSnapshot:
    snapshot: TelegramMenuSnapshot
    expires_at: float | None = None


@dataclass
class _StoredTelegramMenuPendingInput:
    pending_input: TelegramMenuPendingInput
    expires_at: float | None = None


class InMemoryTelegramMenuStore:
    """In-memory menu state store for simple plugin menus."""

    def __init__(self) -> None:
        self._snapshots: dict[str, _StoredTelegramMenuSnapshot] = {}
        self._pending_inputs: dict[str, _StoredTelegramMenuPendingInput] = {}

    async def save(
        self,
        token: str,
        snapshot: TelegramMenuSnapshot,
        *,
        expires_at: float | None = None,
    ) -> None:
        self._snapshots[token] = _StoredTelegramMenuSnapshot(
            snapshot=_copy_snapshot(snapshot),
            expires_at=expires_at,
        )

    async def load(self, token: str) -> TelegramMenuSnapshot | None:
        stored = self._snapshots.get(token)
        if stored is None:
            return None
        if _is_expired(stored.expires_at):
            await self.delete(token)
            return None
        return _copy_snapshot(stored.snapshot)

    async def delete(self, token: str) -> None:
        self._snapshots.pop(token, None)

    async def cleanup(self) -> None:
        expired_tokens = [
            token
            for token, stored in self._snapshots.items()
            if _is_expired(stored.expires_at)
        ]
        for token in expired_tokens:
            await self.delete(token)

        expired_pending_keys = [
            key
            for key, stored in self._pending_inputs.items()
            if _is_expired(stored.expires_at)
        ]
        for key in expired_pending_keys:
            await self.delete_pending_input(key)

    async def save_pending_input(
        self,
        key: str,
        pending_input: TelegramMenuPendingInput,
        *,
        expires_at: float | None = None,
    ) -> None:
        self._pending_inputs[key] = _StoredTelegramMenuPendingInput(
            pending_input=_copy_pending_input(pending_input),
            expires_at=expires_at,
        )

    async def load_pending_input(
        self,
        key: str,
    ) -> TelegramMenuPendingInput | None:
        stored = self._pending_inputs.get(key)
        if stored is None:
            return None
        if _is_expired(stored.expires_at):
            await self.delete_pending_input(key)
            return None
        return _copy_pending_input(stored.pending_input)

    async def delete_pending_input(self, key: str) -> None:
        self._pending_inputs.pop(key, None)


class PluginKVTelegramMenuStore:
    """Menu state store backed by a plugin's KV storage methods."""

    def __init__(self, plugin: Any, *, key_prefix: str = "telegram_menu") -> None:
        self.plugin = plugin
        self.key_prefix = key_prefix

    async def save(
        self,
        token: str,
        snapshot: TelegramMenuSnapshot,
        *,
        expires_at: float | None = None,
    ) -> None:
        await self.plugin.put_kv_data(
            self._key(token),
            {
                "state": snapshot.state,
                "stack": snapshot.stack,
                "expires_at": expires_at,
            },
        )

    async def load(self, token: str) -> TelegramMenuSnapshot | None:
        payload = await self.plugin.get_kv_data(self._key(token), None)
        if not isinstance(payload, dict):
            return None
        expires_at = payload.get("expires_at")
        if _is_expired(expires_at if isinstance(expires_at, int | float) else None):
            await self.delete(token)
            return None
        state = payload.get("state")
        stack = payload.get("stack")
        if not isinstance(state, dict):
            return None
        return TelegramMenuSnapshot(
            state=dict(state),
            stack=[dict(item) for item in stack if isinstance(item, dict)]
            if isinstance(stack, list)
            else [],
        )

    async def delete(self, token: str) -> None:
        await self.plugin.delete_kv_data(self._key(token))

    async def cleanup(self) -> None:
        # Plugin KV storage does not expose key scanning, so cleanup happens on load.
        return None

    def _key(self, token: str) -> str:
        return f"{self.key_prefix}:{token}"

    async def save_pending_input(
        self,
        key: str,
        pending_input: TelegramMenuPendingInput,
        *,
        expires_at: float | None = None,
    ) -> None:
        await self.plugin.put_kv_data(
            self._pending_key(key),
            {
                "token": pending_input.token,
                "field": pending_input.field,
                "prompt": pending_input.prompt,
                "placeholder": pending_input.placeholder,
                "action": pending_input.action,
                "cancel_action": pending_input.cancel_action,
                "expires_at": expires_at,
            },
        )

    async def load_pending_input(
        self,
        key: str,
    ) -> TelegramMenuPendingInput | None:
        payload = await self.plugin.get_kv_data(self._pending_key(key), None)
        if not isinstance(payload, dict):
            return None
        expires_at = payload.get("expires_at")
        if _is_expired(expires_at if isinstance(expires_at, int | float) else None):
            await self.delete_pending_input(key)
            return None

        token = payload.get("token")
        field = payload.get("field")
        prompt = payload.get("prompt")
        if not isinstance(token, str) or not isinstance(field, str):
            return None
        if not isinstance(prompt, str):
            return None
        placeholder = payload.get("placeholder")
        action = payload.get("action")
        cancel_action = payload.get("cancel_action")
        return TelegramMenuPendingInput(
            token=token,
            field=field,
            prompt=prompt,
            placeholder=placeholder if isinstance(placeholder, str) else None,
            action=action if isinstance(action, str) else "",
            cancel_action=cancel_action
            if isinstance(cancel_action, str)
            else "cancel_input",
        )

    async def delete_pending_input(self, key: str) -> None:
        await self.plugin.delete_kv_data(self._pending_key(key))

    def _pending_key(self, key: str) -> str:
        return f"{self.key_prefix}:pending:{key}"


@dataclass
class TelegramMenuInput:
    """Single-field text input prompt used by TelegramMenu."""

    field: str
    prompt: str
    placeholder: str | None = None
    action: str | None = None
    cancel_action: str = "cancel_input"
    parse: TelegramMenuInputParser | None = None
    on_success: TelegramMenuInputSuccessHandler | None = None
    error_text: TelegramMenuInputErrorText = "输入无效，请重新输入。"


@dataclass
class TelegramMenuButton:
    """Button whose callback action is encoded by TelegramMenu."""

    text: str
    action: str


@dataclass
class TelegramMenuView:
    """Rendered Telegram menu page."""

    text: str
    rows: Sequence[Sequence[TelegramMenuButton | SupportsTelegramButton]] = field(
        default_factory=list,
    )
    parse_mode: str | None = None
    link_preview_options: Any = None


class TelegramMenuContext:
    """Runtime context passed to a Telegram menu render function."""

    def __init__(
        self,
        *,
        event: Any | None,
        action: str,
        state: TelegramMenuState,
        stack: list[TelegramMenuState],
        menu: "TelegramMenu | None" = None,
        token: str | None = None,
    ) -> None:
        self.event = event
        self.action = action
        self.state = state
        self.stack = stack
        self._menu = menu
        self._token = token
        self._input_prompt_chain: MessageChain | None = None
        self._pending_input: TelegramMenuPendingInput | None = None

    def goto(self, state: TelegramMenuState) -> None:
        """Push the current state and navigate to a new menu state."""
        self.stack.append(dict(self.state))
        self.state = dict(state)

    def replace(self, state: TelegramMenuState) -> None:
        """Replace the current menu state without changing the back stack."""
        self.state = dict(state)

    def back(self) -> bool:
        """Navigate back to the previous state when available."""
        if not self.stack:
            return False
        self.state = self.stack.pop()
        return True

    def prompt_input(self, menu_input: TelegramMenuInput) -> MessageChain:
        """Record a pending text input and return the ForceReply prompt."""
        if self._menu is None or self._token is None or self.event is None:
            raise RuntimeError(
                "Telegram menu input prompts require an active Telegram event.",
            )
        if not menu_input.field:
            raise ValueError("Telegram menu input field must not be empty.")

        self._menu._register_input(menu_input)
        pending_input = TelegramMenuPendingInput(
            token=self._token,
            field=menu_input.field,
            prompt=menu_input.prompt,
            placeholder=menu_input.placeholder,
            action=menu_input.action or "",
            cancel_action=menu_input.cancel_action,
        )
        chain = _build_input_prompt_chain(pending_input)
        self._pending_input = pending_input
        self._input_prompt_chain = chain
        return chain


class TelegramMenuPaginator:
    """Helper for rendering paginated menu item buttons."""

    def __init__(
        self,
        items: Sequence[Any],
        *,
        page: int = 0,
        page_size: int = 8,
    ) -> None:
        if page_size < 1:
            raise ValueError("Telegram menu page_size must be at least 1.")
        self.items = list(items)
        self.page_size = page_size
        self.page = max(0, min(page, self.page_count - 1))

    @property
    def page_count(self) -> int:
        return max(1, (len(self.items) + self.page_size - 1) // self.page_size)

    @property
    def page_items(self) -> list[Any]:
        start = self.page * self.page_size
        return self.items[start : start + self.page_size]

    def item_rows(
        self,
        *,
        text: Callable[[Any], str] | None = None,
        action: Callable[[Any], str],
    ) -> list[list[TelegramMenuButton]]:
        rows: list[list[TelegramMenuButton]] = []
        for item in self.page_items:
            label = text(item) if text is not None else str(item)
            rows.append([TelegramMenuButton(label, action(item))])
        return rows

    def navigation_row(
        self,
        *,
        previous_text: str = "<",
        next_text: str = ">",
        indicator: bool = True,
        action_prefix: str = "page",
    ) -> list[TelegramMenuButton]:
        row: list[TelegramMenuButton] = []
        if self.page > 0:
            row.append(
                TelegramMenuButton(
                    previous_text,
                    f"{action_prefix}:{self.page - 1}",
                ),
            )
        if indicator:
            row.append(
                TelegramMenuButton(
                    f"{self.page + 1} / {self.page_count}",
                    f"{action_prefix}:{self.page}",
                ),
            )
        if self.page < self.page_count - 1:
            row.append(
                TelegramMenuButton(
                    next_text,
                    f"{action_prefix}:{self.page + 1}",
                ),
            )
        return row


class TelegramMenu:
    """Semi-automatic Telegram inline menu controller."""

    def __init__(
        self,
        namespace: str,
        render: TelegramMenuRender,
        *,
        store: TelegramMenuStateStore | None = None,
        invalid_text: str = "菜单已失效，请重新打开。",
        expires_in: float | None = None,
    ) -> None:
        _validate_callback_part(namespace, "namespace")
        self.namespace = namespace
        self.render = render
        self.store = store or InMemoryTelegramMenuStore()
        self.invalid_text = invalid_text
        self.expires_in = expires_in
        self._inputs: dict[tuple[str, str], TelegramMenuInput] = {}

    @property
    def callback_data_prefix(self) -> str:
        return f"{TELEGRAM_MENU_CALLBACK_PREFIX}:{self.namespace}:"

    async def open(
        self, initial_state: TelegramMenuState | None = None
    ) -> MessageChain:
        token = self._new_token()
        snapshot = TelegramMenuSnapshot(state=dict(initial_state or {}))
        context = TelegramMenuContext(
            event=None,
            action="",
            state=snapshot.state,
            stack=snapshot.stack,
            menu=self,
            token=token,
        )
        view = await self._render(context)
        await self.store.save(
            token,
            TelegramMenuSnapshot(state=context.state, stack=context.stack),
            expires_at=self._expires_at(),
        )
        return self._build_message_chain(token, view)

    async def handle_event(self, event: Any) -> bool:
        callback_data = str(event.get_interaction_data() or "")
        parsed = self._parse_callback_data(callback_data)
        if parsed is None:
            return False
        token, action = parsed

        await event.ack_interaction()
        snapshot = await self.store.load(token)
        if snapshot is None:
            await event.edit_text(self.invalid_text, reply_markup=None)
            return True

        context = TelegramMenuContext(
            event=event,
            action=action,
            state=snapshot.state,
            stack=snapshot.stack,
            menu=self,
            token=token,
        )
        await self._delete_pending_input_for_cancel_action(event, token, action)
        view = await self._render(context)
        await self._save_context_pending_input(context)
        await self.store.save(
            token,
            TelegramMenuSnapshot(state=context.state, stack=context.stack),
            expires_at=self._expires_at(),
        )
        await event.edit_text(
            view.text,
            reply_markup=self._build_markup(token, view),
            parse_mode=view.parse_mode,
            link_preview_options=view.link_preview_options,
        )
        if context._input_prompt_chain is not None:
            await _send_chain(event, context._input_prompt_chain)
        return True

    async def handle_input_event(self, event: Any) -> bool:
        """Handle the next ordinary Telegram text message for a pending input."""
        if not _is_telegram_text_input_event(event):
            return False

        pending_key = _pending_input_key(event)
        pending_input = await _load_store_pending_input(self.store, pending_key)
        if pending_input is None:
            return False

        if _is_cancel_text(getattr(event, "message_str", "")):
            await self._finish_cancelled_input(event, pending_key, pending_input)
            return True

        snapshot = await self.store.load(pending_input.token)
        if snapshot is None:
            await _delete_store_pending_input(self.store, pending_key)
            await _send_chain(event, _build_text_chain(self.invalid_text))
            _stop_event(event)
            return True

        menu_input = self._find_input(pending_input)
        context = TelegramMenuContext(
            event=event,
            action=pending_input.action or f"input:{pending_input.field}",
            state=snapshot.state,
            stack=snapshot.stack,
            menu=self,
            token=pending_input.token,
        )
        raw_value = str(getattr(event, "message_str", "") or "").strip()
        try:
            parsed_value = await _parse_input_value(menu_input, raw_value, context)
        except Exception as exc:
            await _send_chain(
                event,
                _build_input_error_chain(pending_input, menu_input, exc),
            )
            _stop_event(event)
            return True

        context.state[pending_input.field] = parsed_value
        await _run_input_success_handler(menu_input, parsed_value, context)
        await _delete_store_pending_input(self.store, pending_key)
        view = await self._render(context)
        await self._save_context_pending_input(context)
        await self.store.save(
            pending_input.token,
            TelegramMenuSnapshot(state=context.state, stack=context.stack),
            expires_at=self._expires_at(),
        )
        await _send_chain(event, self._build_message_chain(pending_input.token, view))
        _stop_event(event)
        return True

    async def delete(self, token: str) -> None:
        await self.store.delete(token)

    async def cleanup(self) -> None:
        await self.store.cleanup()

    def _register_input(self, menu_input: TelegramMenuInput) -> None:
        key = (menu_input.field, menu_input.action or "")
        self._inputs[key] = menu_input

    def _find_input(
        self,
        pending_input: TelegramMenuPendingInput,
    ) -> TelegramMenuInput:
        key = (pending_input.field, pending_input.action)
        fallback_key = (pending_input.field, "")
        menu_input = self._inputs.get(key) or self._inputs.get(fallback_key)
        if menu_input is not None:
            return menu_input
        return TelegramMenuInput(
            field=pending_input.field,
            prompt=pending_input.prompt,
            placeholder=pending_input.placeholder,
            action=pending_input.action or None,
            cancel_action=pending_input.cancel_action,
        )

    async def _save_context_pending_input(
        self,
        context: TelegramMenuContext,
    ) -> None:
        if context._pending_input is None or context.event is None:
            return
        await _save_store_pending_input(
            self.store,
            _pending_input_key(context.event),
            context._pending_input,
            expires_at=self._expires_at(),
        )

    async def _delete_pending_input_for_cancel_action(
        self,
        event: Any,
        token: str,
        action: str,
    ) -> None:
        pending_key = _pending_input_key(event)
        pending_input = await _load_store_pending_input(self.store, pending_key)
        if (
            pending_input is not None
            and pending_input.token == token
            and action == pending_input.cancel_action
        ):
            await _delete_store_pending_input(self.store, pending_key)

    async def _finish_cancelled_input(
        self,
        event: Any,
        pending_key: str,
        pending_input: TelegramMenuPendingInput,
    ) -> None:
        await _delete_store_pending_input(self.store, pending_key)
        snapshot = await self.store.load(pending_input.token)
        if snapshot is None:
            await _send_chain(event, _build_text_chain(self.invalid_text))
            _stop_event(event)
            return

        context = TelegramMenuContext(
            event=event,
            action=pending_input.cancel_action,
            state=snapshot.state,
            stack=snapshot.stack,
            menu=self,
            token=pending_input.token,
        )
        view = await self._render(context)
        await self._save_context_pending_input(context)
        await self.store.save(
            pending_input.token,
            TelegramMenuSnapshot(state=context.state, stack=context.stack),
            expires_at=self._expires_at(),
        )
        await _send_chain(event, self._build_message_chain(pending_input.token, view))
        _stop_event(event)

    def _new_token(self) -> str:
        return uuid4().hex[:12]

    def _expires_at(self) -> float | None:
        if self.expires_in is None:
            return None
        return time.time() + self.expires_in

    async def _render(self, context: TelegramMenuContext) -> TelegramMenuView:
        view = self.render(context)
        if inspect.isawaitable(view):
            view = await view
        if not isinstance(view, TelegramMenuView):
            raise TypeError("Telegram menu render must return TelegramMenuView.")
        return view

    def _build_message_chain(self, token: str, view: TelegramMenuView) -> MessageChain:
        chain = MessageChain()
        chain.chain.append(
            TelegramText(
                view.text,
                parse_mode=view.parse_mode,
                link_preview_options=view.link_preview_options,
            ),
        )
        chain.chain.append(self._build_markup(token, view))
        return chain

    def _build_markup(
        self, token: str, view: TelegramMenuView
    ) -> TelegramInlineKeyboard:
        rows: list[list[SupportsTelegramButton]] = []
        for row in view.rows:
            rows.append(
                [
                    self._build_button(token, button)
                    if isinstance(button, TelegramMenuButton)
                    else button
                    for button in row
                ],
            )
        return TelegramInlineKeyboard(rows)

    def _build_button(
        self,
        token: str,
        button: TelegramMenuButton,
    ) -> TelegramInlineButton:
        callback_data = self._build_callback_data(token, button.action)
        return TelegramInlineButton(button.text, callback_data=callback_data)

    def _build_callback_data(self, token: str, action: str) -> str:
        _validate_callback_part(token, "token")
        if not action:
            raise ValueError("Telegram menu action must not be empty.")
        callback_data = (
            f"{TELEGRAM_MENU_CALLBACK_PREFIX}:{self.namespace}:{token}:{action}"
        )
        callback_data_length = len(callback_data.encode("utf-8"))
        if callback_data_length > TELEGRAM_CALLBACK_DATA_MAX_BYTES:
            raise ValueError(
                "Telegram menu callback_data must be 64 UTF-8 bytes or fewer.",
            )
        return callback_data

    def _parse_callback_data(self, callback_data: str) -> tuple[str, str] | None:
        prefix = self.callback_data_prefix
        if not callback_data.startswith(prefix):
            return None
        remainder = callback_data[len(prefix) :]
        token, separator, action = remainder.partition(":")
        if not separator or not token or not action:
            return None
        return token, action


def _copy_snapshot(snapshot: TelegramMenuSnapshot) -> TelegramMenuSnapshot:
    return TelegramMenuSnapshot(
        state=dict(snapshot.state),
        stack=[dict(item) for item in snapshot.stack],
    )


def _copy_pending_input(
    pending_input: TelegramMenuPendingInput,
) -> TelegramMenuPendingInput:
    return TelegramMenuPendingInput(
        token=pending_input.token,
        field=pending_input.field,
        prompt=pending_input.prompt,
        placeholder=pending_input.placeholder,
        action=pending_input.action,
        cancel_action=pending_input.cancel_action,
    )


def _is_expired(expires_at: float | None) -> bool:
    return expires_at is not None and expires_at <= time.time()


def _is_telegram_text_input_event(event: Any) -> bool:
    getter = getattr(event, "get_platform_name", None)
    if not callable(getter) or getter() != "telegram":
        return False
    interaction_checker = getattr(event, "is_button_interaction", None)
    if callable(interaction_checker) and interaction_checker():
        return False
    message_text = str(getattr(event, "message_str", "") or "").strip()
    return bool(message_text)


def _pending_input_key(event: Any) -> str:
    platform_id = _event_value(event, "get_platform_id", "telegram")
    session_id = _event_value(event, "get_session_id", "")
    if not session_id:
        session_id = str(getattr(event, "session_id", "") or "")
    sender_id = _event_value(event, "get_sender_id", "")
    return f"{platform_id}:{session_id}:{sender_id}"


def _event_value(event: Any, method_name: str, default: str) -> str:
    getter = getattr(event, method_name, None)
    if not callable(getter):
        return default
    value = getter()
    if value is None:
        return default
    return str(value)


def _is_cancel_text(text: str) -> bool:
    return text.strip().lower() in {"取消", "cancel"}


async def _save_store_pending_input(
    store: Any,
    key: str,
    pending_input: TelegramMenuPendingInput,
    *,
    expires_at: float | None = None,
) -> None:
    saver = getattr(store, "save_pending_input", None)
    if not callable(saver):
        raise RuntimeError(
            "Telegram menu input requires a state store with save_pending_input().",
        )
    await saver(key, pending_input, expires_at=expires_at)


async def _load_store_pending_input(
    store: Any,
    key: str,
) -> TelegramMenuPendingInput | None:
    loader = getattr(store, "load_pending_input", None)
    if not callable(loader):
        return None
    return await loader(key)


async def _delete_store_pending_input(store: Any, key: str) -> None:
    deleter = getattr(store, "delete_pending_input", None)
    if callable(deleter):
        await deleter(key)


def _build_input_prompt_chain(
    pending_input: TelegramMenuPendingInput,
) -> MessageChain:
    chain = MessageChain()
    chain.message(pending_input.prompt)
    chain.chain.append(
        TelegramForceReply(input_field_placeholder=pending_input.placeholder),
    )
    return chain


def _build_text_chain(text: str) -> MessageChain:
    chain = MessageChain()
    chain.message(text)
    return chain


def _build_input_error_chain(
    pending_input: TelegramMenuPendingInput,
    menu_input: TelegramMenuInput,
    error: Exception,
) -> MessageChain:
    error_text = (
        menu_input.error_text(error)
        if callable(menu_input.error_text)
        else menu_input.error_text
    )
    chain = MessageChain()
    chain.message(f"{error_text}\n\n{pending_input.prompt}")
    chain.chain.append(
        TelegramForceReply(input_field_placeholder=pending_input.placeholder),
    )
    return chain


async def _parse_input_value(
    menu_input: TelegramMenuInput,
    value: str,
    context: TelegramMenuContext,
) -> Any:
    if menu_input.parse is None:
        return value
    parsed = menu_input.parse(value, context)
    if inspect.isawaitable(parsed):
        return await parsed
    return parsed


async def _run_input_success_handler(
    menu_input: TelegramMenuInput,
    value: Any,
    context: TelegramMenuContext,
) -> None:
    if menu_input.on_success is None:
        return
    result = menu_input.on_success(value, context)
    if inspect.isawaitable(result):
        await result


async def _send_chain(event: Any, chain: MessageChain) -> None:
    sender = getattr(event, "send", None)
    if not callable(sender):
        raise RuntimeError("Telegram menu input event cannot send messages.")
    await sender(chain)


def _stop_event(event: Any) -> None:
    stopper = getattr(event, "stop_event", None)
    if callable(stopper):
        stopper()


def _validate_callback_part(value: str, name: str) -> None:
    if not value:
        raise ValueError(f"Telegram menu {name} must not be empty.")
    if ":" in value:
        raise ValueError(f"Telegram menu {name} must not contain ':'.")

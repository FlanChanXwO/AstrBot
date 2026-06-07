import importlib
import sys
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from tests.fixtures.mocks.telegram import create_mock_telegram_modules

_TELEGRAM_MODULES: dict[str, object] = {}


def _load_telegram_menu():
    module_name = "astrbot.core.platform.sources.telegram.menu"
    module = _TELEGRAM_MODULES.get(module_name)
    if module is not None:
        return module

    modules = create_mock_telegram_modules()
    components_module_name = "astrbot.core.platform.sources.telegram.components"
    with patch.dict(
        sys.modules,
        {
            "telegram": modules["telegram"],
            "telegram.constants": modules["telegram"].constants,
            "telegram.error": modules["telegram"].error,
            "telegram.ext": modules["telegram.ext"],
        },
    ):
        components = importlib.import_module(
            components_module_name,
        )
        module = importlib.import_module(module_name)
    sys.modules[components_module_name] = components
    sys.modules[module_name] = module
    _TELEGRAM_MODULES[components_module_name] = components
    _TELEGRAM_MODULES[module_name] = module
    return module


class FakeTelegramMenuEvent:
    def __init__(
        self,
        callback_data: str,
        *,
        session_id: str = "chat-1",
        sender_id: str = "user-1",
        platform_id: str = "telegram",
    ) -> None:
        self.callback_data = callback_data
        self.session_id = session_id
        self.sender_id = sender_id
        self.platform_id = platform_id
        self.ack_interaction = AsyncMock()
        self.edit_text = AsyncMock()
        self.send = AsyncMock()

    def get_interaction_data(self) -> str:
        return self.callback_data

    def get_platform_name(self) -> str:
        return "telegram"

    def get_platform_id(self) -> str:
        return self.platform_id

    def get_session_id(self) -> str:
        return self.session_id

    def get_sender_id(self) -> str:
        return self.sender_id

    def is_button_interaction(self) -> bool:
        return True


class FakeTelegramInputEvent:
    def __init__(
        self,
        message_str: str,
        *,
        session_id: str = "chat-1",
        sender_id: str = "user-1",
        platform_name: str = "telegram",
        platform_id: str = "telegram",
    ) -> None:
        self.message_str = message_str
        self.session_id = session_id
        self.sender_id = sender_id
        self.platform_name = platform_name
        self.platform_id = platform_id
        self.send = AsyncMock()
        self.stopped = False

    def get_platform_name(self) -> str:
        return self.platform_name

    def get_platform_id(self) -> str:
        return self.platform_id

    def get_session_id(self) -> str:
        return self.session_id

    def get_sender_id(self) -> str:
        return self.sender_id

    def is_button_interaction(self) -> bool:
        return False

    def stop_event(self) -> None:
        self.stopped = True


class FakePlugin:
    def __init__(self) -> None:
        self.data: dict[str, Any] = {}

    async def put_kv_data(self, key: str, value: Any) -> None:
        self.data[key] = value

    async def get_kv_data(self, key: str, default: Any) -> Any:
        return self.data.get(key, default)

    async def delete_kv_data(self, key: str) -> None:
        self.data.pop(key, None)


class CustomStore:
    def __init__(self) -> None:
        self.saved = {}
        self.deleted: list[str] = []
        self.pending_inputs = {}
        self.deleted_pending: list[str] = []

    async def save(self, token, snapshot, *, expires_at=None):
        self.saved[token] = (snapshot, expires_at)

    async def load(self, token):
        saved = self.saved.get(token)
        if saved is None:
            return None
        return saved[0]

    async def delete(self, token):
        self.deleted.append(token)
        self.saved.pop(token, None)

    async def cleanup(self):
        self.saved.clear()

    async def save_pending_input(self, key, pending_input, *, expires_at=None):
        self.pending_inputs[key] = (pending_input, expires_at)

    async def load_pending_input(self, key):
        saved = self.pending_inputs.get(key)
        if saved is None:
            return None
        return saved[0]

    async def delete_pending_input(self, key):
        self.deleted_pending.append(key)
        self.pending_inputs.pop(key, None)


def _first_callback_data(chain) -> str:
    keyboard = chain.chain[1].to_telegram_markup()
    return keyboard.inline_keyboard[0][0].callback_data


def _sent_text(event) -> str:
    return event.send.await_args.args[0].chain[0].text


@pytest.mark.asyncio
async def test_telegram_menu_open_generates_text_and_keyboard():
    menu_module = _load_telegram_menu()

    def render(ctx):
        return menu_module.TelegramMenuView(
            text=f"Page {ctx.state['page']}",
            rows=[[menu_module.TelegramMenuButton("Next", "page:1")]],
            parse_mode="HTML",
        )

    menu = menu_module.TelegramMenu("settings", render)

    chain = await menu.open({"page": 0})

    assert chain.chain[0].text == "Page 0"
    assert chain.chain[0].parse_mode == "HTML"
    callback_data = _first_callback_data(chain)
    assert callback_data.startswith("tgm:settings:")
    assert callback_data.endswith(":page:1")


@pytest.mark.asyncio
async def test_telegram_menu_handle_event_updates_state_and_edits_message():
    menu_module = _load_telegram_menu()

    def render(ctx):
        if ctx.action.startswith("page:"):
            ctx.replace({"page": int(ctx.action.split(":", 1)[1])})
        page = ctx.state["page"]
        paginator = menu_module.TelegramMenuPaginator(
            ["A", "B", "C", "D"],
            page=page,
            page_size=2,
        )
        rows = paginator.item_rows(action=lambda item: f"select:{item}")
        rows.append(paginator.navigation_row(previous_text="<", next_text=">"))
        return menu_module.TelegramMenuView(text=f"Page {page + 1}", rows=rows)

    menu = menu_module.TelegramMenu("settings", render)
    chain = await menu.open({"page": 0})
    keyboard = chain.chain[1].to_telegram_markup()
    next_callback = keyboard.inline_keyboard[-1][-1].callback_data
    event = FakeTelegramMenuEvent(next_callback)

    handled = await menu.handle_event(event)

    assert handled is True
    event.ack_interaction.assert_awaited_once()
    event.edit_text.assert_awaited_once()
    edit_kwargs = event.edit_text.await_args.kwargs
    assert event.edit_text.await_args.args == ("Page 2",)
    assert (
        edit_kwargs["reply_markup"].to_telegram_markup().inline_keyboard[0][0].text
        == "C"
    )


@pytest.mark.asyncio
async def test_telegram_menu_goto_and_back_persist_navigation_stack():
    menu_module = _load_telegram_menu()

    def render(ctx):
        if ctx.action == "detail":
            ctx.goto({"page": "detail"})
        elif ctx.action == "back":
            ctx.back()
        if ctx.state["page"] == "detail":
            return menu_module.TelegramMenuView(
                "Detail",
                rows=[[menu_module.TelegramMenuButton("< Back", "back")]],
            )
        return menu_module.TelegramMenuView(
            "List",
            rows=[[menu_module.TelegramMenuButton("Open", "detail")]],
        )

    menu = menu_module.TelegramMenu("settings", render)
    chain = await menu.open({"page": "list"})
    detail_callback = _first_callback_data(chain)
    detail_event = FakeTelegramMenuEvent(detail_callback)

    await menu.handle_event(detail_event)
    back_callback = (
        detail_event.edit_text.await_args.kwargs["reply_markup"]
        .to_telegram_markup()
        .inline_keyboard[0][0]
        .callback_data
    )
    back_event = FakeTelegramMenuEvent(back_callback)
    await menu.handle_event(back_event)

    assert detail_event.edit_text.await_args.args == ("Detail",)
    assert back_event.edit_text.await_args.args == ("List",)


@pytest.mark.asyncio
async def test_telegram_menu_rejects_callback_data_over_telegram_limit():
    menu_module = _load_telegram_menu()

    def render(ctx):
        return menu_module.TelegramMenuView(
            "Too long",
            rows=[[menu_module.TelegramMenuButton("Bad", "x" * 65)]],
        )

    menu = menu_module.TelegramMenu("settings", render)

    with pytest.raises(ValueError, match="64 UTF-8 bytes"):
        await menu.open({})


@pytest.mark.asyncio
async def test_telegram_menu_edits_invalid_text_when_token_missing():
    menu_module = _load_telegram_menu()

    def render(ctx):
        return menu_module.TelegramMenuView(
            "List",
            rows=[[menu_module.TelegramMenuButton("Open", "detail")]],
        )

    menu = menu_module.TelegramMenu("settings", render, invalid_text="Expired")
    event = FakeTelegramMenuEvent("tgm:settings:missing:detail")

    handled = await menu.handle_event(event)

    assert handled is True
    event.ack_interaction.assert_awaited_once()
    event.edit_text.assert_awaited_once_with("Expired", reply_markup=None)


@pytest.mark.asyncio
async def test_telegram_menu_returns_false_for_other_callback_prefix():
    menu_module = _load_telegram_menu()

    menu = menu_module.TelegramMenu(
        "settings",
        lambda ctx: menu_module.TelegramMenuView("List"),
    )
    event = FakeTelegramMenuEvent("other:settings:token:open")

    handled = await menu.handle_event(event)

    assert handled is False
    event.ack_interaction.assert_not_awaited()
    event.edit_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_plugin_kv_telegram_menu_store_persists_snapshot():
    menu_module = _load_telegram_menu()
    plugin = FakePlugin()
    store = menu_module.PluginKVTelegramMenuStore(plugin)
    snapshot = menu_module.TelegramMenuSnapshot(
        state={"page": "detail"},
        stack=[{"page": "list"}],
    )

    await store.save("token", snapshot)
    loaded = await store.load("token")

    assert loaded.state == {"page": "detail"}
    assert loaded.stack == [{"page": "list"}]
    await store.delete("token")
    assert await store.load("token") is None


@pytest.mark.asyncio
async def test_custom_telegram_menu_store_is_supported():
    menu_module = _load_telegram_menu()
    store = CustomStore()

    def render(ctx):
        return menu_module.TelegramMenuView(
            "List",
            rows=[[menu_module.TelegramMenuButton("Open", "detail")]],
        )

    menu = menu_module.TelegramMenu("settings", render, store=store)
    chain = await menu.open({})
    token = _first_callback_data(chain).split(":")[2]

    assert token in store.saved
    await menu.delete(token)
    assert store.deleted == [token]
    assert token not in store.saved


@pytest.mark.asyncio
async def test_telegram_menu_prompt_input_sends_force_reply_and_persists_pending():
    menu_module = _load_telegram_menu()

    def render(ctx):
        if ctx.action == "edit_url":
            ctx.prompt_input(
                menu_module.TelegramMenuInput(
                    "url",
                    "请输入 RSS URL",
                    placeholder="https://example.com/feed.xml",
                    action="save_url",
                ),
            )
        return menu_module.TelegramMenuView(
            "Detail",
            rows=[[menu_module.TelegramMenuButton("Edit URL", "edit_url")]],
        )

    menu = menu_module.TelegramMenu("settings", render)
    chain = await menu.open({"page": "detail"})
    event = FakeTelegramMenuEvent(_first_callback_data(chain))

    handled = await menu.handle_event(event)

    assert handled is True
    event.send.assert_awaited_once()
    prompt_chain = event.send.await_args.args[0]
    assert prompt_chain.chain[0].text == "请输入 RSS URL"
    assert prompt_chain.chain[1].input_field_placeholder == (
        "https://example.com/feed.xml"
    )
    pending = await menu.store.load_pending_input("telegram:chat-1:user-1")
    assert pending.field == "url"
    assert pending.action == "save_url"


@pytest.mark.asyncio
async def test_telegram_menu_handle_input_event_updates_state_and_stops_event():
    menu_module = _load_telegram_menu()

    async def parse_url(value, ctx):
        if not value.startswith("https://"):
            raise ValueError("URL must use HTTPS.")
        return value.rstrip("/")

    async def on_success(value, ctx):
        ctx.state["saved"] = True
        ctx.state["last_action"] = ctx.action

    def render(ctx):
        if ctx.action == "edit_url":
            ctx.prompt_input(
                menu_module.TelegramMenuInput(
                    "url",
                    "请输入 RSS URL",
                    placeholder="https://example.com/feed.xml",
                    action="save_url",
                    parse=parse_url,
                    on_success=on_success,
                ),
            )
        return menu_module.TelegramMenuView(
            f"URL: {ctx.state.get('url', '-')}",
            rows=[[menu_module.TelegramMenuButton("Edit URL", "edit_url")]],
        )

    menu = menu_module.TelegramMenu("settings", render)
    chain = await menu.open({"page": "detail"})
    await menu.handle_event(FakeTelegramMenuEvent(_first_callback_data(chain)))

    input_event = FakeTelegramInputEvent("https://example.com/feed/")
    handled = await menu.handle_input_event(input_event)

    assert handled is True
    assert input_event.stopped is True
    assert _sent_text(input_event) == "URL: https://example.com/feed"
    assert await menu.store.load_pending_input("telegram:chat-1:user-1") is None
    token = _first_callback_data(input_event.send.await_args.args[0]).split(":")[2]
    snapshot = await menu.store.load(token)
    assert snapshot.state["url"] == "https://example.com/feed"
    assert snapshot.state["saved"] is True
    assert snapshot.state["last_action"] == "save_url"


@pytest.mark.asyncio
async def test_telegram_menu_input_validation_error_keeps_pending_input():
    menu_module = _load_telegram_menu()

    def parse_url(value, ctx):
        if not value.startswith("https://"):
            raise ValueError("URL must use HTTPS.")
        return value

    def render(ctx):
        if ctx.action == "edit_url":
            ctx.prompt_input(
                menu_module.TelegramMenuInput(
                    "url",
                    "请输入 RSS URL",
                    placeholder="https://example.com/feed.xml",
                    parse=parse_url,
                    error_text=lambda error: f"错误：{error}",
                ),
            )
        return menu_module.TelegramMenuView(
            "Detail",
            rows=[[menu_module.TelegramMenuButton("Edit URL", "edit_url")]],
        )

    menu = menu_module.TelegramMenu("settings", render)
    chain = await menu.open({})
    await menu.handle_event(FakeTelegramMenuEvent(_first_callback_data(chain)))

    input_event = FakeTelegramInputEvent("http://example.com/feed")
    handled = await menu.handle_input_event(input_event)

    assert handled is True
    assert input_event.stopped is True
    assert _sent_text(input_event).startswith("错误：URL must use HTTPS.")
    pending = await menu.store.load_pending_input("telegram:chat-1:user-1")
    assert pending is not None
    assert pending.field == "url"


@pytest.mark.asyncio
async def test_telegram_menu_input_cancel_clears_pending_and_rerenders_menu():
    menu_module = _load_telegram_menu()

    def render(ctx):
        if ctx.action == "edit_name":
            ctx.prompt_input(
                menu_module.TelegramMenuInput("name", "请输入名称"),
            )
        if ctx.action == "cancel_input":
            ctx.state["cancelled"] = True
        return menu_module.TelegramMenuView(
            f"Cancelled: {ctx.state.get('cancelled', False)}",
            rows=[[menu_module.TelegramMenuButton("Edit", "edit_name")]],
        )

    menu = menu_module.TelegramMenu("settings", render)
    chain = await menu.open({})
    await menu.handle_event(FakeTelegramMenuEvent(_first_callback_data(chain)))

    input_event = FakeTelegramInputEvent("取消")
    handled = await menu.handle_input_event(input_event)

    assert handled is True
    assert input_event.stopped is True
    assert _sent_text(input_event) == "Cancelled: True"
    assert await menu.store.load_pending_input("telegram:chat-1:user-1") is None


@pytest.mark.asyncio
async def test_telegram_menu_pending_input_is_isolated_by_session_and_sender():
    menu_module = _load_telegram_menu()

    def render(ctx):
        if ctx.action == "edit_name":
            ctx.prompt_input(menu_module.TelegramMenuInput("name", "请输入名称"))
        return menu_module.TelegramMenuView(
            f"Name: {ctx.state.get('name', '-')}",
            rows=[[menu_module.TelegramMenuButton("Edit", "edit_name")]],
        )

    menu = menu_module.TelegramMenu("settings", render)
    chain = await menu.open({})
    await menu.handle_event(
        FakeTelegramMenuEvent(
            _first_callback_data(chain),
            session_id="group-1",
            sender_id="alice",
        ),
    )

    bob_event = FakeTelegramInputEvent(
        "Bob",
        session_id="group-1",
        sender_id="bob",
    )
    alice_event = FakeTelegramInputEvent(
        "Alice",
        session_id="group-1",
        sender_id="alice",
    )

    assert await menu.handle_input_event(bob_event) is False
    bob_event.send.assert_not_awaited()
    assert await menu.handle_input_event(alice_event) is True
    assert _sent_text(alice_event) == "Name: Alice"


@pytest.mark.asyncio
async def test_plugin_kv_telegram_menu_store_persists_pending_input():
    menu_module = _load_telegram_menu()
    plugin = FakePlugin()
    store = menu_module.PluginKVTelegramMenuStore(plugin)
    pending = menu_module.TelegramMenuPendingInput(
        token="token",
        field="url",
        prompt="请输入 URL",
        placeholder="https://example.com/feed.xml",
        action="save_url",
    )

    await store.save_pending_input("telegram:chat:user", pending)
    loaded = await store.load_pending_input("telegram:chat:user")

    assert loaded == pending
    await store.delete_pending_input("telegram:chat:user")
    assert await store.load_pending_input("telegram:chat:user") is None


@pytest.mark.asyncio
async def test_custom_telegram_menu_store_supports_pending_input_protocol():
    menu_module = _load_telegram_menu()
    store = CustomStore()
    pending = menu_module.TelegramMenuPendingInput(
        token="token",
        field="name",
        prompt="请输入名称",
    )

    await store.save_pending_input("telegram:chat:user", pending)

    assert await store.load_pending_input("telegram:chat:user") == pending
    await store.delete_pending_input("telegram:chat:user")
    assert await store.load_pending_input("telegram:chat:user") is None

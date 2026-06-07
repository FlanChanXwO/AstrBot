# Sending Messages

## Passive Messages

Passive messages refer to the bot responding to messages reactively.

```python
@filter.command("helloworld")
async def helloworld(self, event: AstrMessageEvent):
    yield event.plain_result("Hello!")
    yield event.plain_result("你好！")

    yield event.image_result("path/to/image.jpg") # Send an image
    yield event.image_result("https://example.com/image.jpg") # Send an image from URL, must start with http or https
```

## Active Messages

Active messages refer to the bot proactively pushing messages. Some platforms may not support active message sending.

For scheduled tasks or when you don't want to send messages immediately, you can use `event.unified_msg_origin` to get a string and store it, then use `self.context.send_message(unified_msg_origin, chains)` to send messages when needed.

```python
from astrbot.api.event import MessageChain

@filter.command("helloworld")
async def helloworld(self, event: AstrMessageEvent):
    umo = event.unified_msg_origin
    message_chain = MessageChain().message("Hello!").file_image("path/to/image.jpg")
    await self.context.send_message(event.unified_msg_origin, message_chain)
```

With this feature, you can store the `unified_msg_origin` and send messages when needed.

> [!TIP]
> About unified_msg_origin.
> `unified_msg_origin` is a string that records the unique ID of a session. AstrBot uses it to identify which messaging platform and which session it belongs to. This allows messages to be sent to the correct session when using `send_message`. For more about MessageChain, see the next section.

## Rich Media Messages

AstrBot supports sending rich media messages such as images, audio, videos, etc. Use `MessageChain` to construct messages.

```python
import astrbot.api.message_components as Comp

@filter.command("helloworld")
async def helloworld(self, event: AstrMessageEvent):
    chain = [
        Comp.At(qq=event.get_sender_id()), # Mention the message sender
        Comp.Plain("Check out this image:"),
        Comp.Image.fromURL("https://example.com/image.jpg"), # Send image from URL
        Comp.Image.fromFileSystem("path/to/image.jpg"), # Send image from local file system
        Comp.Plain("This is an image.")
    ]
    yield event.chain_result(chain)
```

The above constructs a `message chain`, which will ultimately send a message containing both images and text while preserving the order.

> [!TIP]
> In the aiocqhttp message adapter, for messages of type `plain`, the `strip()` method is used during sending to remove spaces and line breaks. You can add zero-width spaces `\u200b` before and after the message to resolve this issue.

Similarly,

**File**

```py
Comp.File(file="path/to/file.txt", name="file.txt") # Not supported by some platforms
```

**Audio Record**

```py
path = "path/to/record.wav" # Currently only accepts wav format, please convert other formats yourself
Comp.Record(file=path, url=path)
```

**Video**

```py
path = "path/to/video.mp4"
Comp.Video.fromFileSystem(path=path)
Comp.Video.fromURL(url="https://example.com/video.mp4")
```

## Sending Video Messages

```python
from astrbot.api.event import filter, AstrMessageEvent

@filter.command("test")
async def test(self, event: AstrMessageEvent):
    from astrbot.api.message_components import Video
    # fromFileSystem requires the user's protocol client and bot to be on the same system.
    video = Video.fromFileSystem(
        path="test.mp4"
    )
    # More universal approach
    video = Video.fromURL(
        url="https://example.com/video.mp4"
    )
    yield event.chain_result([video])
```

![Sending video messages](https://files.astrbot.app/docs/source/images/plugin/db93a2bb-671c-4332-b8ba-9a91c35623c2.png)

## Telegram-Specific Text and Interaction Components

The Telegram adapter supports Telegram-specific components in `MessageChain` for text or media captions with Markdown/HTML parsing, link previews, and Inline Keyboard. These components also work with proactive sends through `self.context.send_message(unified_msg_origin, chains)`.

```python
from astrbot.api.event import MessageChain, filter, AstrMessageEvent
from astrbot.api.message_components import Image
from astrbot.core.platform.sources.telegram.components import (
    TelegramCaption,
    TelegramInlineButton,
    TelegramInlineKeyboard,
    TelegramText,
    TelegramReplyKeyboard,
    TelegramKeyboardButton,
    TelegramRemoveKeyboard,
    TelegramForceReply,
)

@filter.command("review")
async def review(self, event: AstrMessageEvent):
    chain = MessageChain()
    chain.chain.append(
        TelegramText(
            "**Choose an approval action**\n\n[Open details](https://example.com/item/42)",
            parse_mode="MarkdownV2",
            link_preview_is_disabled=False,
            link_preview_url="https://example.com/item/42",
            link_preview_prefer_large_media=True,
            link_preview_show_above_text=True,
        )
    )
    chain.chain.append(
        TelegramInlineKeyboard(
            [
                [
                    TelegramInlineButton("Approve", callback_data="approve:42"),
                    TelegramInlineButton("Reject", callback_data="reject:42"),
                ],
                [TelegramInlineButton("Open Web Page", url="https://example.com/item/42")],
            ]
        )
    )
    chain.chain.append(TelegramCaption("Attachment caption", parse_mode="HTML"))
    chain.chain.append(Image.fromURL("https://example.com/item/42.png"))
    yield event.chain_result(chain.chain)
```

`TelegramText.parse_mode` and `TelegramCaption.parse_mode` support `MarkdownV2`, `Markdown`, and `HTML`. You can also pass `plaintext`, `plain`, or `none` to send plain text. `TelegramText` link preview fields map to Telegram `LinkPreviewOptions`: disabled state, preview URL, small/large media preference, and whether the preview is shown above the text.

Each `TelegramInlineButton` must set exactly one action. Supported actions are `url`, `callback_data`, `login_url`, `web_app`, `switch_inline_query`, `switch_inline_query_current_chat`, `switch_inline_query_chosen_chat`, `copy_text`, `callback_game`, and `pay`, plus `style` and `icon_custom_emoji_id` when supported by the Bot API. `callback_data` must be 1-64 UTF-8 bytes.

### Telegram Album / MediaGroup

The Telegram adapter automatically sends consecutive media in the same segment as an album. Adjacent `Plain` components become the media caption. The adapter does not insert line breaks automatically; write `\n` in the text when you want a line break.

```python
import astrbot.api.message_components as Comp

chain = MessageChain()
chain.chain.extend(
    [
        Comp.Plain("Today's media\n"),
        Comp.Image.fromURL("https://example.com/1.jpg"),
        Comp.Image.fromURL("https://example.com/2.jpg"),
        Comp.Video.fromURL("https://example.com/demo.mp4"),
    ]
)
yield event.chain_result(chain.chain)
```

Automatic album rules:

- `Image` and `Video` can form a mixed photo/video album.
- Consecutive `File` components form a document album.
- `Record` means Telegram voice message and is not sent as an audio album.
- Each album can contain at most 10 media items. Longer sequences are sent in order as multiple batches, with the caption only on the first batch.
- Telegram Bot API limits captions to 1024 characters. Longer captions raise an error and are not truncated or split.
- Telegram media groups do not support `reply_markup`; send a separate message with `TelegramInlineKeyboard` when you need buttons.

Use explicit `TelegramMediaGroup` when you need Telegram audio albums or common advanced media options such as spoiler, video streaming, and thumbnails:

```python
from astrbot.core.platform.sources.telegram.components import TelegramMediaGroup

chain = MessageChain()
chain.chain.append(
    TelegramMediaGroup(
        [
            TelegramMediaGroup.photo(
                "https://example.com/secret.jpg",
                has_spoiler=True,
            ),
            TelegramMediaGroup.video(
                "https://example.com/movie.mp4",
                supports_streaming=True,
                thumbnail="path/to/thumb.jpg",
            ),
        ],
        caption="<b>Media preview</b>",
        parse_mode="HTML",
    )
)
yield event.chain_result(chain.chain)
```

`TelegramMediaGroup.audio(...)` supports explicit audio albums without changing the generic `Record` voice-message meaning. For more detailed Telegram Bot API parameters, use `event.get_telegram_client()` and call `python-telegram-bot` directly.

You can also send Telegram Reply Keyboard, remove an existing keyboard, or force a reply:

```python
chain = MessageChain()
chain.message("Choose a contact method")
chain.chain.append(
    TelegramReplyKeyboard(
        [[TelegramKeyboardButton("Share phone", request_contact=True), "Cancel"]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Choose",
    )
)
yield event.chain_result(chain.chain)

remove = MessageChain()
remove.message("Cancelled")
remove.chain.append(TelegramRemoveKeyboard(selective=True))
yield event.chain_result(remove.chain)

force = MessageChain()
force.message("Please reply with the approval reason")
force.chain.append(TelegramForceReply(input_field_placeholder="Reason"))
yield event.chain_result(force.chain)
```

Plugins can listen for button callbacks with the Telegram custom filter to build approval, confirmation, pagination, and similar flows. The important part is `@filter.custom_filter(telegram_event_filter(...))`; regular command filters do not specifically match Telegram callback/inline/member events:

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.core.platform.sources.telegram.filters import telegram_event_filter

@filter.custom_filter(telegram_event_filter("callback_query"))
async def on_telegram_button(self, event: AstrMessageEvent):
    action = event.get_interaction_data()
    await event.ack_interaction()

    if action == "approve:42":
        yield event.plain_result("Approved")
        return

    if action == "reject:42":
        await event.answer_interaction("Rejected", show_alert=True)
        return

    await event.answer_interaction(f"Unknown action: {action}", show_alert=True)
```

Use `event.ack_interaction()` for a quick acknowledgment so the Telegram client stops showing the button loading state. Use `event.answer_interaction(text, show_alert=False)` to answer the callback query; `show_alert=True` shows an alert dialog. `event.get_interaction_custom_id()` and `event.get_interaction_data()` both return Telegram `callback_data`, which is the value set by `TelegramInlineButton(..., callback_data="approve:42")` above.

For more complex menus such as paginated lists, setting selection, and back navigation, use the Telegram-specific menu framework. The framework stores a short token, state, and back stack for each menu message. Button `callback_data` uses `tgm:<namespace>:<token>:<action>`, so keep complex data in menu state or plugin storage instead of putting it in `callback_data`.

```python
from urllib.parse import urlsplit

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.core.platform.sources.telegram.filters import telegram_event_filter
from astrbot.core.platform.sources.telegram.menu import (
    PluginKVTelegramMenuStore,
    TelegramMenu,
    TelegramMenuButton,
    TelegramMenuContext,
    TelegramMenuInput,
    TelegramMenuPaginator,
    TelegramMenuView,
)

TELEGRAM_SETTINGS_CALLBACK_PREFIX = "tgm:rss_settings:"


class Main:
    def __init__(self, context):
        self.context = context
        self.settings_menu = TelegramMenu(
            "rss_settings",
            self.render_settings_menu,
            store=PluginKVTelegramMenuStore(self),
            invalid_text="This menu has expired. Please send /set again.",
        )

    @filter.command("set")
    async def open_settings(self, event: AstrMessageEvent):
        chain = await self.settings_menu.open(
            {
                "page": "list",
                "page_index": 0,
                "urls": {
                    "morning": "https://example.com/morning.xml",
                    "pixiv": "https://example.com/pixiv.xml",
                },
            }
        )
        yield event.chain_result(chain.chain)

    @filter.custom_filter(
        telegram_event_filter(
            "callback_query",
            callback_data_prefix=TELEGRAM_SETTINGS_CALLBACK_PREFIX,
        )
    )
    async def on_settings_menu(self, event: AstrMessageEvent):
        await self.settings_menu.handle_event(event)

    @filter.event_message_type(filter.EventMessageType.ALL, priority=10)
    async def on_settings_menu_input(self, event: AstrMessageEvent):
        await self.settings_menu.handle_input_event(event)

    def parse_subscription_url(
        self,
        value: str,
        ctx: TelegramMenuContext,
    ) -> str:
        value = value.strip()
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Please enter a full http or https URL.")
        return value

    def save_subscription_url(
        self,
        value: str,
        ctx: TelegramMenuContext,
    ) -> None:
        subscription_id = ctx.state["subscription_id"]
        urls = dict(ctx.state.get("urls", {}))
        urls[subscription_id] = value
        ctx.state["urls"] = urls

    async def render_settings_menu(self, ctx: TelegramMenuContext) -> TelegramMenuView:
        subscriptions = [
            {"id": "morning", "title": "Morning AI digest"},
            {"id": "pixiv", "title": "New Pixiv follows"},
        ]

        if ctx.action.startswith("page:"):
            ctx.replace({"page": "list", "page_index": int(ctx.action.split(":", 1)[1])})
        elif ctx.action.startswith("open:"):
            ctx.goto({"page": "detail", "subscription_id": ctx.action.split(":", 1)[1]})
        elif ctx.action == "back":
            ctx.back()
        elif ctx.action == "edit_url":
            ctx.prompt_input(
                TelegramMenuInput(
                    "subscription_url",
                    "Send the new subscription URL. Send cancel to exit input.",
                    placeholder="https://example.com/feed.xml",
                    action="save_url",
                    parse=self.parse_subscription_url,
                    on_success=self.save_subscription_url,
                    error_text=lambda error: f"Invalid URL: {error}",
                )
            )

        if ctx.state["page"] == "detail":
            subscription_id = ctx.state["subscription_id"]
            current_url = ctx.state.get("urls", {}).get(subscription_id, "Not set")
            return TelegramMenuView(
                f"Subscription\n\nCurrent subscription: {subscription_id}\nURL: {current_url}",
                rows=[
                    [TelegramMenuButton("Status: enabled", "toggle_status")],
                    [TelegramMenuButton("Edit URL", "edit_url")],
                    [TelegramMenuButton("< Back", "back")],
                ],
            )

        paginator = TelegramMenuPaginator(
            subscriptions,
            page=ctx.state.get("page_index", 0),
            page_size=5,
        )
        rows = paginator.item_rows(
            text=lambda item: item["title"],
            action=lambda item: f"open:{item['id']}",
        )
        rows.append(paginator.navigation_row(previous_text="<", next_text=">"))
        return TelegramMenuView("Choose the subscription to configure.", rows=rows)
```

If you do not need persistent menu state, omit `store` and the framework will use in-memory storage. Decorators usually cannot access `self.settings_menu.callback_data_prefix`, so define a fixed prefix constant for the menu namespace as shown above. `handle_input_event()` only consumes pending input from the same platform, session, and sender; after success or cancellation it calls `event.stop_event()` so the user input does not continue into normal chat handling or the LLM.

The same filter entrypoint can also listen for Telegram inline/member events. Inline Mode uses standalone models that are only for `event.answer_inline_query(...)`; they are not `MessageChain` components and must not be placed in `event.chain_result(...)` chains. For these events, read the original Telegram `Update` object from `event.message_obj.raw_message`:

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.core.platform.sources.telegram.inline import (
    TelegramInlineQueryResult,
    TelegramInlineQueryResultsButton,
    TelegramInputTextMessageContent,
)
from astrbot.core.platform.sources.telegram.filters import telegram_event_filter

@filter.custom_filter(telegram_event_filter("inline_query"))
async def on_telegram_inline_query(self, event: AstrMessageEvent):
    query = event.get_inline_query_text()
    await event.answer_inline_query(
        [
            TelegramInlineQueryResult(
                "article",
                id="echo",
                title=f"Send: {query}",
                input_message_content=TelegramInputTextMessageContent(query or "Empty query"),
            )
        ],
        cache_time=0,
        is_personal=True,
        button=TelegramInlineQueryResultsButton("Open more results", start_parameter="more"),
    )

@filter.custom_filter(telegram_event_filter("chat_member"))
async def on_telegram_chat_member(self, event: AstrMessageEvent):
    member_update = event.get_chat_member_update()
    yield event.plain_result(f"Member status changed: {member_update.new_chat_member.status}")
```

Available event types include `callback_query`, `inline_query`, `chosen_inline_result`, `chat_member`, `my_chat_member`, `member_joined`, `member_left`, `poll`, and `dice`. Button callbacks are the most common interaction enhancement case. A practical pattern is to encode `callback_data` as `action:resource_id` and branch explicitly in the handler.

If AstrBot has not wrapped a Telegram Bot API method yet, Telegram events expose `event.get_telegram_client()` for direct `python-telegram-bot` Bot calls. Use `event.get_telegram_update()` when you need the raw Telegram `Update`.

## Sending Group Forward Messages

> Most platforms do not support this message type. Current support: OneBot v11

You can send group forward messages as follows.

```py
from astrbot.api.event import filter, AstrMessageEvent

@filter.command("test")
async def test(self, event: AstrMessageEvent):
    from astrbot.api.message_components import Node, Plain, Image
    node = Node(
        uin=905617992,
        name="Soulter",
        content=[
            Plain("hi"),
            Image.fromFileSystem("test.jpg")
        ]
    )
    yield event.chain_result([node])
```

![Sending group forward messages](https://files.astrbot.app/docs/source/images/plugin/image-4.png)

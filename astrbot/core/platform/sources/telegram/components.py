from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

from telegram import (
    CallbackGame,
    CopyTextButton,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    LinkPreviewOptions,
    LoginUrl,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    SwitchInlineQueryChosenChat,
    WebAppInfo,
)

from astrbot.api.message_components import BaseMessageComponent

TELEGRAM_CALLBACK_DATA_MAX_BYTES = 64


class TelegramMessageComponent(BaseMessageComponent, ABC):
    """Base class for Telegram-specific MessageChain components."""


class TelegramButtonComponent(TelegramMessageComponent):
    """Base class for Telegram button components."""

    @abstractmethod
    def to_telegram_button(self) -> Any: ...


class TelegramReplyMarkupComponent(TelegramMessageComponent):
    """Base class for Telegram reply_markup components."""

    @abstractmethod
    def to_telegram_markup(self) -> Any: ...


class TelegramTextComponent(TelegramMessageComponent):
    """Base class for Telegram text-like components."""


class TelegramMediaGroupComponent(TelegramMessageComponent):
    """Base class for Telegram explicit media group components."""


@runtime_checkable
class SupportsTelegramButton(Protocol):
    """Object that can be converted to a Telegram button."""

    def to_telegram_button(self) -> Any: ...


@runtime_checkable
class SupportsTelegramMarkup(Protocol):
    """Object that can be converted to Telegram reply markup."""

    def to_telegram_markup(self) -> Any: ...


def build_link_preview_options(
    *,
    link_preview_options: Any = None,
    link_preview_is_disabled: bool | None = None,
    link_preview_url: str | None = None,
    link_preview_prefer_small_media: bool | None = None,
    link_preview_prefer_large_media: bool | None = None,
    link_preview_show_above_text: bool | None = None,
) -> Any:
    """Build PTB LinkPreviewOptions from Telegram text fields."""
    if link_preview_options is not None:
        return link_preview_options
    if not any(
        value is not None
        for value in (
            link_preview_is_disabled,
            link_preview_url,
            link_preview_prefer_small_media,
            link_preview_prefer_large_media,
            link_preview_show_above_text,
        )
    ):
        return None

    return LinkPreviewOptions(
        is_disabled=link_preview_is_disabled,
        url=link_preview_url,
        prefer_small_media=link_preview_prefer_small_media,
        prefer_large_media=link_preview_prefer_large_media,
        show_above_text=link_preview_show_above_text,
    )


class TelegramInlineButton(TelegramButtonComponent):
    """Telegram inline keyboard button component."""

    type: str = "telegram_inline_button"
    text: str
    url: str | None = None
    callback_data: str | None = None
    login_url: Any = None
    web_app: Any = None
    switch_inline_query: str | None = None
    switch_inline_query_current_chat: str | None = None
    switch_inline_query_chosen_chat: Any = None
    copy_text: Any = None
    callback_game: Any = None
    pay: bool | None = None
    style: str | None = None
    icon_custom_emoji_id: str | None = None

    def __init__(
        self,
        text: str,
        *,
        url: str | None = None,
        callback_data: str | None = None,
        login_url: LoginUrl | str | None = None,
        web_app: WebAppInfo | str | None = None,
        switch_inline_query: str | None = None,
        switch_inline_query_current_chat: str | None = None,
        switch_inline_query_chosen_chat: SwitchInlineQueryChosenChat
        | dict
        | None = None,
        copy_text: CopyTextButton | str | None = None,
        callback_game: CallbackGame | None = None,
        pay: bool | None = None,
        style: str | None = None,
        icon_custom_emoji_id: str | None = None,
    ) -> None:
        super().__init__(
            text=text,
            url=url,
            callback_data=callback_data,
            login_url=login_url,
            web_app=web_app,
            switch_inline_query=switch_inline_query,
            switch_inline_query_current_chat=switch_inline_query_current_chat,
            switch_inline_query_chosen_chat=switch_inline_query_chosen_chat,
            copy_text=copy_text,
            callback_game=callback_game,
            pay=pay,
            style=style,
            icon_custom_emoji_id=icon_custom_emoji_id,
        )
        self._validate_action()

    def _action_values(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "callback_data": self.callback_data,
            "login_url": self.login_url,
            "web_app": self.web_app,
            "switch_inline_query": self.switch_inline_query,
            "switch_inline_query_current_chat": self.switch_inline_query_current_chat,
            "switch_inline_query_chosen_chat": self.switch_inline_query_chosen_chat,
            "copy_text": self.copy_text,
            "callback_game": self.callback_game,
            "pay": self.pay,
        }

    def _validate_action(self) -> None:
        actions = {
            key: value
            for key, value in self._action_values().items()
            if value is not None and value is not False
        }
        if len(actions) != 1:
            raise ValueError(
                "Telegram inline button requires exactly one optional action.",
            )

        if self.callback_data is None:
            return

        callback_data_length = len(self.callback_data.encode("utf-8"))
        if not 1 <= callback_data_length <= TELEGRAM_CALLBACK_DATA_MAX_BYTES:
            raise ValueError(
                "Telegram inline button callback_data must be 1-64 UTF-8 bytes.",
            )

    def to_telegram_button(self) -> InlineKeyboardButton:
        payload = self._action_values()
        if isinstance(self.login_url, str):
            payload["login_url"] = LoginUrl(self.login_url)
        if isinstance(self.web_app, str):
            payload["web_app"] = WebAppInfo(self.web_app)
        if isinstance(self.switch_inline_query_chosen_chat, dict):
            payload["switch_inline_query_chosen_chat"] = SwitchInlineQueryChosenChat(
                **self.switch_inline_query_chosen_chat,
            )
        if isinstance(self.copy_text, str):
            payload["copy_text"] = CopyTextButton(self.copy_text)

        button_payload = {
            key: value
            for key, value in payload.items()
            if value is not None and value is not False
        }
        if self.style is not None:
            button_payload["style"] = self.style
        if self.icon_custom_emoji_id is not None:
            button_payload["icon_custom_emoji_id"] = self.icon_custom_emoji_id

        return InlineKeyboardButton(
            text=self.text,
            **button_payload,
        )


class TelegramInlineKeyboard(TelegramReplyMarkupComponent):
    """Telegram inline keyboard component."""

    type: str = "telegram_inline_keyboard"
    rows: list[list[Any]]

    def __init__(
        self,
        rows: list[list[SupportsTelegramButton | InlineKeyboardButton]],
    ) -> None:
        super().__init__(rows=rows)

    def to_telegram_markup(self) -> InlineKeyboardMarkup:
        keyboard: list[list[InlineKeyboardButton]] = []
        for row in self.rows:
            keyboard.append(
                [
                    button.to_telegram_button()
                    if isinstance(button, SupportsTelegramButton)
                    else button
                    for button in row
                ],
            )
        return InlineKeyboardMarkup(keyboard)


class TelegramKeyboardButton(TelegramButtonComponent):
    """Telegram reply-keyboard button component."""

    type: str = "telegram_keyboard_button"
    text: str
    request_contact: bool | None = None
    request_location: bool | None = None
    request_poll: Any = None
    web_app: Any = None
    request_chat: Any = None
    request_users: Any = None
    style: str | None = None
    icon_custom_emoji_id: str | None = None

    def __init__(
        self,
        text: str,
        *,
        request_contact: bool | None = None,
        request_location: bool | None = None,
        request_poll: Any = None,
        web_app: WebAppInfo | str | None = None,
        request_chat: Any = None,
        request_users: Any = None,
        style: str | None = None,
        icon_custom_emoji_id: str | None = None,
    ) -> None:
        super().__init__(
            text=text,
            request_contact=request_contact,
            request_location=request_location,
            request_poll=request_poll,
            web_app=web_app,
            request_chat=request_chat,
            request_users=request_users,
            style=style,
            icon_custom_emoji_id=icon_custom_emoji_id,
        )

    def to_telegram_button(self) -> KeyboardButton:
        web_app = (
            WebAppInfo(self.web_app) if isinstance(self.web_app, str) else self.web_app
        )
        return KeyboardButton(
            text=self.text,
            request_contact=self.request_contact,
            request_location=self.request_location,
            request_poll=self.request_poll,
            web_app=web_app,
            request_chat=self.request_chat,
            request_users=self.request_users,
            style=self.style,
            icon_custom_emoji_id=self.icon_custom_emoji_id,
        )


class TelegramReplyKeyboard(TelegramReplyMarkupComponent):
    """Telegram custom reply keyboard component."""

    type: str = "telegram_reply_keyboard"
    rows: list[list[Any]]
    resize_keyboard: bool | None = None
    one_time_keyboard: bool | None = None
    selective: bool | None = None
    input_field_placeholder: str | None = None
    is_persistent: bool | None = None

    def __init__(
        self,
        rows: list[list[str | SupportsTelegramButton | KeyboardButton]],
        *,
        resize_keyboard: bool | None = None,
        one_time_keyboard: bool | None = None,
        selective: bool | None = None,
        input_field_placeholder: str | None = None,
        is_persistent: bool | None = None,
    ) -> None:
        super().__init__(
            rows=rows,
            resize_keyboard=resize_keyboard,
            one_time_keyboard=one_time_keyboard,
            selective=selective,
            input_field_placeholder=input_field_placeholder,
            is_persistent=is_persistent,
        )

    def to_telegram_markup(self) -> ReplyKeyboardMarkup:
        keyboard: list[list[str | KeyboardButton]] = []
        for row in self.rows:
            keyboard.append(
                [
                    button.to_telegram_button()
                    if isinstance(button, SupportsTelegramButton)
                    else button
                    for button in row
                ],
            )
        return ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=self.resize_keyboard,
            one_time_keyboard=self.one_time_keyboard,
            selective=self.selective,
            input_field_placeholder=self.input_field_placeholder,
            is_persistent=self.is_persistent,
        )


class TelegramRemoveKeyboard(TelegramReplyMarkupComponent):
    """Telegram reply-keyboard removal component."""

    type: str = "telegram_remove_keyboard"
    selective: bool | None = None

    def __init__(self, *, selective: bool | None = None) -> None:
        super().__init__(selective=selective)

    def to_telegram_markup(self) -> ReplyKeyboardRemove:
        return ReplyKeyboardRemove(selective=self.selective)


class TelegramForceReply(TelegramReplyMarkupComponent):
    """Telegram force-reply prompt component."""

    type: str = "telegram_force_reply"
    selective: bool | None = None
    input_field_placeholder: str | None = None

    def __init__(
        self,
        *,
        selective: bool | None = None,
        input_field_placeholder: str | None = None,
    ) -> None:
        super().__init__(
            selective=selective,
            input_field_placeholder=input_field_placeholder,
        )

    def to_telegram_markup(self) -> ForceReply:
        return ForceReply(
            selective=self.selective,
            input_field_placeholder=self.input_field_placeholder,
        )


class TelegramText(TelegramTextComponent):
    """Visible Telegram text message with Bot API text rendering options."""

    type: str = "telegram_text"
    text: str
    parse_mode: str | None = None
    link_preview_options: Any = None
    link_preview_is_disabled: bool | None = None
    link_preview_url: str | None = None
    link_preview_prefer_small_media: bool | None = None
    link_preview_prefer_large_media: bool | None = None
    link_preview_show_above_text: bool | None = None

    def __init__(
        self,
        text: str,
        *,
        parse_mode: str | None = None,
        link_preview_options: Any = None,
        link_preview_is_disabled: bool | None = None,
        link_preview_url: str | None = None,
        link_preview_prefer_small_media: bool | None = None,
        link_preview_prefer_large_media: bool | None = None,
        link_preview_show_above_text: bool | None = None,
    ) -> None:
        super().__init__(
            text=text,
            parse_mode=parse_mode,
            link_preview_options=link_preview_options,
            link_preview_is_disabled=link_preview_is_disabled,
            link_preview_url=link_preview_url,
            link_preview_prefer_small_media=link_preview_prefer_small_media,
            link_preview_prefer_large_media=link_preview_prefer_large_media,
            link_preview_show_above_text=link_preview_show_above_text,
        )


class TelegramCaption(TelegramTextComponent):
    """Visible Telegram media caption for the next captionable media segment."""

    type: str = "telegram_caption"
    text: str
    parse_mode: str | None = None

    def __init__(self, text: str, *, parse_mode: str | None = None) -> None:
        super().__init__(
            text=text,
            parse_mode=parse_mode,
        )


class TelegramMediaGroupItem(TelegramMediaGroupComponent):
    """Telegram media group item for explicit album sending."""

    type: str = "telegram_media_group_item"
    media_type: str
    media: Any
    filename: str | None = None
    thumbnail: Any = None
    has_spoiler: bool | None = None
    show_caption_above_media: bool | None = None
    supports_streaming: bool | None = None
    disable_content_type_detection: bool | None = None
    duration: int | None = None
    performer: str | None = None
    title: str | None = None

    def __init__(
        self,
        media_type: str,
        media: Any,
        *,
        filename: str | None = None,
        thumbnail: Any = None,
        has_spoiler: bool | None = None,
        show_caption_above_media: bool | None = None,
        supports_streaming: bool | None = None,
        disable_content_type_detection: bool | None = None,
        duration: int | None = None,
        performer: str | None = None,
        title: str | None = None,
    ) -> None:
        normalized_media_type = media_type.strip().lower()
        if normalized_media_type not in {"photo", "video", "document", "audio"}:
            raise ValueError(
                "Telegram media group item type must be one of photo, video, document, or audio.",
            )
        super().__init__(
            media_type=normalized_media_type,
            media=media,
            filename=filename,
            thumbnail=thumbnail,
            has_spoiler=has_spoiler,
            show_caption_above_media=show_caption_above_media,
            supports_streaming=supports_streaming,
            disable_content_type_detection=disable_content_type_detection,
            duration=duration,
            performer=performer,
            title=title,
        )


class TelegramMediaGroup(TelegramMediaGroupComponent):
    """Explicit Telegram album component with common InputMedia options."""

    type: str = "telegram_media_group"
    items: list[TelegramMediaGroupItem]
    caption: str | None = None
    parse_mode: str | None = None

    def __init__(
        self,
        items: list[TelegramMediaGroupItem],
        *,
        caption: str | None = None,
        parse_mode: str | None = None,
    ) -> None:
        if len(items) < 2:
            raise ValueError("TelegramMediaGroup requires at least 2 media items.")
        super().__init__(items=items, caption=caption, parse_mode=parse_mode)

    @staticmethod
    def photo(
        media: Any,
        *,
        filename: str | None = None,
        has_spoiler: bool | None = None,
        show_caption_above_media: bool | None = None,
    ) -> TelegramMediaGroupItem:
        return TelegramMediaGroupItem(
            "photo",
            media,
            filename=filename,
            has_spoiler=has_spoiler,
            show_caption_above_media=show_caption_above_media,
        )

    @staticmethod
    def video(
        media: Any,
        *,
        filename: str | None = None,
        thumbnail: Any = None,
        has_spoiler: bool | None = None,
        show_caption_above_media: bool | None = None,
        supports_streaming: bool | None = None,
    ) -> TelegramMediaGroupItem:
        return TelegramMediaGroupItem(
            "video",
            media,
            filename=filename,
            thumbnail=thumbnail,
            has_spoiler=has_spoiler,
            show_caption_above_media=show_caption_above_media,
            supports_streaming=supports_streaming,
        )

    @staticmethod
    def document(
        media: Any,
        *,
        filename: str | None = None,
        thumbnail: Any = None,
        disable_content_type_detection: bool | None = None,
    ) -> TelegramMediaGroupItem:
        return TelegramMediaGroupItem(
            "document",
            media,
            filename=filename,
            thumbnail=thumbnail,
            disable_content_type_detection=disable_content_type_detection,
        )

    @staticmethod
    def audio(
        media: Any,
        *,
        filename: str | None = None,
        thumbnail: Any = None,
        duration: int | None = None,
        performer: str | None = None,
        title: str | None = None,
    ) -> TelegramMediaGroupItem:
        return TelegramMediaGroupItem(
            "audio",
            media,
            filename=filename,
            thumbnail=thumbnail,
            duration=duration,
            performer=performer,
            title=title,
        )

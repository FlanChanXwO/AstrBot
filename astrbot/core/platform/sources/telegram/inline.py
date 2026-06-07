from typing import Any, Protocol, runtime_checkable

from telegram import (
    InlineQueryResultArticle,
    InlineQueryResultAudio,
    InlineQueryResultCachedAudio,
    InlineQueryResultCachedDocument,
    InlineQueryResultCachedGif,
    InlineQueryResultCachedMpeg4Gif,
    InlineQueryResultCachedPhoto,
    InlineQueryResultCachedSticker,
    InlineQueryResultCachedVideo,
    InlineQueryResultCachedVoice,
    InlineQueryResultContact,
    InlineQueryResultDocument,
    InlineQueryResultGame,
    InlineQueryResultGif,
    InlineQueryResultLocation,
    InlineQueryResultMpeg4Gif,
    InlineQueryResultPhoto,
    InlineQueryResultsButton,
    InlineQueryResultVenue,
    InlineQueryResultVideo,
    InlineQueryResultVoice,
    InputTextMessageContent,
    WebAppInfo,
)

from .components import SupportsTelegramButton, SupportsTelegramMarkup

TELEGRAM_INLINE_QUERY_RESULT_TYPES: dict[str, type] = {
    "article": InlineQueryResultArticle,
    "audio": InlineQueryResultAudio,
    "cached_audio": InlineQueryResultCachedAudio,
    "cached_document": InlineQueryResultCachedDocument,
    "cached_gif": InlineQueryResultCachedGif,
    "cached_mpeg4_gif": InlineQueryResultCachedMpeg4Gif,
    "cached_photo": InlineQueryResultCachedPhoto,
    "cached_sticker": InlineQueryResultCachedSticker,
    "cached_video": InlineQueryResultCachedVideo,
    "cached_voice": InlineQueryResultCachedVoice,
    "contact": InlineQueryResultContact,
    "document": InlineQueryResultDocument,
    "game": InlineQueryResultGame,
    "gif": InlineQueryResultGif,
    "location": InlineQueryResultLocation,
    "mpeg4_gif": InlineQueryResultMpeg4Gif,
    "photo": InlineQueryResultPhoto,
    "venue": InlineQueryResultVenue,
    "video": InlineQueryResultVideo,
    "voice": InlineQueryResultVoice,
}


@runtime_checkable
class SupportsTelegramInputContent(Protocol):
    """Object that can be converted to Telegram inline input content."""

    def to_telegram_content(self) -> Any: ...


@runtime_checkable
class SupportsTelegramInlineResult(Protocol):
    """Object that can be converted to a Telegram inline query result."""

    def to_telegram_result(self) -> Any: ...


class TelegramInputTextMessageContent:
    """Telegram inline-query text message content model."""

    message_text: str
    parse_mode: str | None = None
    entities: Any = None
    link_preview_options: Any = None
    disable_web_page_preview: bool | None = None
    api_kwargs: dict[str, Any] | None = None

    def __init__(
        self,
        message_text: str,
        *,
        parse_mode: str | None = None,
        entities: Any = None,
        link_preview_options: Any = None,
        disable_web_page_preview: bool | None = None,
        api_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.message_text = message_text
        self.parse_mode = parse_mode
        self.entities = entities
        self.link_preview_options = link_preview_options
        self.disable_web_page_preview = disable_web_page_preview
        self.api_kwargs = api_kwargs

    def to_telegram_content(self) -> InputTextMessageContent:
        return InputTextMessageContent(
            message_text=self.message_text,
            parse_mode=self.parse_mode,
            entities=self.entities,
            link_preview_options=self.link_preview_options,
            disable_web_page_preview=self.disable_web_page_preview,
            api_kwargs=self.api_kwargs,
        )


class TelegramInlineQueryResult:
    """Telegram inline-query answer result model."""

    result_type: str
    payload: dict[str, Any]

    def __init__(self, result_type: str, **payload: Any) -> None:
        self.result_type = result_type
        self.payload = payload

    def to_telegram_result(self) -> Any:
        result_type = self.result_type.strip().lower()
        result_class = TELEGRAM_INLINE_QUERY_RESULT_TYPES.get(result_type)
        if result_class is None:
            supported = ", ".join(sorted(TELEGRAM_INLINE_QUERY_RESULT_TYPES))
            raise ValueError(
                f"Unsupported Telegram inline query result type: {self.result_type}. "
                f"Supported types: {supported}.",
            )
        return result_class(**convert_inline_payload(self.payload))


class TelegramInlineQueryResultsButton:
    """Telegram inline-query answer button model."""

    text: str
    web_app: Any = None
    start_parameter: str | None = None

    def __init__(
        self,
        text: str,
        *,
        web_app: WebAppInfo | str | None = None,
        start_parameter: str | None = None,
    ) -> None:
        self.text = text
        self.web_app = web_app
        self.start_parameter = start_parameter

    def to_telegram_button(self) -> InlineQueryResultsButton:
        web_app = (
            WebAppInfo(self.web_app) if isinstance(self.web_app, str) else self.web_app
        )
        return InlineQueryResultsButton(
            text=self.text,
            web_app=web_app,
            start_parameter=self.start_parameter,
        )


def convert_inline_payload(value: Any) -> Any:
    if isinstance(value, SupportsTelegramMarkup):
        return value.to_telegram_markup()
    if isinstance(value, SupportsTelegramInputContent):
        return value.to_telegram_content()
    if isinstance(value, SupportsTelegramButton):
        return value.to_telegram_button()
    if isinstance(value, SupportsTelegramInlineResult):
        return value.to_telegram_result()
    if isinstance(value, list):
        return [convert_inline_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(convert_inline_payload(item) for item in value)
    if isinstance(value, dict):
        return {key: convert_inline_payload(item) for key, item in value.items()}
    return value

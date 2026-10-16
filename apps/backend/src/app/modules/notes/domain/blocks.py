import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from typing import Literal
from uuid import UUID, uuid4

from app.core.urls import http_url

MAX_DOCUMENT_BYTES = 1048576
MAX_BLOCKS = 1000
MAX_CONTENT_LENGTH = 100000
MAX_LIST_ITEMS = 1000


class InvalidDocumentInput(ValueError):
    pass


@dataclass(frozen=True)
class TextBlock:
    id: UUID
    text: str
    text_format: Literal["plain", "markdown"] = "plain"
    type: Literal["text"] = field(default="text", init=False)


@dataclass(frozen=True)
class HeadingBlock:
    id: UUID
    text: str
    level: int
    type: Literal["heading"] = field(default="heading", init=False)


@dataclass(frozen=True)
class ListBlock:
    id: UUID
    items: tuple[str, ...]
    style: Literal["bulleted", "numbered"] = "bulleted"
    type: Literal["list"] = field(default="list", init=False)


@dataclass(frozen=True)
class CheckboxBlock:
    id: UUID
    text: str
    checked: bool = False
    type: Literal["checkbox"] = field(default="checkbox", init=False)


@dataclass(frozen=True)
class LinkBlock:
    id: UUID
    text: str
    url: str
    type: Literal["link"] = field(default="link", init=False)


Block = TextBlock | HeadingBlock | ListBlock | CheckboxBlock | LinkBlock


@dataclass(frozen=True)
class PageDocument:
    blocks: tuple[Block, ...] = ()
    schema_version: Literal[1] = 1


def _text(value: object, *, single_line: bool = False) -> str:
    if not isinstance(value, str) or len(value) > MAX_CONTENT_LENGTH or "\x00" in value:
        raise InvalidDocumentInput()
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise InvalidDocumentInput() from None
    if single_line and any(character in value for character in "\r\n"):
        raise InvalidDocumentInput()
    return value


def _url(value: object) -> str:
    try:
        return http_url(value)
    except ValueError:
        raise InvalidDocumentInput() from None


def _block(value: object) -> Block:
    if not isinstance(value, Mapping):
        raise InvalidDocumentInput()
    kind = value.get("type")
    fields = {
        "text": ({"text"}, {"text_format"}),
        "heading": ({"text", "level"}, set()),
        "list": ({"items"}, {"style"}),
        "checkbox": ({"text"}, {"checked"}),
        "link": ({"text", "url"}, set()),
    }
    if not isinstance(kind, str) or kind not in fields:
        raise InvalidDocumentInput()
    required, optional = fields[kind]
    required = required | {"id", "type"}
    if required - value.keys() or value.keys() - required - optional:
        raise InvalidDocumentInput()
    identifier = value["id"]
    if isinstance(identifier, str):
        try:
            identifier = UUID(identifier)
        except ValueError:
            raise InvalidDocumentInput() from None
    if not isinstance(identifier, UUID):
        raise InvalidDocumentInput()
    if kind == "list":
        items = value["items"]
        style = value.get("style", "bulleted")
        if not isinstance(items, list | tuple) or not 1 <= len(items) <= MAX_LIST_ITEMS:
            raise InvalidDocumentInput()
        if style != "bulleted" and style != "numbered":
            raise InvalidDocumentInput()
        return ListBlock(identifier, tuple(_text(item, single_line=True) for item in items), style)
    text = _text(value["text"], single_line=kind != "text")
    if kind == "text":
        text_format = value.get("text_format", "plain")
        if text_format != "plain" and text_format != "markdown":
            raise InvalidDocumentInput()
        return TextBlock(identifier, text, text_format)
    if kind == "heading":
        level = value["level"]
        if type(level) is not int or not 1 <= level <= 6:
            raise InvalidDocumentInput()
        return HeadingBlock(identifier, text, level)
    if kind == "checkbox":
        checked = value.get("checked", False)
        if type(checked) is not bool:
            raise InvalidDocumentInput()
        return CheckboxBlock(identifier, text, checked)
    return LinkBlock(identifier, text, _url(value["url"]))


def parse_document(value: object) -> PageDocument:
    if not isinstance(value, Mapping) or value.keys() != {"schema_version", "blocks"}:
        raise InvalidDocumentInput()
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise InvalidDocumentInput()
    values = value["blocks"]
    if not isinstance(values, list | tuple) or len(values) > MAX_BLOCKS:
        raise InvalidDocumentInput()
    blocks = tuple(_block(block) for block in values)
    if len({block.id for block in blocks}) != len(blocks):
        raise InvalidDocumentInput()
    size = sum(
        sum(len(item) for item in block.items)
        if isinstance(block, ListBlock)
        else len(block.text) + (len(block.url) if isinstance(block, LinkBlock) else 0)
        for block in blocks
    )
    if size > MAX_CONTENT_LENGTH:
        raise InvalidDocumentInput()
    document = PageDocument(blocks)
    encoded = json.dumps(document_value(document), ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise InvalidDocumentInput()
    return document


def document_value(document: PageDocument) -> dict[str, object]:
    blocks = []
    for block in document.blocks:
        value = asdict(block) | {"id": str(block.id)}
        if isinstance(block, ListBlock):
            value["items"] = list(block.items)
        blocks.append(value)
    return {"schema_version": document.schema_version, "blocks": blocks}


def markdown_document(content: str, *, block_id: UUID | None = None) -> PageDocument:
    _text(content)
    return (
        PageDocument((TextBlock(block_id or uuid4(), content, "markdown"),))
        if content
        else PageDocument()
    )


def is_markdown_document(document: PageDocument) -> bool:
    return not document.blocks or (
        len(document.blocks) == 1
        and isinstance(document.blocks[0], TextBlock)
        and document.blocks[0].text_format == "markdown"
    )


def replace_markdown(
    document: PageDocument, content: str, *, block_id: UUID | None = None
) -> PageDocument:
    if not is_markdown_document(document):
        raise InvalidDocumentInput()
    _text(content)
    if content and document.blocks:
        return PageDocument((replace(document.blocks[0], text=content),))
    return markdown_document(content, block_id=block_id)


def _escape(text: str) -> str:
    return "".join(
        "\\" + character if character in "\\`*_{}[]<>()#+-.!|~>" else character
        for character in text
    )


def document_markdown(document: PageDocument) -> str:
    parts: list[str] = []
    for block in document.blocks:
        if isinstance(block, TextBlock):
            parts.append(block.text if block.text_format == "markdown" else _escape(block.text))
        elif isinstance(block, HeadingBlock):
            parts.append("#" * block.level + " " + _escape(block.text))
        elif isinstance(block, ListBlock):
            parts.append(
                "\n".join(
                    (f"{index}. " if block.style == "numbered" else "- ") + _escape(item)
                    for index, item in enumerate(block.items, 1)
                )
            )
        elif isinstance(block, CheckboxBlock):
            parts.append(f"- [{'x' if block.checked else ' '}] " + _escape(block.text))
        else:
            url = block.url.replace("<", "%3C").replace(">", "%3E")
            parts.append(f"[{_escape(block.text)}](<{url}>)")
    return "\n\n".join(parts)

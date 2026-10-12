from dataclasses import replace
from uuid import uuid4

import pytest

from app.modules.notes.domain.blocks import (
    MAX_BLOCKS,
    CheckboxBlock,
    HeadingBlock,
    InvalidDocumentInput,
    LinkBlock,
    ListBlock,
    TextBlock,
    document_markdown,
    document_value,
    is_markdown_document,
    markdown_document,
    parse_document,
    replace_markdown,
)


def block(kind: str = "text", **values) -> dict:
    return {"id": str(uuid4()), "type": kind, "text": "Hello"} | values


def document(*blocks: object) -> dict:
    return {"schema_version": 1, "blocks": list(blocks)}


def test_typed_document_round_trip_and_order() -> None:
    values = document(
        block(text_format="plain"),
        block("heading", level=2),
        {"id": str(uuid4()), "type": "list", "items": ["First", "Second"], "style": "numbered"},
        block("checkbox", checked=True),
        block("link", url="https://example.com/path?q=one#two"),
    )
    parsed = parse_document(values)
    assert isinstance(parsed.blocks[0], TextBlock)
    assert isinstance(parsed.blocks[1], HeadingBlock)
    assert isinstance(parsed.blocks[2], ListBlock)
    assert isinstance(parsed.blocks[3], CheckboxBlock)
    assert isinstance(parsed.blocks[4], LinkBlock)
    assert document_value(parsed) == values
    assert parse_document(document_value(parsed)) == parsed
    reversed_document = parse_document(document(*reversed(values["blocks"])))
    assert reversed_document.blocks == tuple(reversed(parsed.blocks))
    assert document_markdown(parsed) == (
        "Hello\n\n## Hello\n\n1. First\n2. Second\n\n- [x] Hello\n\n"
        "[Hello](<https://example.com/path?q=one#two>)"
    )


@pytest.mark.parametrize(
    "content", ["", "# Legacy\n\n**bold**\n- [x] task\n", "Привет\r\n\r\n世界 😀", "a" * 100000]
)
def test_legacy_markdown_is_preserved_exactly(content: str) -> None:
    identifier = uuid4()
    parsed = markdown_document(content, block_id=identifier)
    assert document_markdown(parsed) == content and is_markdown_document(parsed)
    assert parse_document(document_value(parsed)) == parsed
    if content:
        assert isinstance(parsed.blocks[0], TextBlock)
        assert parsed.blocks[0].id == identifier
        updated = replace_markdown(parsed, "Changed")
        assert updated.blocks[0].id == identifier
        assert parsed.blocks[0].text == content
    else:
        assert parsed.blocks == ()
    assert replace_markdown(parsed, "").blocks == ()


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {},
        {"schema_version": True, "blocks": []},
        {"schema_version": 1.0, "blocks": []},
        {"schema_version": 2, "blocks": []},
        {"schema_version": 1, "blocks": {}},
        {"schema_version": 1, "blocks": [], "unknown": 1},
    ],
)
def test_document_shape_and_schema_version(value: object) -> None:
    with pytest.raises(InvalidDocumentInput):
        parse_document(value)


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        block("unknown"),
        block(id=True),
        block(id="bad"),
        block(extra="field"),
        block(text=None),
        block(text=42),
        block(text="bad\x00value"),
        block(text="bad\ud800value"),
        block(text_format="html"),
        block(text_format=[]),
        block("heading", level=True),
        block("heading", level="1"),
        block("heading", level=0),
        block("heading", level=7),
        block("heading", level=1, text="Line\nBreak"),
        block("checkbox", checked="true"),
        block("checkbox", checked=1),
        {"id": str(uuid4()), "type": "list", "items": []},
        {"id": str(uuid4()), "type": "list", "items": "text"},
        {"id": str(uuid4()), "type": "list", "items": [False]},
        {"id": str(uuid4()), "type": "list", "items": ["a\nb"]},
        {"id": str(uuid4()), "type": "list", "items": ["x"], "style": []},
        {"id": str(uuid4()), "type": "list", "items": ["x"], "style": "tree"},
    ],
)
def test_invalid_blocks(value: object) -> None:
    with pytest.raises(InvalidDocumentInput):
        parse_document(document(value))


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:text/html,bad",
        "file:///etc/passwd",
        "/relative",
        "https://",
        "https://user:password@example.com",
        "https://example.com:70000",
        "https://example.com:0",
        "https://example.com:abc",
        "https://example.com/path with spaces",
        "https://example.com/\n",
        "https://example.com/\\path",
        "https://example.com/\x00",
        "https://example.com/\ud800",
        "x" * 2049,
    ],
)
def test_only_valid_http_links_are_accepted(url: str) -> None:
    with pytest.raises(InvalidDocumentInput):
        parse_document(document(block("link", url=url)))


def test_bounded_content_and_unique_block_ids() -> None:
    repeated = block()
    invalid = [
        document(repeated, repeated),
        document(block(text="x" * 100001)),
        document(block(text="x" * 50001), block(text="y" * 50000)),
        document(*(block() for _ in range(MAX_BLOCKS + 1))),
        document({"id": str(uuid4()), "type": "list", "items": [""] * 1001}),
        document(*({"id": str(uuid4()), "type": "list", "items": [""] * 1000} for _ in range(400))),
    ]
    for value in invalid:
        with pytest.raises(InvalidDocumentInput):
            parse_document(value)


def test_structured_document_is_not_writable_through_legacy_text() -> None:
    parsed = parse_document(document(block("heading", level=1)))
    assert not is_markdown_document(parsed)
    with pytest.raises(InvalidDocumentInput):
        replace_markdown(parsed, "Overwrite")
    assert parsed.blocks[0].type == "heading"


def test_markdown_projection_escapes_plain_text_and_link_labels() -> None:
    parsed = parse_document(
        document(
            block(text="<script>*text*[label]"),
            block("link", text="[label]", url="https://example.com/a>path"),
        )
    )
    assert document_markdown(parsed) == (
        "\\<script\\>\\*text\\*\\[label\\]\n\n[\\[label\\]](<https://example.com/a%3Epath>)"
    )
    assert document_markdown(replace(parsed, blocks=())) == ""

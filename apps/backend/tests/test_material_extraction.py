from io import BytesIO
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.modules.materials.domain.materials import MAX_TEXT_BYTES, DocumentExtractionError
from app.modules.materials.infrastructure.extractor import BoundedDocumentExtractor


def pdf_bytes(text: str | None = "Searchable lecture") -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(612, 792)
    if text:
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 40 700 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = stream
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def office_bytes(parts: dict[str, str]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        for name, text in parts.items():
            archive.writestr(name, text)
    return output.getvalue()


def test_text_pdf_and_no_ocr_behavior() -> None:
    extractor = BoundedDocumentExtractor()
    assert (
        extractor.extract(BytesIO("Учебный текст".encode()), "lecture.md").text == "Учебный текст"
    )
    assert "Searchable lecture" in extractor.extract(BytesIO(pdf_bytes()), "lecture.pdf").text
    assert extractor.extract(BytesIO(pdf_bytes(None)), "scan.pdf").text == ""


def test_docx_body_tables_and_embedded_images_are_not_ocr_processed() -> None:
    content = office_bytes(
        {
            "word/document.xml": """
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body>
<w:p>
<w:r>
<w:t>Lecture</w:t>
</w:r>
</w:p>
<w:tbl>
<w:tr>
<w:tc>
<w:p>
<w:r>
<w:t>Table value</w:t>
</w:r>
</w:p>
</w:tc>
</w:tr>
</w:tbl>
</w:body>
</w:document>
""",
            "word/media/image.png": "not inspected",
        }
    )
    text = BoundedDocumentExtractor().extract(BytesIO(content), "lecture.docx").text
    assert "Lecture" in text and "Table value" in text and "not inspected" not in text


def test_pptx_respects_slide_order_and_reads_table_text() -> None:
    content = office_bytes(
        {
            "ppt/presentation.xml": """
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<p:sldIdLst>
<p:sldId id="1" r:id="rB"/>
<p:sldId id="2" r:id="rA"/>
</p:sldIdLst>
</p:presentation>
""",
            "ppt/_rels/presentation.xml.rels": """
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rA" Target="slides/slide1.xml"/>
<Relationship Id="rB" Target="slides/slide2.xml"/>
</Relationships>
""",
            "ppt/slides/slide1.xml": """
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
 xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
<a:t>Second</a:t>
</p:sld>
""",
            "ppt/slides/slide2.xml": """
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
 xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
<a:t>First table cell</a:t>
</p:sld>
""",
        }
    )
    assert (
        BoundedDocumentExtractor().extract(BytesIO(content), "lecture.pptx").text
        == "First table cell\nSecond"
    )


@pytest.mark.parametrize(
    "body,filename",
    [
        (b"broken", "lecture.pdf"),
        (b"\xff\xfe\x00", "lecture.txt"),
        (b"x\x00y", "lecture.md"),
        (b"image", "image.jpg"),
        (
            office_bytes({"word/document.xml": '<!DOCTYPE x [<!ENTITY x "attack">]><x>&x;</x>'}),
            "lecture.docx",
        ),
        (office_bytes({"../unsafe": "x", "word/document.xml": "<x/>"}), "lecture.docx"),
    ],
)
def test_invalid_documents_are_fixed_errors(body: bytes, filename: str) -> None:
    with pytest.raises(DocumentExtractionError) as failure:
        BoundedDocumentExtractor().extract(BytesIO(body), filename)
    assert str(failure.value) == "invalid_document"


def test_text_limit_and_pdf_page_limit() -> None:
    with pytest.raises(DocumentExtractionError, match="document_limit"):
        BoundedDocumentExtractor().extract(BytesIO(b"x" * (MAX_TEXT_BYTES + 1)), "large.txt")
    writer, content = PdfWriter(), BytesIO()
    for _ in range(501):
        writer.add_blank_page(10, 10)
    writer.write(content)
    with pytest.raises(DocumentExtractionError, match="document_limit"):
        BoundedDocumentExtractor().extract(BytesIO(content.getvalue()), "large.pdf")


def test_parser_child_has_no_service_credentials() -> None:
    import subprocess

    original = subprocess.run

    def inspect_child(*args, **kwargs):
        assert kwargs["env"] == {"LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
        assert kwargs["timeout"] == 60
        return original(*args, **kwargs)

    with patch("subprocess.run", inspect_child):
        assert BoundedDocumentExtractor().extract(BytesIO(b"safe"), "lecture.txt").text == "safe"


def test_encrypted_pdf_and_oversized_xml() -> None:
    writer, output = PdfWriter(), BytesIO()
    writer.add_blank_page(10, 10)
    writer.encrypt("not-supported")
    writer.write(output)
    with pytest.raises(DocumentExtractionError, match="invalid_document"):
        BoundedDocumentExtractor().extract(BytesIO(output.getvalue()), "private.pdf")
    compressed = office_bytes({"word/document.xml": "x" * (8 * 1024 * 1024 + 1)})
    with pytest.raises(DocumentExtractionError, match="document_limit"):
        BoundedDocumentExtractor().extract(BytesIO(compressed), "oversized.docx")


def test_parser_timeout_is_a_fixed_failure() -> None:
    import subprocess

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("parser", 60)):
        with pytest.raises(DocumentExtractionError, match="document_limit"):
            BoundedDocumentExtractor().extract(BytesIO(b"safe"), "lecture.txt")


def test_pdf_locations_are_real_and_empty_pages_keep_numbering() -> None:
    from pypdf import PdfReader

    writer, output = PdfWriter(), BytesIO()
    writer.add_blank_page(612, 792)
    writer.add_page(PdfReader(BytesIO(pdf_bytes("Located text"))).pages[0])
    writer.write(output)
    document = BoundedDocumentExtractor().extract(BytesIO(output.getvalue()), "lecture.pdf")
    assert len(document.locations) == 1
    location = document.locations[0]
    assert (location.kind, location.number) == ("page", 2)
    assert "Located text" in document.text[location.start : location.end]

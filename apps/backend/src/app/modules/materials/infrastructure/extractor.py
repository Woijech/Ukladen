import json
import logging
import posixpath
import resource
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import BinaryIO, Literal
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from app.modules.materials.domain.extraction import ExtractedText, TextLocation
from app.modules.materials.domain.materials import (
    MAX_FILE_BYTES,
    MAX_TEXT_BYTES,
    MIME_TYPES,
    DocumentExtractionError,
)

MAX_PARTS = 500
WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
DRAWING = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
PRESENTATION = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
RELATIONSHIP = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def bounded_text(parts, separator: str = "\n") -> str:
    chunks, size = [], 0
    for part in parts:
        if "\x00" in part:
            raise DocumentExtractionError()
        size += len(part.encode("utf-8")) + (len(separator) if chunks else 0)
        if size > MAX_TEXT_BYTES:
            raise DocumentExtractionError("document_limit")
        chunks.append(part)
    return separator.join(chunks).strip()


def xml_part(archive: ZipFile, name: str) -> ET.Element:
    with archive.open(name) as source:
        data = source.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024:
        raise DocumentExtractionError("document_limit")
    declarations = data.replace(b"\x00", b"").upper()
    if b"<!DOCTYPE" in declarations or b"<!ENTITY" in declarations:
        raise DocumentExtractionError()
    return ET.fromstring(data)


def located_text(parts, kind: Literal["page", "slide"]) -> ExtractedText:
    texts = [bounded_text([part]) for part in parts]
    text = bounded_text(texts)
    # Preserve empty pages/slides in numbering; only text-bearing ranges are searchable.
    locations, offset = [], 0
    for number, part in enumerate(texts, 1):
        if part:
            start = text.find(part, offset)
            locations.append(TextLocation(start, start + len(part), kind, number))
            offset = start + len(part)
    return ExtractedText(text, tuple(locations))


def office_text(path: Path, extension: str) -> ExtractedText:
    with ZipFile(path) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(entries) > 5000 or sum(entry.file_size for entry in entries) > 100 * 1024 * 1024:
            raise DocumentExtractionError("document_limit")
        if len(set(names)) != len(names) or any(
            entry.flag_bits & 1
            or "\\" in entry.filename
            or PurePosixPath(entry.filename).is_absolute()
            or ".." in PurePosixPath(entry.filename).parts
            for entry in entries
        ):
            raise DocumentExtractionError()
        content_types = xml_part(archive, "[Content_Types].xml")
        if any("macroEnabled" in item.attrib.get("ContentType", "") for item in content_types):
            raise DocumentExtractionError()
        if extension == ".docx":
            root = xml_part(archive, "word/document.xml")
            return ExtractedText(
                bounded_text(
                    (
                        node.text or ""
                        if node.tag == WORD + "t"
                        else "\t"
                        if node.tag == WORD + "tab"
                        else "\n"
                        for node in root.iter()
                        if node.tag
                        in {WORD + "t", WORD + "p", WORD + "tr", WORD + "tab", WORD + "br"}
                    ),
                    separator="",
                )
            )
        root = xml_part(archive, "ppt/presentation.xml")
        relationships = xml_part(archive, "ppt/_rels/presentation.xml.rels")
        targets = {
            item.attrib["Id"]: item.attrib["Target"]
            for item in relationships
            if item.attrib.get("TargetMode") != "External"
        }
        slides = list(root.iter(PRESENTATION + "sldId"))
        if len(slides) > MAX_PARTS:
            raise DocumentExtractionError("document_limit")
        parts = []
        for slide in slides:
            target = targets[slide.attrib[RELATIONSHIP + "id"]]
            name = posixpath.normpath(
                target.lstrip("/") if target.startswith("/") else "ppt/" + target
            )
            if not name.startswith("ppt/slides/") or "\\" in name:
                raise DocumentExtractionError()
            tree = xml_part(archive, name)
            parts.append(
                bounded_text(
                    (
                        node.text or "" if node.tag == DRAWING + "t" else "\n"
                        for node in tree.iter()
                        if node.tag in {DRAWING + "t", DRAWING + "p"}
                    ),
                    separator="",
                )
            )
        return located_text(parts, "slide")


def extract_text(path: Path, extension: str) -> ExtractedText:
    if extension not in MIME_TYPES or path.stat().st_size > MAX_FILE_BYTES:
        raise DocumentExtractionError("document_limit")
    if extension in {".txt", ".md"}:
        return ExtractedText(bounded_text([path.read_bytes().decode("utf-8-sig")]))
    if extension in {".docx", ".pptx"}:
        return office_text(path, extension)
    from pypdf import PdfReader

    reader = PdfReader(path, strict=True)
    if reader.is_encrypted:
        raise DocumentExtractionError()
    if len(reader.pages) > MAX_PARTS:
        raise DocumentExtractionError("document_limit")
    return located_text((page.extract_text() or "" for page in reader.pages), "page")


class BoundedDocumentExtractor:
    """Parse in a child with no service credentials and hard Linux resource limits."""

    def extract(self, body: BinaryIO, filename: str) -> ExtractedText:
        extension = PurePosixPath(filename).suffix.lower()
        if extension not in MIME_TYPES:
            raise DocumentExtractionError()
        with TemporaryDirectory(prefix="ukladen-extract-") as directory:
            source, output = Path(directory) / "source", Path(directory) / "result.json"
            body.seek(0)
            total = 0
            with source.open("wb") as target:
                while chunk := body.read(64 * 1024):
                    total += len(chunk)
                    if total > MAX_FILE_BYTES:
                        raise DocumentExtractionError("document_limit")
                    target.write(chunk)
            try:
                result = subprocess.run(
                    [sys.executable, "-m", __name__, str(source), extension, str(output)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=60,
                    env={"LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"},
                )
                if result.returncode != 0 or not output.exists():
                    raise DocumentExtractionError("document_limit")
                with output.open("rb") as document:
                    data = document.read(MAX_TEXT_BYTES * 3 + 1)
                if len(data) > MAX_TEXT_BYTES * 3:
                    raise DocumentExtractionError("document_limit")
                payload = json.loads(data)
                if payload["error"] is not None:
                    raise DocumentExtractionError(payload["error"])
                text = bounded_text([payload["text"]])
                locations = tuple(TextLocation(**item) for item in payload.get("locations", []))
                if any(not 0 <= item.start < item.end <= len(text) for item in locations):
                    raise DocumentExtractionError()
                return ExtractedText(text, locations)
            except subprocess.TimeoutExpired:
                raise DocumentExtractionError("document_limit") from None


def child(source: str, extension: str, output: str) -> None:
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (40, 40))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_TEXT_BYTES * 3, MAX_TEXT_BYTES * 3))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    logging.disable(logging.CRITICAL)
    try:
        document, error = extract_text(Path(source), extension), None
    except DocumentExtractionError as failure:
        document, error = ExtractedText(""), failure.code
    except MemoryError:
        document, error = ExtractedText(""), "document_limit"
    except Exception:
        document, error = ExtractedText(""), "invalid_document"
    Path(output).write_text(
        json.dumps(
            {
                "text": document.text,
                "locations": [asdict(item) for item in document.locations],
                "error": error,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    child(*sys.argv[1:])

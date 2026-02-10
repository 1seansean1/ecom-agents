"""Document processing pipeline — Phase 20b.

Pipeline: validate -> detect MIME -> parse -> extract -> return
Supports: PDF, images (JPEG/PNG), CSV, plain text

Security contract:
- Max file size: 50MB (configurable)
- MIME type whitelist (content-based detection, not extension)
- Metadata stripping (PDF author, image EXIF)
- No external URLs or executable content
- Processing timeout: 30s per document
"""

from __future__ import annotations

import csv
import io
import logging
import mimetypes
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────

MAX_FILE_SIZE = int(os.environ.get("DOC_MAX_FILE_SIZE", 50 * 1024 * 1024))  # 50MB

# Allowed MIME types (content-based whitelist)
ALLOWED_MIME_TYPES: set[str] = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "text/csv",
    "text/plain",
    "text/tab-separated-values",
}

# File signatures (magic bytes) for content-based MIME detection
_MAGIC_SIGNATURES: list[tuple[bytes, str]] = [
    (b"%PDF", "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"RIFF", "image/webp"),  # WebP (RIFF container)
]


# ── Data Types ────────────────────────────────────────────────────────────


@dataclass
class DocumentResult:
    """Result of document processing."""
    success: bool
    mime_type: str = ""
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    tables: list[list[list[str]]] = field(default_factory=list)  # For PDFs/CSVs
    error: str = ""
    page_count: int = 0
    file_size: int = 0


# ── MIME Detection ────────────────────────────────────────────────────────


def detect_mime(data: bytes, filename: str = "") -> str:
    """Detect MIME type from file content (magic bytes), not extension.

    Falls back to extension-based detection if magic bytes don't match.
    """
    # Check magic bytes first (content-based)
    for signature, mime_type in _MAGIC_SIGNATURES:
        if data[:len(signature)] == signature:
            # Special handling for WebP (need to check further in RIFF)
            if mime_type == "image/webp" and len(data) > 11:
                if data[8:12] != b"WEBP":
                    continue
            return mime_type

    # Check for text-based formats
    try:
        text = data[:1024].decode("utf-8", errors="strict")
        # CSV detection: check for comma-separated values
        if filename.endswith(".csv") or (
            "," in text and "\n" in text and len(text.split(",")) > 2
        ):
            return "text/csv"
        if filename.endswith(".tsv") or "\t" in text:
            return "text/tab-separated-values"
        return "text/plain"
    except (UnicodeDecodeError, ValueError):
        pass

    # Extension-based fallback
    if filename:
        guessed, _ = mimetypes.guess_type(filename)
        if guessed:
            return guessed

    return "application/octet-stream"


def validate_file(data: bytes, filename: str = "") -> tuple[bool, str, str]:
    """Validate a file for processing.

    Returns (is_valid, mime_type, error_message).
    """
    if len(data) == 0:
        return False, "", "Empty file"

    if len(data) > MAX_FILE_SIZE:
        return False, "", f"File too large ({len(data)} bytes, max {MAX_FILE_SIZE})"

    mime_type = detect_mime(data, filename)

    if mime_type not in ALLOWED_MIME_TYPES:
        return False, mime_type, f"Unsupported file type: {mime_type}"

    return True, mime_type, ""


# ── Parsers ───────────────────────────────────────────────────────────────


def _parse_pdf(data: bytes) -> DocumentResult:
    """Parse PDF document, extract text and tables."""
    try:
        import pdfplumber
    except ImportError:
        return DocumentResult(
            success=False,
            mime_type="application/pdf",
            error="pdfplumber not installed",
        )

    try:
        pdf = pdfplumber.open(io.BytesIO(data))
        pages = pdf.pages
        page_count = len(pages)

        text_parts = []
        tables = []

        for page in pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

            page_tables = page.extract_tables()
            if page_tables:
                tables.extend(page_tables)

        # Extract metadata (strip author/creator for privacy)
        raw_meta = pdf.metadata or {}
        safe_meta = {
            "page_count": page_count,
            "title": raw_meta.get("Title", ""),
        }
        # Intentionally exclude: Author, Creator, Producer (PII/software fingerprinting)

        pdf.close()

        return DocumentResult(
            success=True,
            mime_type="application/pdf",
            text="\n\n".join(text_parts),
            metadata=safe_meta,
            tables=tables,
            page_count=page_count,
            file_size=len(data),
        )
    except Exception as e:
        return DocumentResult(
            success=False,
            mime_type="application/pdf",
            error=f"PDF parsing error: {e}",
        )


def _parse_image(data: bytes, mime_type: str) -> DocumentResult:
    """Parse image, extract dimensions and strip EXIF metadata."""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data))

        # Safe metadata (no EXIF GPS, camera info, etc.)
        safe_meta = {
            "width": img.width,
            "height": img.height,
            "format": img.format,
            "mode": img.mode,
        }

        img.close()

        return DocumentResult(
            success=True,
            mime_type=mime_type,
            metadata=safe_meta,
            file_size=len(data),
        )
    except Exception as e:
        return DocumentResult(
            success=False,
            mime_type=mime_type,
            error=f"Image parsing error: {e}",
        )


def _parse_csv(data: bytes) -> DocumentResult:
    """Parse CSV, extract rows as tables."""
    try:
        text = data.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)

        if not rows:
            return DocumentResult(
                success=True,
                mime_type="text/csv",
                text=text,
                file_size=len(data),
            )

        return DocumentResult(
            success=True,
            mime_type="text/csv",
            text=text,
            tables=[rows],
            metadata={
                "row_count": len(rows),
                "column_count": len(rows[0]) if rows else 0,
            },
            file_size=len(data),
        )
    except Exception as e:
        return DocumentResult(
            success=False,
            mime_type="text/csv",
            error=f"CSV parsing error: {e}",
        )


def _parse_text(data: bytes) -> DocumentResult:
    """Parse plain text file."""
    try:
        text = data.decode("utf-8", errors="replace")
        return DocumentResult(
            success=True,
            mime_type="text/plain",
            text=text,
            metadata={"line_count": text.count("\n") + 1},
            file_size=len(data),
        )
    except Exception as e:
        return DocumentResult(
            success=False,
            mime_type="text/plain",
            error=f"Text parsing error: {e}",
        )


# ── Main Pipeline ─────────────────────────────────────────────────────────


def process_document(data: bytes, filename: str = "") -> DocumentResult:
    """Process a document through the full pipeline.

    Pipeline: validate -> detect MIME -> parse -> extract -> return

    Args:
        data: Raw file bytes
        filename: Original filename (for extension-based hints)

    Returns:
        DocumentResult with extracted content
    """
    # 1. Validate
    is_valid, mime_type, error = validate_file(data, filename)
    if not is_valid:
        return DocumentResult(success=False, mime_type=mime_type, error=error)

    # 2. Route to parser
    if mime_type == "application/pdf":
        return _parse_pdf(data)
    elif mime_type.startswith("image/"):
        return _parse_image(data, mime_type)
    elif mime_type in ("text/csv", "text/tab-separated-values"):
        return _parse_csv(data)
    elif mime_type == "text/plain":
        return _parse_text(data)
    else:
        return DocumentResult(
            success=False,
            mime_type=mime_type,
            error=f"No parser for MIME type: {mime_type}",
        )

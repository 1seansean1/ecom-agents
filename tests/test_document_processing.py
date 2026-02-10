"""Tests for document processing pipeline — Phase 20b.

Tests:
- MIME type detection (magic bytes, not extension)
- File validation (size limits, whitelist)
- PDF parsing and metadata stripping
- Image parsing and EXIF stripping
- CSV parsing
- Text parsing
- Security: rejects executables, oversized files
"""

from __future__ import annotations

import io
import struct

import pytest

from src.tools.document import (
    ALLOWED_MIME_TYPES,
    MAX_FILE_SIZE,
    DocumentResult,
    detect_mime,
    process_document,
    validate_file,
)


# ── MIME Detection ────────────────────────────────────────────────────────


class TestMimeDetection:
    """MIME detection uses magic bytes, not file extension."""

    def test_detects_pdf(self):
        data = b"%PDF-1.4 fake pdf content"
        assert detect_mime(data) == "application/pdf"

    def test_detects_jpeg(self):
        data = b"\xff\xd8\xff\xe0fake jpeg"
        assert detect_mime(data) == "image/jpeg"

    def test_detects_png(self):
        data = b"\x89PNG\r\n\x1a\nfake png"
        assert detect_mime(data) == "image/png"

    def test_detects_gif87(self):
        data = b"GIF87afake gif"
        assert detect_mime(data) == "image/gif"

    def test_detects_gif89(self):
        data = b"GIF89afake gif"
        assert detect_mime(data) == "image/gif"

    def test_detects_csv(self):
        data = b"name,age,city\nAlice,30,NYC\nBob,25,LA\n"
        assert detect_mime(data, "data.csv") == "text/csv"

    def test_detects_plain_text(self):
        data = b"Hello, this is just some plain text."
        assert detect_mime(data, "readme.txt") == "text/plain"

    def test_extension_doesnt_override_magic(self):
        """Even with .txt extension, PDF magic bytes win."""
        data = b"%PDF-1.4 this is really a PDF"
        assert detect_mime(data, "sneaky.txt") == "application/pdf"

    def test_binary_unknown(self):
        """Unknown binary data returns octet-stream."""
        data = bytes(range(256))
        assert detect_mime(data) == "application/octet-stream"


# ── File Validation ───────────────────────────────────────────────────────


class TestFileValidation:
    """File validation enforces size and type restrictions."""

    def test_empty_file_rejected(self):
        valid, _, error = validate_file(b"")
        assert not valid
        assert "Empty" in error

    def test_oversized_file_rejected(self):
        data = b"x" * (MAX_FILE_SIZE + 1)
        valid, _, error = validate_file(data)
        assert not valid
        assert "too large" in error

    def test_valid_pdf(self):
        data = b"%PDF-1.4 content"
        valid, mime, error = validate_file(data, "test.pdf")
        assert valid
        assert mime == "application/pdf"

    def test_valid_jpeg(self):
        data = b"\xff\xd8\xff\xe0content"
        valid, mime, error = validate_file(data, "photo.jpg")
        assert valid
        assert mime == "image/jpeg"

    def test_valid_csv(self):
        data = b"a,b,c\n1,2,3\n"
        valid, mime, error = validate_file(data, "data.csv")
        assert valid
        assert mime == "text/csv"

    def test_exe_rejected(self):
        """Executables are not in the whitelist."""
        # Binary data that fails UTF-8 decode (contains invalid continuation bytes)
        data = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff" + b"\x80\x81\x82" * 50
        valid, mime, error = validate_file(data, "malware.exe")
        assert not valid
        assert "Unsupported" in error

    def test_unknown_binary_rejected(self):
        data = bytes(range(256))
        valid, _, error = validate_file(data)
        assert not valid


# ── PDF Processing ────────────────────────────────────────────────────────


class TestPdfProcessing:
    """PDF parsing and metadata stripping."""

    def _make_minimal_pdf(self, text: str = "Hello World") -> bytes:
        """Create a minimal valid PDF for testing."""
        import pdfplumber
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        c.drawString(100, 700, text)
        c.setAuthor("Secret Author Name")  # Should be stripped
        c.setTitle("Test Document")
        c.save()
        return buf.getvalue()

    def test_extracts_text(self):
        try:
            pdf_data = self._make_minimal_pdf("Liberty Forge Invoice")
        except ImportError:
            pytest.skip("reportlab not installed")
        result = process_document(pdf_data, "invoice.pdf")
        assert result.success
        assert "Liberty Forge Invoice" in result.text

    def test_strips_author_metadata(self):
        try:
            pdf_data = self._make_minimal_pdf()
        except ImportError:
            pytest.skip("reportlab not installed")
        result = process_document(pdf_data, "test.pdf")
        assert result.success
        # Author should NOT be in metadata (privacy)
        assert "Author" not in result.metadata
        assert "Secret Author Name" not in str(result.metadata)
        # Title IS preserved (non-PII)
        assert "title" in result.metadata

    def test_page_count(self):
        try:
            pdf_data = self._make_minimal_pdf()
        except ImportError:
            pytest.skip("reportlab not installed")
        result = process_document(pdf_data, "test.pdf")
        assert result.page_count >= 1


# ── Image Processing ─────────────────────────────────────────────────────


class TestImageProcessing:
    """Image parsing and EXIF stripping."""

    def _make_test_image(self, width: int = 100, height: int = 50) -> bytes:
        """Create a minimal JPEG image."""
        from PIL import Image

        img = Image.new("RGB", (width, height), color="red")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return buf.getvalue()

    def test_extracts_dimensions(self):
        img_data = self._make_test_image(200, 150)
        result = process_document(img_data, "photo.jpg")
        assert result.success
        assert result.metadata["width"] == 200
        assert result.metadata["height"] == 150

    def test_format_detected(self):
        img_data = self._make_test_image()
        result = process_document(img_data, "photo.jpg")
        assert result.success
        assert result.metadata["format"] == "JPEG"

    def test_png_works(self):
        from PIL import Image

        img = Image.new("RGBA", (50, 50), color="blue")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_data = buf.getvalue()

        result = process_document(png_data, "icon.png")
        assert result.success
        assert result.metadata["format"] == "PNG"

    def test_no_exif_in_result(self):
        """EXIF data (GPS, camera model) should NOT appear in metadata."""
        img_data = self._make_test_image()
        result = process_document(img_data, "photo.jpg")
        assert result.success
        meta_keys = set(result.metadata.keys())
        # Only safe metadata fields
        assert meta_keys <= {"width", "height", "format", "mode"}


# ── CSV Processing ────────────────────────────────────────────────────────


class TestCsvProcessing:
    """CSV parsing and table extraction."""

    def test_parses_csv(self):
        data = b"name,age,city\nAlice,30,NYC\nBob,25,LA\n"
        result = process_document(data, "people.csv")
        assert result.success
        assert result.metadata["row_count"] == 3  # Including header
        assert result.metadata["column_count"] == 3

    def test_csv_as_table(self):
        data = b"product,price\nTee,29.99\nHoodie,49.99\n"
        result = process_document(data, "catalog.csv")
        assert result.success
        assert len(result.tables) == 1
        assert result.tables[0][0] == ["product", "price"]
        assert result.tables[0][1] == ["Tee", "29.99"]

    def test_empty_csv(self):
        data = b""
        result = process_document(data, "empty.csv")
        assert not result.success  # Empty file is rejected

    def test_single_column(self):
        data = b"items\nA\nB\nC\n"
        result = process_document(data, "items.csv")
        assert result.success


# ── Text Processing ───────────────────────────────────────────────────────


class TestTextProcessing:
    """Plain text parsing."""

    def test_parses_text(self):
        data = b"Hello\nWorld\nThird line\n"
        result = process_document(data, "notes.txt")
        assert result.success
        assert "Hello" in result.text
        assert result.metadata["line_count"] == 4  # 3 newlines + trailing

    def test_utf8_text(self):
        data = "Héllo Wörld café".encode("utf-8")
        result = process_document(data, "unicode.txt")
        assert result.success
        assert "café" in result.text


# ── Security ──────────────────────────────────────────────────────────────


class TestDocumentSecurity:
    """Security properties of document processing."""

    def test_rejects_executable(self):
        data = b"MZ\x90\x00" + b"\x00" * 100  # PE header
        result = process_document(data, "malware.exe")
        assert not result.success
        assert "Unsupported" in result.error

    def test_rejects_oversized(self):
        data = b"x" * (MAX_FILE_SIZE + 1)
        result = process_document(data, "huge.txt")
        assert not result.success
        assert "too large" in result.error

    def test_mime_whitelist_enforced(self):
        """Only whitelisted MIME types are processed."""
        assert "application/x-executable" not in ALLOWED_MIME_TYPES
        assert "application/javascript" not in ALLOWED_MIME_TYPES

    def test_pdf_no_author(self):
        """PDF metadata doesn't include author."""
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas
        except ImportError:
            pytest.skip("reportlab not installed")

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        c.setAuthor("John Doe")
        c.drawString(100, 700, "Test")
        c.save()

        result = process_document(buf.getvalue(), "test.pdf")
        assert result.success
        assert "John Doe" not in str(result.metadata)

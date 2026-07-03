"""Smoke tests for BookGenerator: valid PDF with the expected page count."""

from __future__ import annotations

import pytest

from src.books.generator import BookGenerator, BookSpec
from src.books.params import pick_book_params


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("books")
    params = pick_book_params({}, existing=[], seed=42)
    params["page_count"] = 12
    spec = BookSpec(
        title=params["display_title"],
        subtitle=params["subtitle"],
        year=2026,
        palette_name=params["art_palette"],
        params=params,
        output_dir=out_dir,
    )
    path = BookGenerator().generate(spec)
    return path, params


def test_pdf_written(generated):
    path, _ = generated
    assert path.exists()
    assert path.stat().st_size > 10_000
    assert path.suffix == ".pdf"


def test_page_count_and_geometry(generated):
    fitz = pytest.importorskip("fitz")
    path, params = generated
    doc = fitz.open(str(path))
    # cover + title + 12 story + moral + 4 coloring + end = 20
    assert doc.page_count == params["page_count"] + 8
    rect = doc[0].rect
    # 215.9 mm = 8.5 in = 612 pt (square)
    assert abs(rect.width - 612) < 1.5
    assert abs(rect.height - 612) < 1.5
    doc.close()


def test_pdf_has_text(generated):
    fitz = pytest.importorskip("fitz")
    path, _ = generated
    doc = fitz.open(str(path))
    all_text = "\n".join(page.get_text() for page in doc)
    assert "The Lesson of the Story" in all_text
    assert "Color me!" in all_text
    assert "The End" in all_text
    doc.close()


def test_generate_16_page_book(tmp_path):
    params = pick_book_params({}, existing=[], seed=7)
    params["page_count"] = 16
    spec = BookSpec(title="Test Sixteen", palette_name=params["art_palette"],
                    params=params, output_dir=tmp_path)
    path = BookGenerator().generate(spec)
    fitz = pytest.importorskip("fitz")
    doc = fitz.open(str(path))
    assert doc.page_count == 24
    doc.close()


def test_defaults_only_spec(tmp_path):
    """Generator must not crash with a bare spec (orchestrator safety)."""
    spec = BookSpec(title="Bare Minimum Book", output_dir=tmp_path)
    path = BookGenerator().generate(spec)
    assert path.exists()

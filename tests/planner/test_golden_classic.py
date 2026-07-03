"""Golden regression: the default (classic) planner must match the
pre-refactor baseline exactly -- per-page text, GOTO link rects + targets,
outline entries, and page count for two palettes.

The fixture ``golden_classic.json`` was generated from the code as it stood
before the design-parameter refactor.  If this test fails, the classic
rendering changed -- which violates backward compatibility.
"""

from __future__ import annotations

import json
from pathlib import Path

import fitz
import pytest

from src.planner.generator import PlannerGenerator, PlannerSpec

FIXTURE = Path(__file__).parent / "golden_classic.json"


def _snapshot(path: Path) -> dict:
    doc = fitz.open(str(path))
    pages = []
    for page in doc:
        text_lines = sorted(
            ln.strip() for ln in page.get_text().splitlines() if ln.strip()
        )
        links = sorted(
            [
                round(l["from"].x0, 1), round(l["from"].y0, 1),
                round(l["from"].x1, 1), round(l["from"].y1, 1),
                l["page"],
            ]
            for l in page.get_links()
            if l["kind"] == fitz.LINK_GOTO
        )
        pages.append({"text": text_lines, "links": links,
                      "rect": [page.rect.width, page.rect.height]})
    toc = [[lvl, title, pno] for lvl, title, pno in doc.get_toc()]
    out = {"page_count": len(doc), "toc": toc, "pages": pages}
    doc.close()
    return out


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(FIXTURE.read_text())


@pytest.mark.parametrize("palette", ["neutral_beige", "ocean_blue"])
def test_classic_matches_golden(tmp_path_factory, golden, palette):
    import src.planner.generator as gen_mod

    out_dir = tmp_path_factory.mktemp(f"golden_{palette}")
    original = gen_mod.OUTPUT_DIR
    gen_mod.OUTPUT_DIR = out_dir
    try:
        path = PlannerGenerator().generate(PlannerSpec(palette_name=palette))
    finally:
        gen_mod.OUTPUT_DIR = original

    # Default spec must keep the pre-design filename (no theme suffix)
    assert path.name == f"2026_planner_{palette}.pdf"

    now = _snapshot(path)
    want = golden[palette]

    assert now["page_count"] == want["page_count"]
    assert now["toc"] == want["toc"]
    for idx, (got, exp) in enumerate(zip(now["pages"], want["pages"])):
        assert got["rect"] == exp["rect"], f"page {idx} size changed"
        assert got["text"] == exp["text"], f"page {idx} text changed"
        assert got["links"] == exp["links"], f"page {idx} links changed"

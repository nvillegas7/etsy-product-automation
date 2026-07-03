"""Bundle several product files into a single ZIP for digital delivery.

Etsy digital downloads deliver identical files regardless of any variation a
buyer picks, so a multi-palette planner ships as one ZIP containing every
color. This is a small, dependency-free helper used by the pipeline.
"""

from __future__ import annotations

import zipfile
from pathlib import Path


def bundle_files(
    paths: list[str | Path],
    out_zip: str | Path,
    arcnames: list[str] | None = None,
) -> Path:
    """Zip ``paths`` into ``out_zip`` and return the zip path.

    Parameters
    ----------
    paths:
        Files to include. Must be non-empty; every path must exist.
    out_zip:
        Destination ``.zip`` path. Parent directories are created.
    arcnames:
        Optional in-zip names, one per path (e.g.
        ``'2026_Budget_Planner_ocean_blue.pdf'``). When omitted, each file's
        basename is used. Absolute arcnames are reduced to their basename so
        the archive never leaks filesystem paths.
    """
    input_paths = [Path(p) for p in paths]
    if not input_paths:
        raise ValueError("bundle_files requires at least one input path")
    if arcnames is not None and len(arcnames) != len(input_paths):
        raise ValueError(
            f"arcnames length ({len(arcnames)}) must match paths length "
            f"({len(input_paths)})"
        )

    missing = [str(p) for p in input_paths if not p.exists()]
    if missing:
        raise FileNotFoundError(f"cannot bundle missing files: {missing}")

    out_zip = Path(out_zip)
    out_zip.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for idx, path in enumerate(input_paths):
            raw = arcnames[idx] if arcnames is not None else path.name
            arcname = _safe_arcname(raw)
            zf.write(path, arcname=arcname)
    return out_zip


def _safe_arcname(name: str | Path) -> str:
    """Return an archive-safe name that never embeds an absolute path."""
    candidate = Path(name)
    if candidate.is_absolute() or candidate.drive or candidate.anchor:
        return candidate.name
    # Strip any leading separators / parent traversal while keeping a clean name.
    return candidate.name if not candidate.parts else str(candidate).lstrip("/\\")

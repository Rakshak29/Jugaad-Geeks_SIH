"""
Write a transfer package to disk in the requested formats.

Markdown is always written -- it is the canonical form. PDF and DOCX are
rendered from that same Markdown and are skipped, with a recorded reason, if
their optional library is missing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from backend.rag import config as cfg
from backend.rag.packaging.build import TransferPackage
from backend.rag.packaging.markdown import render_markdown
from backend.rag.packaging.render import RendererUnavailable, render_docx, render_pdf

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")

ALL_FORMATS = ("md", "pdf", "docx")


@dataclass
class ExportResult:
    slug: str
    files: dict[str, str] = field(default_factory=dict)   # format -> path
    skipped: dict[str, str] = field(default_factory=dict)  # format -> reason

    def as_dict(self) -> dict:
        return {"slug": self.slug, "files": self.files, "skipped": self.skipped}


def package_slug(package: TransferPackage) -> str:
    """Stable, filesystem-safe name for one generated package."""
    who = "-".join(package.absent_employee_ids) or "unknown"
    stamp = package.generated_at.strftime("%Y%m%d-%H%M%S")
    return _UNSAFE.sub("_", "transfer-package-%s-%s" % (who, stamp))


def write_package(
    package: TransferPackage,
    formats: list[str] | None = None,
    output_dir: Path | None = None,
) -> ExportResult:
    """Render and write the package. Markdown is always produced."""
    requested = [f.lower() for f in (formats or list(ALL_FORMATS))]
    unknown = [f for f in requested if f not in ALL_FORMATS]
    if unknown:
        raise ValueError(
            "Unsupported format(s): %s. Supported: %s"
            % (", ".join(unknown), ", ".join(ALL_FORMATS))
        )

    output_dir = output_dir or cfg.OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    slug = package_slug(package)
    markdown = render_markdown(package)
    result = ExportResult(slug=slug)

    md_path = output_dir / ("%s.md" % slug)
    md_path.write_text(markdown, encoding="utf-8")
    result.files["md"] = str(md_path)

    if "pdf" in requested:
        try:
            path = render_pdf(markdown, output_dir / ("%s.pdf" % slug))
            result.files["pdf"] = str(path)
        except RendererUnavailable as exc:
            result.skipped["pdf"] = str(exc)

    if "docx" in requested:
        try:
            path = render_docx(markdown, output_dir / ("%s.docx" % slug))
            result.files["docx"] = str(path)
        except RendererUnavailable as exc:
            result.skipped["docx"] = str(exc)

    return result

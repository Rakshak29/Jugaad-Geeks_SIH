# tests/test_rag_package.py
"""Transfer package assembly, Markdown rendering, and file export."""

import pytest

from backend.rag.confluence.sync import run_sync
from backend.rag.packaging.build import build_transfer_package
from backend.rag.packaging.export import package_slug, write_package
from backend.rag.packaging.markdown import render_markdown
from backend.rag.packaging.render import available_formats, parse_blocks, strip_inline
from tests.test_rag_retrieval import FakeConfluenceClient


@pytest.fixture
def package(rag_session):
    run_sync(rag_session, client=FakeConfluenceClient())
    return build_transfer_package(rag_session, ["E003"])


# --- assembly ---------------------------------------------------------------


def test_package_contains_only_low_and_none_capabilities(package):
    assert {g.coverage.capability_id for g in package.gaps} == {"C003", "C005"}
    assert {c.capability_id for c in package.maintained} == {"C001"}


def test_gaps_are_ordered_worst_first(package):
    """NONE outranks LOW -- the reader should hit the worst problem first."""
    assert [g.coverage.band_after for g in package.gaps] == ["NONE", "LOW"]


def test_documented_and_undocumented_gaps_are_distinguished(package):
    c003 = next(g for g in package.gaps if g.coverage.capability_id == "C003")
    c005 = next(g for g in package.gaps if g.coverage.capability_id == "C005")

    assert c003.documented
    # Nothing in the fixture wiki covers deployment, so this gap has no docs.
    assert not c005.documented
    assert c005 in package.undocumented_gaps


def test_package_works_with_an_empty_knowledge_index(rag_session):
    """A missing Confluence sync must not block the coverage analysis."""
    package = build_transfer_package(rag_session, ["E003"])
    assert package.index_empty
    assert len(package.gaps) == 2
    assert len(package.undocumented_gaps) == 2


# --- markdown ---------------------------------------------------------------


def test_markdown_has_summary_and_a_section_per_gap(package):
    md = render_markdown(package)
    assert "# Knowledge Transfer Package" in md
    # The document leads with the gap and its documentation. An "Executive
    # Summary" heading over a block of score tables pushed the actual
    # documentation below the fold, so it was removed.
    assert "fall to LOW or NONE without" in md
    assert "## Database Recovery" in md
    assert "## Deployment & Rollback" in md


def test_markdown_links_back_to_confluence(package):
    md = render_markdown(package)
    # webui paths are relative to the wiki root, so the /wiki segment must be
    # present -- without it every link in the package 404s.
    assert "https://acme.atlassian.net/wiki/spaces/DBOPS/pages/5001/PITR" in md
    assert "[Open in Confluence]" in md


def test_markdown_states_why_each_document_was_included(package):
    md = render_markdown(package)
    assert "Matched by Confluence label" in md
    assert "Matched by keyword match" in md


def test_markdown_quotes_copied_material(package):
    """Copied text is blockquoted so it is visibly the org's words, not ours."""
    md = render_markdown(package)
    assert "> Stop the server and replay the WAL archive" in md


def test_markdown_flags_gaps_with_no_documentation(package):
    md = render_markdown(package)
    assert "No Confluence documentation matched this capability" in md


def test_markdown_records_that_no_model_wrote_it(package):
    md = render_markdown(package)
    assert "No content in this document was generated or paraphrased by a language model." in md


def test_markdown_reports_a_clean_bill_of_health(rag_session):
    package = build_transfer_package(rag_session, ["E001"])
    md = render_markdown(package)
    assert "No knowledge transfer is required." in md


# --- export -----------------------------------------------------------------


def test_slug_is_stable_and_filesystem_safe(package):
    slug = package_slug(package)
    assert slug == package_slug(package)
    assert "E003" in slug
    assert not set(slug) & set('/\\:*?"<>|')


def test_markdown_is_always_written(package, tmp_path):
    result = write_package(package, formats=["md"], output_dir=tmp_path)
    path = tmp_path / (result.slug + ".md")
    assert path.exists()
    assert "Knowledge Transfer Package" in path.read_text(encoding="utf-8")


def test_all_requested_formats_are_produced_or_explained(package, tmp_path):
    result = write_package(package, formats=["md", "pdf", "docx"], output_dir=tmp_path)
    installed = available_formats()

    for fmt in ("md", "pdf", "docx"):
        if installed[fmt]:
            assert fmt in result.files, "%s renderer is installed but produced nothing" % fmt
            assert (tmp_path / (result.slug + "." + fmt)).stat().st_size > 0
        else:
            # A missing optional library must say so, not fail silently.
            assert fmt in result.skipped
            assert "pip install" in result.skipped[fmt]


def test_unsupported_format_is_rejected(package, tmp_path):
    with pytest.raises(ValueError, match="Unsupported format"):
        write_package(package, formats=["rtf"], output_dir=tmp_path)


# --- markdown -> renderer parsing -------------------------------------------


def test_block_parser_handles_the_markdown_we_emit(package):
    blocks = parse_blocks(render_markdown(package))
    kinds = {b.kind for b in blocks}
    assert {"heading", "para", "table", "quote"} <= kinds

    tables = [b for b in blocks if b.kind == "table"]
    assert all(len(row) == len(t.rows[0]) for t in tables for row in t.rows)


def test_inline_markup_is_stripped_for_plain_text_targets():
    assert strip_inline("**bold** and *italic*") == "bold and italic"
    assert strip_inline("[Runbook](https://example.com/x)") == "Runbook"
    assert strip_inline("`pg_ctl stop`") == "pg_ctl stop"

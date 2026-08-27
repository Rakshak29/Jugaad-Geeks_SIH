"""
Transfer package -> Markdown.

Markdown is the canonical output; PDF and DOCX are rendered from this, so all
three formats always agree.

Everything written here is either a number the engine computed or text copied
from Confluence. Quoted material keeps its page title and URL beside it.
"""

from __future__ import annotations

from backend.rag.packaging.build import GapEntry, TransferPackage
from backend.rag.retrieval.retrieve import SECTIONS, WHOLE

_BAND_MARK = {"NONE": "NONE", "LOW": "LOW", "MODERATE": "MODERATE", "HIGH": "HIGH"}

_MATCH_LABEL = {
    "label": "Confluence label",
    "ancestor": "parent page",
    "space": "space",
    "keyword": "keyword match",
}


def render_markdown(package: TransferPackage) -> str:
    out: list[str] = []
    _header(out, package)
    _summary(out, package)
    _gap_table(out, package)

    for entry in package.gaps:
        _gap_section(out, entry)

    _maintained(out, package)
    _provenance(out, package)

    return "\n".join(out).rstrip() + "\n"


# ---------------------------------------------------------------------------


def _header(out: list[str], package: TransferPackage) -> None:
    names = ", ".join(package.absent_employee_names) or ", ".join(package.absent_employee_ids)
    out.append("# Knowledge Transfer Package")
    out.append("")
    out.append("**Absence simulated:** %s" % names)
    out.append("")
    out.append("**Generated:** %s" % package.generated_at.strftime("%Y-%m-%d %H:%M UTC"))
    out.append("")
    out.append("---")
    out.append("")


def _summary(out: list[str], package: TransferPackage) -> None:
    if not package.gaps:
        out.append(
            "All %d capabilities keep MODERATE or better coverage after this absence. "
            "No knowledge transfer is required." % package.total_capabilities
        )
        out.append("")
        return

    names = ", ".join(package.absent_employee_names) or "this engineer"
    out.append(
        "%d of %d capabilities fall to LOW or NONE without %s. The documentation for "
        "each one follows."
        % (len(package.gaps), package.total_capabilities, names)
    )
    out.append("")

    if package.index_empty:
        out.append(
            "> **No Confluence content has been synced**, so no documentation could be "
            "attached. Connect Confluence in the Setup tab and regenerate."
        )
        out.append("")
    elif package.undocumented_gaps:
        missing = ", ".join(g.coverage.capability_name for g in package.undocumented_gaps)
        out.append(
            "> **No documentation exists for: %s.** These carry the highest risk — "
            "there is neither a person nor a document to hand over." % missing
        )
        out.append("")


def _gap_table(out: list[str], package: TransferPackage) -> None:
    if not package.gaps:
        return
    out.append("### Capabilities Requiring Transfer")
    out.append("")
    out.append("| Capability | Before | After | Score | Documents |")
    out.append("|---|---|---|---|---|")
    for entry in package.gaps:
        coverage = entry.coverage
        out.append(
            "| %s (%s) | %s | **%s** | %.2f | %d |"
            % (
                coverage.capability_name,
                coverage.capability_id,
                _BAND_MARK.get(coverage.band_before, coverage.band_before),
                _BAND_MARK.get(coverage.band_after, coverage.band_after),
                coverage.score_after,
                len(entry.retrieval.documents),
            )
        )
    out.append("")
    out.append("---")
    out.append("")


def _gap_section(out: list[str], entry: GapEntry) -> None:
    """
    One capability, then its documentation.

    Deliberately short. An earlier version listed every remaining engineer's
    score, the evidence counts by source, and the module mapping -- and the
    result was a handover document that was mostly audit trail with a sentence
    of documentation buried in it. The person picking this work up needs the
    runbook; the scoring detail is available in the dashboard and the API.
    """
    coverage = entry.coverage

    out.append("## %s" % coverage.capability_name)
    out.append("")
    out.append(
        "**%s** — coverage fell from %s (%.2f) to %s (%.2f).%s"
        % (
            coverage.band_after,
            coverage.band_before,
            coverage.score_before,
            coverage.band_after,
            coverage.score_after,
            (" Strongest remaining: %s." % coverage.remaining[0].employee_name)
            if coverage.remaining else " No remaining coverage.",
        )
    )
    out.append("")
    if coverage.description:
        out.append("_%s_" % coverage.description)
        out.append("")

    _documents(out, entry)
    out.append("---")
    out.append("")


def _documents(out: list[str], entry: GapEntry) -> None:
    retrieval = entry.retrieval

    if not retrieval.documents:
        out.append("### Supporting Documentation")
        out.append("")
        out.append(
            "_No Confluence documentation matched this capability._ Searched for: %s."
            % ", ".join(retrieval.query_terms[:12])
        )
        out.append("")
        return

    out.append("### Supporting Documentation")
    out.append("")

    for i, doc in enumerate(retrieval.documents, start=1):
        out.append("#### %d. [%s](%s)" % (i, doc.title, doc.url))
        out.append("")

        why = _MATCH_LABEL.get(doc.match_type, doc.match_type)
        detail = "; ".join(doc.match_evidence) if doc.match_evidence else ""
        out.append("*Matched by %s%s*" % (why, (" — " + detail) if detail else ""))
        out.append("")
        out.append("*Space: %s%s*" % (doc.space_key, (" · Labels: " + ", ".join(doc.labels)) if doc.labels else ""))
        out.append("")

        if doc.inclusion == WHOLE:
            out.append("<!-- full document included: page is tagged to this capability -->")
            out.append("")
            for section in doc.sections:
                if section.heading:
                    out.append("##### %s" % section.heading)
                    out.append("")
                if section.text:
                    out.append(_quote(section.text))
                    out.append("")
            if not doc.sections and doc.body_text:
                out.append(_quote(doc.body_text))
                out.append("")
        elif doc.inclusion == SECTIONS:
            out.append("<!-- full page included; the matching sections are flagged below -->")
            out.append("")
            for section in doc.sections:
                if section.heading:
                    out.append("##### %s" % section.heading)
                    out.append("")
                if section.matched_terms:
                    out.append("*Matched: %s*" % ", ".join(sorted(section.matched_terms)[:8]))
                    out.append("")
                if section.text:
                    out.append(_quote(section.text))
                    out.append("")

        out.append("[Open in Confluence](%s)" % doc.url)
        out.append("")


def _maintained(out: list[str], package: TransferPackage) -> None:
    """
    Deliberately empty.

    Capabilities that are still covered need no handover, and listing them
    pushed the actual documentation further down the page. The dashboard shows
    full coverage for every capability.
    """
    return


def _provenance(out: list[str], package: TransferPackage) -> None:
    # Each gap section already ends with a rule; adding another here left two
    # back to back once the "not affected" table was removed.
    while out and out[-1] in ("", "---"):
        out.pop()
    out.append("")
    out.append("---")
    out.append("")
    out.append("## How This Package Was Produced")
    out.append("")
    out.append(
        "Coverage figures come from the evidence-scoring engine (evidence mass with "
        "2-year recency half-life, noisy-OR aggregation). Capabilities scoring LOW or "
        "NONE after the simulated absence are treated as documentation requirements."
    )
    out.append("")
    out.append(
        "Documentation was retrieved from %d Confluence page(s) / %d section(s) by exact "
        "metadata match (label, parent page, or space) and by keyword search using "
        "terminology drawn from each capability's own historical evidence."
        % (package.index_page_count, package.index_section_count)
    )
    out.append("")
    out.append(
        "All quoted material is copied verbatim from the linked Confluence pages. "
        "No content in this document was generated or paraphrased by a language model."
    )
    out.append("")


def _quote(text: str) -> str:
    """Blockquote copied material so it is visibly not our own words."""
    lines = text.split("\n")
    return "\n".join("> " + line if line.strip() else ">" for line in lines)

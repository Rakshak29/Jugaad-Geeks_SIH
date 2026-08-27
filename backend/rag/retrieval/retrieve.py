"""
Capability-based retrieval over the Confluence index.

Two tiers, in strict priority order:

  1. STRUCTURAL -- the page is linked to the capability by label, ancestor, or
     space (resolved at sync time, stored in confluence_page_capabilities).
     This is an exact lookup, not a score. Such a page is *about* the
     capability, so the whole document is included.

  2. KEYWORD -- BM25 over sections, queried with the capability's mined
     vocabulary. Finds the runbook that never says "Database Recovery" but
     does say "restore from WAL archive". Only the matching sections are
     included, since the rest of the page may be unrelated.

How many keyword results survive is decided by the data, not by a configured
threshold: an absolute quality bar derived from the query (cutoff.mass_floor)
followed by a natural-break cut through the result set (cutoff.natural_break_cut).
A capability with no relevant documentation returns nothing rather than the
least-bad thing available -- see cutoff.py.

Nothing is inferred by a model. Every result carries the reason it is there:
a label, a parent page, a space, or the specific terms that matched.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.rag.compat import tokenize as _tokenize
from backend.models.core import Capability
from backend.rag import config as cfg
from backend.rag.models import ConfluencePage, ConfluencePageCapability, ConfluenceSection
from backend.rag.retrieval.bm25 import BM25Index, ScoredDoc
from backend.rag.retrieval.cutoff import mass_floor, natural_break_cut
from backend.rag.retrieval.vocabulary import CapabilityVocabulary, build_vocabularies

# Structural signals, strongest first.
_STRUCTURAL_RANK = {"label": 3, "ancestor": 2, "space": 1}

# How many scored sections to hand to the cutoff logic. Not a quality
# threshold -- both cutoffs are derived from the data -- just a bound on how
# much of a large corpus's tail gets carried around. Anything this far down
# is already far below the natural break.
_KEYWORD_CANDIDATE_LIMIT = 500

WHOLE = "whole_document"
SECTIONS = "extracted_sections"


@dataclass
class RetrievedSection:
    section_id: str
    heading: str | None
    level: int
    text: str
    score: float = 0.0   # relative to the best section for this capability
    mass: float = 0.0    # absolute: share of query IDF mass matched
    matched_terms: list[str] = field(default_factory=list)


@dataclass
class RetrievedDocument:
    page_id: str
    title: str
    url: str
    space_key: str
    space_name: str | None
    labels: list[str]

    inclusion: str                # WHOLE | SECTIONS
    match_type: str               # label | ancestor | space | keyword
    match_evidence: list[str]     # why this page is here
    score: float

    body_text: str = ""                              # populated when WHOLE
    sections: list[RetrievedSection] = field(default_factory=list)  # when SECTIONS

    def as_dict(self) -> dict:
        return {
            "page_id": self.page_id,
            "title": self.title,
            "url": self.url,
            "space_key": self.space_key,
            "labels": self.labels,
            "inclusion": self.inclusion,
            "match_type": self.match_type,
            "match_evidence": self.match_evidence,
            "score": round(self.score, 4),
            "section_count": len(self.sections),
        }


@dataclass
class CapabilityRetrieval:
    capability_id: str
    capability_name: str
    query_terms: list[str]
    evidence_terms: list[str]
    documents: list[RetrievedDocument] = field(default_factory=list)

    @property
    def has_results(self) -> bool:
        return bool(self.documents)


class KnowledgeIndex:
    """
    The searchable view over synced Confluence content.

    Built once and queried per capability -- the section corpus is loaded and
    tokenized a single time no matter how many gaps are being documented.
    """

    def __init__(self, db_session):
        self.db = db_session
        self.vocabularies: dict[str, CapabilityVocabulary] = build_vocabularies(db_session)

        self.pages: dict[str, ConfluencePage] = {
            page.id: page for page in db_session.query(ConfluencePage).all()
        }
        self.sections: dict[str, ConfluenceSection] = {}
        corpus: dict[str, list[str]] = {}

        for section in db_session.query(ConfluenceSection).all():
            self.sections[section.id] = section
            page = self.pages.get(section.page_id)
            # Index the page title and section heading alongside the body so a
            # well-titled page is findable even when its prose is terse.
            text = " ".join(
                filter(
                    None,
                    [
                        page.title if page else "",
                        " ".join(page.labels or []) if page else "",
                        section.heading or "",
                        section.text or "",
                    ],
                )
            )
            corpus[section.id] = list(_tokenize(text))

        self.bm25 = BM25Index(corpus)

        self.structural: dict[str, list[ConfluencePageCapability]] = {}
        for link in db_session.query(ConfluencePageCapability).all():
            self.structural.setdefault(link.capability_id, []).append(link)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def section_count(self) -> int:
        return len(self.sections)

    def is_empty(self) -> bool:
        return not self.pages

    # -- retrieval ----------------------------------------------------------

    def retrieve_for_capability(self, capability_id: str) -> CapabilityRetrieval:
        """All relevant documentation for one capability, ranked and de-duplicated."""
        vocabulary = self.vocabularies.get(capability_id)
        if vocabulary is None:
            capability = self.db.get(Capability, capability_id)
            vocabulary = CapabilityVocabulary(
                capability_id=capability_id,
                capability_name=capability.name if capability else capability_id,
            )

        documents: dict[str, RetrievedDocument] = {}

        # -- tier 1: structural -------------------------------------------
        for link in self._best_structural_links(capability_id):
            page = self.pages.get(link.page_id)
            if not page:
                continue
            documents[page.id] = RetrievedDocument(
                page_id=page.id,
                title=page.title,
                url=page.url,
                space_key=page.space_key,
                space_name=page.space_name,
                labels=list(page.labels or []),
                inclusion=WHOLE,
                match_type=link.match_type,
                match_evidence=list(link.evidence or []),
                score=link.confidence,
                body_text=page.body_text or "",
                sections=[
                    RetrievedSection(
                        section_id=s.id,
                        heading=s.heading,
                        level=s.level,
                        text=s.text,
                    )
                    for s in sorted(page.sections, key=lambda s: s.ordinal)
                ],
            )

        # -- tier 2: keyword ----------------------------------------------
        hits = self._keyword_hits(vocabulary)
        by_page: dict[str, list[RetrievedSection]] = {}

        for hit in hits:
            section = self.sections.get(hit.doc_id)
            if not section:
                continue
            # A page already included whole needs no section extraction.
            if section.page_id in documents:
                continue
            by_page.setdefault(section.page_id, []).append(
                RetrievedSection(
                    section_id=section.id,
                    heading=section.heading,
                    level=section.level,
                    text=section.text,
                    score=hit.score,
                    mass=hit.mass,
                    matched_terms=hit.matched_terms,
                )
            )

        for page_id, sections in by_page.items():
            page = self.pages.get(page_id)
            if not page:
                continue
            sections.sort(key=lambda s: s.score, reverse=True)
            matched_ids = {s.section_id for s in sections[: cfg.MAX_SECTIONS_PER_DOC]}

            # Ship the whole page, not just the sections that matched.
            #
            # Extracting only matched sections keeps the document tight, but it
            # produced handovers where the "documentation" was a single
            # sentence surrounded by score tables -- useless to the engineer
            # who has to pick the work up. A runbook is only actionable whole:
            # the prerequisites and verification steps rarely contain the
            # search terms, yet you cannot follow the procedure without them.
            #
            # The sections that matched are still flagged, so the reader can
            # see why the page was selected.
            kept = [
                RetrievedSection(
                    section_id=s.id,
                    heading=s.heading,
                    level=s.level,
                    text=s.text,
                    score=next((m.score for m in sections if m.section_id == s.id), 0.0),
                    mass=next((m.mass for m in sections if m.section_id == s.id), 0.0),
                    matched_terms=next(
                        (m.matched_terms for m in sections if m.section_id == s.id), []
                    ),
                )
                for s in sorted(page.sections, key=lambda s: s.ordinal)
            ]
            best = sections[0]  # strongest matching section drives the score
            terms = sorted({t for s in sections for t in s.matched_terms})
            documents[page_id] = RetrievedDocument(
                page_id=page.id,
                title=page.title,
                url=page.url,
                space_key=page.space_key,
                space_name=page.space_name,
                labels=list(page.labels or []),
                inclusion=SECTIONS,
                match_type="keyword",
                match_evidence=["matched terms: %s" % ", ".join(terms[:10])] if terms else [],
                score=best.score,
                sections=kept,   # already in page order
            )

        ranked = sorted(documents.values(), key=_rank_key)

        return CapabilityRetrieval(
            capability_id=capability_id,
            capability_name=vocabulary.capability_name,
            query_terms=vocabulary.query_terms()[:25],
            evidence_terms=vocabulary.evidence_terms[:15],
            documents=ranked[: cfg.MAX_DOCS_PER_GAP],
        )

    def _keyword_hits(self, vocabulary: CapabilityVocabulary) -> list[ScoredDoc]:
        """
        Keyword-matched sections, with both cutoffs applied.

        Order matters. The absolute bar runs first, so a capability whose
        documentation simply does not exist returns nothing at all. Only then
        does the relative cut decide where quality falls off among sections
        that already cleared the bar.
        """
        if not vocabulary.terms:
            return []

        hits = self.bm25.search(vocabulary.terms, top_k=_KEYWORD_CANDIDATE_LIMIT)
        if not hits:
            return []

        # 1. Absolute: is this section worth more than one ordinary query term?
        floor = mass_floor(self.bm25.term_mass(vocabulary.terms))
        qualified = [hit for hit in hits if hit.mass > floor]
        if not qualified:
            return []  # nothing here is documentation for this capability

        # 2. Relative: where does quality fall off among what survived?
        keep = natural_break_cut([hit.score for hit in qualified])
        return qualified[:keep]

    def _best_structural_links(self, capability_id: str) -> list[ConfluencePageCapability]:
        """One link per page -- its strongest signal -- ordered by that strength."""
        best: dict[str, ConfluencePageCapability] = {}
        for link in self.structural.get(capability_id, []):
            current = best.get(link.page_id)
            if current is None or _STRUCTURAL_RANK.get(link.match_type, 0) > _STRUCTURAL_RANK.get(
                current.match_type, 0
            ):
                best[link.page_id] = link
        return sorted(
            best.values(),
            key=lambda l: (-_STRUCTURAL_RANK.get(l.match_type, 0), -l.confidence, l.page_id),
        )


def _rank_key(doc: RetrievedDocument):
    """Structural matches outrank keyword matches; ties break on score, then title."""
    structural = _STRUCTURAL_RANK.get(doc.match_type, 0)
    return (-structural, -doc.score, doc.title.lower())

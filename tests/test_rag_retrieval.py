# tests/test_rag_retrieval.py
"""Confluence sync, vocabulary building, and capability-based retrieval."""

import pytest

from backend.rag.confluence.client import ConfluencePageData, ConfluenceSpace
from backend.rag.confluence.sync import run_sync
from backend.rag.models import ConfluencePage, ConfluencePageCapability, ConfluenceSection
from backend.rag.retrieval.bm25 import BM25Index
from backend.rag.retrieval.retrieve import SECTIONS, WHOLE, KnowledgeIndex

SPACES = [
    ConfluenceSpace(id="1", key="DBOPS", name="Database Operations",
                    description="Database reliability, recovery and data integrity runbooks."),
    ConfluenceSpace(id="2", key="GEN", name="General", description="Team notes."),
]

PAGES = [
    # Labelled: resolves structurally to C003.
    ConfluencePageData(
        id="5001", title="PostgreSQL PITR & Disaster Recovery Runbook",
        space_id="1", parent_id=None, version=3,
        webui_path="/spaces/DBOPS/pages/5001/PITR",
        labels=["database-recovery", "runbook"],
        body_storage="""
            <p>Restoring the primary cluster after corruption.</p>
            <h2>Point-In-Time Recovery</h2>
            <p>Stop the server and replay the WAL archive to a target LSN.</p>
            <h2>Verification</h2><p>Confirm replay advances before reopening traffic.</p>
        """,
    ),
    # Unlabelled, and never says "Database Recovery": only keyword search finds it.
    ConfluencePageData(
        id="5002", title="Standby Failover Drill", space_id="2",
        parent_id=None, version=1,
        webui_path="/spaces/GEN/pages/5002/Failover",
        labels=[],
        body_storage="""
            <h2>Quarterly drill</h2><p>Promote the warm standby.</p>
            <h2>Restoring from backup</h2>
            <p>If promotion fails, restore from the latest WAL archive and replay to the
            last known good LSN. Verify integrity and corruption checks before reopening.</p>
            <h2>Catering</h2><p>Order lunch for the drill team.</p>
        """,
    ),
    # Entirely unrelated: must never surface.
    ConfluencePageData(
        id="5003", title="Office Wifi Password", space_id="2",
        parent_id=None, version=1,
        webui_path="/spaces/GEN/pages/5003/Wifi",
        labels=[],
        body_storage="<p>Ask reception for the guest wifi password.</p>",
    ),
]


class FakeConfluenceClient:
    def __init__(self, pages=None, spaces=None):
        self.pages = pages if pages is not None else PAGES
        self.spaces = spaces if spaces is not None else SPACES

    def iter_spaces(self):
        return iter(self.spaces)

    def iter_pages(self, space_ids=None):
        return iter(self.pages)

    def close(self):
        pass


@pytest.fixture
def synced(rag_session):
    run_sync(rag_session, client=FakeConfluenceClient())
    return rag_session


# --- sync -------------------------------------------------------------------


def test_sync_stores_pages_and_sections(synced):
    assert synced.query(ConfluencePage).count() == 3
    assert synced.query(ConfluenceSection).count() > 0

    page = synced.get(ConfluencePage, "5001")
    assert page.space_key == "DBOPS"
    assert page.url.endswith("/spaces/DBOPS/pages/5001/PITR")
    assert "database-recovery" in page.labels


def test_sync_derives_structural_capability_links(synced):
    links = synced.query(ConfluencePageCapability).filter_by(page_id="5001").all()
    assert [l.capability_id for l in links] == ["C003"]
    assert links[0].match_type == "label"


def test_unchanged_pages_are_not_reparsed(rag_session):
    first = run_sync(rag_session, client=FakeConfluenceClient())
    assert first.pages_created == 3

    second = run_sync(rag_session, client=FakeConfluenceClient())
    assert second.pages_unchanged == 3
    assert second.pages_created == 0
    assert second.pages_updated == 0


def test_an_edit_is_reparsed_even_when_version_never_changes(rag_session):
    """
    The failure this guards against is silent.

    If a Confluence deployment omits `version` from the pages listing, every
    page reads as version 1. Gating re-parses on version alone would then mark
    every page unchanged forever, and edits would quietly stop being indexed
    with nothing in the logs. Change detection hashes the body instead.
    """
    run_sync(rag_session, client=FakeConfluenceClient())

    edited = ConfluencePageData(
        id="5001", title="PostgreSQL PITR & Disaster Recovery Runbook",
        space_id="1", parent_id=None,
        version=1,  # unchanged, as an API that omits the field would report
        webui_path="/spaces/DBOPS/pages/5001/PITR",
        labels=["database-recovery"],
        body_storage="<h2>Rewritten</h2><p>The procedure changed completely.</p>",
    )
    result = run_sync(rag_session, client=FakeConfluenceClient(pages=[edited]))

    assert result.pages_updated == 1
    assert result.pages_unchanged == 0
    assert "The procedure changed completely." in rag_session.get(ConfluencePage, "5001").body_text


def test_an_untouched_page_is_not_reparsed_even_if_version_moves(rag_session):
    """The mirror case: a version bump with identical content is not a change."""
    run_sync(rag_session, client=FakeConfluenceClient())

    original = PAGES[0]
    rebumped = ConfluencePageData(
        id=original.id, title=original.title, space_id=original.space_id,
        parent_id=None, version=original.version + 5,
        webui_path=original.webui_path, labels=original.labels,
        body_storage=original.body_storage,
    )
    result = run_sync(rag_session, client=FakeConfluenceClient(pages=[rebumped]))

    assert result.pages_unchanged == 1
    assert result.pages_updated == 0
    # The new version number is still recorded for provenance.
    assert rag_session.get(ConfluencePage, "5001").version == original.version + 5


def test_a_version_bump_triggers_a_reparse(rag_session):
    run_sync(rag_session, client=FakeConfluenceClient())

    bumped = ConfluencePageData(
        id="5001", title="PostgreSQL PITR Runbook (v4)", space_id="1",
        parent_id=None, version=4, webui_path="/spaces/DBOPS/pages/5001/PITR",
        labels=["database-recovery"],
        body_storage="<h2>New Procedure</h2><p>Rewritten recovery steps.</p>",
    )
    result = run_sync(rag_session, client=FakeConfluenceClient(pages=[bumped]))

    assert result.pages_updated == 1
    page = rag_session.get(ConfluencePage, "5001")
    assert page.title == "PostgreSQL PITR Runbook (v4)"
    assert "Rewritten recovery steps." in page.body_text
    # Stale sections from the previous version must be gone.
    assert all("Verification" != s.heading for s in page.sections)


def test_sync_reports_spaces_it_could_not_resolve(rag_session):
    result = run_sync(rag_session, client=FakeConfluenceClient())
    unresolved = {u["space_key"] for u in result.unresolved_spaces}
    assert "GEN" in unresolved
    assert "DBOPS" not in unresolved


# --- BM25 -------------------------------------------------------------------


def test_bm25_ranks_the_term_dense_document_first():
    index = BM25Index({
        "a": ["wal", "archive", "restore", "recovery"],
        "b": ["lunch", "menu", "catering"],
        "c": ["restore", "backup"],
    })
    hits = index.search({"wal": 2.0, "restore": 2.0, "recovery": 3.0})
    assert hits[0].doc_id == "a"
    assert hits[0].score == 1.0
    assert "lunch" not in [h.doc_id for h in hits]


def test_bm25_reports_which_terms_matched():
    index = BM25Index({"a": ["wal", "archive", "restore"]})
    hit = index.search({"wal": 1.0, "restore": 1.0, "unrelated": 1.0})[0]
    assert hit.matched_terms == ["restore", "wal"]
    assert hit.match_count == 2


def test_bm25_on_empty_corpus_or_query_returns_nothing():
    assert BM25Index({}).search({"wal": 1.0}) == []
    assert BM25Index({"a": ["wal"]}).search({}) == []


# --- vocabulary -------------------------------------------------------------


def test_vocabulary_includes_curated_domain_synonyms(synced):
    index = KnowledgeIndex(synced)
    terms = index.vocabularies["C003"].terms
    # From CAPABILITY_KEYWORD_OVERRIDES -- words the capability name never uses.
    assert "wal" in terms
    assert "pitr" in terms
    assert "recovery" in terms


# --- retrieval --------------------------------------------------------------


def test_tagged_page_is_returned_whole(synced):
    result = KnowledgeIndex(synced).retrieve_for_capability("C003")
    tagged = next(d for d in result.documents if d.page_id == "5001")

    assert tagged.inclusion == WHOLE
    assert tagged.match_type == "label"
    assert len(tagged.sections) == 3


def test_keyword_page_is_returned_whole_with_matches_flagged(synced):
    """
    The point of the second tier: find the runbook that uses different words.

    The whole page ships, not only the matched sections. Extracting just the
    matches produced handovers where the "documentation" was one sentence --
    a runbook is only actionable whole, since its prerequisites and
    verification steps rarely contain the search terms. Which sections matched
    is still recorded, so the reader can see why the page was chosen.
    """
    result = KnowledgeIndex(synced).retrieve_for_capability("C003")
    found = next(d for d in result.documents if d.page_id == "5002")

    assert found.inclusion == SECTIONS
    assert found.match_type == "keyword"

    headings = [s.heading for s in found.sections]
    assert "Restoring from backup" in headings
    # Sections that did not match still travel with the page.
    assert "Quarterly drill" in headings
    assert "Catering" in headings

    # Page order is preserved so the procedure reads top to bottom.
    assert headings == ["Quarterly drill", "Restoring from backup", "Catering"]

    matched = [s.heading for s in found.sections if s.matched_terms]
    assert "Restoring from backup" in matched
    assert "Catering" not in matched, "an unmatched section must not be flagged as matching"


def test_structural_matches_outrank_keyword_matches(synced):
    result = KnowledgeIndex(synced).retrieve_for_capability("C003")
    assert result.documents[0].page_id == "5001"


def test_irrelevant_pages_are_never_returned(synced):
    result = KnowledgeIndex(synced).retrieve_for_capability("C003")
    assert "5003" not in [d.page_id for d in result.documents]


def test_every_result_carries_its_reason(synced):
    result = KnowledgeIndex(synced).retrieve_for_capability("C003")
    for doc in result.documents:
        assert doc.match_evidence, "a retrieved document must state why it matched"


def test_a_page_is_never_both_whole_and_extracted(synced):
    result = KnowledgeIndex(synced).retrieve_for_capability("C003")
    page_ids = [d.page_id for d in result.documents]
    assert len(page_ids) == len(set(page_ids))


def test_capability_with_no_documentation_returns_empty(synced):
    result = KnowledgeIndex(synced).retrieve_for_capability("C001")
    assert result.documents == []


def test_empty_index_is_detectable(rag_session):
    index = KnowledgeIndex(rag_session)
    assert index.is_empty()
    assert index.retrieve_for_capability("C003").documents == []


# --- derived cutoffs, not configured thresholds -----------------------------


def test_capability_with_no_relevant_docs_returns_nothing_not_the_least_bad(rag_session):
    """
    The property the absolute quality bar exists for.

    A decoy page brushes C001's vocabulary with one incidental word and
    nothing else. It is the only candidate, so it scores 1.0 *relative* --
    the best of a worthless set. It must still be rejected, because the
    package saying "no documentation exists for this gap" is more useful than
    it offering the least-bad page in the wiki.
    """
    decoy = ConfluencePageData(
        id="7001", title="Cafeteria Services Schedule", space_id="2",
        parent_id=None, version=1, webui_path="/spaces/GEN/pages/7001/Cafeteria",
        labels=[],
        # "rate" is in C001's vocabulary via the API Gateway module's
        # "rate limiting" -- an incidental brush, and the only one.
        body_storage="<h2>Hours</h2><p>Lunch is served at a flat rate from noon.</p>",
    )
    run_sync(rag_session, client=FakeConfluenceClient(pages=PAGES + [decoy]))

    index = KnowledgeIndex(rag_session)

    raw_hits = index.bm25.search(index.vocabularies["C001"].terms, top_k=10)
    assert raw_hits, "the decoy should share at least one term, else the test proves nothing"
    assert raw_hits[0].score == 1.0, "the best of a bad set still scores 1.0 relative"

    assert index.retrieve_for_capability("C001").documents == []


def test_a_whole_run_of_good_sections_survives(synced):
    """A smooth score distribution must not be cut down to its single best."""
    index = KnowledgeIndex(synced)
    hits = index._keyword_hits(index.vocabularies["C003"])
    assert len(hits) > 1


def test_retrieval_is_unaffected_by_irrelevant_corpus_growth(synced, rag_session):
    """
    Adding unrelated pages must not change what a capability retrieves.

    A relative-only cutoff would drift as the corpus grew; the absolute bar is
    what keeps this stable.
    """
    before = [d.page_id for d in KnowledgeIndex(synced).retrieve_for_capability("C003").documents]

    filler = [
        ConfluencePageData(
            id="9%03d" % i, title="Team Offsite Notes %d" % i, space_id="2",
            parent_id=None, version=1, webui_path="/spaces/GEN/pages/9%03d/Notes" % i,
            labels=[],
            body_storage="<h2>Agenda</h2><p>Lunch, karaoke, and the quarterly photo.</p>",
        )
        for i in range(30)
    ]
    run_sync(rag_session, client=FakeConfluenceClient(pages=filler))

    after = [d.page_id for d in KnowledgeIndex(rag_session).retrieve_for_capability("C003").documents]
    assert after == before

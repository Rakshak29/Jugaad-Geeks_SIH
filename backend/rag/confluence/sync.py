"""
Confluence ingestion.

    Confluence API -> clean text + sections -> capability links -> database

Idempotent by page content: a page whose storage-format body hashes to the
same value as last sync is not re-parsed. Capability links are always
re-resolved, because they can change without the page changing (a new module,
a renamed space, a human resolving an ambiguous mapping).

Nothing here touches the evidence, scoring, or coverage tables.
"""

from __future__ import annotations

import logging
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.rag import config as cfg
from backend.rag.confluence.client import (
    ConfluenceClient,
    ConfluenceError,
    ConfluencePageData,
)
from backend.rag.confluence.storage_format import parse_storage_format, sections_to_text
from backend.rag.mapping import store as mapping_store
from backend.rag.mapping.derive import PageMapper, derive_space_service
from backend.rag.models import ConfluencePage, ConfluencePageCapability, ConfluenceSection

logger = logging.getLogger("rag.confluence.sync")


@dataclass
class SyncResult:
    spaces_seen: int = 0
    pages_fetched: int = 0
    pages_created: int = 0
    pages_updated: int = 0
    pages_unchanged: int = 0
    sections_written: int = 0
    capability_links: int = 0
    pages_without_capability: int = 0
    unresolved_spaces: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    # Totals in the index after the run. `sections_written` counts only what
    # this run re-parsed, which is 0 on a sync where nothing changed -- and
    # reporting that alone reads as "nothing is indexed" when in fact the
    # whole wiki is already there.
    indexed_pages: int = 0
    indexed_sections: int = 0

    def as_dict(self) -> dict:
        return {
            "spaces_seen": self.spaces_seen,
            "pages_fetched": self.pages_fetched,
            "pages_created": self.pages_created,
            "pages_updated": self.pages_updated,
            "pages_unchanged": self.pages_unchanged,
            "sections_written": self.sections_written,
            "capability_links": self.capability_links,
            "pages_without_capability": self.pages_without_capability,
            "indexed_pages": self.indexed_pages,
            "indexed_sections": self.indexed_sections,
            "unresolved_spaces": self.unresolved_spaces,
            "errors": self.errors,
        }


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def run_sync(db_session, client: ConfluenceClient | None = None, force: bool = False) -> SyncResult:
    """
    Full Confluence ingestion pass.

    `force=True` re-parses every page regardless of version -- use it after
    changing the storage-format parser, not routinely.
    """
    result = SyncResult()
    owns_client = client is None
    client = client or ConfluenceClient()

    try:
        space_index, matches = _sync_spaces(db_session, client, result)
        space_service = _persist_mapping(matches, result)

        mapper = PageMapper(db_session, space_service=space_service)
        target_space_ids = _target_space_ids(space_index)

        # page_id -> parent_id, built during the fetch and used afterwards to
        # walk each page's ancestor chain. Not stored on the model: it is only
        # meaningful within a single sync.
        parents: dict[str, str | None] = {}

        touched_page_ids: list[str] = []
        for page in client.iter_pages(space_ids=target_space_ids):
            result.pages_fetched += 1
            try:
                _upsert_page(db_session, page, space_index, result, parents, force=force)
                touched_page_ids.append(page.id)
            except Exception as exc:  # one bad page must not sink the sync
                logger.exception("failed to store page %s", page.id)
                result.errors.append("page %s: %s" % (page.id, exc))

        db_session.commit()

        _resolve_capabilities(db_session, mapper, touched_page_ids, parents, result)
        db_session.commit()

        result.indexed_pages = db_session.query(ConfluencePage).count()
        result.indexed_sections = db_session.query(ConfluenceSection).count()

    except ConfluenceError as exc:
        db_session.rollback()
        result.errors.append(str(exc))
        raise
    finally:
        if owns_client:
            client.close()

    return result


# ---------------------------------------------------------------------------
# spaces
# ---------------------------------------------------------------------------


def _sync_spaces(db_session, client: ConfluenceClient, result: SyncResult):
    """Fetch spaces and derive each one's service match."""
    space_index: dict[str, dict] = {}   # space_id -> {key, name, description}
    matches = []

    for space in client.iter_spaces():
        space_index[space.id] = {
            "key": space.key,
            "name": space.name,
            "description": space.description,
        }
        matches.append(
            derive_space_service(space.key, space.name, space.description, db_session)
        )

    result.spaces_seen = len(space_index)
    return space_index, matches


def _persist_mapping(matches, result: SyncResult) -> dict[str, str]:
    """Merge derived matches into the mapping file, preserving manual entries."""
    existing = mapping_store.load_mapping()
    merged = mapping_store.merge_space_matches(existing, matches)
    mapping_store.save_mapping(merged)
    result.unresolved_spaces = mapping_store.unresolved_spaces(merged)
    return mapping_store.resolved_space_service(merged)


def _target_space_ids(space_index: dict[str, dict]) -> list[str] | None:
    """Restrict the page pull to CONFLUENCE_SPACE_KEYS, if it is set."""
    if not cfg.CONFLUENCE_SPACE_KEYS:
        return None
    wanted = {k.upper() for k in cfg.CONFLUENCE_SPACE_KEYS}
    ids = [sid for sid, meta in space_index.items() if (meta["key"] or "").upper() in wanted]
    return ids or None


# ---------------------------------------------------------------------------
# pages
# ---------------------------------------------------------------------------


def _upsert_page(
    db_session,
    page: ConfluencePageData,
    space_index: dict[str, dict],
    result: SyncResult,
    parents: dict[str, str | None],
    force: bool = False,
) -> None:
    """Store one page and its sections, skipping the parse when unchanged."""
    space_meta = space_index.get(page.space_id, {})
    existing = db_session.get(ConfluencePage, page.id)
    parents[page.id] = page.parent_id

    content_hash = _content_hash(page.body_storage)

    if existing and existing.content_hash == content_hash and not force:
        # Labels and version are cheap to refresh and can move without the
        # body changing at all.
        existing.labels = page.labels
        existing.version = page.version
        existing.synced_at = datetime.now(timezone.utc)
        result.pages_unchanged += 1
        return

    sections = parse_storage_format(page.body_storage)
    body_text = sections_to_text(sections)

    if existing:
        target = existing
        result.pages_updated += 1
        # Sections are derived data -- replace wholesale rather than diffing.
        db_session.query(ConfluenceSection).filter(
            ConfluenceSection.page_id == page.id
        ).delete(synchronize_session=False)
    else:
        target = ConfluencePage(id=page.id)
        db_session.add(target)
        result.pages_created += 1

    target.space_key = space_meta.get("key") or page.space_id
    target.space_name = space_meta.get("name")
    target.title = page.title
    target.url = _page_url(page)
    target.version = page.version
    target.content_hash = content_hash
    target.labels = page.labels
    target.body_text = body_text
    target.created_at = _parse_iso(page.created_at)
    target.updated_at = datetime.now(timezone.utc)
    target.synced_at = datetime.now(timezone.utc)
    # Filled in by _resolve_capabilities, once every page title is known.
    target.ancestor_titles = list(target.ancestor_titles or [])

    for section in sections:
        db_session.add(
            ConfluenceSection(
                id="%s#%d" % (page.id, section.ordinal),
                page_id=page.id,
                ordinal=section.ordinal,
                heading=section.heading,
                level=section.level,
                text=section.text,
            )
        )
        result.sections_written += 1


def _content_hash(body: str) -> str:
    """Stable fingerprint of a page body, used to detect real changes."""
    return hashlib.sha256((body or "").encode("utf-8")).hexdigest()


def _page_url(page: ConfluencePageData) -> str:
    """
    Browser URL for a page.

    `_links.webui` is relative to the WIKI root ("/spaces/KEY/pages/..."), not
    the site root -- unlike `_links.next` on the paginated collections, which
    already carries the /wiki prefix. Joining webui to the site root drops the
    /wiki segment and every link in the transfer package 404s.
    """
    base = cfg.CONFLUENCE_BASE_URL.rstrip("/")
    if not page.webui_path:
        return base
    if page.webui_path.startswith("http"):
        return page.webui_path
    if not base.endswith("/wiki"):
        base = base + "/wiki"
    return base + page.webui_path


# ---------------------------------------------------------------------------
# capability resolution
# ---------------------------------------------------------------------------


def _resolve_capabilities(
    db_session,
    mapper: PageMapper,
    page_ids: list[str],
    parents: dict[str, str | None],
    result: SyncResult,
) -> None:
    """
    Recompute every touched page's capability links.

    Runs for unchanged pages too: the mapping can change without the page
    changing (a renamed space, a new module, a resolved ambiguity).
    """
    titles = {
        pid: title
        for pid, title in db_session.query(ConfluencePage.id, ConfluencePage.title).all()
    }

    for page_id in page_ids:
        page = db_session.get(ConfluencePage, page_id)
        if not page:
            continue

        ancestors = _ancestor_titles(page_id, titles, parents)
        page.ancestor_titles = ancestors

        links = mapper.resolve(
            labels=list(page.labels or []),
            ancestor_titles=ancestors,
            space_key=page.space_key or "",
        )

        db_session.query(ConfluencePageCapability).filter(
            ConfluencePageCapability.page_id == page_id
        ).delete(synchronize_session=False)

        if not links:
            result.pages_without_capability += 1

        for link in links:
            db_session.add(
                ConfluencePageCapability(
                    page_id=page_id,
                    capability_id=link.capability_id,
                    match_type=link.match_type,
                    evidence=link.evidence,
                    confidence=link.confidence,
                )
            )
            result.capability_links += 1


def _ancestor_titles(
    page_id: str,
    titles: dict[str, str],
    parents: dict[str, str | None],
    max_depth: int = 10,
) -> list[str]:
    """Walk parentId up to the space root, nearest ancestor first."""
    out: list[str] = []
    seen = {page_id}
    current = parents.get(page_id)
    depth = 0
    while current and depth < max_depth and current not in seen:
        seen.add(current)
        title = titles.get(current)
        if title:
            out.append(title)
        current = parents.get(current)
        depth += 1
    return out

"""
ORM models for the Confluence knowledge index.

Additive only -- these tables sit alongside the existing core/raw schema and
are never written to by the scoring engine. They share backend.database.Base
so a single `alembic upgrade head` / `init_db()` creates everything.
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.database import Base


class ConfluencePage(Base):
    """One Confluence page, as fetched from the API and flattened to text."""

    __tablename__ = "confluence_pages"

    # Confluence's own numeric page id, kept as a string.
    id = Column(String(50), primary_key=True)

    space_key = Column(String(100), nullable=False, index=True)
    space_name = Column(String(255), nullable=True)

    title = Column(String(500), nullable=False)
    url = Column(String(1000), nullable=False)

    # Confluence version.number, for display and provenance.
    version = Column(Integer, nullable=False, default=1)

    # SHA-256 of the raw storage-format body: the actual re-sync gate.
    #
    # Version alone is not safe to gate on. If a Confluence deployment omits
    # `version` from the pages listing, every page reads as version 1, and a
    # version-only check would then treat every page as unchanged forever --
    # edits would silently stop being indexed with nothing in the logs. The
    # body is fetched either way, so hashing it costs nothing and cannot be
    # fooled.
    content_hash = Column(String(64), nullable=True, index=True)

    labels = Column(JSON, nullable=False, default=list)      # ["database-recovery", ...]
    ancestor_titles = Column(JSON, nullable=False, default=list)

    # Flattened, macro-stripped plain text of the whole page.
    body_text = Column(Text, nullable=False, default="")

    created_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    synced_at = Column(DateTime(timezone=True), nullable=True)

    sections = relationship(
        "ConfluenceSection",
        back_populates="page",
        cascade="all, delete-orphan",
        order_by="ConfluenceSection.ordinal",
    )
    capability_links = relationship(
        "ConfluencePageCapability",
        back_populates="page",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<ConfluencePage(id='{self.id}', title='{self.title[:40]}')>"


class ConfluenceSection(Base):
    """
    One section of a page, split on the author's own headings.

    Sections are the retrieval unit for keyword search and the extraction unit
    when a package includes only the relevant parts of a document.
    """

    __tablename__ = "confluence_sections"

    id = Column(String(120), primary_key=True)  # "<page_id>#<ordinal>"
    page_id = Column(String(50), ForeignKey("confluence_pages.id"), nullable=False, index=True)

    ordinal = Column(Integer, nullable=False)     # position within the page
    heading = Column(String(500), nullable=True)  # None for lead-in text before the first heading
    level = Column(Integer, nullable=False, default=0)  # 1..6 from h1..h6, 0 for lead-in
    text = Column(Text, nullable=False, default="")

    page = relationship("ConfluencePage", back_populates="sections")

    def __repr__(self):
        return f"<ConfluenceSection(id='{self.id}', heading='{(self.heading or '')[:30]}')>"


class ConfluencePageCapability(Base):
    """
    Why a page is considered relevant to a capability.

    One row per (page, capability, match_type). This is the traceability
    record: every document in a transfer package can state the signal that
    put it there, in the same spirit as EvidenceRecord's source/source_ref.
    """

    __tablename__ = "confluence_page_capabilities"
    __table_args__ = (
        UniqueConstraint("page_id", "capability_id", "match_type", name="uq_page_capability_match"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    page_id = Column(String(50), ForeignKey("confluence_pages.id"), nullable=False, index=True)
    capability_id = Column(String(50), ForeignKey("capabilities.id"), nullable=False, index=True)

    # "label" | "space" | "ancestor" -- structural, exact lookups.
    # "keyword" links are NOT stored here; they are computed per query.
    match_type = Column(String(20), nullable=False)

    # Human-readable justification, e.g. ["label:database-recovery -> M003"].
    evidence = Column(JSON, nullable=False, default=list)

    confidence = Column(Float, nullable=False, default=1.0)

    page = relationship("ConfluencePage", back_populates="capability_links")

    def __repr__(self):
        return (
            f"<ConfluencePageCapability(page='{self.page_id}', "
            f"cap='{self.capability_id}', via='{self.match_type}')>"
        )

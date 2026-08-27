"""
HTTP surface for the Capability Gap RAG.

Mounted as its own router under /api/rag so it adds to the existing API
without altering any current endpoint.

    POST /api/rag/confluence/sync        pull Confluence into the index
    GET  /api/rag/confluence/status      index + configuration state
    POST /api/rag/mapping/space          resolve one ambiguous space mapping
    POST /api/rag/simulate               absence -> per-capability coverage
    POST /api/rag/gap-context            gaps + the context retrieval will use
    POST /api/rag/retrieve               documentation for one capability
    POST /api/rag/transfer-package       full package, written to disk
    POST /api/rag/transfer-package/download   build + stream in one call
    GET  /api/rag/transfer-package/{slug}/download
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.rag import config as cfg
from backend.rag.confluence.client import ConfluenceError, ConfluenceNotConfigured
from backend.rag.confluence.sync import run_sync
from backend.rag.coverage.context import build_context_for_capability, build_gap_contexts
from backend.rag.coverage.simulate import simulate_absence
from backend.rag.mapping import store as mapping_store
from backend.rag.models import ConfluencePage, ConfluenceSection
from backend.rag.packaging.build import build_transfer_package
from backend.rag.packaging.export import ALL_FORMATS, write_package
from backend.rag.packaging.markdown import render_markdown
from backend.rag.retrieval.retrieve import KnowledgeIndex

logger = logging.getLogger("rag.api")

router = APIRouter(prefix="/api/rag", tags=["rag"])


# ---------------------------------------------------------------------------
# request models
# ---------------------------------------------------------------------------


class SyncRequest(BaseModel):
    force: bool = Field(
        default=False,
        description="Re-parse every page even if its Confluence version is unchanged.",
    )


class SpaceMappingRequest(BaseModel):
    space_key: str
    service_id: str | None = Field(
        default=None,
        description="Service this space documents. Null records 'maps to nothing'.",
    )


class ConfluenceSettingsRequest(BaseModel):
    base_url: str | None = Field(
        default=None,
        description="Atlassian site base URL, e.g. https://acme.atlassian.net/wiki",
    )
    email: str | None = Field(
        default=None,
        description="Atlassian account email used for HTTP Basic auth.",
    )
    api_token: str | None = Field(
        default=None,
        description="Atlassian API token (id.atlassian.com -> Security -> API tokens).",
    )
    space_keys: str | None = Field(
        default=None,
        description="Comma-separated space keys to sync. Blank = every readable space.",
    )


class SimulateRequest(BaseModel):
    employee_ids: list[str] = Field(..., min_length=1)


class RetrieveRequest(BaseModel):
    capability_id: str


class GapContextRequest(BaseModel):
    employee_ids: list[str] = Field(..., min_length=1)
    capability_id: str | None = Field(
        default=None,
        description="Inspect one capability instead of every gap. Works whether or not it is a gap.",
    )


class PackageRequest(BaseModel):
    employee_ids: list[str] = Field(..., min_length=1)
    formats: list[str] = Field(default_factory=lambda: list(ALL_FORMATS))
    include_markdown: bool = Field(
        default=False, description="Return the rendered Markdown in the response body."
    )


# ---------------------------------------------------------------------------
# confluence
# ---------------------------------------------------------------------------


@router.get("/confluence/status")
def confluence_status(db: Session = Depends(get_db)):
    """Whether Confluence is configured, and what is currently indexed."""
    mapping = mapping_store.load_mapping()
    page_count = db.query(ConfluencePage).count()
    section_count = db.query(ConfluenceSection).count()

    return {
        "configured": cfg.confluence_is_configured(),
        "missing_settings": cfg.missing_confluence_settings(),
        "unset_settings": cfg.unset_confluence_settings(),
        "placeholder_settings": cfg.placeholder_confluence_settings(),
        "config_problem": cfg.confluence_config_problem(),
        "base_url": cfg.CONFLUENCE_BASE_URL or None,
        "space_keys": cfg.CONFLUENCE_SPACE_KEYS or "all readable spaces",
        "indexed_pages": page_count,
        "indexed_sections": section_count,
        "mapping_file": str(cfg.MAPPING_FILE),
        "mapping_generated_at": mapping.get("generated_at"),
        "resolved_spaces": mapping_store.resolved_space_service(mapping),
        "unresolved_spaces": mapping_store.unresolved_spaces(mapping),
    }


@router.post("/confluence/sync")
def confluence_sync(request: SyncRequest | None = None, db: Session = Depends(get_db)):
    """Pull Confluence pages into the knowledge index."""
    request = request or SyncRequest()
    try:
        result = run_sync(db, force=request.force)
    except ConfluenceNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ConfluenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"success": True, **result.as_dict()}


@router.get("/confluence/settings")
def get_confluence_settings():
    """
    The effective Confluence configuration, safe for the browser to read.

    The API token is never returned -- only whether one is present is.
    """
    from backend.rag import settings as settings_store

    effective = cfg.reload_persisted_confluence_settings()
    configured = cfg.confluence_is_configured()
    return {
        "success": True,
        "configured": configured,
        "missing_settings": cfg.missing_confluence_settings(),
        "config_problem": cfg.confluence_config_problem(),
        "settings": {
            "base_url": effective["base_url"],
            "email": effective["email"],
            "space_keys": [s for s in (effective["space_keys"] or [])],
            "api_token_set": bool(effective["api_token"]),
        },
        "saved": bool(settings_store.load()),
    }


@router.post("/confluence/settings")
def save_confluence_settings(request: ConfluenceSettingsRequest):
    """
    Save Confluence connection settings from the Setup tab and load them into
    the running process immediately, so a following sync uses them.
    """
    from backend.rag import settings as settings_store

    base_url = (request.base_url or "").strip().rstrip("/")
    if base_url and "://" not in base_url:
        raise HTTPException(
            status_code=422,
            detail="base_url must be a full URL including the scheme, e.g. https://your-site.atlassian.net/wiki",
        )

    saved = settings_store.save(
        {
            "base_url": base_url,
            "email": (request.email or "").strip(),
            "api_token": (request.api_token or "").strip(),
            "space_keys": (request.space_keys or "").strip(),
        }
    )
    cfg.reload_persisted_confluence_settings()
    return {
        "success": True,
        "configured": cfg.confluence_is_configured(),
        "settings": saved,
    }


@router.post("/mapping/space")
def set_space_mapping(request: SpaceMappingRequest):
    """
    Record a decision for a space the sync could not resolve.

    Persisted as "manual" and never overwritten by a later sync.
    """
    entry = mapping_store.set_manual(request.space_key, request.service_id)
    return {"success": True, "space_key": request.space_key, "entry": entry}


# ---------------------------------------------------------------------------
# simulation + retrieval
# ---------------------------------------------------------------------------


@router.post("/simulate")
def simulate(request: SimulateRequest, db: Session = Depends(get_db)):
    """Per-capability coverage with the given engineers absent."""
    try:
        result = simulate_absence(db, request.employee_ids)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, **result.as_dict()}


@router.post("/gap-context")
def gap_context(request: GapContextRequest, db: Session = Depends(get_db)):
    """
    The LOW/NONE capabilities plus everything retrieval will use for them:
    coverage figures, modules and services, and the exact search vocabulary
    with each term's weight, discriminating power, and whether it came from
    historical evidence.

    Runs no retrieval, so it works before any Confluence sync -- use it to see
    what the system is about to search for, or to feed the gap set into a
    different retriever.
    """
    try:
        if request.capability_id:
            context = build_context_for_capability(db, request.capability_id, request.employee_ids)
            if context is None:
                raise HTTPException(
                    status_code=404, detail="Unknown capability: %s" % request.capability_id
                )
            contexts = [context]
        else:
            contexts = build_gap_contexts(db, request.employee_ids)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "success": True,
        "absent_employee_ids": request.employee_ids,
        "count": len(contexts),
        "contexts": [c.as_dict() for c in contexts],
    }


@router.post("/retrieve")
def retrieve(request: RetrieveRequest, db: Session = Depends(get_db)):
    """Documentation retrieved for a single capability, with match reasons."""
    index = KnowledgeIndex(db)
    if index.is_empty():
        raise HTTPException(
            status_code=409,
            detail="No Confluence content indexed. Run POST /api/rag/confluence/sync first.",
        )

    result = index.retrieve_for_capability(request.capability_id)
    return {
        "success": True,
        "capability_id": result.capability_id,
        "capability_name": result.capability_name,
        "query_terms": result.query_terms,
        "evidence_terms": result.evidence_terms,
        "documents": [doc.as_dict() for doc in result.documents],
    }


# ---------------------------------------------------------------------------
# transfer package
# ---------------------------------------------------------------------------


@router.post("/transfer-package")
def transfer_package(request: PackageRequest, db: Session = Depends(get_db)):
    """
    Build the full transfer package and write it to disk.

    Generation never fails on an empty index -- the package is still produced
    with the coverage analysis, and says plainly that no documentation was
    attached.
    """
    try:
        package = build_transfer_package(db, request.employee_ids)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        export = write_package(package, formats=request.formats)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = {
        "success": True,
        "package": package.as_dict(),
        "export": export.as_dict(),
        "download_base": "/api/rag/transfer-package/%s/download" % export.slug,
    }
    if request.include_markdown:
        payload["markdown"] = render_markdown(package)
    return payload


_MEDIA_TYPES = {
    "md": "text/markdown",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class PackageDownloadRequest(BaseModel):
    employee_ids: list[str] = Field(..., min_length=1)
    format: str = Field(default="md", pattern="^(md|pdf|docx)$")


@router.post("/transfer-package/download")
def download_package_direct(request: PackageDownloadRequest, db: Session = Depends(get_db)):
    """
    Build a package and return the file in one call.

    The slug-based GET below serves a file some earlier request left on disk,
    which 404s as soon as that file is gone -- and data/rag/packages/ is
    gitignored, so a git clean, a branch switch, or a fresh clone removes it
    while the dashboard is still holding the old slug. That is the failure
    people actually hit.

    This route reads nothing but the database, so a download cannot break for
    a reason the user has no way to see.
    """
    try:
        package = build_transfer_package(db, request.employee_ids)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        export = write_package(package, formats=[request.format])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    path = export.files.get(request.format)
    if not path:
        # The only way here is a missing optional renderer, and export already
        # recorded exactly which library to install.
        raise HTTPException(
            status_code=503,
            detail=export.skipped.get(
                request.format, "%s export is unavailable." % request.format.upper()
            ),
        )

    return FileResponse(
        path=path,
        media_type=_MEDIA_TYPES[request.format],
        filename=Path(path).name,
    )


@router.get("/transfer-package/{slug}/download")
def download_package(
    slug: str,
    format: str = Query(default="pdf", pattern="^(md|pdf|docx)$"),
):
    """Download a previously generated package file."""
    # Reject any slug that could escape the output directory.
    if "/" in slug or "\\" in slug or ".." in slug:
        raise HTTPException(status_code=400, detail="Invalid package name.")

    path = (cfg.OUTPUT_DIR / ("%s.%s" % (slug, format))).resolve()
    try:
        path.relative_to(cfg.OUTPUT_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid package name.") from None

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="No %s file for package '%s'. It may not have been generated in that format."
            % (format.upper(), slug),
        )

    return FileResponse(
        path=str(path),
        media_type=_MEDIA_TYPES[format],
        filename=path.name,
    )


@router.get("/packages")
def list_packages():
    """Every package written to the output directory, newest first."""
    output_dir: Path = cfg.OUTPUT_DIR
    if not output_dir.exists():
        return {"success": True, "packages": []}

    by_slug: dict[str, dict] = {}
    for path in output_dir.iterdir():
        if not path.is_file() or path.suffix.lstrip(".") not in ALL_FORMATS:
            continue
        entry = by_slug.setdefault(
            path.stem,
            {"slug": path.stem, "formats": [], "modified": path.stat().st_mtime},
        )
        entry["formats"].append(path.suffix.lstrip("."))
        entry["modified"] = max(entry["modified"], path.stat().st_mtime)

    packages = sorted(by_slug.values(), key=lambda e: e["modified"], reverse=True)
    for entry in packages:
        entry["formats"] = sorted(entry["formats"])
        entry["download_base"] = "/api/rag/transfer-package/%s/download" % entry["slug"]

    return {"success": True, "packages": packages}

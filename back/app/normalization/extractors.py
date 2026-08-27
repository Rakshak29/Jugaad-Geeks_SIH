"""Feature extraction — three payload shapes become one row shape.

Piece 2 §6.3.  This is the *structural normalization* half of the panel's
"normalized and linked": three incompatible JSON shapes reduced to the same five
facts — who, when, what kind, what it touched, how sure we are.  Linking is a
different mechanism with a different failure mode and happens later.

Deterministic field lookups only.  Nothing here infers anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.enums import Certainty, ExtractionMethod, RecordKind
from app.normalization import roles as role_ladders


@dataclass
class ExtractedRow:
    """One normalized row, pre-persistence."""
    raw_record_id: int
    source_type: str
    record_kind: RecordKind
    native_actor_id: str
    occurred_at: datetime
    feature_tokens: list[str]
    extraction_method: ExtractionMethod
    certainty: Certainty
    actor_role: str
    ceiling_basis: str
    effort_signal: float | None = None
    jira_refs: list[str] = field(default_factory=list)   # cross-source links
    note: str = ""


def _parse_ts(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _path_tokens(paths: list[str]) -> list[str]:
    """A path plus every directory prefix of it.

    Prefixes are what make overlap meaningful: two commits touching different
    files under `payment-db/recovery/` share the prefix and therefore cluster,
    where bare filenames would not overlap at all.
    """
    tokens: set[str] = set()
    for p in paths:
        if not p:
            continue
        tokens.add(f"path:{p}")
        parts = p.split("/")
        for i in range(1, len(parts)):
            tokens.add(f"dir:{'/'.join(parts[:i])}")
    return sorted(tokens)


# ── GitHub ───────────────────────────────────────────────────────────────────
def extract_github(raw_record_id: int, native_id: str, payload: dict[str, Any]) -> list[ExtractedRow]:
    # A PR review is its own record kind at its own ladder rungs — the ladder is
    # selected by source but the RUNG is decided by record kind and actor role,
    # never by the source alone (Piece 2 §6.3).
    if "_pr_number" in payload or payload.get("state") in {"APPROVED", "COMMENTED", "CHANGES_REQUESTED"}:
        return _extract_review(raw_record_id, payload)
    if "number" in payload and "commit" not in payload:
        return _extract_pull(raw_record_id, payload)
    return _extract_commit(raw_record_id, payload)


def _extract_commit(raw_record_id: int, payload: dict[str, Any]) -> list[ExtractedRow]:
    commit = payload.get("commit") or {}
    message = commit.get("message", "") or ""
    files = [f.get("filename", "") for f in (payload.get("files") or [])]
    stats = payload.get("stats") or {}

    # The AUTHORED date, never the committer date: it is writable, which is what
    # carries the constructed timeline (Piece 5 §3.4 / amendment D3).
    occurred = _parse_ts((commit.get("author") or {}).get("date"))
    tokens = _path_tokens(files)
    refs = _jira_refs(message)

    rows = []
    for r in role_ladders.github_commit_roles(payload):
        rows.append(ExtractedRow(
            raw_record_id=raw_record_id,
            source_type="github",
            record_kind=RecordKind.COMMIT,
            native_actor_id=r.native_actor_id,
            occurred_at=occurred,
            feature_tokens=tokens,
            extraction_method=ExtractionMethod.FILE_PATH,
            certainty=Certainty.CERTAIN,
            actor_role=r.actor_role,
            ceiling_basis=r.ceiling_basis,
            # Lines changed. Code records ONLY — Jira and incident substance is
            # carried by their role ladders, not by duration (Piece 3 §6.5).
            effort_signal=float(stats.get("total") or 0),
            jira_refs=refs,
            note=message.splitlines()[0][:120] if message else "",
        ))
    return rows


def _extract_pull(raw_record_id: int, payload: dict[str, Any]) -> list[ExtractedRow]:
    files = [f.get("filename", "") for f in (payload.get("_files") or [])]
    body = f"{payload.get('title','')}\n{payload.get('body','')}"
    # created_at, not merged_at: both are server-assigned and unbackdatable, so
    # any unit containing a real PR is necessarily fresh — accepted, not fought.
    occurred = _parse_ts(payload.get("created_at"))
    rows = []
    for r in role_ladders.github_pr_roles(payload):
        rows.append(ExtractedRow(
            raw_record_id=raw_record_id,
            source_type="github",
            record_kind=RecordKind.COMMIT,     # authorship evidence, PR-shaped
            native_actor_id=r.native_actor_id,
            occurred_at=occurred,
            feature_tokens=_path_tokens(files),
            extraction_method=ExtractionMethod.FILE_PATH,
            certainty=Certainty.CERTAIN,
            actor_role=r.actor_role,
            ceiling_basis=r.ceiling_basis,
            effort_signal=None,
            jira_refs=_jira_refs(body),
            note=(payload.get("title") or "")[:120],
        ))
    return rows


def _extract_review(raw_record_id: int, payload: dict[str, Any]) -> list[ExtractedRow]:
    files = [f.get("filename", "") for f in (payload.get("_pr_files") or [])]
    occurred = _parse_ts(payload.get("submitted_at"))
    rows = []
    for r in role_ladders.github_review_roles(payload):
        rows.append(ExtractedRow(
            raw_record_id=raw_record_id,
            source_type="github",
            record_kind=RecordKind.PR_REVIEW,
            native_actor_id=r.native_actor_id,
            occurred_at=occurred,
            feature_tokens=_path_tokens(files),
            extraction_method=ExtractionMethod.FILE_PATH,
            certainty=Certainty.CERTAIN,
            actor_role=r.actor_role,
            ceiling_basis=r.ceiling_basis,
            effort_signal=None,     # a review has no diff of its own
            note=f"review on PR #{payload.get('_pr_number')}",
        ))
    return rows


def _jira_refs(text: str) -> list[str]:
    import re
    return sorted(set(re.findall(r"\b(?:PAY|JIRA)-\d+\b", text or "")))


# ── Jira — the fallback ladder ───────────────────────────────────────────────
#
# Component and label are OPTIONAL fields in Jira, and many real organisations
# populate them inconsistently or not at all.  No single field is assumed.  The
# chain is a list of (method, certainty, extractor) tried in order, so adding a
# tier is a list entry and the ORDER is assertable by a test.
#
# Tier 4 (text similarity) cannot run here: it compares against cluster
# summaries that do not exist until clustering.  It is applied as a narrow,
# named write-back during cross-source linking instead — see clustering.
JIRA_LADDER = (
    (ExtractionMethod.COMPONENT, Certainty.CERTAIN,
     lambda f: [f"component:{c['name']}" for c in (f.get("components") or []) if c.get("name")]),
    (ExtractionMethod.LABEL, Certainty.CERTAIN,
     lambda f: [f"label:{l}" for l in (f.get("labels") or []) if l]),
    # Mandatory in Jira, so ALWAYS available — but coarse. It tells you the
    # ticket belongs to Payment Service, not which capability inside it, which
    # is exactly why it is `probable` and caps the evidence at MODERATE.
    (ExtractionMethod.PROJECT, Certainty.PROBABLE,
     lambda f: [f"project:{(f.get('project') or {}).get('key')}"]
     if (f.get("project") or {}).get("key") else []),
)


def extract_jira(raw_record_id: int, native_id: str, payload: dict[str, Any]) -> list[ExtractedRow]:
    fields = payload.get("fields") or {}
    occurred = _parse_ts(fields.get("resolutiondate") or fields.get("updated") or fields.get("created"))

    method, certainty, tokens = ExtractionMethod.UNCLASSIFIED, Certainty.TENTATIVE, []
    for m, c, extractor in JIRA_LADDER:
        produced = extractor(fields)
        if produced:
            method, certainty, tokens = m, c, produced
            break

    summary = fields.get("summary") or ""
    description = fields.get("description") or ""

    rows = []
    for r in role_ladders.jira_roles(payload):
        rows.append(ExtractedRow(
            raw_record_id=raw_record_id,
            source_type="jira",
            record_kind=RecordKind.TICKET,
            native_actor_id=r.native_actor_id,
            occurred_at=occurred,
            feature_tokens=sorted(tokens),
            extraction_method=method,
            certainty=certainty,
            actor_role=r.actor_role,
            ceiling_basis=r.ceiling_basis,
            effort_signal=None,   # duration is not effort, and it inverts
            jira_refs=[native_id],
            note=f"{native_id} {summary}"[:120],
        ))
    # Carry the text so the similarity tier has something to work with later.
    for row in rows:
        row.__dict__["_text"] = f"{summary} {description}".strip()
    return rows


# ── Incidents ────────────────────────────────────────────────────────────────
def extract_incident(raw_record_id: int, native_id: str, payload: dict[str, Any]) -> list[ExtractedRow]:
    service_id = (payload.get("service_id")
                  or (payload.get("service") or {}).get("id") or "").strip()
    occurred = _parse_ts(payload.get("resolved_at") or payload.get("created_at"))

    # `service:x` plus the repository path prefix it maps to. That second token
    # is what makes the incident-to-GitHub link an EXPLICIT reference rather
    # than a guess (Piece 2 §14).
    tokens = [f"service:{service_id}"] if service_id else []

    # The tracking ticket, when the incident tool carries one.
    #
    # A service is COARSER than a capability: `payment-db` hosts both Database
    # Recovery and Schema Migration, so clustering on the service alone puts
    # every incident on that database into one leaf, and the whole leaf then
    # attaches to whichever capability it matched first. The tracking ticket is
    # the capability-specific signal, so it belongs in the signature.
    tracking = (payload.get("tracking_ticket") or "").strip()
    if tracking:
        tokens.append(f"ticket:{tracking}")

    urgency = (payload.get("urgency") or "high").strip().lower()

    rows = []
    for r in role_ladders.incident_roles(payload):
        rows.append(ExtractedRow(
            raw_record_id=raw_record_id,
            source_type="incident",
            record_kind=RecordKind.INCIDENT,
            native_actor_id=r.native_actor_id,
            occurred_at=occurred,
            feature_tokens=sorted(tokens),
            extraction_method=ExtractionMethod.AFFECTED_SERVICE,
            certainty=Certainty.CERTAIN,
            actor_role=r.actor_role,
            ceiling_basis=r.ceiling_basis,
            effort_signal=None,
            note=f"{native_id} {payload.get('title','')}"[:120],
        ))
    for row in rows:
        # Severity modulates using `urgency`, which is always present — not
        # `priority`, which is plan-gated and often absent (Piece 3 §16).
        row.__dict__["_urgency"] = urgency
    return rows


EXTRACTORS = {
    "github": extract_github,
    "jira": extract_jira,
    "incident": extract_incident,
}

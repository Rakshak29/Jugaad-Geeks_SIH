"""
Derive Confluence -> taxonomy mappings from the data itself.

Nothing here is hand-authored. Every mapping is derived from metadata the
Confluence API already returns, matched against the taxonomy the scoring
engine already uses:

    label     -> module     exact slug match (strongest; checked first)
    ancestor  -> module     exact slug match on a parent page title
    space     -> service    keyword overlap on name + description (fallback)

A page normally resolves on its labels alone, in which case the space mapping
is never consulted. The space signal only matters for pages nobody labelled.

Where the data genuinely cannot decide -- a generically-named space that
overlaps two services equally -- the result is recorded as AMBIGUOUS rather
than guessed. A human resolves those once and the answer is remembered.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from backend.models.core import Capability, Module, Service
from backend.rag.compat import keyword_overlap as _keyword_overlap
from backend.rag.compat import label_module_aliases, tokenize as _tokenize
from backend.rag.retrieval.cutoff import CLEAR_LEAD_RATIO, separation

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
_MODULES_JSON = BASE_DIR / "backend" / "input" / "modules.json"

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")

AUTO = "auto"
AMBIGUOUS = "ambiguous"
MANUAL = "manual"
UNMATCHED = "unmatched"

# How far ahead the best-matching service has to be before the match is taken
# as settled. Shared with retrieval so "clear winner" means one thing across
# the system -- see cutoff.CLEAR_LEAD_RATIO.
CLEAR_WINNER_RATIO = CLEAR_LEAD_RATIO


def normalize_slug(value: str) -> str:
    """'API Gateway' -> 'api-gateway'. The shared shape of a Confluence label."""
    if not value:
        return ""
    return _SLUG_STRIP.sub("-", value.strip().lower()).strip("-")


# ---------------------------------------------------------------------------
# label / ancestor -> module
# ---------------------------------------------------------------------------


@dataclass
class LabelRule:
    """One label-to-module rule, with the reason it exists."""

    label: str
    module_id: str
    origin: str  # "jira_component" | "module_name" | "curated"


def build_label_module_rules(session) -> dict[str, LabelRule]:
    """
    Every label spelling that resolves to a module.

    Three sources, all already present in the project:
      1. modules.json `jira_component` -- already slug-shaped, and the
         convention most wikis label pages with.
      2. The module's own name, normalized ("Database Recovery" ->
         "database-recovery").
      3. backend.mapper.LABEL_TO_MODULE_MAP -- the curated aliases the
         ingestion pipeline already uses for GitHub labels and Jira
         components. Reused verbatim so Confluence and GitHub resolve
         identically.
    """
    rules: dict[str, LabelRule] = {}

    # 3 first, so the more specific sources below can override an alias.
    for label, module_id in label_module_aliases().items():
        if not module_id:
            continue  # explicitly-ignored generic labels ("bug", "enhancement")
        slug = normalize_slug(label)
        if slug:
            rules[slug] = LabelRule(label=slug, module_id=module_id, origin="curated")

    # 2. Module names from the database.
    for module in session.query(Module).all():
        slug = normalize_slug(module.name)
        if slug:
            rules[slug] = LabelRule(label=slug, module_id=module.id, origin="module_name")

    # 1. jira_component from modules.json, if present.
    for row in _load_modules_json():
        component = row.get("jira_component")
        module_id = row.get("id")
        if not (component and module_id):
            continue
        slug = normalize_slug(component)
        if slug:
            rules[slug] = LabelRule(label=slug, module_id=module_id, origin="jira_component")

    return rules


def _load_modules_json() -> list[dict]:
    """modules.json is optional -- the DB alone is enough to run."""
    if not _MODULES_JSON.exists():
        return []
    try:
        return json.loads(_MODULES_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def module_capability_map(session) -> dict[str, list[str]]:
    """module_id -> [capability_id], read from the existing join table."""
    out: dict[str, list[str]] = {}
    for module in session.query(Module).all():
        out[module.id] = [cap.id for cap in module.capabilities]
    return out


# ---------------------------------------------------------------------------
# space -> service
# ---------------------------------------------------------------------------


@dataclass
class SpaceMatch:
    space_key: str
    space_name: str
    service_id: str | None
    status: str                      # auto | ambiguous | unmatched | manual
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)


def derive_space_service(space_key: str, space_name: str, space_description: str, session) -> SpaceMatch:
    """
    Score a Confluence space against every service and pick a winner.

    Uses the engine's own `_keyword_overlap`, so a space matches a service by
    the same rule that evidence matches a capability -- one relevance notion
    across the whole system.
    """
    space_tokens = _tokenize(space_name) | _tokenize(space_description) | _tokenize(space_key)

    scored: list[tuple[float, str, list[str]]] = []
    for service in session.query(Service).all():
        service_tokens = _tokenize(service.name) | _tokenize(service.description or "")
        score, matched = _keyword_overlap(space_tokens, service_tokens)
        if score > 0:
            scored.append((score, service.id, matched))

    scored.sort(key=lambda t: t[0], reverse=True)

    candidates = [
        {"service_id": sid, "score": round(score, 4), "matched_terms": matched}
        for score, sid, matched in scored[:4]
    ]

    # No shared vocabulary with any service at all. This is the honest
    # "unmatched" case and needs no threshold to detect -- there is simply
    # nothing to score.
    if not scored:
        return SpaceMatch(
            space_key=space_key,
            space_name=space_name,
            service_id=None,
            status=UNMATCHED,
            reasons=["no term overlap with any service name or description"],
            candidates=[],
        )

    best_score, best_service, best_terms = scored[0]
    lead = separation([score for score, _, _ in scored])

    # A clear winner leads the runner-up by a wide margin; a genuinely
    # ambiguous space does not. Expressed as a ratio rather than a difference
    # so it reads the same regardless of the score scale, and compared against
    # CLEAR_WINNER_RATIO -- "at least twice as good as the alternative", which
    # is a statement about what counts as clear, not a tuned value.
    if lead < CLEAR_WINNER_RATIO:
        tied = [sid for score, sid, _ in scored if score * CLEAR_WINNER_RATIO >= best_score]
        return SpaceMatch(
            space_key=space_key,
            space_name=space_name,
            service_id=None,
            status=AMBIGUOUS,
            score=round(best_score, 4),
            reasons=[
                "%s score within %.1fx of each other (best leads by only %.2fx)"
                % (", ".join(tied), CLEAR_WINNER_RATIO, lead)
            ],
            candidates=candidates,
        )

    return SpaceMatch(
        space_key=space_key,
        space_name=space_name,
        service_id=best_service,
        status=AUTO,
        score=round(best_score, 4),
        reasons=[
            "name/description overlap: %s (leads next candidate by %s)"
            % (", ".join(best_terms[:6]), "everything" if lead == float("inf") else "%.1fx" % lead)
        ],
        candidates=candidates,
    )


def service_capability_map(session) -> dict[str, list[str]]:
    """service_id -> [capability_id], via its modules."""
    out: dict[str, list[str]] = {}
    for service in session.query(Service).all():
        caps: list[str] = []
        for module in service.modules:
            for cap in module.capabilities:
                if cap.id not in caps:
                    caps.append(cap.id)
        out[service.id] = caps
    return out


# ---------------------------------------------------------------------------
# page -> capabilities
# ---------------------------------------------------------------------------


@dataclass
class CapabilityLink:
    capability_id: str
    match_type: str          # label | ancestor | space
    evidence: list[str]
    confidence: float


class PageMapper:
    """
    Resolves one page's capabilities from its metadata.

    Built once per sync so the taxonomy lookups happen once, not per page.
    """

    # Structural signals in descending order of authority.
    CONFIDENCE = {"label": 1.0, "ancestor": 0.8, "space": 0.6}

    def __init__(self, session, space_service: dict[str, str] | None = None):
        self.label_rules = build_label_module_rules(session)
        self.module_caps = module_capability_map(session)
        self.service_caps = service_capability_map(session)
        self.space_service = space_service or {}
        self.known_capabilities = {c.id for c in session.query(Capability).all()}

    def resolve(
        self,
        labels: list[str],
        ancestor_titles: list[str],
        space_key: str,
    ) -> list[CapabilityLink]:
        """
        Capability links for one page, best signal first.

        A capability reached by more than one signal is recorded once, under
        its strongest signal -- a page labelled `database-recovery` inside the
        DB space is a label match, not a weaker space match.
        """
        found: dict[str, CapabilityLink] = {}

        def add(cap_id: str, match_type: str, evidence: str) -> None:
            if cap_id not in self.known_capabilities:
                return
            existing = found.get(cap_id)
            confidence = self.CONFIDENCE[match_type]
            if existing and existing.confidence >= confidence:
                if evidence not in existing.evidence:
                    existing.evidence.append(evidence)
                return
            found[cap_id] = CapabilityLink(
                capability_id=cap_id,
                match_type=match_type,
                evidence=[evidence],
                confidence=confidence,
            )

        # 1. Labels -- strongest.
        for label in labels:
            rule = self.label_rules.get(normalize_slug(label))
            if not rule:
                continue
            for cap_id in self.module_caps.get(rule.module_id, []):
                add(cap_id, "label", "label:%s -> %s (%s)" % (rule.label, rule.module_id, rule.origin))

        # 2. Ancestor page titles -- a page under "Database Recovery" inherits it.
        for title in ancestor_titles:
            rule = self.label_rules.get(normalize_slug(title))
            if not rule:
                continue
            for cap_id in self.module_caps.get(rule.module_id, []):
                add(cap_id, "ancestor", "parent page:%s -> %s" % (title, rule.module_id))

        # 3. Space -- only for pages the explicit signals above did not place.
        #
        # A space maps to a whole service, so it would otherwise attach every
        # one of that service's capabilities to every page in it: a rollback
        # runbook in the Payments space would come back as documentation for
        # Payment Reconciliation. When an author has labelled a page, or filed
        # it under a module's page tree, they have already said what it covers
        # -- the space has nothing to add and only adds noise.
        if not found:
            service_id = self.space_service.get(space_key)
            if service_id:
                for cap_id in self.service_caps.get(service_id, []):
                    add(cap_id, "space", "space:%s -> %s" % (space_key, service_id))

        return sorted(found.values(), key=lambda l: (-l.confidence, l.capability_id))

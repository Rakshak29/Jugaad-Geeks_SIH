"""Vocabulary.

Piece 0 §5 is the controlled vocabulary and it is used exactly as written — in
the code, the API and the pitch.  Most confused-judge questions come from
drifting between two of these terms, so they are types rather than strings.

Note what has a Postgres counterpart and what does not.  `RecordKind`,
`ExtractionMethod`, `Certainty` and `NodeRole` are stored.  `CoverageStatus`,
`Exposure`, `Activity` and `Density` are COMPUTED and stored nowhere — that
absence is deliberate and should survive review (Piece 2 §1, §8).
"""

from __future__ import annotations

from enum import Enum


class RecordKind(str, Enum):
    """Not derivable from source_type: commits and PR reviews are both 'github'
    yet sit at different ladder rungs with different ceilings (Piece 2 §6.3)."""

    COMMIT = "commit"
    PR_REVIEW = "pr_review"
    TICKET = "ticket"
    INCIDENT = "incident"


class ExtractionMethod(str, Enum):
    """Which rung of the classification ladder fired."""

    FILE_PATH = "file_path"
    COMPONENT = "component"           # jira tier 1
    LABEL = "label"                   # jira tier 2
    PROJECT = "project"               # jira tier 3
    AFFECTED_SERVICE = "affected_service"
    SIMILARITY = "similarity"         # jira tier 4 — TF-IDF cosine
    UNCLASSIFIED = "unclassified"     # jira tier 5 — parked, never force-fitted


class Certainty(str, Enum):
    """OBSERVED, not calculated.  There is no confidence computation anywhere in
    this system: certainty records which rung of the ladder fired.

    Order matters and matches the Postgres enum declaration order, so the WEAKER
    of two links is the LARGER value (Piece 2 §8).
    """

    CERTAIN = "certain"
    PROBABLE = "probable"
    TENTATIVE = "tentative"

    @property
    def rank(self) -> int:
        return {"certain": 0, "probable": 1, "tentative": 2}[self.value]

    def weaker_of(self, other: "Certainty") -> "Certainty":
        return self if self.rank >= other.rank else other


class NodeRole(str, Enum):
    """The frontier is RAGGED, not flat — which is why this is a flag and not a
    depth number.  One branch may reach tightness at depth 1, another at depth 3
    (Piece 2 §3)."""

    GROUPING = "grouping"        # above the frontier — UI organisation only
    CAPABILITY = "capability"    # AT the frontier — the coverage unit
    SUBCATEGORY = "subcategory"  # below the frontier — evidence detail


class CoverageStatus(str, Enum):
    """The CHANGE to a capability under a simulated loss.

    At baseline, with nobody simulated, only COVERED and UNCOVERED apply —
    DEGRADED is a before/after comparison and there is nothing to compare to.
    """

    COVERED = "Covered"
    UNCOVERED = "Uncovered"      # nobody before either — a PRE-EXISTING gap
    MAINTAINED = "Maintained"
    DEGRADED = "Degraded"
    LOST = "Lost"                # had coverers, now none, BECAUSE of this simulation


class Exposure(str, Enum):
    """Risk arriving via the dependency graph.  Never modifies a band or status.

    A band means "what evidence exists"; architecture cannot change what someone
    has done.  Keeping these orthogonal is what lets the system say the sentence
    neither graph could say alone (Piece 3 §9.4).
    """

    NONE = "none"
    SECOND_DEGREE = "second_degree"
    DIRECT = "direct"


class Activity(str, Enum):
    """Has anyone at all touched this recently — including departed employees."""

    ACTIVE = "Active"
    DORMANT = "Dormant"


class Density(str, Enum):
    """Is there enough evidence for the conclusion to mean anything.

    Changes no band.  It flags the CONCLUSION as low-certainty, which is what
    stops the system stating a confident band from two data points.
    """

    ADEQUATE = "Adequate"
    THIN = "Thin"


class MergeMethod(str, Enum):
    WITHIN_SOURCE = "within_source"
    EXPLICIT_REFERENCE = "explicit_reference"
    SIMILARITY = "similarity"


class ReviewState(str, Enum):
    AUTO_APPLIED = "auto_applied"
    PENDING_REVIEW = "pending_review"
    HUMAN_APPROVED = "human_approved"
    HUMAN_REJECTED = "human_rejected"

"""The synthetic organisation — the dataset's specification.

Piece 5 §4.  This module DECLARES the target; it generates nothing.  The
generator's job is to produce evidence that makes discovery and the coverage
engine reproduce what is written here, and the validator's job is to check that
it did.

The generation direction matters and is the opposite of the obvious one
(Piece 5 §2):

    target capability tree
        -> design overlapping feature signals
            -> generate source records
                -> clustering
                    -> validator: did discovery reproduce the target?
                        -> no: ADD OVERLAP TO THE DATA, never loosen the threshold

Tuning a threshold to make one dataset work is the exact failure the
derive-or-justify rule exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.bands import Band


def _utc(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, 12, 0, 0, tzinfo=timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# Cast — six people, five active (Piece 5 §4.1)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Person:
    employee_id: str
    display_name: str
    role_title: str
    status: str                 # 'active' | 'departed'
    github_login: str
    jira_account_id: str
    pagerduty_id: str
    note: str                   # role in the dataset, for the walkthrough


PEOPLE: tuple[Person, ...] = (
    Person("rahul", "Rahul Kulkarni", "Senior Backend Engineer", "active",
           "rahul-k", "5b10a2844c20165700ede21g", "PXR4HL1",
           "Canonical simulation target. Sole coverer of Database Recovery — HIGH via incident escalation."),
    Person("karan", "Karan Mehta", "Staff Engineer", "active",
           "karan-m", "5b10a2844c20165700ede22h", "PKRN229",
           "Broad senior coverage across six capabilities. The Case F simulation target."),
    Person("priya", "Priya Nair", "Backend Engineer", "active",
           "priya-n", "5b10a2844c20165700ede23i", "PPRY337",
           "Payment API specialist. HIGH via authorship dominance."),
    Person("sneha", "Sneha Rao", "Platform Engineer", "active",
           "sneha-r", "5b10a2844c20165700ede24j", "PSNH445",
           "Reconciliation and production. Incident resolver."),
    Person("amit", "Amit Desai", "Backend Engineer", "active",
           "amit-d", "5b10a2844c20165700ede25k", "PAMT553",
           "Highest commit count in the dataset, no operational evidence — Case C."),
    Person("vikram", "Vikram Shah", "Senior Backend Engineer", "departed",
           "vikram-s", "5b10a2844c20165700ede26l", "PVKM661",
           "Departed March 2026. Was the Schema Migration expert — his exit is why "
           "that capability reads Uncovered at baseline."),
)

# Bots and CI identities.  Stage A drops their records: a Dependabot commit is
# not evidence of human knowledge (Piece 3 §4).
SERVICE_ACCOUNTS: tuple[Person, ...] = (
    Person("dependabot", "Dependabot", "bot", "active",
           "dependabot[bot]", "bot:dependabot", "PBOT001", "Bot — ineligible evidence."),
)

DEPARTURE_DATE = _utc(2026, 3, 18)


# ─────────────────────────────────────────────────────────────────────────────
# Components and the hand-authored dependency graph (Piece 5 §4.2)
#
#   prod-env ──▶ payment-api ──▶ reconciliation-worker ──▶ payment-db
#                     │                                        ▲
#                     └────────────────────────────────────────┘
#
# Chosen so a problem on payment-db propagates outward across two hops and
# reaches everything — which is what makes the dormant load-bearing finding
# visible rather than theoretical.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Component:
    component_id: str
    display_name: str
    service: str = "Payment Service"


COMPONENTS: tuple[Component, ...] = (
    Component("payment-api", "Payment API"),
    Component("reconciliation-worker", "Reconciliation Worker"),
    Component("payment-db", "Payment DB"),
    Component("prod-env", "Production Environment"),
)

# from_component DEPENDS ON to_component.  Exposure flows AGAINST the arrow.
DEPENDENCY_EDGES: tuple[tuple[str, str, str], ...] = (
    ("payment-api", "payment-db", "API reads and writes the database"),
    ("reconciliation-worker", "payment-db", "Worker reads the ledger"),
    ("payment-api", "reconciliation-worker", "API triggers reconciliation"),
    ("prod-env", "payment-api", "Environment hosts the API"),
)


# ─────────────────────────────────────────────────────────────────────────────
# Target capability tree — eight capabilities (Piece 5 §4.3)
#
# Eight, not five: Case F is provably impossible with fewer than six target
# capabilities, and the dormant load-bearing case needs a capability the
# architecture depends on that nobody is touching.
#
# "Incident Response" is deliberately ABSENT.  Incident records are the EVIDENCE
# for every other capability; a cluster made of them would be precisely the
# operational evidence that should have attached to Database Recovery and
# Reconciliation, so it would come out empty or cannibalise what it exists to
# strengthen.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Capability:
    key: str
    name: str
    component: str
    path_prefix: str            # GitHub namespace — creates within-source overlap
    jira_component: str         # Jira `components[].name`
    service_id: str             # incident `service_id`
    subcategories: tuple[str, ...] = ()


CAPABILITIES: tuple[Capability, ...] = (
    Capability("api-logic", "API Logic", "payment-api",
               "payment-api/logic", "Payment API", "payment-api",
               ("request validation", "idempotency keys")),
    Capability("gateway-integration", "Payment Gateway Integration", "payment-api",
               "payment-api/gateway", "Payment Gateway", "payment-api",
               ("provider adapters", "webhook intake")),
    Capability("reconciliation", "Payment Reconciliation", "reconciliation-worker",
               "reconciliation/matching", "Reconciliation", "reconciliation-worker",
               ("settlement matching", "exception queue")),
    Capability("ledger-adjustment", "Ledger Adjustment", "reconciliation-worker",
               "reconciliation/ledger", "Ledger", "reconciliation-worker",
               ("manual adjustments", "balance rollup")),
    Capability("database-recovery", "Database Recovery", "payment-db",
               "payment-db/recovery", "Payment DB", "payment-db",
               ("replica failover", "backup restore", "connection pool recovery")),
    Capability("schema-migration", "Schema Migration", "payment-db",
               "payment-db/migrations", "Schema Migration", "payment-db",
               ()),   # leaf capability — reached tightness without subdivision
    Capability("deployment-rollback", "Deployment & Rollback", "prod-env",
               "prod-env/deploy", "Deployment", "prod-env",
               ("release pipeline", "rollback procedure")),
    Capability("release-verification", "Release Verification", "prod-env",
               "prod-env/verify", "Release Verification", "prod-env",
               ()),   # leaf, and deliberately THIN — fewer units than density_min
)

CAPABILITY_BY_KEY = {c.key: c for c in CAPABILITIES}
ROOT_GROUPING_NAME = "Payment Service"


# ─────────────────────────────────────────────────────────────────────────────
# Baseline coverage matrix (Piece 5 §5.1)
#
# Who clears MODERATE for what, with nobody simulated.  THIS TABLE IS THE
# DATASET'S SPECIFICATION — the generator's job is to produce evidence that
# yields exactly this, and the validator asserts it exactly.
# ─────────────────────────────────────────────────────────────────────────────
BASELINE_COVERERS: dict[str, tuple[str, ...]] = {
    "api-logic":           ("karan", "rahul", "priya", "amit"),
    "gateway-integration": ("karan", "rahul", "priya"),
    "reconciliation":      ("karan", "rahul", "sneha"),
    "ledger-adjustment":   ("karan", "rahul", "sneha"),
    "database-recovery":   ("rahul",),                  # single coverer — Case A
    "schema-migration":    (),                          # nobody — Case E
    "deployment-rollback": ("karan", "priya"),
    "release-verification": ("karan", "sneha"),
}

# The baseline at-risk list the dashboard shows before anyone clicks.
AT_RISK_UNCOVERED = ("schema-migration",)
AT_RISK_SINGLE_COVERER = ("database-recovery",)


# ─────────────────────────────────────────────────────────────────────────────
# Intended bands — what the generator must produce evidence FOR.
#
# This is the inversion made concrete: rather than sprinkling evidence and
# hoping the engine agrees, each (person, capability, band) below is turned into
# the minimum evidence that PRODUCES that band under Piece 3's rules.
#
# Only entries at or above MODERATE appear as coverers above; LOW entries exist
# so the residual gap can name who is closest and why.
# ─────────────────────────────────────────────────────────────────────────────
INTENDED_BANDS: dict[tuple[str, str], Band] = {
    # Database Recovery — Rahul alone. HIGH via incident escalation (rung 2).
    ("rahul", "database-recovery"): Band.HIGH,
    ("amit", "database-recovery"): Band.LOW,        # closest candidate in the residual gap
    ("vikram", "database-recovery"): Band.LOW,

    # Schema Migration — nobody clears. Vikram held it and left; Karan's
    # commits are all over two years old and age-cap to LOW (Case D).
    #
    # Vikram is MODERATE, not HIGH, and that is forced rather than chosen: this
    # capability must also read DORMANT, and dormancy means no eligible work
    # unit from ANY person — departed included — inside the fresh window. Fresh
    # evidence strong enough for HIGH would make it Active and cost us the
    # strongest finding the system produces (Uncovered + Dormant + three
    # components depending on it). So his incident sits in the aging window:
    # incident rung 3 caps at HIGH, the age cap pulls it to MODERATE, and he
    # still cleared the threshold before he left. The baseline sentence is
    # "the person who covered this left in March" rather than "...held HIGH",
    # which is the same finding and is what the evidence supports.
    ("vikram", "schema-migration"): Band.MODERATE,  # departed — retained, explains the gap
    ("karan", "schema-migration"): Band.LOW,        # stale commits — Case D, and the
                                                    # "closest" name in the residual gap

    # API Logic — Amit has the highest commit count in the dataset and still
    # caps at MODERATE (Case C); Priya reaches HIGH by authorship dominance.
    ("priya", "api-logic"): Band.HIGH,
    ("karan", "api-logic"): Band.MODERATE,
    ("rahul", "api-logic"): Band.MODERATE,
    ("amit", "api-logic"): Band.MODERATE,
    ("sneha", "api-logic"): Band.LOW,

    ("karan", "gateway-integration"): Band.MODERATE,
    ("rahul", "gateway-integration"): Band.MODERATE,
    ("priya", "gateway-integration"): Band.MODERATE,
    ("amit", "gateway-integration"): Band.LOW,

    ("karan", "reconciliation"): Band.MODERATE,
    ("rahul", "reconciliation"): Band.MODERATE,
    ("sneha", "reconciliation"): Band.HIGH,          # incident resolver, fresh
    ("priya", "reconciliation"): Band.LOW,

    ("karan", "ledger-adjustment"): Band.MODERATE,
    ("rahul", "ledger-adjustment"): Band.MODERATE,
    ("sneha", "ledger-adjustment"): Band.MODERATE,
    ("amit", "ledger-adjustment"): Band.LOW,
    ("priya", "ledger-adjustment"): Band.LOW,        # from the wide refactor, breadth-capped

    ("karan", "deployment-rollback"): Band.MODERATE,
    ("priya", "deployment-rollback"): Band.MODERATE,
    ("sneha", "deployment-rollback"): Band.LOW,

    ("karan", "release-verification"): Band.MODERATE,
    ("sneha", "release-verification"): Band.MODERATE,
    ("priya", "release-verification"): Band.LOW,
}


# ─────────────────────────────────────────────────────────────────────────────
# Timeline (Piece 5 §4.4).  Evidence spans three years, ending at the freeze.
# as_of_date is pinned to the newest occurred_at so the demo does not age.
#
# Real PR timestamps are server-assigned and cannot be backdated, so any work
# unit containing a real PR is necessarily in the fresh window.  That is
# realistic rather than a compromise: recent work has commits AND PRs;
# three-year-old work is commits only (Piece 5 §3.4).
# ─────────────────────────────────────────────────────────────────────────────
# Anchored at the real 'today' because live PR timestamps are server-assigned
# and land here. Calibration still sets as_of_date = max(occurred_at) at freeze.
AS_OF = _utc(2026, 8, 22)

FRESH_START = _utc(2025, 9, 1)     # <= 12 months before AS_OF
AGING_START = _utc(2024, 9, 1)     # 12–24 months
STALE_START = _utc(2023, 8, 1)     # > 24 months


@dataclass(frozen=True)
class Window:
    key: str
    start: datetime
    end: datetime
    note: str


WINDOWS: tuple[Window, ...] = (
    Window("fresh", FRESH_START, AS_OF,
           "Most current activity; all real PRs; Rahul's escalation incident; Priya's authorship run."),
    Window("aging", AGING_START, FRESH_START,
           "Karan's broader work; one incident that demonstrates the HIGH to MODERATE age drop."),
    Window("stale", STALE_START, AGING_START,
           "Vikram's Schema Migration work; Karan's stale Schema Migration commits; Amit's oldest volume."),
)


# ─────────────────────────────────────────────────────────────────────────────
# Rule-coverage records (Piece 5 §5.10).  Individual rules need at least one
# record each or they are untested.  A cap that never binds is a cap nobody has
# checked.
# ─────────────────────────────────────────────────────────────────────────────
REQUIRED_RULE_COVERAGE: tuple[str, ...] = (
    "HIGH via incident escalation target (rung 2)",
    "HIGH via authorship dominance (the authorship exception)",
    "A sparse Jira ticket with no component and no label, falling through to the project tier",
    "A breadth-capped unit — one wide refactor above the 98th percentile",
    "A substance-capped unit — one trivial commit in the bottom decile",
    "An ineligible bot commit",
    "An ineligible revert commit",
    "An ineligible won't-fix ticket",
    "A multi-record work unit — ticket + commit + PR describing one task",
    "An aging incident that would be HIGH if fresh, demonstrating the age cap in isolation",
)


@dataclass(frozen=True)
class DatasetShape:
    """Expected counts, asserted loosely by the validator — the shape matters,
    the exact totals do not."""
    employees: int = len(PEOPLE)
    components: int = len(COMPONENTS)
    dependency_edges: int = len(DEPENDENCY_EDGES)
    capabilities: int = len(CAPABILITIES)
    source_identities: int = len(PEOPLE) * 3
    min_items: int = 70
    max_items: int = 140


SHAPE = DatasetShape()

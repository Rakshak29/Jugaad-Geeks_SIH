"""Evidence recipes — the generation inversion made concrete.

Piece 5 §2.  The dataset cannot DECLARE its capabilities, because discovery is
what produces them.  So it is generated backwards: for each (person, capability,
intended band) in `spec.INTENDED_BANDS`, this module emits the *minimum evidence
that produces that band* under Piece 3's rules.

The recipes are written out explicitly rather than derived from the band, because
three of them collide with Piece 3 in ways worth recording where the next reader
will see them:

1.  **The acknowledger problem.**  Piece 3 §15's "on-call rotation manufactures a
    false expert" case has someone acknowledge an incident and escalate away,
    landing them at incident rung 4 — which caps at MODERATE, which makes them a
    COVERER.  Put that on Database Recovery and Amit becomes a second coverer,
    breaking "Rahul only".  So the ack-and-escalate case lives on Payment
    Reconciliation, where the acknowledger (Karan) is a coverer anyway.  The
    robustness demo survives; the matrix survives.

2.  **"Eighteen months" is an aging window, and aging caps at MODERATE.**
    Piece 5 §5.2 wants Amit closest at LOW on Database Recovery "from a handful
    of commits eighteen months old" — but the age cap alone would leave him at
    MODERATE and make him a coverer.  His commits are therefore also *trivial*
    (bottom decile), so the SUBSTANCE cap binds at LOW.  This is not a patch: it
    makes the residual-gap sentence more precise ("three small commits, eighteen
    months ago") and it gives the substance cap a unit it actually binds on,
    which the validator requires.

3.  **The wide refactor must not be fresh.**  A breadth-capped refactor touching
    six capabilities adds a *fresh authored unit* to each of them, and the
    authorship exception counts authored units regardless of their ceiling.  A
    fresh refactor would hand Priya dominance on Deployment & Rollback and turn
    her MODERATE into HIGH.  So it sits in the aging window: the breadth cap
    still binds, and dominance (fresh-only) is untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.dataset.spec import AS_OF, CAPABILITY_BY_KEY


def months_before(n: int, day_offset: int = 0) -> datetime:
    """A date n months before as_of_date.  Approximated at 30.44 days/month —
    exactness does not matter, which side of a window boundary does."""
    return AS_OF - timedelta(days=int(n * 30.44) - day_offset)


# ─────────────────────────────────────────────────────────────────────────────
# Record specs.  Source-agnostic descriptions; `generators.py` turns each into
# the real API shape for its source.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class CommitSpec:
    key: str                       # stable id -> deterministic SHA
    author: str                    # employee_id, or a bot login
    capability_keys: tuple[str, ...]
    occurred_at: datetime
    lines_changed: int
    message: str
    files: tuple[str, ...] = ()
    jira_ref: str | None = None    # 'Closes PAY-501' -> cross-source link + work unit
    co_authors: tuple[str, ...] = ()
    is_revert: bool = False
    is_merge: bool = False
    parents: int = 1


@dataclass
class PRSpec:
    number: int
    author: str
    capability_keys: tuple[str, ...]
    occurred_at: datetime          # server-assigned in reality -> always fresh
    title: str
    jira_ref: str | None = None
    reviewers: tuple[tuple[str, bool], ...] = ()   # (employee_id, left_comments)


@dataclass
class TicketSpec:
    key: str                       # 'PAY-501'
    capability_key: str | None     # None -> deliberately sparse, falls to project tier
    assignee: str
    occurred_at: datetime
    summary: str
    description: str
    issue_type: str = "Task"
    resolution: str | None = "Done"
    transitioned_by: str | None = None      # made BOTH transitions -> jira rung 1
    commenters: tuple[str, ...] = ()
    with_component: bool = True
    with_label: bool = True


@dataclass
class IncidentSpec:
    key: str                       # 'INC-741'
    capability_key: str
    occurred_at: datetime
    urgency: str = "high"
    triggered_by: str = "monitoring"         # service account -> Stage A drops it
    acknowledged_by: str | None = None       # rung 4 if they then escalate away
    escalated_to: str | None = None          # rung 2 — the strongest signal we have
    resolved_by: str | None = None           # rung 3
    summary: str = ""
    linked_ticket: str | None = None         # tracking ticket — the explicit
                                             # reference that places an incident at
                                             # CAPABILITY rather than SERVICE
                                             # granularity. Real incident tools
                                             # carry one; without it, an incident
                                             # on `payment-db` cannot be told apart
                                             # from any other work on that service.


@dataclass
class Plan:
    commits: list[CommitSpec] = field(default_factory=list)
    prs: list[PRSpec] = field(default_factory=list)
    tickets: list[TicketSpec] = field(default_factory=list)
    incidents: list[IncidentSpec] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "commits": len(self.commits),
            "prs": len(self.prs),
            "tickets": len(self.tickets),
            "incidents": len(self.incidents),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Path helpers — file paths are the within-source clustering signal, so they are
# designed rather than incidental.  Commits belonging to one capability share a
# directory prefix; cross-capability commits are deliberate.
# ─────────────────────────────────────────────────────────────────────────────
_FILE_STEMS = (
    "handler", "service", "client", "store", "worker", "validator",
    "adapter", "runner", "config", "helper", "mapper", "reporter",
)


def paths_for(capability_key: str, n: int, offset: int = 0) -> tuple[str, ...]:
    prefix = CAPABILITY_BY_KEY[capability_key].path_prefix
    return tuple(
        f"{prefix}/{_FILE_STEMS[(offset + i) % len(_FILE_STEMS)]}.py" for i in range(n)
    )


# ─────────────────────────────────────────────────────────────────────────────
# The plan
# ─────────────────────────────────────────────────────────────────────────────
def build_plan() -> Plan:
    p = Plan()
    c = p.commits.append
    t = p.tickets.append
    inc = p.incidents.append
    pr = p.prs.append

    # ══ DATABASE RECOVERY ════════════════════════════════════════════════════
    # Rahul HIGH via incident rung 2 (escalation target), fresh.
    # The trigger is a monitoring service account, so no human picks up a
    # rung-4 MODERATE here and Rahul stays the sole coverer.
    inc(IncidentSpec(
        key="INC-741", capability_key="database-recovery",
        occurred_at=months_before(4),
        urgency="high", triggered_by="monitoring",
        escalated_to="rahul", resolved_by="rahul", linked_ticket="PAY-501",
        summary="Replica lag on payment-db after failover; writes queuing",
    ))
    # The multi-record work unit: one ticket + one commit + one PR, one task.
    # Counting these as three would inflate an afternoon into a pattern, and
    # would let a single afternoon satisfy the authorship exception.
    t(TicketSpec(
        key="PAY-501", capability_key="database-recovery", assignee="rahul",
        occurred_at=months_before(5), transitioned_by="rahul",
        summary="Restore replica after failover",
        description="Replica did not rejoin after the failover window; restore and verify.",
    ))
    c(CommitSpec(
        key="dbr-rahul-1", author="rahul", capability_keys=("database-recovery",),
        occurred_at=months_before(5), lines_changed=210,
        message="Restore replica after failover. Closes PAY-501",
        files=paths_for("database-recovery", 3), jira_ref="PAY-501",
    ))
    pr(PRSpec(
        number=88, author="rahul", capability_keys=("database-recovery",),
        occurred_at=months_before(1), title="Restore replica after failover",
        jira_ref="PAY-501", reviewers=(("karan", True),),
    ))
    c(CommitSpec(
        key="dbr-rahul-2", author="rahul", capability_keys=("database-recovery",),
        occurred_at=months_before(7), lines_changed=140,
        message="Harden connection pool recovery on primary promotion",
        files=paths_for("database-recovery", 2, offset=4),
    ))
    # Amit LOW — see docstring note 2: aging alone would leave him MODERATE and
    # make him a coverer, so these are also trivial and the SUBSTANCE cap binds.
    for i in range(3):
        c(CommitSpec(
            key=f"dbr-amit-{i}", author="amit", capability_keys=("database-recovery",),
            occurred_at=months_before(18, day_offset=i * 9), lines_changed=3 + i,
            message="Fix typo in recovery runbook comment",
            files=paths_for("database-recovery", 1, offset=6 + i),
        ))
    # Vikram LOW — stale.
    for i in range(2):
        c(CommitSpec(
            key=f"dbr-vikram-{i}", author="vikram", capability_keys=("database-recovery",),
            occurred_at=months_before(29, day_offset=i * 14), lines_changed=95,
            message="Add backup restore verification step",
            files=paths_for("database-recovery", 2, offset=8 + i),
        ))

    # ══ SCHEMA MIGRATION ═════════════════════════════════════════════════════
    # Uncovered + Dormant + three components depend on payment-db.
    # Nothing here may be FRESH or dormancy breaks (see spec.py).
    inc(IncidentSpec(
        key="INC-655", capability_key="schema-migration",
        occurred_at=months_before(14),          # aging -> rung 3 HIGH, age caps MODERATE
        urgency="high", triggered_by="monitoring",
        resolved_by="vikram", linked_ticket="PAY-820",
        summary="Migration lock held during deploy; schema change blocked writes",
    ))
    for i in range(3):
        c(CommitSpec(
            key=f"sm-vikram-{i}", author="vikram", jira_ref=("PAY-820" if i == 0 else None), capability_keys=("schema-migration",),
            occurred_at=months_before(15, day_offset=i * 20), lines_changed=180,
            message="Add online migration runner with backfill checkpoints",
            files=paths_for("schema-migration", 3, offset=i),
        ))
    # Karan LOW — stale. This is Case D, and the "closest" name in the gap.
    for i in range(3):
        c(CommitSpec(
            key=f"sm-karan-{i}", author="karan", capability_keys=("schema-migration",),
            occurred_at=months_before(31, day_offset=i * 25), lines_changed=240,
            message="Introduce expand-contract migration pattern",
            files=paths_for("schema-migration", 3, offset=3 + i),
        ))

    # ══ API LOGIC ════════════════════════════════════════════════════════════
    # Priya HIGH via the authorship exception: fresh authored units must exceed
    # everyone else's fresh authored units COMBINED, and be more than one.
    #   priya 6  >  amit 3 + karan 1 + rahul 1 = 5   ✓
    # Amit has the most commits in the dataset and still caps at MODERATE —
    # that is Case C, and the drill-down is the demo beat.
    for i in range(6):
        c(CommitSpec(
            key=f"api-priya-{i}", author="priya", jira_ref=("PAY-790" if i == 0 else None), capability_keys=("api-logic",),
            occurred_at=months_before(2, day_offset=i * 11), lines_changed=160 + i * 20,
            message="Tighten idempotency key handling on payment intents",
            files=paths_for("api-logic", 3, offset=i),
        ))
    for i in range(3):
        c(CommitSpec(
            key=f"api-amit-{i}", author="amit", capability_keys=("api-logic",),
            occurred_at=months_before(3, day_offset=i * 13), lines_changed=120,
            message="Extend request validation for partial captures",
            files=paths_for("api-logic", 2, offset=6 + i),
        ))
    c(CommitSpec(key="api-karan-0", author="karan", capability_keys=("api-logic",),
                 occurred_at=months_before(6), lines_changed=95,
                 message="Normalise error envelope on payment routes",
                 files=paths_for("api-logic", 2, offset=9)))
    c(CommitSpec(key="api-rahul-0", author="rahul", capability_keys=("api-logic",),
                 occurred_at=months_before(8), lines_changed=110,
                 message="Add retry budget to payment intent creation",
                 files=paths_for("api-logic", 2, offset=1)))
    # Sneha LOW via a stale commit.
    #
    # This was originally a PR review (github rung 3). It cannot be: a
    # single-account repository has one reviewer identity — the operator's — so
    # review evidence resolves to an account that is not in the cast and is
    # correctly discarded. Rung 3 stays implemented and its live instance is a
    # real GitHub review; it simply attributes to nobody here. Rather than
    # fabricate a mapping, Sneha's adjacency comes from work she actually did.
    c(CommitSpec(key="api-sneha-0", author="sneha", capability_keys=("api-logic",),
                 occurred_at=months_before(28), lines_changed=75,
                 message="Add structured logging to payment intent handler",
                 files=paths_for("api-logic", 1, offset=11)))
    pr(PRSpec(number=91, author="priya", capability_keys=("api-logic",),
              occurred_at=months_before(1), title="Idempotency key handling",
              reviewers=(("sneha", True),)))

    # ══ PAYMENT GATEWAY INTEGRATION ══════════════════════════════════════════
    for i in range(2):
        c(CommitSpec(key=f"gw-karan-{i}", author="karan", jira_ref=("PAY-612" if i == 0 else None), capability_keys=("gateway-integration",),
                     occurred_at=months_before(5, day_offset=i * 15), lines_changed=150,
                     message="Add provider adapter for tokenised cards",
                     files=paths_for("gateway-integration", 2, offset=i)))
    for i in range(2):
        c(CommitSpec(key=f"gw-priya-{i}", author="priya", capability_keys=("gateway-integration",),
                     occurred_at=months_before(7, day_offset=i * 15), lines_changed=130,
                     message="Harden webhook signature verification",
                     files=paths_for("gateway-integration", 2, offset=2 + i)))
    t(TicketSpec(key="PAY-612", capability_key="gateway-integration", assignee="rahul",
                 occurred_at=months_before(4), transitioned_by="rahul",
                 summary="Gateway webhook retries duplicating captures",
                 description="Provider retries on 5xx are creating duplicate capture rows."))
    # Amit LOW via a stale commit.
    #
    # Rung 4 (approval with no comments) has NO live instance: GitHub refuses to
    # let an account approve its own pull request, so a single-account
    # repository cannot produce one. The rung is implemented and unit-tested;
    # it is recorded here as untested-by-live-data rather than quietly counted.
    c(CommitSpec(key="gw-amit-0", author="amit", capability_keys=("gateway-integration",),
                 occurred_at=months_before(26), lines_changed=85,
                 message="Add gateway timeout configuration",
                 files=paths_for("gateway-integration", 1, offset=6)))
    pr(PRSpec(number=94, author="karan", capability_keys=("gateway-integration",),
              occurred_at=months_before(1), title="Tokenised card adapter",
              reviewers=(("amit", False),)))

    # ══ PAYMENT RECONCILIATION ═══════════════════════════════════════════════
    # The "on-call rotation manufactures a false expert" case lives HERE, not on
    # Database Recovery — see docstring note 1.  Karan acknowledges and escalates
    # away (rung 4 -> MODERATE, which he holds anyway); Sneha is escalated to
    # (rung 2 -> HIGH).  The person others turned to is the one credited.
    inc(IncidentSpec(
        key="INC-802", capability_key="reconciliation",
        occurred_at=months_before(3), urgency="high", triggered_by="monitoring",
        acknowledged_by="karan", escalated_to="sneha", resolved_by="sneha",
        linked_ticket="PAY-655",
        summary="Settlement file mismatch; reconciliation queue backing up",
    ))
    # Karan's second reconciliation commit sits in the AGING window. He is the
    # broad senior engineer, and the point of the authorship exception is that
    # dominance is hard: on a capability with two genuinely active contributors,
    # neither should qualify (Piece 3 §7.2). Sneha is the specialist here — she
    # holds HIGH from being escalated to, and her code work belongs here too.
    for i in range(2):
        c(CommitSpec(key=f"rec-karan-{i}", author="karan",
                     jira_ref=("PAY-655" if i == 0 else None),
                     capability_keys=("reconciliation",),
                     occurred_at=months_before(6 if i == 0 else 15, day_offset=i * 15),
                     lines_changed=170,
                     message="Rework settlement matching tolerance windows",
                     files=paths_for("reconciliation", 2, offset=i)))
    for i in range(3):
        c(CommitSpec(key=f"rec-sneha-{i}", author="sneha", capability_keys=("reconciliation",),
                     occurred_at=months_before(5, day_offset=i * 12), lines_changed=160,
                     message="Rebuild the settlement exception queue drain",
                     files=paths_for("reconciliation", 2, offset=3 + i)))

    t(TicketSpec(key="PAY-655", capability_key="reconciliation", assignee="rahul",
                 occurred_at=months_before(9), transitioned_by="rahul",
                 summary="Exception queue not draining for partial settlements",
                 description="Partial settlements are parked and never retried."))
    # Closes the deliberately sparse ticket. The ticket is PLACED by this
    # explicit reference, but it is not re-classified: its own extraction still
    # stopped at the project tier, so its certainty stays `probable` and the
    # certainty cap binds at MODERATE. Without a link like this the sparse
    # ticket is simply parked, and the cap has nothing to bind on.
    c(CommitSpec(key="rec-karan-sparse", author="karan", jira_ref="PAY-777",
                 capability_keys=("reconciliation",),
                 occurred_at=months_before(3), lines_changed=130,
                 message="Log provider reference on unmatched settlements",
                 files=paths_for("reconciliation", 2, offset=9)))

    c(CommitSpec(key="rec-priya-0", author="priya", capability_keys=("reconciliation",),
                 occurred_at=months_before(28), lines_changed=90,
                 message="Log unmatched settlement rows with provider id",
                 files=paths_for("reconciliation", 1, offset=5)))

    # ══ LEDGER ADJUSTMENT ════════════════════════════════════════════════════
    for i in range(2):
        c(CommitSpec(key=f"led-karan-{i}", author="karan", capability_keys=("ledger-adjustment",),
                     occurred_at=months_before(16, day_offset=i * 20), lines_changed=200,
                     message="Add manual ledger adjustment audit trail",
                     files=paths_for("ledger-adjustment", 2, offset=i)))
    c(CommitSpec(key="led-rahul-0", jira_ref="PAY-701", author="rahul", capability_keys=("ledger-adjustment",),
                 occurred_at=months_before(6), lines_changed=140,
                 message="Fix balance rollup for reversed adjustments",
                 files=paths_for("ledger-adjustment", 2, offset=2)))
    t(TicketSpec(key="PAY-701", capability_key="ledger-adjustment", assignee="sneha",
                 occurred_at=months_before(5), transitioned_by="sneha",
                 summary="Rollup drift after bulk adjustment import",
                 description="Balances drift by a few paise after bulk imports."))
    c(CommitSpec(key="led-amit-0", author="amit", capability_keys=("ledger-adjustment",),
                 occurred_at=months_before(27), lines_changed=80,
                 message="Add ledger adjustment reason codes",
                 files=paths_for("ledger-adjustment", 1, offset=4)))

    # ══ DEPLOYMENT & ROLLBACK ════════════════════════════════════════════════
    for i in range(2):
        c(CommitSpec(key=f"dep-karan-{i}", author="karan", jira_ref=("PAY-810" if i == 0 else None), capability_keys=("deployment-rollback",),
                     occurred_at=months_before(4, day_offset=i * 18), lines_changed=155,
                     message="Add canary gate to payment release pipeline",
                     files=paths_for("deployment-rollback", 2, offset=i)))
    for i in range(2):
        c(CommitSpec(key=f"dep-priya-{i}", author="priya", capability_keys=("deployment-rollback",),
                     occurred_at=months_before(8, day_offset=i * 18), lines_changed=145,
                     message="Automate rollback to previous release manifest",
                     files=paths_for("deployment-rollback", 2, offset=2 + i)))
    c(CommitSpec(key="dep-sneha-0", author="sneha", capability_keys=("deployment-rollback",),
                 occurred_at=months_before(30), lines_changed=70,
                 message="Document deploy freeze windows",
                 files=paths_for("deployment-rollback", 1, offset=5)))

    # ══ RELEASE VERIFICATION ═════════════════════════════════════════════════
    # Deliberately THIN — the fewest work units of any capability, so the
    # density flag appears at least once and the conclusion is marked
    # low-certainty rather than stated confidently.
    c(CommitSpec(key="rel-karan-0", jira_ref="PAY-733", author="karan", capability_keys=("release-verification",),
                 occurred_at=months_before(5), lines_changed=120,
                 message="Add post-release smoke verification job",
                 files=paths_for("release-verification", 2)))
    t(TicketSpec(key="PAY-733", capability_key="release-verification", assignee="sneha",
                 occurred_at=months_before(6), transitioned_by="sneha",
                 summary="Smoke checks pass while gateway is degraded",
                 description="Verification job reports green on a degraded provider."))
    c(CommitSpec(key="rel-priya-0", author="priya", capability_keys=("release-verification",),
                 occurred_at=months_before(29), lines_changed=60,
                 message="Record release verification results to build log",
                 files=paths_for("release-verification", 1, offset=3)))

    t(TicketSpec(key="PAY-790", capability_key="api-logic", assignee="priya",
                 occurred_at=months_before(2), transitioned_by="priya",
                 summary="Idempotency keys collide across retries",
                 description="Two retries of one intent produce distinct keys."))
    t(TicketSpec(key="PAY-810", capability_key="deployment-rollback", assignee="karan",
                 occurred_at=months_before(4), transitioned_by="karan",
                 summary="Canary gate does not halt on error-rate spike",
                 description="Release proceeds past the canary despite elevated 5xx."))
    t(TicketSpec(key="PAY-820", capability_key="schema-migration", assignee="vikram",
                 occurred_at=months_before(15), transitioned_by="vikram",
                 summary="Migration lock blocks writes during deploy",
                 description="Expand-contract step holds a lock for the full backfill."))

    # ══ RULE-COVERAGE RECORDS (Piece 5 §5.10) ════════════════════════════════
    # Each of these exists so a specific rule has at least one record that
    # exercises it.  A cap that never binds is a cap nobody has checked.

    # Breadth cap: one wide refactor above the 98th percentile.  AGING, not
    # fresh — see docstring note 3.
    wide_caps = ("api-logic", "gateway-integration", "reconciliation",
                 "ledger-adjustment", "deployment-rollback", "release-verification")
    wide_files: tuple[str, ...] = ()
    for k in wide_caps:
        wide_files += paths_for(k, 2, offset=10)
    c(CommitSpec(
        key="wide-refactor", author="priya", capability_keys=wide_caps,
        occurred_at=months_before(13), lines_changed=1840,
        message="Rename settlement_id to settlement_ref across payment services",
        files=wide_files,
    ))

    # Ineligible: bot commit.
    c(CommitSpec(key="bot-bump", author="dependabot[bot]", capability_keys=("api-logic",),
                 occurred_at=months_before(2), lines_changed=14,
                 message="Bump urllib3 from 2.2.1 to 2.2.2",
                 files=("payment-api/logic/requirements.txt", "poetry.lock")))

    # Ineligible: revert.
    c(CommitSpec(key="revert-1", author="amit", capability_keys=("api-logic",),
                 occurred_at=months_before(3), lines_changed=160,
                 message='Revert "Extend request validation for partial captures"',
                 files=paths_for("api-logic", 2, offset=6), is_revert=True))

    # Ineligible: merge commit with no own changes.
    c(CommitSpec(key="merge-1", author="karan", capability_keys=("api-logic",),
                 occurred_at=months_before(2), lines_changed=0,
                 message="Merge branch 'main' into feature/idempotency",
                 files=(), is_merge=True, parents=2))

    # Ineligible: won't-fix ticket.
    t(TicketSpec(key="PAY-780", capability_key="api-logic", assignee="amit",
                 occurred_at=months_before(4), resolution="Won't Do",
                 transitioned_by=None,
                 summary="Support legacy v1 payment payloads",
                 description="Requested by one integrator; superseded by v3."))

    # The deliberately sparse ticket: no component, no label.  Falls through
    # component -> label -> project and lands at tier 3, `probable`.  This is
    # the honest answer to "what happens in an org that doesn't tag things
    # well", and it is demonstrated live.
    t(TicketSpec(key="PAY-777", capability_key=None, assignee="karan",
                 occurred_at=months_before(3), transitioned_by="karan",
                 summary="Investigate intermittent settlement mismatch",
                 description="Occasional mismatch between provider report and ledger "
                             "for reconciliation runs; needs investigation.",
                 with_component=False, with_label=False))

    # Co-authored commit — GitHub rung 1 credits co-authors too.  Without this a
    # pairing session credits only the person who ran `git commit`.
    c(CommitSpec(key="coauth-1", author="karan", capability_keys=("reconciliation",),
                 occurred_at=months_before(7), lines_changed=185,
                 message="Add settlement exception replay tool",
                 files=paths_for("reconciliation", 2, offset=7),
                 co_authors=("sneha",)))

    return p

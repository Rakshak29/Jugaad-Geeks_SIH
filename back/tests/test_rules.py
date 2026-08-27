"""Unit tests for the rules, independent of the dataset.

The validator proves the DATASET exercises the rules correctly.  These prove the
RULES themselves, on constructed inputs, so a rule cannot silently change while
the dataset happens to still produce the same matrix.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.bands import Band, strongest
from app.core.enums import Activity, Certainty, CoverageStatus, Density, Exposure
from app.clustering.similarity import MATCH_FLOOR, score
from app.normalization.roles import (
    github_commit_roles, github_pr_roles, github_review_roles,
    incident_roles, jira_roles,
)
from app.coverage.engine import (
    Edge, World, _age_cap, activity, ceiling_for, density, exposed_components, propagate,
)

AS_OF = datetime(2026, 8, 22, tzinfo=timezone.utc)


class FakeConfig:
    as_of_date = AS_OF
    fresh_window_months = 12
    aging_window_months = 24
    coverage_threshold = Band.MODERATE
    effort_p10 = 50.0
    breadth_p90 = 1.0
    breadth_p98 = 2.0
    density_min = 4.0
    propagation_max_hops = 2


def months_ago(n: float) -> datetime:
    return AS_OF - timedelta(days=n * 30.44)


def make_edge(**kw) -> Edge:
    base = dict(
        employee_id="rahul", capability_id=1, work_unit_id=1, item_id=1,
        raw_record_id=1, source_type="github", record_kind="commit",
        actor_role="author", ceiling_basis="authored the commit",
        occurred_at=months_ago(1), effort_signal=200.0, certainty="certain",
    )
    base.update(kw)
    return Edge(**base)


def make_world(edges, **kw) -> World:
    unit_time = {e.work_unit_id: e.occurred_at for e in edges}
    unit_caps: dict[int, set[int]] = {}
    for e in edges:
        unit_caps.setdefault(e.work_unit_id, set()).add(e.capability_id)
    defaults = dict(
        edges=edges, capabilities={1: "Database Recovery"},
        primary_component={1: "payment-db"}, components_of={1: ["payment-db"]},
        employees={"rahul": {"display_name": "Rahul", "status": "active",
                             "is_service_account": False}},
        dep_edges=[], role_caps={("github", "author"): 2,
                                 ("github", "reviewer_substantive"): 1,
                                 ("incident", "escalation_target"): 3,
                                 ("incident", "resolver"): 3,
                                 ("jira", "transition_actor"): 2},
        unit_time=unit_time, unit_caps=unit_caps, cfg=FakeConfig(),
    )
    defaults.update(kw)
    return World(**defaults)


# ── SC3: band codes are ordinal, never cardinal ──────────────────────────────
class TestBandArithmetic:
    def test_bands_cannot_be_summed(self):
        """Two MODERATE people are not one HIGH person (Piece 0 §6, SC3)."""
        with pytest.raises(TypeError):
            Band.MODERATE + Band.MODERATE

    def test_bands_cannot_be_averaged(self):
        with pytest.raises(TypeError):
            (Band.HIGH + Band.LOW) / 2

    def test_sum_builtin_raises(self):
        """The forbidden optimizer tier — max Σ band_code·y — fails loudly."""
        with pytest.raises(TypeError):
            sum([Band.LOW, Band.MODERATE])

    def test_bands_compare_and_max(self):
        assert Band.HIGH > Band.MODERATE > Band.LOW > Band.NONE
        assert strongest([Band.LOW, Band.HIGH, Band.MODERATE]) is Band.HIGH
        assert strongest([]) is Band.NONE


# ── Stage C: the five ceilings ───────────────────────────────────────────────
class TestAgeCap:
    def test_fresh_within_twelve_months(self):
        assert _age_cap(months_ago(5), FakeConfig()) == (Band.HIGH, "fresh")

    def test_aging_between_twelve_and_twentyfour(self):
        assert _age_cap(months_ago(18), FakeConfig()) == (Band.MODERATE, "aging")

    def test_stale_beyond_twentyfour(self):
        assert _age_cap(months_ago(30), FakeConfig()) == (Band.LOW, "stale")

    def test_thirteen_month_incident_drops_from_high(self):
        """The boundary bites deliberately: a year without touching something is
        a real change in how confidently you can be sent to fix it at 2am."""
        edge = make_edge(source_type="incident", actor_role="resolver",
                         occurred_at=months_ago(13), effort_signal=None)
        assert ceiling_for(edge, make_world([edge])).band is Band.MODERATE


class TestSubstanceCap:
    def test_null_effort_is_a_noop_not_none(self):
        """NULL must be a NO-OP. Returning NONE here would silently zero every
        Jira and incident record — the easiest way to break the engine with no
        test failing."""
        edge = make_edge(source_type="incident", actor_role="resolver", effort_signal=None)
        assert ceiling_for(edge, make_world([edge])).band is Band.HIGH

    def test_trivial_commit_capped_low(self):
        edge = make_edge(effort_signal=3.0)
        c = ceiling_for(edge, make_world([edge]))
        assert c.band is Band.LOW and c.binding_cap == "substance"

    def test_substantial_commit_not_capped_by_substance(self):
        edge = make_edge(effort_signal=500.0)
        assert ceiling_for(edge, make_world([edge])).binding_cap != "substance"


class TestCertaintyCap:
    def test_probable_caps_at_moderate(self):
        edge = make_edge(source_type="incident", actor_role="resolver",
                         effort_signal=None, certainty="probable")
        assert ceiling_for(edge, make_world([edge])).band is Band.MODERATE

    def test_tentative_caps_at_low(self):
        edge = make_edge(source_type="incident", actor_role="resolver",
                         effort_signal=None, certainty="tentative")
        assert ceiling_for(edge, make_world([edge])).band is Band.LOW


class TestBreadthCap:
    def test_wide_change_capped(self):
        """A sweeping refactor still counts — weakly, per capability."""
        edges = [make_edge(capability_id=i, work_unit_id=9) for i in range(1, 7)]
        world = make_world(edges, capabilities={i: f"cap{i}" for i in range(1, 7)},
                           components_of={i: ["c"] for i in range(1, 7)})
        assert ceiling_for(edges[0], world).band is Band.LOW

    def test_normal_change_not_capped(self):
        edge = make_edge()
        assert ceiling_for(edge, make_world([edge])).binding_cap != "breadth"


class TestRoleCap:
    def test_no_github_rung_reaches_high(self):
        """Writing code proves you changed the system; it does not prove you can
        operate it under pressure (Piece 3 §6.1)."""
        edge = make_edge(effort_signal=9999.0)
        assert ceiling_for(edge, make_world([edge])).band <= Band.MODERATE

    def test_escalation_target_reaches_high(self):
        """The strongest signal in the system, and invisible to Git."""
        edge = make_edge(source_type="incident", actor_role="escalation_target",
                         effort_signal=None)
        assert ceiling_for(edge, make_world([edge])).band is Band.HIGH

    def test_unknown_role_yields_none(self):
        edge = make_edge(actor_role="merger_only")
        assert ceiling_for(edge, make_world([edge])).band is Band.NONE


# ── Attributes: orthogonal by construction ───────────────────────────────────
class TestAttributes:
    def test_dormant_when_nothing_fresh(self):
        edge = make_edge(occurred_at=months_ago(20))
        assert activity(1, make_world([edge])) is Activity.DORMANT

    def test_departed_person_fresh_work_still_counts_as_active(self):
        """Activity counts units from ANYONE — filtering to the coverage set
        would make a capability look dormant because its expert left."""
        edge = make_edge(employee_id="vikram", occurred_at=months_ago(2))
        world = make_world([edge], employees={
            "vikram": {"display_name": "Vikram", "status": "departed",
                       "is_service_account": False}})
        assert activity(1, world) is Activity.ACTIVE

    def test_thin_below_density_floor(self):
        edge = make_edge()
        assert density(1, make_world([edge])) is Density.THIN

    def test_adequate_above_floor(self):
        edges = [make_edge(work_unit_id=i, item_id=i) for i in range(1, 6)]
        assert density(1, make_world(edges)) is Density.ADEQUATE


# ── Exposure: against the arrow, two hops, strongest wins ────────────────────
class TestExposure:
    def _world(self):
        edge = make_edge()
        return make_world(
            [edge],
            capabilities={1: "Database Recovery", 2: "API Logic", 3: "Deploy"},
            components_of={1: ["payment-db"], 2: ["payment-api"], 3: ["prod-env"]},
            dep_edges=[("payment-api", "payment-db"), ("prod-env", "payment-api")],
        )

    def test_direct_dependent_is_exposed(self):
        assert propagate([1], self._world())[2] is Exposure.DIRECT

    def test_second_degree_bounded_at_two_hops(self):
        assert propagate([1], self._world())[3] is Exposure.SECOND_DEGREE

    def test_origin_is_not_exposed_via_itself(self):
        assert propagate([1], self._world())[1] is Exposure.NONE

    def test_cycles_terminate(self):
        """Cycles are permitted — real architectures contain them — and the
        two-hop bound makes traversal safe regardless."""
        w = self._world()
        w.dep_edges = [("a", "b"), ("b", "a")]
        w.components_of = {1: ["a"], 2: ["b"], 3: ["c"]}
        assert propagate([1], w) is not None

    def test_sibling_on_same_component_not_exposed(self):
        """Auto-exposing siblings would light up most of the board on every
        simulation; their evidence is independent (Piece 3 §9.3)."""
        w = self._world()
        w.components_of = {1: ["payment-db"], 2: ["payment-db"], 3: ["prod-env"]}
        assert propagate([1], w)[2] is Exposure.NONE

    def test_empty_graph_exposes_nothing(self):
        w = self._world()
        w.dep_edges = []
        assert all(v is Exposure.NONE for v in propagate([1], w).values())


class TestExposedComponents:
    """The at-risk headline counts what `propagate` reaches, not one-hop edges.

    Two numbers for one fact is how a dashboard loses its credibility mid-demo:
    the card draws two hops and the headline counted one, so Schema Migration
    read "2 components depend on it" while the badge said three were exposed.
    """

    def _world(self):
        return make_world(
            [make_edge()],
            capabilities={1: "Schema Migration", 2: "API Logic", 3: "Deploy"},
            components_of={1: ["payment-db"], 2: ["payment-api"], 3: ["prod-env"]},
            dep_edges=[("payment-api", "payment-db"), ("prod-env", "payment-api")],
        )

    def test_counts_both_hops(self):
        assert exposed_components(1, self._world()) == ["payment-api", "prod-env"]

    def test_agrees_with_propagate(self):
        w = self._world()
        reached = {c for cap, exp in propagate([1], w).items()
                   if exp is not Exposure.NONE for c in w.components_of[cap]}
        assert set(exposed_components(1, w)) == reached

    def test_origin_component_never_counts_itself(self):
        assert "payment-db" not in exposed_components(1, self._world())

    def test_empty_graph_exposes_nothing(self):
        w = self._world()
        w.dep_edges = []
        assert exposed_components(1, w) == []


class TestSimilarityTier:
    """Jira ladder tier 4 — TF-IDF cosine (Piece 1 §3.2, DEMO_SCOPE_PLAN §2).

    Pinned on constructed strings, so the rung is tested even though the demo
    dataset tags every ticket and never reaches it.
    """

    SUMMARIES = [
        "gateway charge retry backoff timeout handling for card processor",
        "database schema migration rollback ddl versioning",
    ]

    def test_matches_the_cluster_it_shares_language_with(self):
        row = score(["payment gateway timeout retry backoff on charge"], self.SUMMARIES)[0]
        assert row[0] > row[1]
        assert row[0] >= MATCH_FLOOR

    def test_unrelated_text_falls_below_the_floor(self):
        row = score(["annual leave policy for the finance team"], self.SUMMARIES)[0]
        assert max(row) < MATCH_FLOOR

    def test_empty_inputs_do_not_raise(self):
        assert score([], self.SUMMARIES) == []
        assert score(["anything"], []) == [[]]

    def test_scores_are_deterministic(self):
        """No tie-break rule exists anywhere in this system, so a rung that
        returned a different answer per run would break Piece 5 §8.18."""
        a = score(["gateway retry timeout"], self.SUMMARIES)
        b = score(["gateway retry timeout"], self.SUMMARIES)
        assert a == b


# -----------------------------------------------------------------------------
# Role ladders - all 16 rungs, on constructed payloads.
#
# Nine of these never fire in the demo dataset (the repository has no reachable
# pull requests at all, so every GitHub PR rung is dark). Piece 5's own rule is
# that a rule its data does not exercise is untested - these tests are what stop
# that being true at the RULE level, and validator D6 names the ones the DATASET
# still does not reach.
# -----------------------------------------------------------------------------
class TestGitHubLadder:
    def test_rung1_author(self):
        r = github_commit_roles({"commit": {"author": {"email": "a@sih26.invalid"},
                                            "message": "fix"}})
        assert [(x.actor_role, x.rung) for x in r] == [("author", 1)]

    def test_rung1_co_author_trailer(self):
        """Without this a pairing session credits only whoever ran the commit."""
        r = github_commit_roles({"commit": {
            "author": {"email": "a@sih26.invalid"},
            "message": "fix\n\nCo-authored-by: B <b@sih26.invalid>"}})
        assert [x.native_actor_id for x in r] == ["a@sih26.invalid", "b@sih26.invalid"]

    def test_rung5_merge_commit_is_not_authorship(self):
        r = github_commit_roles({"commit": {"author": {"email": "a@sih26.invalid"},
                                            "message": "Merge pull request #3"},
                                 "parents": [{"sha": "x"}, {"sha": "y"}]})
        assert [(x.actor_role, x.rung) for x in r] == [("merger_only", 5)]

    def test_rung2_pr_author_from_commits_not_opener(self):
        """`user.login` is who OPENED the PR, routinely not who wrote it."""
        r = github_pr_roles({"merged_at": "2026-01-01T00:00:00Z",
                             "user": {"login": "release-bot"},
                             "_commits": [{"commit": {"author": {"email": "real@sih26.invalid"}}}]})
        assert [(x.actor_role, x.native_actor_id) for x in r] == \
               [("pr_author", "real@sih26.invalid")]

    def test_rung2_falls_back_to_opener_without_commit_detail(self):
        r = github_pr_roles({"merged_at": "x", "user": {"login": "priya"}, "_commits": []})
        assert [(x.actor_role, x.native_actor_id) for x in r] == [("pr_author", "priya")]

    def test_unmerged_pr_is_no_evidence(self):
        assert github_pr_roles({"user": {"login": "priya"}}) == []

    def test_merged_at_alone_is_enough(self):
        """The PR LIST endpoint returns merged_at but not merged - checking
        `merged` alone silently disables rung 2 against the real API."""
        assert github_pr_roles({"merged_at": "x", "user": {"login": "p"}})

    def test_rung3_substantive_review(self):
        r = github_review_roles({"user": {"login": "karan"}, "body": "this leaks a cursor"})
        assert [(x.actor_role, x.rung) for x in r] == [("reviewer_substantive", 3)]

    def test_rung4_bare_approval(self):
        r = github_review_roles({"user": {"login": "karan"}, "body": "  "})
        assert [(x.actor_role, x.rung) for x in r] == [("reviewer_approval", 4)]


class TestJiraLadder:
    def _ticket(self, **kw):
        base = {"fields": {}, "changelog": {"histories": []}}
        base.update(kw)
        return base

    def test_rung1_needs_both_transitions(self):
        def hist(to):
            return {"author": {"accountId": "u1"},
                    "items": [{"field": "status", "toString": to}]}
        r = jira_roles(self._ticket(changelog={"histories": [hist("In Progress"), hist("Done")]}))
        assert [(x.actor_role, x.rung) for x in r] == [("transition_actor", 1)]

    def test_one_transition_alone_is_not_rung1(self):
        r = jira_roles(self._ticket(changelog={"histories": [
            {"author": {"accountId": "u1"},
             "items": [{"field": "status", "toString": "In Progress"}]}]}))
        assert all(x.actor_role != "transition_actor" for x in r)

    def test_rung2_assignee_at_resolution(self):
        r = jira_roles(self._ticket(fields={"assignee": {"accountId": "u2"},
                                            "resolution": {"name": "Done"}}))
        assert [(x.actor_role, x.rung) for x in r] == [("assignee_at_resolution", 2)]

    def test_rung4_assignee_who_never_moved_it(self):
        r = jira_roles(self._ticket(fields={"assignee": {"accountId": "u2"}}))
        assert [(x.actor_role, x.rung) for x in r] == [("assignee_only", 4)]

    def test_rung3_substantive_commenter(self):
        r = jira_roles(self._ticket(
            fields={}, comment={"comments": [{"author": {"accountId": "u3"},
                                              "body": "the retry is unbounded"}]}))
        assert [(x.actor_role, x.rung) for x in r] == [("commenter_substantive", 3)]

    def test_empty_comment_is_not_a_rung(self):
        r = jira_roles(self._ticket(
            comment={"comments": [{"author": {"accountId": "u3"}, "body": "  "}]}))
        assert r == []

    def test_rung5_reporter_only(self):
        r = jira_roles(self._ticket(fields={"reporter": {"accountId": "u4"}}))
        assert [(x.actor_role, x.rung) for x in r] == [("reporter_only", 5)]

    def test_strongest_rung_wins_per_actor(self):
        """One person may hold several roles; they are credited once."""
        r = jira_roles(self._ticket(
            fields={"assignee": {"accountId": "u1"}, "reporter": {"accountId": "u1"},
                    "resolution": {"name": "Done"}}))
        assert [(x.actor_role, x.native_actor_id) for x in r] == \
               [("assignee_at_resolution", "u1")]


class TestIncidentLadder:
    def test_rung1_postmortem_author(self):
        """Seeded in role_ceiling with no resolver at all - an incident that
        carried a postmortem fell through to a weaker rung."""
        r = incident_roles({"postmortem": {"author": {"id": "u1"}},
                            "log_entries": [{"type": "resolve_log_entry",
                                             "agent": {"id": "u2", "type": "user_reference"}}]})
        assert ("postmortem_author", 1, "u1") in [(x.actor_role, x.rung, x.native_actor_id)
                                                  for x in r]

    def test_postmortem_counts_without_any_log(self):
        r = incident_roles({"postmortem": {"author": {"id": "u1"}}, "responder": "u2"})
        assert [(x.actor_role, x.rung) for x in r] == \
               [("postmortem_author", 1), ("assigned_no_detail", 5)]

    def test_rung2_escalation_target(self):
        r = incident_roles({"log_entries": [
            {"type": "escalate_log_entry", "agent": {"id": "bot", "type": "service_reference"},
             "assignees": [{"id": "u1", "type": "user_reference"}]}]})
        assert [(x.actor_role, x.rung) for x in r] == [("escalation_target", 2)]

    def test_rung3_resolver(self):
        r = incident_roles({"log_entries": [
            {"type": "resolve_log_entry", "agent": {"id": "u1", "type": "user_reference"}}]})
        assert [(x.actor_role, x.rung) for x in r] == [("resolver", 3)]

    def test_rung4_acknowledged_then_escalated_away(self):
        r = incident_roles({"log_entries": [
            {"type": "acknowledge_log_entry", "agent": {"id": "u1", "type": "user_reference"}}]})
        assert [(x.actor_role, x.rung) for x in r] == [("ack_then_escalated_away", 4)]

    def test_rung5_responder_without_log_detail(self):
        r = incident_roles({"responder": "u1"})
        assert [(x.actor_role, x.rung) for x in r] == [("assigned_no_detail", 5)]

    def test_rung6_notified_only(self):
        r = incident_roles({"log_entries": [
            {"type": "trigger_log_entry", "agent": {"id": "u1", "type": "user_reference"}}]})
        assert [(x.actor_role, x.rung) for x in r] == [("notified_only", 6)]

    def test_escalation_target_outranks_being_the_resolver(self):
        """Rung 2 is the strongest signal in the system: someone else CHOSE
        them. A person holding both is credited at their strongest rung."""
        r = incident_roles({"log_entries": [
            {"type": "escalate_log_entry", "agent": {"id": "bot", "type": "service_reference"},
             "assignees": [{"id": "u1", "type": "user_reference"}]},
            {"type": "resolve_log_entry", "agent": {"id": "u1", "type": "user_reference"}}]})
        assert [(x.actor_role, x.rung) for x in r] == [("escalation_target", 2)]

    def test_monitor_is_never_an_actor(self):
        """Only `user_reference` agents are people. A Datadog monitor that
        triggers an incident is not on the paging list."""
        r = incident_roles({"log_entries": [
            {"type": "trigger_log_entry",
             "agent": {"id": "PMONITOR", "type": "service_reference"}}]})
        assert r == []

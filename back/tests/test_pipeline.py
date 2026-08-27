"""Behaviour tests against the frozen demo database.

These exercise the pipeline's OUTPUT — eligibility, work-unit collapse,
simulation, and the standing commitments — rather than the rules in isolation.
They assume `ece pipeline run` has been executed.
"""

from __future__ import annotations

import pytest

from app.core.bands import Band
from app.core.config_table import Config
from app.core.errors import NotInCoverageSetError
from app.coverage.engine import assign_bands, coverers, load_world
from app.db.conn import connect, query, query_one
from app.domain import services


@pytest.fixture(scope="module")
def conn():
    with connect() as c:
        yield c


@pytest.fixture(scope="module")
def world_and_bands(conn):
    cfg = Config.load(conn)
    w = load_world(conn, cfg)
    return w, assign_bands(w), cfg


@pytest.fixture(scope="module")
def caps(world_and_bands):
    w, _, _ = world_and_bands
    return {v: k for k, v in w.capabilities.items()}


# ── Stage A — eligibility ────────────────────────────────────────────────────
class TestEligibility:
    def test_every_exclusion_records_a_reason(self, conn):
        """The CHECK constraint makes a reasonless exclusion impossible to write;
        this asserts none slipped in through a default."""
        n = query_one(conn, "SELECT count(*) n FROM extracted_item "
                            "WHERE eligibility_state='excluded' AND exclusion_reason IS NULL")["n"]
        assert n == 0

    def test_bot_commits_excluded(self, conn):
        assert query_one(conn, "SELECT count(*) n FROM extracted_item "
                               "WHERE exclusion_reason='bot'")["n"] > 0

    def test_revert_commits_excluded(self, conn):
        assert query_one(conn, "SELECT count(*) n FROM extracted_item "
                               "WHERE exclusion_reason='revert'")["n"] > 0

    def test_non_work_resolutions_excluded(self, conn):
        assert query_one(conn, "SELECT count(*) n FROM extracted_item "
                               "WHERE exclusion_reason='non_work_resolution'")["n"] > 0

    def test_merge_button_commits_do_not_earn_authorship(self, conn):
        """GitHub's merge button authors the commit as whoever clicked it.
        Crediting that as rung-1 authorship would reward merging, not building."""
        n = query_one(conn, "SELECT count(*) n FROM extracted_item "
                            "WHERE actor_role='merger_only' "
                            "AND eligibility_state='eligible'")["n"]
        assert n == 0

    def test_departed_employees_are_never_excluded(self, conn):
        """Eligibility asks whether work happened, not whether the person is
        still here. Removing their evidence would delete the finding."""
        n = query_one(conn, """
            SELECT count(*) n FROM extracted_item ei
            JOIN employee e ON e.employee_id = ei.employee_id
            WHERE e.status='departed' AND ei.eligibility_state='excluded'
              AND ei.exclusion_reason NOT IN ('bot','revert','merge_commit',
                                              'generated_paths','non_work_resolution',
                                              'reporter_only','notified_only',
                                              'unresolved_ticket','merger_only')
        """)["n"]
        assert n == 0

    def test_excluded_items_never_reach_the_evidence_view(self, conn):
        """Enforced by the view's WHERE clause, not by discipline."""
        n = query_one(conn, """
            SELECT count(*) n FROM evidence_edge ee
            JOIN extracted_item ei ON ei.item_id = ee.item_id
            WHERE ei.eligibility_state <> 'eligible'
        """)["n"]
        assert n == 0


# ── Stage B — work units ─────────────────────────────────────────────────────
class TestWorkUnits:
    def test_an_item_belongs_to_exactly_one_unit(self, conn):
        n = query_one(conn, "SELECT count(*) n FROM (SELECT item_id FROM work_unit_member "
                            "GROUP BY item_id HAVING count(*) > 1) x")["n"]
        assert n == 0

    def test_multi_record_units_exist(self, conn):
        """One task leaves a ticket, a commit and a PR. Counting three would
        inflate an afternoon into a pattern."""
        assert query_one(conn, "SELECT count(*) n FROM work_unit "
                               "WHERE member_count > 1")["n"] > 0

    def test_a_multi_source_unit_exists(self, conn):
        """The cross-source collapse actually fires on real data."""
        rows = query(conn, """
            SELECT wu.work_unit_id, count(DISTINCT ei.source_type) AS sources
            FROM work_unit wu
            JOIN work_unit_member wm ON wm.work_unit_id = wu.work_unit_id
            JOIN extracted_item ei ON ei.item_id = wm.item_id
            GROUP BY wu.work_unit_id HAVING count(DISTINCT ei.source_type) > 1
        """)
        assert rows, "no work unit spans more than one source"

    def test_unit_occurred_at_is_the_latest_member(self, conn):
        bad = query(conn, """
            SELECT wu.work_unit_id FROM work_unit wu
            JOIN work_unit_member wm ON wm.work_unit_id = wu.work_unit_id
            JOIN extracted_item ei ON ei.item_id = wm.item_id
            GROUP BY wu.work_unit_id, wu.occurred_at
            HAVING max(ei.occurred_at) <> wu.occurred_at
        """)
        assert not bad


# ── Simulation ───────────────────────────────────────────────────────────────
class TestSimulation:
    def test_rahul_matches_expected(self, conn):
        s = services.simulate(conn, "rahul")["summary"]
        assert (s["lost"], s["degraded"], s["maintained"], s["uncovered"]) == (1, 4, 2, 1)

    def test_database_recovery_is_lost_with_a_named_closest(self, conn):
        dbr = next(c for c in services.simulate(conn, "rahul")["capabilities"]
                   if c["name"] == "Database Recovery")
        assert dbr["status"] == "Lost"
        assert dbr["coverers_after"] == 0
        # "None remaining" would claim nobody has ANY evidence, usually false.
        assert dbr["best_band_after"] == "LOW"
        assert dbr["best_band_after_holder"]["display_name"] == "Amit Desai"

    def test_pre_existing_gap_never_reads_as_lost(self, conn):
        """The failure Piece 3 §12 exists to prevent."""
        for who in ("rahul", "karan", "priya", "sneha", "amit"):
            schema = next(c for c in services.simulate(conn, who)["capabilities"]
                          if c["name"] == "Schema Migration")
            assert schema["status"] == "Uncovered", f"{who} -> {schema['status']}"

    def test_simulating_a_departed_person_is_rejected(self, conn):
        """A departed employee is already a permanent unavailability."""
        with pytest.raises(NotInCoverageSetError):
            services.simulate(conn, "vikram")

    def test_activity_and_density_are_unchanged_by_simulation(self, conn):
        base = {c["name"]: (c["activity"], c["density"])
                for c in services.get_overview(conn)["capabilities"]}
        after = {c["name"]: (c["activity"], c["density"])
                 for c in services.simulate(conn, "karan")["capabilities"]}
        assert base == after

    def test_simulation_writes_nothing(self, conn):
        before = query_one(conn, "SELECT count(*) n FROM extracted_item")["n"]
        services.simulate(conn, "rahul")
        assert query_one(conn, "SELECT count(*) n FROM extracted_item")["n"] == before


# ── Standing commitments ─────────────────────────────────────────────────────
class TestStandingCommitments:
    def test_no_capability_carries_a_band(self, conn):
        """A band is always a person x capability pair (Piece 6 §2.1)."""
        for c in services.get_overview(conn)["capabilities"]:
            assert "band" not in c
        for c in services.simulate(conn, "rahul")["capabilities"]:
            assert "band" not in c

    def test_every_response_claim_carries_its_origin(self, conn):
        for c in services.get_overview(conn)["capabilities"]:
            for coverer in c["coverers"]:
                assert coverer["raw_record_id"], f"{c['name']}/{coverer['employee_id']}"
                assert coverer["ceiling_basis"]

    def test_evidence_rows_reach_a_raw_record(self, conn):
        caps = services.get_overview(conn)["capabilities"]
        ev = services.get_evidence(conn, caps[0]["capability_id"])
        for person in ev["by_person"]:
            for item in person["items"]:
                assert services.get_raw_record(conn, item["raw_record_id"])["payload"]

    def test_no_percentage_appears_in_any_response(self, conn):
        """The system produces qualitative, defensible categories on purpose."""
        import json
        blob = json.dumps([services.get_overview(conn), services.get_at_risk(conn),
                           services.simulate(conn, "rahul")])
        assert "percent" not in blob.lower() and "%" not in blob

    def test_departed_people_never_appear_as_coverers(self, conn):
        for c in services.get_overview(conn)["capabilities"]:
            assert "vikram" not in {x["employee_id"] for x in c["coverers"]}

    def test_departed_evidence_is_still_visible(self, conn):
        """It is what explains the gap."""
        holders = [c["departed_holders"] for c in services.get_overview(conn)["capabilities"]]
        assert any(h for h in holders)

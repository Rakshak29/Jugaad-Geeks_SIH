"""The acceptance gate.

Piece 5 §1: *"dataset validation passes before the evidence engine is considered
working. A rule tested against data that doesn't exercise it is untested."*

Two design rules, both deliberate:

  * **It runs every assertion, then reports.**  Stopping at the first failure
    tells you one thing is broken; running them all tells you six are, which is
    what you actually need at 2am the night before a demo.
  * **It fails loudly.**  A validator that warns is a validator that gets
    ignored.  Non-zero exit, the offending row named, and the Piece reference
    that says what should have happened.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import typer

from app.core.bands import Band
from app.core.config_table import Config
from app.coverage.engine import (
    activity, assign_bands, ceiling_for, coverers, density, load_world, propagate,
)
from app.dataset.spec import (
    AT_RISK_SINGLE_COVERER, AT_RISK_UNCOVERED, BASELINE_COVERERS,
    CAPABILITY_BY_KEY, INTENDED_BANDS, PEOPLE, REQUIRED_RULE_COVERAGE,
)
from app.db.conn import connect, query, query_one
from app.domain import services


@dataclass
class Result:
    ident: str
    name: str
    passed: bool
    detail: str = ""
    reference: str = ""
    offenders: list[str] = field(default_factory=list)


class Checks:
    def __init__(self) -> None:
        self.results: list[Result] = []

    def add(self, ident, name, passed, detail="", reference="", offenders=None):
        self.results.append(Result(ident, name, bool(passed), detail, reference,
                                   offenders or []))


# ─────────────────────────────────────────────────────────────────────────────
def run_validation() -> bool:
    c = Checks()
    with connect() as conn:
        cfg = Config.load(conn)
        world = load_world(conn, cfg)
        bands = assign_bands(world)
        name_to_id = {v: k for k, v in world.capabilities.items()}

        _referential(c, conn, world)
        _structural(c, conn, world, name_to_id)
        _distributional(c, conn, world, bands)
        _scenario(c, conn, world, bands, cfg, name_to_id)
        _optimizer(c, conn)
        _integrity(c, conn, world, bands)

    return _report(c)


# ── Referential ──────────────────────────────────────────────────────────────
def _referential(c: Checks, conn, world) -> None:
    orphans = query_one(conn, """
        SELECT count(*) n FROM extracted_item ei
        LEFT JOIN raw_record rr ON rr.raw_record_id = ei.raw_record_id
        WHERE rr.raw_record_id IS NULL
    """)["n"]
    c.add("R1", "Every item resolves to a raw record", orphans == 0,
          f"{orphans} orphaned items", "Piece 2 §5.1")

    bad_ident = query(conn, """
        SELECT si.native_actor_id FROM source_identity si
        LEFT JOIN employee e ON e.employee_id = si.employee_id
        WHERE e.employee_id IS NULL
    """)
    c.add("R2", "Every source_identity maps to a real employee", not bad_ident,
          f"{len(bad_ident)} dangling", "Piece 2 §6.2",
          [r["native_actor_id"] for r in bad_ident])

    # An unmapped actor holding ELIGIBLE evidence is a real data-quality problem:
    # it makes the system understate coverage. One holding only excluded records
    # costs nothing.
    lost = query(conn, """
        SELECT native_actor_id, count(*) n FROM extracted_item
        WHERE employee_id IS NULL AND eligibility_state='eligible'
        GROUP BY native_actor_id ORDER BY n DESC
    """)
    known_single_account_artifact = {"krish-exe"}
    unexpected = [r for r in lost if r["native_actor_id"] not in known_single_account_artifact]
    c.add("R3", "No unexpected actor loses eligible evidence", not unexpected,
          f"{len(unexpected)} unmapped actors hold eligible evidence", "Piece 2 §12",
          [f"{r['native_actor_id']} ({r['n']} records)" for r in unexpected])

    self_edges = query_one(conn, "SELECT count(*) n FROM dependency_edge "
                                 "WHERE from_component = to_component")["n"]
    c.add("R4", "No self-edges in the dependency graph", self_edges == 0,
          f"{self_edges} self-edges", "Piece 2 §7.3")

    # Piece 5 §8.3, second half. The FK makes this true today; the check exists
    # because the dependency editor writes here at runtime and a future
    # auto-extraction path would too — an edge to a component nobody seeded
    # would silently drop a whole branch of exposure propagation.
    dangling = query(conn, """
        SELECT de.from_component, de.to_component FROM dependency_edge de
        LEFT JOIN component f ON f.component_id = de.from_component
        LEFT JOIN component t ON t.component_id = de.to_component
        WHERE f.component_id IS NULL OR t.component_id IS NULL
    """)
    c.add("R5", "Every dependency edge references existing components", not dangling,
          f"{len(dangling)} dangling edges", "Piece 5 §8.3",
          [f"{r['from_component']}->{r['to_component']}" for r in dangling])

    # Piece 5 §8.1. S3 proves every capability HAS a component; this proves the
    # component it points at exists and belongs to a service.
    orphan_map = query(conn, """
        SELECT cc.capability_node_id, cc.component_id FROM capability_component cc
        LEFT JOIN component c ON c.component_id = cc.component_id
        WHERE c.component_id IS NULL OR c.service IS NULL
    """)
    c.add("R6", "Every capability-component mapping resolves to a real service",
          not orphan_map, f"{len(orphan_map)} unresolved mappings", "Piece 5 §8.1",
          [f"{r['capability_node_id']}->{r['component_id']}" for r in orphan_map])


# ── Structural ───────────────────────────────────────────────────────────────
def _structural(c: Checks, conn, world, name_to_id) -> None:
    expected = {cap.name for cap in CAPABILITY_BY_KEY.values()}
    found = set(world.capabilities.values())
    c.add("S1", "Discovery reproduces the target capability tree", found == expected,
          f"expected {len(expected)}, found {len(found)}", "Piece 5 §2",
          sorted(expected.symmetric_difference(found)))

    ancestors = query(conn, """
        WITH RECURSIVE walk AS (
            SELECT node_id AS root, node_id AS cur FROM cluster_node WHERE node_role='capability'
          UNION ALL
            SELECT w.root, n.node_id FROM walk w JOIN cluster_node n ON n.parent_id = w.cur)
        SELECT w.root FROM walk w JOIN cluster_node n ON n.node_id = w.cur
        WHERE n.node_role='capability' AND w.root <> w.cur
    """)
    c.add("S2", "No capability is an ancestor of another (I1)", not ancestors,
          f"{len(ancestors)} violations", "Piece 2 §10 I1")

    unmapped = query(conn, """
        SELECT n.name FROM cluster_node n
        LEFT JOIN capability_component cc ON cc.capability_node_id = n.node_id
        WHERE n.node_role='capability' AND cc.capability_node_id IS NULL
    """)
    c.add("S3", "Every capability maps to a component (I3)", not unmapped,
          f"{len(unmapped)} unmapped", "Piece 2 §10 I3",
          [r["name"] for r in unmapped])

    pending = query_one(conn, "SELECT count(*) n FROM cluster_membership "
                              "WHERE review_state='pending_review'")["n"]
    c.add("S4", "No membership awaits review at freeze (I7)", pending == 0,
          f"{pending} pending", "Piece 2 §10 I7")

    frozen = query_one(conn, "SELECT count(*) n FROM tree_version WHERE status='frozen'")["n"]
    c.add("S5", "Exactly one frozen tree version", frozen == 1,
          f"{frozen} frozen versions", "Piece 2 §7.1")

    # A multi-record work unit must exist, or the "one task is not three" claim
    # is untested.
    multi = query_one(conn, "SELECT count(*) n FROM work_unit WHERE member_count > 1")["n"]
    c.add("S6", "At least one multi-record work unit exists", multi > 0,
          f"{multi} multi-record units", "Piece 3 §5.1")

    # Piece 5 §8.7 — cross-task contamination.
    #
    # A unit that spans capabilities is fine when a sweeping change genuinely
    # touched them; it is a DEFECT when the members were collapsed without an
    # explicit reference joining them, because then unrelated work has been
    # merged and the breadth cap will quietly weaken evidence that deserved
    # full weight. Every multi-member unit here must be joined by a `certain`
    # reference — which is exactly what `build_work_units` claims to require.
    contaminated = query(conn, """
        SELECT wu.work_unit_id,
               count(DISTINCT cd.capability_node_id) AS caps,
               wu.member_count
        FROM work_unit wu
        JOIN work_unit_member wm ON wm.work_unit_id = wu.work_unit_id
        JOIN cluster_membership cm ON cm.item_id = wm.item_id
        JOIN capability_descendant cd ON cd.descendant_id = cm.node_id
        WHERE wu.member_count > 1
        GROUP BY wu.work_unit_id, wu.member_count
        HAVING count(DISTINCT cd.capability_node_id) > 1
    """)
    unjustified = []
    for row in contaminated:
        shared = query_one(conn, """
            SELECT count(*) n FROM cluster_membership cm
            JOIN work_unit_member wm ON wm.item_id = cm.item_id
            WHERE wm.work_unit_id = %s AND cm.certainty <> 'certain'
        """, (row["work_unit_id"],))["n"]
        if shared:
            unjustified.append(f"unit {row['work_unit_id']} spans "
                               f"{row['caps']} capabilities on non-certain links")
    c.add("S7", "No work unit merges unrelated tasks (§8.7)", not unjustified,
          f"{len(unjustified)} contaminated units", "Piece 5 §8.7", unjustified)


# ── Distributional ───────────────────────────────────────────────────────────
def _distributional(c: Checks, conn, world, bands) -> None:
    labels = set()
    binding = set()
    for e in world.edges:
        ceil = ceiling_for(e, world)
        labels.add(ceil.age_label)
        binding.add(ceil.binding_cap)

    c.add("D1", "All three age windows are populated",
          {"fresh", "aging", "stale"} <= labels,
          f"found {sorted(labels)}", "Piece 5 §8.8")

    # A cap that never binds is a cap nobody has checked.
    required = {"role", "age", "breadth", "certainty", "substance"}
    c.add("D2", "Every ceiling binds on at least one unit", required <= binding,
          f"never binding: {sorted(required - binding)}", "Piece 5 §8.10",
          sorted(required - binding))

    via_incident = any(
        br.band == Band.HIGH and not br.via_authorship
        for person in bands.values() for br in person.values())
    via_authorship = any(
        br.via_authorship for person in bands.values() for br in person.values())
    c.add("D3", "Both routes to HIGH occur", via_incident and via_authorship,
          f"incident={via_incident} authorship={via_authorship}", "Piece 5 §8.9")

    thin = [cap for cap in world.capabilities if density(cap, world).value == "Thin"]
    dormant = [cap for cap in world.capabilities if activity(cap, world).value == "Dormant"]
    c.add("D4", "At least one Thin and one Dormant capability",
          bool(thin) and bool(dormant),
          f"thin={len(thin)} dormant={len(dormant)}", "Piece 5 §8.11")

    # Routine code activity must never reach HIGH without dominance.
    offenders = []
    for person, caps in bands.items():
        for cap, br in caps.items():
            if br.band == Band.HIGH and not br.via_authorship and br.basis:
                if br.basis.ceiling_basis and "commit" in br.basis.ceiling_basis:
                    offenders.append(f"{person}/{world.capabilities[cap]}")
    c.add("D5", "Code activity alone never reaches HIGH", not offenders,
          f"{len(offenders)} violations", "Piece 3 §7.1", offenders)

    _rung_coverage(c, conn)


#: Ladder rungs this dataset does not reach, each with the reason it does not.
#:
#: The same pattern as R3's `known_single_account_artifact`, for the same
#: reason: an unexercised rung IS a gap, and the honest handling is to name it
#: in the repository rather than to leave the check out. The rules themselves
#: are pinned on constructed payloads in `tests/test_rules.py` — these are the
#: rungs no RECORD in the demo data lands on.
#:
#: A rung that starts firing fails this check too, and that is deliberate: it
#: means the dataset changed shape and the expected matrix needs re-deriving.
UNEXERCISED_RUNGS: dict[tuple[str, str], str] = {
    ("github", "pr_author"):
        "the constructed repository has no pull request whose merge commit is "
        "still reachable from the default branch, so no PR record is ingested",
    ("github", "reviewer_substantive"):
        "no PR records, therefore no reviews",
    ("github", "reviewer_approval"):
        "GitHub does not permit approving your own pull request, and the "
        "repository is single-account",
    ("github", "merger_only"):
        "the constructed history is linear — no merge commits to credit",
    ("jira", "commenter_substantive"):
        "the generated tickets carry no comment thread",
    ("jira", "assignee_only"):
        "every generated ticket resolves, so an assignee is always an "
        "assignee-at-resolution",
    ("incident", "postmortem_author"):
        "PagerDuty exposes postmortems as a separate resource and the generator "
        "emits none; the rung is `bonus` availability and the resolver is "
        "pinned by unit test",
    ("incident", "assigned_no_detail"):
        "every generated incident carries log_entries, so the flat-responder "
        "fallback never fires",
    ("incident", "notified_only"):
        "incidents are triggered by a monitor, which is a service_reference "
        "and never an actor",
}


def _rung_coverage(c: Checks, conn) -> None:
    """Which of the 16 ladder rungs any real record actually lands on.

    Piece 1 §3.2 declares all 16 as built and Piece 5 §1 says a rule its data
    does not exercise is untested. Both are true at once here, and the only
    honest way to hold them together is to state exactly which rungs the data
    reaches and which it does not.
    """
    defined = {(r["source_type"], r["role"]) for r in query(
        conn, "SELECT source_type, role FROM role_ceiling")}
    fired_roles = {r["actor_role"] for r in query(
        conn, "SELECT DISTINCT actor_role FROM extracted_item "
              "WHERE actor_role IS NOT NULL")}
    dark = {rung for rung in defined if rung[1] not in fired_roles}

    documented = set(UNEXERCISED_RUNGS)
    undocumented = sorted(f"{s}/{r}" for s, r in dark - documented)
    unexpectedly_live = sorted(f"{s}/{r}" for s, r in documented - dark)

    c.add("D6", "Every ladder rung either fires or is a documented gap",
          not undocumented and not unexpectedly_live,
          f"{len(dark)}/{len(defined)} rungs dark; "
          f"{len(undocumented)} undocumented, "
          f"{len(unexpectedly_live)} newly firing", "Piece 1 §3.2; Piece 5 §1",
          [f"UNDOCUMENTED dark rung: {r}" for r in undocumented]
          + [f"now fires, remove from UNEXERCISED_RUNGS: {r}" for r in unexpectedly_live])


# ── Scenario ─────────────────────────────────────────────────────────────────
def _scenario(c: Checks, conn, world, bands, cfg, name_to_id) -> None:
    mismatches = []
    for key, expected in BASELINE_COVERERS.items():
        cap_name = CAPABILITY_BY_KEY[key].name
        cap_id = name_to_id.get(cap_name)
        if cap_id is None:
            mismatches.append(f"{cap_name}: capability missing")
            continue
        got = set(coverers(cap_id, world.coverage_set, bands, cfg))
        if got != set(expected):
            mismatches.append(f"{cap_name}: expected {sorted(expected)}, got {sorted(got)}")
    c.add("C1", "Baseline coverage matrix matches expected exactly", not mismatches,
          f"{len(mismatches)} capabilities differ", "Piece 5 §5.1", mismatches)

    band_mismatch = []
    for (person, cap_key), expected_band in INTENDED_BANDS.items():
        cap_id = name_to_id.get(CAPABILITY_BY_KEY[cap_key].name)
        if cap_id is None:
            continue
        got = bands.get(person, {}).get(cap_id)
        if got is None or got.band != expected_band:
            band_mismatch.append(
                f"{person}/{cap_key}: expected {expected_band.name}, "
                f"got {got.band.name if got else 'MISSING'}")
    c.add("C2", "Every intended person x capability band is produced", not band_mismatch,
          f"{len(band_mismatch)} bands differ", "Piece 5 §5.1", band_mismatch)

    at_risk = services.get_at_risk(conn)
    uncovered = {i["name"] for i in at_risk["items"] if i["category"] == "uncovered"}
    single = {i["name"] for i in at_risk["items"] if i["category"] == "single_coverer"}
    exp_unc = {CAPABILITY_BY_KEY[k].name for k in AT_RISK_UNCOVERED}
    exp_sing = {CAPABILITY_BY_KEY[k].name for k in AT_RISK_SINGLE_COVERER}
    c.add("C3", "At-risk list is exactly Uncovered + single-coverer",
          uncovered == exp_unc and single == exp_sing,
          f"uncovered={sorted(uncovered)} single={sorted(single)}", "Piece 4 §2.2")

    # Case A — the canonical simulation.
    sim = services.simulate(conn, "rahul")
    s = sim["summary"]
    c.add("C4", "Rahul simulation: 1 Lost, 4 Degraded, 2 Maintained, 1 Uncovered",
          (s["lost"], s["degraded"], s["maintained"], s["uncovered"]) == (1, 4, 2, 1),
          f"got {s}", "Piece 5 §5.2")

    dbr = next(x for x in sim["capabilities"] if x["name"] == "Database Recovery")
    c.add("C5", "Database Recovery goes Lost with a named closest candidate",
          dbr["status"] == "Lost" and dbr["coverers_after"] == 0
          and dbr["best_band_after"] == "LOW"
          and dbr["best_band_after_holder"] is not None,
          f"status={dbr['status']} after={dbr['coverers_after']} "
          f"band={dbr['best_band_after']}", "Piece 5 §5.2")

    # The failure Piece 3 §12 exists to prevent: a pre-existing gap must never
    # be reported as Lost (blaming the simulated person) nor as Maintained.
    schema = next(x for x in sim["capabilities"] if x["name"] == "Schema Migration")
    c.add("C6", "Pre-existing gap stays Uncovered under simulation",
          schema["status"] == "Uncovered",
          f"got {schema['status']}", "Piece 3 §12")

    # Case D — the stale expert.
    karan_schema = bands["karan"][name_to_id["Schema Migration"]]
    c.add("C7", "Stale evidence is age-capped below the threshold (Case D)",
          karan_schema.band == Band.LOW
          and karan_schema.basis and karan_schema.basis.binding_cap == "age",
          f"band={karan_schema.band.name} "
          f"binding={karan_schema.basis.binding_cap if karan_schema.basis else None}",
          "Piece 5 §5.6")

    # Case C — the misleading commit count.
    amit_api = bands["amit"][name_to_id["API Logic"]]
    c.add("C8", "High commit volume alone caps at MODERATE (Case C)",
          amit_api.band == Band.MODERATE and not amit_api.via_authorship,
          f"band={amit_api.band.name}", "Piece 5 §5.5")

    # The departed expert explains the gap rather than leaving it unexplained.
    vikram = bands["vikram"][name_to_id["Schema Migration"]]
    c.add("C9", "Departed employee's evidence is retained and visible",
          vikram.band >= Band.MODERATE
          and "vikram" not in coverers(name_to_id["Schema Migration"],
                                       world.coverage_set, bands, cfg),
          f"band={vikram.band.name}, in coverage set={'vikram' in world.coverage_set}",
          "Piece 3 §4.1")

    # Exposure is orthogonal: emptying the dependency graph must change no band
    # and no coverage status.
    origins = [cap for cap in world.capabilities
               if not coverers(cap, world.coverage_set, bands, cfg)]
    with_graph = propagate(origins, world)
    kept_edges = world.dep_edges
    try:
        world.dep_edges = []
        without = propagate(origins, world)
        bands_after = assign_bands(world)
    finally:
        # Restore: `world` is shared with every check that runs after this one,
        # and leaving it edgeless would silently weaken them.
        world.dep_edges = kept_edges
    unchanged = all(bands[p][cc].band == bands_after[p][cc].band
                    for p in bands for cc in bands[p])
    c.add("C10", "Exposure is orthogonal — removing the graph changes no band",
          unchanged and any(v.value != "none" for v in with_graph.values())
          and all(v.value == "none" for v in without.values()),
          "bands changed when the dependency graph was emptied" if not unchanged else "",
          "Piece 3 §2.6, §9.4")


# ── Optimizer (Piece 4 §8, §9; Piece 5 §8.14–15) ────────────────────────────
def _optimizer(c: Checks, conn) -> None:
    plan_rahul = services.coverage_plan(conn, employee_id="rahul")
    team_rahul = {t["employee_id"] for t in plan_rahul["team"]}

    c.add("O1", "Simulate Rahul -> one-person team that absorbs four of five",
          plan_rahul["objective"]["people"] == 1 and team_rahul == {"karan"},
          f"team={sorted(team_rahul)} objective={plan_rahul['objective']}",
          "Piece 5 §5.2")

    db_gap = next((g for g in plan_rahul["residual_gaps"]
                   if g["name"] == "Database Recovery"), None)
    c.add("O2", "Residual gap names who is closest and why",
          db_gap is not None and db_gap["closest"] is not None
          and db_gap["closest"]["display_name"] == "Amit Desai"
          and db_gap["closest"]["band"] == "LOW"
          and db_gap["closest"]["raw_record_id"] is not None,
          f"{db_gap and db_gap['why']}",
          "Piece 4 §6; Piece 5 §5.2")

    plan_karan = services.coverage_plan(conn, employee_id="karan")
    team_karan = {t["employee_id"] for t in plan_karan["team"]}
    greedy = plan_karan.get("greedy_baseline", {}).get("size")

    c.add("O3", "Case F — greedy 3, CP-SAT 2",
          plan_karan["objective"]["people"] == 2
          and team_karan == {"priya", "sneha"}
          and greedy == 3,
          f"exact={plan_karan['objective']['people']} team={sorted(team_karan)} greedy={greedy}",
          "Piece 4 §9; Piece 5 §5.8, §8.14")

    c.add("O4", "No capability is abandoned when a team exists (exact solver)",
          plan_karan["objective"]["abandoned"] == 0
          and plan_rahul["objective"]["abandoned"] == 1,  # DB Recovery uncovered — forced
          "karan abandons nothing; rahul's gap is the shutdown of Database Recovery",
          "Piece 4 §4.1")

    both_unique = (plan_rahul.get("uniqueness", {}).get("verified")
                   and plan_karan.get("uniqueness", {}).get("verified"))
    c.add("O5", "Both demo optima are unique (no-good-cut re-solve)",
          both_unique,
          f"rahul={plan_rahul.get('uniqueness')} karan={plan_karan.get('uniqueness')}",
          "Piece 4 §8; Piece 5 §8.15")

    # Case E — the Uncovered entry point (Piece 4 §2.2, Piece 5 §5.7).
    #
    # This path is structurally different: it must NEVER construct the model.
    # A `solver` of null is the assertion that no optimisation ran, and it is
    # the check that stops the two entry points quietly converging.
    schema_id = query_one(conn, "SELECT node_id FROM cluster_node "
                                "WHERE node_role='capability' AND name='Schema Migration'")
    plan_uncovered = services.coverage_plan(conn, capability_id=schema_id["node_id"])
    gap = (plan_uncovered["residual_gaps"] or [None])[0]
    c.add("O6", "Case E — Uncovered capability answers without running the solver",
          plan_uncovered["basis"]["kind"] == "uncovered"
          and plan_uncovered["solver"] is None
          and plan_uncovered["team"] == []
          and gap is not None and gap["closest"] is not None
          and gap["closest"]["employee_id"] == "karan"
          and gap["closest"]["band"] == "LOW",
          f"solver={plan_uncovered['solver']} closest={gap and gap['closest']}",
          "Piece 4 §2.2, §6; Piece 5 §5.7")

    # Every residual gap must carry a traceable closest candidate.
    untraceable = []
    for plan in (plan_rahul, plan_karan, plan_uncovered):
        for g in plan["residual_gaps"]:
            if g["closest"] is None or not g["closest"]["raw_record_id"]:
                untraceable.append(g["name"])
    c.add("O7", "Every residual gap names a closest candidate with its record",
          not untraceable, f"untraceable: {untraceable}", "Piece 4 §6; SC6")


# ── Integrity ────────────────────────────────────────────────────────────────
def _integrity(c: Checks, conn, world, bands) -> None:
    score_cols = query(conn, """
        SELECT column_name FROM information_schema.columns
        WHERE table_name='employee'
          AND column_name ~* '(score|rating|rank|level|seniority|points)'
    """)
    c.add("I1", "No numeric expertise score exists in the schema", not score_cols,
          f"found {[r['column_name'] for r in score_cols]}", "Piece 0 §6 SC1",
          [r["column_name"] for r in score_cols])

    untraceable = []
    for person, caps in bands.items():
        for cap, br in caps.items():
            if br.band > Band.NONE and (br.basis is None or not br.basis.raw_record_id):
                untraceable.append(f"{person}/{world.capabilities[cap]}")
    c.add("I2", "Every band traces to a raw record", not untraceable,
          f"{len(untraceable)} untraceable bands", "Piece 0 §6 SC6", untraceable)

    try:
        sum([Band.LOW, Band.MODERATE])
        summable = True
    except TypeError:
        summable = False
    c.add("I3", "Band codes cannot be summed", not summable,
          "sum(bands) did not raise", "Piece 0 §6 SC3")

    # Two consecutive runs must produce identical output.
    a = services.get_overview(conn)
    b = services.get_overview(conn)
    c.add("I4", "Two consecutive runs are identical", a == b,
          "overview differed between runs", "Piece 5 §8.18")

    # No model is reachable from the engine.
    import importlib, sys
    engine_mods = ["app.coverage.engine", "app.domain.services", "app.api.main",
                   "app.graph" if "app.graph" in sys.modules else "app.coverage.engine"]
    leaked = []
    for mod_name in set(engine_mods):
        try:
            mod = importlib.import_module(mod_name)
        except Exception:
            continue
        for attr in ("anthropic", "openai", "sentence_transformers"):
            if hasattr(mod, attr):
                leaked.append(f"{mod_name}.{attr}")
    c.add("I5", "No model library is reachable from the engine path", not leaked,
          f"leaked: {leaked}", "Piece 0 §6 SC9", leaked)

    missing = Config.load(conn).missing_derived()
    c.add("I6", "Every derived threshold was calibrated", not missing,
          f"missing {missing}", "Piece 3 §13", missing)


# ── Report ───────────────────────────────────────────────────────────────────
def _report(c: Checks) -> bool:
    passed = [r for r in c.results if r.passed]
    failed = [r for r in c.results if not r.passed]

    typer.secho("\nDATASET VALIDATION", fg="cyan", bold=True)
    for r in c.results:
        mark = "PASS" if r.passed else "FAIL"
        colour = "green" if r.passed else "red"
        typer.secho(f"  {mark}  {r.ident:4} {r.name}", fg=colour)
        if not r.passed:
            if r.detail:
                typer.secho(f"          {r.detail}", fg="red")
            for off in r.offenders[:8]:
                typer.secho(f"            · {off}", fg="red")
            if r.reference:
                typer.secho(f"          expected by {r.reference}", fg="bright_black")

    typer.secho(f"\n  {len(passed)}/{len(c.results)} checks passed",
                fg="green" if not failed else "red", bold=True)
    if failed:
        typer.secho("  The dataset is NOT usable. Fix the data, never the threshold.",
                    fg="red", bold=True)
    return not failed

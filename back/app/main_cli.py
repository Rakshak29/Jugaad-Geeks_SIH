"""`ece` — the pipeline as a command line.

Every stage is separately runnable and separately observable.  That is the point:
the panel's Round 1 question was *"demonstrate how these heterogeneous sources
will actually be accessed, normalized and linked"*, and the honest answer is a
terminal where you can watch each stage happen and inspect what it wrote.

    ece db init                  create the schema and seed the rules
    ece dataset generate         write Jira + incident JSON, and the repo plan
    ece dataset repo             build and push the constructed GitHub repository
    ece dataset capture          snapshot the ingested payloads as the fixture set
    ece ingest --live            pull from the real GitHub API + the generators
    ece ingest --fixture         replay the captured payloads, offline
    ece normalize                three payload shapes -> one row shape
    ece normalize --explain KEY  walk the Jira ladder on one ticket, out loud
    ece discover                 within-source clustering, cross-source linking, tier 4
    ece name                     propose a name per capability
    ece approve                  the human gate — names, components, tier-4 review
    ece freeze                   invariants -> work units -> calibration -> freeze
    ece pipeline run             all of the above, in order
    ece report baseline          the coverage matrix, from a script
    ece report units             work units — one piece of work, not four records
    ece report ladders           the 16 rungs, and which this dataset reaches
    ece report config            every value the system reads, and why
    ece simulate rahul           before/after, from a script
    ece optimize --simulate rahul    the Minimum Coverage Team + residual gap
    ece optimize --simulate karan --greedy   Case F: greedy 3 vs exact 2
    ece optimize --uncovered "Schema Migration"   residual gap, no solver
    ece validate                 the acceptance gate
"""

from __future__ import annotations

import json

import typer

from app.core.config_table import Config
from app.db.conn import connect, execute, init_schema, query, query_one

app = typer.Typer(add_completion=False, help="Engineering Continuity Engine")
db_app = typer.Typer(help="Schema")
dataset_app = typer.Typer(help="Dataset generation")
pipeline_app = typer.Typer(help="Whole-pipeline runs")
report_app = typer.Typer(help="Read-only reports")
app.add_typer(db_app, name="db")
app.add_typer(dataset_app, name="dataset")
app.add_typer(pipeline_app, name="pipeline")
app.add_typer(report_app, name="report")

OVERLAP_THRESHOLD = 0.4          # swept; see `ece dataset sweep`

C_OK, C_DIM, C_HEAD, C_WARN, C_ERR = "green", "bright_black", "cyan", "yellow", "red"


def _h(text: str) -> None:
    typer.secho(f"\n{text}", fg=C_HEAD, bold=True)


def _line(text: str, colour: str = "") -> None:
    typer.secho(f"  {text}", fg=colour or None)


# ── db ───────────────────────────────────────────────────────────────────────
@db_app.command("init")
def db_init() -> None:
    """Create the schema from scratch and seed the rules (idempotent)."""
    init_schema()
    with connect() as conn:
        t = query_one(conn, "SELECT count(*) n FROM information_schema.tables "
                            "WHERE table_schema='public' AND table_type='BASE TABLE'")["n"]
        v = query_one(conn, "SELECT count(*) n FROM information_schema.views "
                            "WHERE table_schema='public'")["n"]
        r = query_one(conn, "SELECT count(*) n FROM role_ceiling")["n"]
        c = query_one(conn, "SELECT count(*) n FROM config")["n"]
    _h("Schema")
    _line(f"{t} tables · {v} views · {r} ladder rungs · {c} config rows", C_OK)


@db_app.command("reset")
def db_reset() -> None:
    """Drop everything downstream of ingestion, keeping raw records."""
    with connect() as conn:
        execute(conn, "TRUNCATE extracted_item, cluster_membership, cluster_node, "
                      "tree_version, capability_component, work_unit, work_unit_member CASCADE")
    _line("cleared everything downstream of raw_record", C_OK)


# ── dataset ──────────────────────────────────────────────────────────────────
@dataset_app.command("generate")
def dataset_generate() -> None:
    """Write the Jira and incident JSON, in their real API shapes."""
    from app.dataset.generators import generate_all
    from app.dataset.recipes import build_plan

    plan = build_plan()
    written = generate_all(plan)
    _h("Generated")
    for k, v in written.items():
        _line(f"{k:18} {v}")
    _line(f"plan: {plan.counts()}", C_DIM)


@dataset_app.command("repo")
def dataset_repo(push: bool = typer.Option(True, help="push to GitHub")) -> None:
    """Build the constructed repository with deliberate author dates, and push."""
    from app.dataset.github_repo import build_repository
    from app.dataset.github_prs import create_pull_requests

    _h("Constructing repository")
    r = build_repository(push=push)
    _line(f"{r['commits']} commits written with GIT_AUTHOR_DATE across three years", C_OK)
    if push:
        for pr in create_pull_requests(r["workdir"]):
            _line(f"PR #{pr.get('number')} {pr.get('title')} merged={pr.get('merged')}", C_OK)
    _line("The pipeline is real; the history is designed. Never call this a "
          "production repository.", C_DIM)


@dataset_app.command("seed")
def dataset_seed() -> None:
    """Seed people, identities, components and the hand-authored dependency graph."""
    from app.dataset.seed import seed_organisation
    with connect() as conn:
        counts = seed_organisation(conn)
    _h("Organisation")
    for k, v in counts.items():
        _line(f"{k:18} {v}")


@dataset_app.command("capture")
def dataset_capture() -> None:
    """Snapshot the GitHub payloads now in `raw_record` as the fixture set.

    This is what `--fixture` should replay. `data/generated/` holds the PLAN the
    repository was built from, and GitHub applies its own reality on top of it —
    replaying the plan ingests records the live path never sees, which is enough
    to change a band and fail the acceptance gate. Capture after a green
    `--live` run and the offline path reaches the same database.
    """
    from app.ingestion.github import capture_fixtures

    with connect() as conn:
        written = capture_fixtures(conn)
    _h("Fixture capture")
    for name, count in written.items():
        _line(f"{name:24} {count} payload(s)", C_OK)
    _line("`ece ingest --fixture` now replays a live run, not the build plan.", C_DIM)


@dataset_app.command("sweep")
def dataset_sweep() -> None:
    """Sweep the clustering threshold and show where discovery is stable.

    The artifact that answers "how did you choose that number?" — a plateau
    rather than a knife-edge is the evidence that clustering is robust rather
    than fitted.
    """
    from app.clustering.discover import discover, execute_returning

    _h("Threshold sweep")
    for th in (0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70):
        with connect() as conn:
            execute(conn, "TRUNCATE cluster_membership, cluster_node, tree_version, "
                          "capability_component CASCADE")
            tv = execute_returning(conn, "INSERT INTO tree_version (label,status) "
                                         "VALUES ('sweep','draft') RETURNING tree_version_id AS node_id", ())
            r = discover(conn, th, tv)
        mark = "  <- target (8)" if r.parents == 8 else ""
        colour = C_OK if r.parents == 8 else C_DIM
        _line(f"threshold {th:.2f}  capabilities={r.parents:2}  leaves={r.leaves:2}{mark}", colour)


# ── stages ───────────────────────────────────────────────────────────────────
@app.command("ingest")
def ingest_cmd(live: bool = typer.Option(True, "--live/--fixture",
                                         help="use the real GitHub API, or replay captured payloads")) -> None:
    """Land raw payloads. Re-running is safe: unchanged records are skipped."""
    from app.ingestion.github import GitHubAdapter, GitHubFixtureAdapter
    from app.ingestion.raw_store import ingest
    from app.ingestion.synthetic import IncidentAdapter, JiraAdapter

    github = GitHubAdapter() if live else GitHubFixtureAdapter()
    if live:
        _h("Ingestion (live GitHub API)")
    else:
        _h(f"Ingestion (replaying {github.dir.name}/)")
        if not github.is_capture:
            # Say it out loud rather than producing a quietly different dataset.
            _line("no capture found — replaying the BUILD PLAN, which is not what "
                  "GitHub returns. Results may differ from a live run; run "
                  "`ece dataset capture` after a green live run.", C_WARN)
    with connect() as conn:
        for adapter in (github, JiraAdapter(), IncidentAdapter()):
            report = ingest(conn, adapter)
            colour = C_OK if report.inserted else C_DIM
            _line(report.line(), colour)
    _line("Run this twice: the second run inserts 0 and reports duplicates. "
          "Idempotency is a unique constraint, not a convention.", C_DIM)


@app.command("normalize")
def normalize_cmd(explain: str = typer.Option(None, help="walk the ladder on one record")) -> None:
    """Three payload shapes become one row shape."""
    from app.normalization.pipeline import normalize_all

    if explain:
        _explain_record(explain)
        return

    with connect() as conn:
        report = normalize_all(conn, Config.load(conn))
    _h("Normalization")
    for line in report.lines():
        _line(line)
    _h("Ingestion health")
    for line in report.health_report():
        _line(line, C_WARN if ("UNRESOLVED" in line or "EXTRACTION FAILED" in line)
              else C_DIM)


def _explain_record(native_id: str) -> None:
    """Narrate the classification ladder for one record.

    This is the honest answer to "what happens in an org that doesn't tag things
    well" — demonstrated on a real record rather than described.
    """
    with connect() as conn:
        row = query_one(conn, "SELECT raw_record_id, source_type, payload FROM raw_record "
                              "WHERE source_native_id=%s", (native_id,))
        if not row:
            typer.secho(f"no raw record with native id {native_id}", fg=C_ERR)
            raise typer.Exit(1)
        items = query(conn, """
            SELECT native_actor_id, employee_id, extraction_method, certainty,
                   feature_tokens, actor_role, ceiling_basis, eligibility_state,
                   exclusion_reason
            FROM extracted_item WHERE raw_record_id=%s ORDER BY item_id
        """, (row["raw_record_id"],))

    _h(f"{native_id}  ({row['source_type']})")
    if row["source_type"] == "jira":
        fields = row["payload"].get("fields", {})
        comps = [c.get("name") for c in (fields.get("components") or [])]
        labels = fields.get("labels") or []
        project = (fields.get("project") or {}).get("key")
        _line("classification ladder:", C_DIM)
        _line(f"  tier 1  components : {comps or 'ABSENT'}",
              C_OK if comps else C_WARN)
        _line(f"  tier 2  labels     : {labels or 'ABSENT'}",
              C_OK if labels and not comps else (C_WARN if not comps else C_DIM))
        _line(f"  tier 3  project    : {project}  (mandatory in Jira, always present — "
              f"but coarse)", C_OK if not comps and not labels else C_DIM)
        _line("  tier 4  text similarity", C_DIM)
        _line("  tier 5  unclassified — parked, never force-fitted", C_DIM)

    for it in items:
        state = it["eligibility_state"]
        colour = C_OK if state == "eligible" else C_WARN
        _line("")
        _line(f"actor {it['native_actor_id']} -> {it['employee_id'] or 'UNMAPPED'}", colour)
        _line(f"  rung fired : {it['extraction_method']}  (certainty {it['certainty']})")
        _line(f"  role       : {it['actor_role']} — {it['ceiling_basis']}")
        _line(f"  tokens     : {it['feature_tokens'][:4]}")
        if state != "eligible":
            _line(f"  EXCLUDED   : {it['exclusion_reason']}", C_WARN)


@app.command("discover")
def discover_cmd(threshold: float = typer.Option(OVERLAP_THRESHOLD)) -> None:
    """Within-source clustering, then cross-source linking by explicit reference."""
    from app.clustering.discover import discover, execute_returning

    with connect() as conn:
        execute(conn, "TRUNCATE cluster_membership, cluster_node, tree_version, "
                      "capability_component CASCADE")
        tv = execute_returning(conn, "INSERT INTO tree_version (label,status) "
                                     "VALUES ('demo','draft') RETURNING tree_version_id AS node_id", ())
        report = discover(conn, threshold, tv)
    _h(f"Discovery (overlap threshold {threshold})")
    for line in report.lines():
        _line(line)
    _line("Clustering does not understand meaning. It measures overlap — two commits "
          "under the same directory are related by that shared fact.", C_DIM)


@app.command("name")
def name_cmd() -> None:
    """Propose a name per capability. The namer NAMES; it never decides."""
    from app.naming import name_tree
    with connect() as conn:
        proposals = name_tree(conn)
    _h(f"Naming ({proposals[0].source if proposals else 'n/a'} provider)")
    # A namer substitution is announced, never silent: the value of the naming
    # boundary is that it can be audited afterwards.
    if getattr(name_tree, "fallback_reason", None):
        _line(f"NAMER fell back: {name_tree.fallback_reason}", C_WARN)
    for p in proposals:
        _line(f"node {p.node_id:4}  {p.name}")
    _line("The namer receives an already-formed group and returns a string. It cannot "
          "add, move or remove a single item.", C_DIM)


@app.command("approve")
def approve_cmd(
    accept_similarity: bool = typer.Option(
        False, "--accept-similarity",
        help="accept tier-4 TF-IDF memberships instead of rejecting them"),
) -> None:
    """The human gate: mark the frontier, map components, approve.

    It also answers the tier-4 question. A TF-IDF match arrives as
    `pending_review` and contributes nothing to any band; invariant I7 forbids
    leaving it open at freeze, so the gate decides. The default is to reject —
    accepting an unverified guess is a deliberate act, not a default.
    """
    from app.taxonomy.freeze import approve_tree
    with connect() as conn:
        counts = approve_tree(conn, accept_similarity=accept_similarity)
        rows = query(conn, "SELECT name, llm_proposed_name, name_source FROM cluster_node "
                           "WHERE node_role='capability' ORDER BY name")
    _h("Approval")
    for r in rows:
        edited = r["name_source"] == "human"
        _line(f"{r['name']:32} proposed '{r['llm_proposed_name']}'"
              f"{'  [edited by human]' if edited else '  [accepted]'}",
              C_WARN if edited else C_OK)
    _line(f"{counts['approved']} approved · {counts['mapped']} mapped to components", C_OK)
    if counts.get("similarity_reviewed"):
        _line(f"tier-4 similarity memberships: {counts['similarity_reviewed']} "
              f"→ {counts['similarity_decision']}",
              C_OK if counts["similarity_decision"] == "human_approved" else C_WARN)
    else:
        _line("no tier-4 similarity memberships awaited review", C_DIM)


@app.command("freeze")
def freeze_cmd(threshold: float = typer.Option(OVERLAP_THRESHOLD)) -> None:
    """Invariants -> work units -> calibration -> freeze, in one transaction."""
    from app.taxonomy.freeze import freeze
    with connect() as conn:
        tv = query_one(conn, "SELECT tree_version_id FROM tree_version "
                             "ORDER BY tree_version_id DESC LIMIT 1")["tree_version_id"]
        result = freeze(conn, tv, threshold)
    _h("Freeze")
    _line("invariants I1, I2, I3, I6, I7 passed", C_OK)
    _line(f"work units collapsed : {result['work_units']}")
    _line("derived thresholds (computed once, from this dataset's own distribution):")
    for k, v in result["derived"].items():
        _line(f"    {k:30} {v}")


@pipeline_app.command("run")
def pipeline_run(
    live: bool = typer.Option(True, "--live/--fixture"),
    threshold: float = typer.Option(OVERLAP_THRESHOLD),
    reset: bool = typer.Option(True, help="clear raw records first"),
) -> None:
    """Everything, in order."""
    if reset:
        with connect() as conn:
            execute(conn, "TRUNCATE raw_record, extracted_item, cluster_membership, "
                          "cluster_node, tree_version, capability_component, work_unit, "
                          "work_unit_member CASCADE")
    dataset_seed()
    ingest_cmd(live=live)
    normalize_cmd(explain=None)
    discover_cmd(threshold=threshold)
    name_cmd()
    approve_cmd()
    freeze_cmd(threshold=threshold)
    _h("Pipeline complete")
    _line("Everything from here on is a pure function over the database: no writes, "
          "no network, no model call between a click and an answer.", C_DIM)


# ── reports ──────────────────────────────────────────────────────────────────
@report_app.command("baseline")
def report_baseline() -> None:
    """The coverage matrix, printed from a script — no API, no frontend."""
    from app.domain import services
    with connect() as conn:
        data = services.get_overview(conn)
        at_risk = services.get_at_risk(conn)

    _h(f"Baseline coverage · as of {data['as_of_date'][:10]}")
    for c in data["capabilities"]:
        marks = []
        if c["exposure"] != "none":
            marks.append(c["exposure"])
        if c["activity"] == "Dormant":
            marks.append("dormant")
        if c["density"] == "Thin":
            marks.append("thin")
        names = ", ".join(x["display_name"].split()[0] for x in c["coverers"]) or "—"
        colour = C_ERR if c["status"] == "Uncovered" else C_OK
        _line(f"{c['status']:10} {c['name']:30} {names:32} "
              f"{' · '.join(marks)}", colour)

    _h(f"At risk ({len(at_risk['items'])})")
    for i in at_risk["items"]:
        _line(f"{i['name']:30} {i['headline']}", C_WARN)


@report_app.command("units")
def report_units() -> None:
    """Work units — one piece of work, not four records."""
    with connect() as conn:
        multi = query(conn, """
            SELECT wu.work_unit_id, wu.member_count, wu.occurred_at,
                   array_agg(DISTINCT rr.source_native_id ORDER BY rr.source_native_id) AS members,
                   array_agg(DISTINCT ei.source_type) AS sources
            FROM work_unit wu
            JOIN work_unit_member wm ON wm.work_unit_id = wu.work_unit_id
            JOIN extracted_item ei ON ei.item_id = wm.item_id
            JOIN raw_record rr ON rr.raw_record_id = ei.raw_record_id
            WHERE wu.member_count > 1
            GROUP BY wu.work_unit_id, wu.member_count, wu.occurred_at
            ORDER BY wu.member_count DESC, wu.work_unit_id
        """)
        total = query_one(conn, "SELECT count(*) n FROM work_unit")["n"]
        items = query_one(conn, "SELECT count(*) n FROM work_unit_member")["n"]

    _h(f"Work units: {total} units from {items} items")
    _line("Multi-record units — records collapsed because an EXPLICIT reference "
          "joins them:", C_DIM)
    for u in multi:
        _line(f"unit {u['work_unit_id']:4}  {u['member_count']} records  "
              f"{sorted(set(u['sources']))}  {u['members'][:4]}", C_OK)
    _line("All counting in band assignment is over UNITS, never raw records — so one "
          "afternoon's work cannot look like a pattern.", C_DIM)


@report_app.command("ladders")
def report_ladders() -> None:
    """The 16 ladder rungs, and which of them this dataset actually reaches.

    Piece 1 §3.2 declares all 16 as built; Piece 5 §1 says a rule its data does
    not exercise is untested. Both are true at once, so the honest artifact is
    the one that shows which is which — rather than a claim of "16 rungs" that
    nobody can check. Validator D6 fails if this table changes unannounced.
    """
    from app.validation.validate import UNEXERCISED_RUNGS

    with connect() as conn:
        rungs = query(conn, "SELECT source_type, rung, role, ceiling, availability, "
                            "rationale FROM role_ceiling ORDER BY source_type, rung")
        counts = {r["actor_role"]: r["n"] for r in query(
            conn, "SELECT actor_role, count(*) n FROM extracted_item "
                  "WHERE actor_role IS NOT NULL GROUP BY actor_role")}

    band = {0: "NONE", 1: "LOW", 2: "MODERATE", 3: "HIGH"}
    _h("Signal ladders")
    source = None
    for r in rungs:
        if r["source_type"] != source:
            source = r["source_type"]
            typer.secho(f"\n  {source.upper()}", fg=C_HEAD)
        n = counts.get(r["role"], 0)
        mark = f"{n:3} record(s)" if n else "  not exercised"
        colour = C_OK if n else C_WARN
        _line(f"  rung {r['rung']}  {r['role']:24} caps at {band[r['ceiling']]:9} "
              f"{mark}", colour)
        if not n:
            reason = UNEXERCISED_RUNGS.get((r["source_type"], r["role"]),
                                           "UNDOCUMENTED — validator D6 will fail")
            _line(f"          why not: {reason}", C_DIM)
    dark = sum(1 for r in rungs if not counts.get(r["role"]))
    _line(f"\n{len(rungs) - dark}/{len(rungs)} rungs exercised by this dataset. "
          f"The rules themselves are pinned on constructed payloads in "
          f"tests/test_rules.py.", C_DIM)


@report_app.command("config")
def report_config() -> None:
    """Every value the system reads, and why it is what it is."""
    with connect() as conn:
        rows = query(conn, "SELECT key, value, kind, basis, rationale FROM config ORDER BY kind, key")
    _h("Configuration — no tuned constants")
    for kind in ("derived", "natural_unit", "definitional", "mapping", "operational"):
        group = [r for r in rows if r["kind"] == kind]
        if not group:
            continue
        typer.secho(f"\n  {kind.upper()}", fg=C_HEAD)
        for r in group:
            value = json.dumps(r["value"])
            if len(value) > 60:
                value = value[:57] + "…"
            _line(f"  {r['key']:36} {value}")
            # `basis` is the percentile that produced a DERIVED value and is a
            # placeholder everywhere else; the rationale is what answers
            # "why is that number what it is?" for the other four kinds.
            detail = r["basis"] if r["basis"] not in (None, "", "-") else r["rationale"]
            _line(f"    {detail}", C_DIM)


@app.command("simulate")
def simulate_cmd(employee_id: str) -> None:
    """Remove one person from the coverage set and recompute."""
    from app.domain import services
    with connect() as conn:
        result = services.simulate(conn, employee_id)
    s = result["summary"]
    _h(f"Simulating {result['display_name']}")
    _line(f"{s['lost']} Lost · {s['degraded']} Degraded · {s['maintained']} Maintained · "
          f"{s['uncovered']} Uncovered", C_WARN)
    for c in result["capabilities"]:
        colour = {"Lost": C_ERR, "Degraded": C_WARN,
                  "Uncovered": C_ERR, "Maintained": C_OK}[c["status"]]
        extra = ""
        if c["coverers_after"] == 0 and c["best_band_after_holder"]:
            extra = f"  closest: {c['best_band_after_holder']['display_name']} " \
                    f"({c['best_band_after']})"
        _line(f"{c['status']:11} {c['name']:30} "
              f"{c['coverers_before']}->{c['coverers_after']}  "
              f"{c['best_band_before']}->{c['best_band_after']}{extra}", colour)


@app.command("optimize")
def optimize_cmd(
    simulate: str | None = typer.Option(
        None, "--simulate", help="Simulate this person's unavailability and solve"),
    uncovered: str | None = typer.Option(
        None, "--uncovered", help="An uncovered capability by name — residual gap only"),
    greedy: bool = typer.Option(
        False, "--greedy", help="also print the offline greedy baseline (Piece 4 §9)"),
) -> None:
    """Minimum Coverage Team — the solver, from a script (Piece 4).

    `ece optimize --simulate rahul`      -> team + residual gap
    `ece optimize --simulate karan --greedy` -> the Case F 2-vs-3 comparison
    `ece optimize --uncovered "Schema Migration"` -> residual gap, no model
    """
    from app.domain import services

    if (simulate is None) == (uncovered is None):
        typer.secho("provide exactly one of --simulate or --uncovered", fg=C_ERR)
        raise typer.Exit(2)

    with connect() as conn:
        if uncovered is not None:
            row = query_one(conn, """
                SELECT node_id FROM cluster_node
                WHERE node_role='capability' AND name=%s
            """, (uncovered,))
            if row is None:
                raise typer.BadParameter(f"no capability named {uncovered!r}")
            plan = services.coverage_plan(conn, capability_id=row["node_id"])
        else:
            plan = services.coverage_plan(conn, employee_id=simulate)

    _print_plan(plan, show_greedy=greedy)


def _print_plan(plan: dict, show_greedy: bool) -> None:
    b = plan["basis"]
    if b["kind"] == "simulation":
        _h("Coverage Plan — simulate " + b["display_name"])
    else:
        _h(f"Coverage Plan — uncovered capability: {b['capability_name']}")

    if plan["team"]:
        for t in plan["team"]:
            _line(f"{t['display_name']:20} "
                  f"[{', '.join(a['name'] for a in t['assignments'])}]", C_OK)
            _line(f"    {t['rationale']}", C_DIM)
            _line(f"    components: {', '.join(t['components'])}", C_DIM)
            for a in t["assignments"]:
                _line(f"    → {a['band']:9} {a['name']:28} "
                      f"raw_record {a['raw_record_id']}"
                      f"{' · authorship exception' if a['via_authorship_exception'] else ''}",
                      C_DIM)
    else:
        _line("no team — nothing to cover (or nothing coverable)", C_DIM)

    if plan["residual_gaps"]:
        _line("Residual gaps", C_HEAD)
        for g in plan["residual_gaps"]:
            _line(f"  {g['name']:30} → {g['why']}", C_WARN)
            c = g.get("closest")
            if c:
                _line(f"      closest: {c['display_name']} at {c['band']} "
                      f"(raw_record {c['raw_record_id']})", C_DIM)

    o = plan["objective"]
    _line(f"Objective — abandoned: {o['abandoned']} · people: {o['people']} · "
          f"switching: {o['switching']} · HIGH assignments: {o['high_assignments']}",
          C_HEAD)

    if b["kind"] == "simulation":
        if plan["solver"]:
            _line(f"solver: {plan['solver']}", C_DIM)
        u = plan.get("uniqueness") or {}
        if "verified" in u:
            _line(f"optimum unique: {u['verified']}  "
                  f"(runner-up {u['found']} -> {u['runner_up']})", C_OK if u["verified"] else C_ERR)
    if show_greedy:
        g = plan.get("greedy_baseline")
        if g:
            _line(f"greedy baseline: {g['size']} people {g['people']} — "
                  f"exact: {plan['objective']['people']}", C_WARN)


@app.command("validate")
def validate_cmd() -> None:
    """The acceptance gate. Non-zero exit on any failure."""
    from app.validation.validate import run_validation
    ok = run_validation()
    raise typer.Exit(0 if ok else 1)


if __name__ == "__main__":
    app()

"""Domain services — the facade the API calls.

Route handlers contain ZERO business logic (Piece 1 §3.16): each one calls a
function here and serialises the result.  The practical payoff is that the whole
engine is testable and demoable from a script before any web server exists,
which is exactly the build order this project used.
"""

from __future__ import annotations

from dataclasses import asdict

import psycopg

from app.core.bands import Band
from app.core.config_table import Config
from app.core.enums import Activity, CoverageStatus, Density, Exposure
from app.core.errors import NotFoundError, NotInCoverageSetError
from app.core.settings import settings
from app.coverage.engine import (
    BandResult, World, activity, assign_bands, best_band, coverers,
    density, exposed_components, load_world, propagate,
)
from app.db.conn import execute, query


def _world(conn: psycopg.Connection) -> tuple[World, dict]:
    cfg = Config.load(conn)
    w = load_world(conn, cfg)
    return w, assign_bands(w)


def _band_of(bands, person: str, cap: int) -> BandResult:
    return bands.get(person, {}).get(cap, BandResult(Band.NONE, None))


def _basis(br: BandResult) -> dict | None:
    if br.basis is None:
        return None
    return {
        "ceiling_basis": br.basis.ceiling_basis,
        "binding_cap": br.basis.binding_cap,
        "age_label": br.basis.age_label,
        "certainty": br.basis.certainty,
        "raw_record_id": br.basis.raw_record_id,
        "occurred_at": br.basis.occurred_at.isoformat(),
        "via_authorship_exception": br.via_authorship,
    }


def _holder(w: World, bands, person: str, cap: int) -> dict:
    """One person's standing on one capability, with the record it rests on.

    The same shape everywhere a person is named against a capability — coverer,
    sub-threshold holder, departed holder — so the UI renders all three with one
    component and cannot accidentally show a coverer more detail than the person
    who fell one band short.
    """
    br = _band_of(bands, person, cap)
    return {
        "employee_id": person,
        "display_name": w.employees[person]["display_name"],
        "role_title": w.employees[person].get("role_title"),
        "status": w.employees[person]["status"],
        "band": br.band.name,
        "band_code": int(br.band),
        "unit_count": br.unit_count,
        **(_basis(br) or {}),
    }


def _holders(w: World, bands, cap: int) -> tuple[list[dict], list[dict], list[dict]]:
    """(coverers, sub-threshold holders, departed holders) for one capability.

    The middle list is the one the UI was missing entirely, and it is the
    difference between "nobody knows this" and "somebody has been near it".
    Piece 6 §9 rejects "Covered by: none remaining" for exactly this reason:
    the claim that nobody holds ANY evidence is usually false — someone holds
    LOW and simply does not clear the threshold. Showing them, clearly marked as
    NOT counting, is what makes the threshold visible instead of mysterious.
    """
    active = w.coverage_set
    cov = coverers(cap, active, bands, w.cfg)
    covering = set(cov)

    below, departed = [], []
    for p, v in sorted(w.employees.items()):
        if v["is_service_account"] or p in covering:
            continue
        br = _band_of(bands, p, cap)
        if br.band == Band.NONE:
            continue
        (departed if v["status"] == "departed" else below).append(_holder(w, bands, p, cap))

    by_band = lambda h: (-h["band_code"], h["display_name"])
    return ([_holder(w, bands, p, cap) for p in cov],
            sorted(below, key=by_band), sorted(departed, key=by_band))


# ─────────────────────────────────────────────────────────────────────────────
def _service_id(conn: psycopg.Connection) -> str:
    """The one service this prototype models, read from `component` rather than
    hardcoded.  One service is a stated scope limit (README) — the schema
    supports more, so the id belongs in a query, not a literal."""
    rows = query(conn, "SELECT DISTINCT service FROM component ORDER BY service")
    return _slug(rows[0]["service"]) if rows else "payment-service"


def _slug(name: str) -> str:
    return "-".join(name.lower().split())


def get_overview(conn: psycopg.Connection, service_id: str | None = None) -> dict:
    """Baseline. Computed BEFORE any simulation, so the dashboard says something
    true on load (Piece 3 §11).

    An unknown `service_id` is a 404, not a silent redirect to the only service
    there is: answering a question about `billing-service` with Payment Service
    numbers is the kind of quiet wrong answer this system exists to avoid.
    """
    known = _service_id(conn)
    if service_id is not None and service_id != known:
        raise NotFoundError("service", service_id)

    w, bands = _world(conn)
    active = w.coverage_set

    uncovered = [cap for cap in w.capabilities if not coverers(cap, active, bands, w.cfg)]
    exposure = propagate(uncovered, w)

    out = []
    for cap, name in sorted(w.capabilities.items(), key=lambda kv: kv[1]):
        cov = coverers(cap, active, bands, w.cfg)
        bb, holder = best_band(cap, active, bands)

        # Three lists, not one. Departed people appear here and never in
        # `coverers` — this is what lets the dashboard say "the person who
        # covered this left in March" instead of reporting an unexplained gap —
        # and `other_holders` is what stops an uncovered capability reading as
        # "nobody has ever touched this" when somebody holds LOW.
        covering, below, departed = _holders(w, bands, cap)

        out.append({
            "capability_id": cap,
            "name": name,
            "status": (CoverageStatus.COVERED if cov else CoverageStatus.UNCOVERED).value,
            "coverers": covering,
            "coverer_count": len(cov),
            "other_holders": below,
            "best_band": bb.name,
            "best_band_holder": holder,
            "departed_holders": departed,
            "exposure": exposure.get(cap, Exposure.NONE).value,
            "activity": activity(cap, w).value,
            "density": density(cap, w).value,
            "primary_component": w.primary_component.get(cap),
            "components": w.components_of.get(cap, []),
            "work_units": len({e.work_unit_id for e in w.edges if e.capability_id == cap}),
            "evidence_items": len({e.item_id for e in w.edges if e.capability_id == cap}),
            "coverage_threshold": w.cfg.coverage_threshold.name,
        })
    return {"service_id": known,
            "as_of_date": w.cfg.as_of_date.isoformat(),
            "capabilities": out}


def get_at_risk(conn: psycopg.Connection) -> dict:
    """Uncovered and single-coverer. `Degraded` deliberately does not appear:
    it is a before/after comparison and there is nothing to compare to."""
    w, bands = _world(conn)
    active = w.coverage_set
    uncovered = [cap for cap in w.capabilities if not coverers(cap, active, bands, w.cfg)]
    exposure = propagate(uncovered, w)

    items = []
    for cap, name in sorted(w.capabilities.items(), key=lambda kv: kv[1]):
        cov = coverers(cap, active, bands, w.cfg)
        if len(cov) > 1:
            continue
        act, den = activity(cap, w), density(cap, w)
        dep_count = len(exposed_components(cap, w))

        if not cov:
            bits = ["Uncovered"]
            if act is Activity.DORMANT:
                bits.append("Dormant")
            if dep_count:
                bits.append(f"{dep_count} component{'s' if dep_count != 1 else ''} depend on it")
            headline = " · ".join(bits)
            category = "uncovered"
            sole = None
        else:
            category = "single_coverer"
            sole = {"employee_id": cov[0],
                    "display_name": w.employees[cov[0]]["display_name"],
                    "band": _band_of(bands, cov[0], cap).band.name}
            headline = f"single coverer ({w.employees[cov[0]]['display_name']})"

        items.append({"capability_id": cap, "name": name, "category": category,
                      "sole_coverer": sole, "headline": headline,
                      "exposure": exposure.get(cap, Exposure.NONE).value,
                      "activity": act.value, "density": den.value,
                      "dependent_component_count": dep_count})
    return {"items": items}


def list_employees(conn: psycopg.Connection) -> dict:
    w, _ = _world(conn)
    return {"employees": [
        {"employee_id": e, "display_name": v["display_name"],
         "role_title": v["role_title"], "status": v["status"],
         "is_simulatable": v["status"] == "active" and not v["is_service_account"]}
        for e, v in sorted(w.employees.items())
        if not v["is_service_account"]
    ]}


def simulate(conn: psycopg.Connection, employee_id: str) -> dict:
    """Remove one person from the COVERAGE SET and recompute.

    Their evidence is NOT removed — it stays visible, and the graph fades their
    node rather than deleting it. Nothing is written; bands are recomputed, never
    edited, so nothing can go stale mid-demo.
    """
    w, bands = _world(conn)
    if employee_id not in w.employees:
        raise NotFoundError("employee", employee_id)
    if employee_id not in w.coverage_set:
        raise NotInCoverageSetError(employee_id)

    before = w.coverage_set
    after = before - {employee_id}

    results, summary = [], {"maintained": 0, "degraded": 0, "lost": 0, "uncovered": 0}
    for cap, name in sorted(w.capabilities.items(), key=lambda kv: kv[1]):
        cov_b = coverers(cap, before, bands, w.cfg)
        cov_a = coverers(cap, after, bands, w.cfg)
        bb_b, _ = best_band(cap, before, bands)
        bb_a, holder_a = best_band(cap, after, bands)

        # Order matters: Uncovered is tested FIRST, so a pre-existing gap can
        # never be labelled Lost (which would blame the simulated person) nor
        # Maintained (which would claim it was fine).
        if not cov_b and not cov_a:
            status = CoverageStatus.UNCOVERED
        elif cov_b and not cov_a:
            status = CoverageStatus.LOST
        elif len(cov_a) < len(cov_b) or bb_a < bb_b:
            status = CoverageStatus.DEGRADED
        else:
            status = CoverageStatus.MAINTAINED
        summary[status.value.lower()] += 1

        holder_basis = None
        if holder_a:
            holder_basis = {"employee_id": holder_a,
                            "display_name": w.employees[holder_a]["display_name"],
                            **(_basis(_band_of(bands, holder_a, cap)) or {})}

        results.append({
            "capability_id": cap, "name": name, "status": status.value,
            "coverers_before": len(cov_b), "coverers_after": len(cov_a),
            "best_band_before": bb_b.name, "best_band_after": bb_a.name,
            "best_band_after_holder": holder_basis,
            "activity": activity(cap, w).value, "density": density(cap, w).value,
            "changed": status is not CoverageStatus.MAINTAINED,
            "primary_component": w.primary_component.get(cap),
        })

    # Uncovered stays an ORIGIN here. It was one at baseline, and a pre-existing
    # gap does not stop radiating risk because someone is now also simulated —
    # dropping it would make downstream badges vanish the moment you click a
    # person, for no reason a user could explain.
    origins = [r["capability_id"] for r in results
               if r["status"] in {CoverageStatus.LOST.value, CoverageStatus.DEGRADED.value,
                                  CoverageStatus.UNCOVERED.value}]
    exposure = propagate(origins, w)
    for r in results:
        r["exposure"] = exposure.get(r["capability_id"], Exposure.NONE).value

    return {"employee_id": employee_id,
            "display_name": w.employees[employee_id]["display_name"],
            "summary": summary, "capabilities": results}


def get_evidence(conn: psycopg.Connection, capability_id: int,
                 exclude_employee: str | None = None) -> dict:
    """Every row carries `ceiling_basis` and `raw_record_id`, so any claim on
    screen is one click from the record it rests on (SC6)."""
    w, bands = _world(conn)
    if capability_id not in w.capabilities:
        raise NotFoundError("capability", str(capability_id))

    from app.coverage.engine import ceiling_for
    by_person: dict[str, list] = {}
    for e in w.edges:
        if e.capability_id != capability_id:
            continue
        c = ceiling_for(e, w)
        by_person.setdefault(e.employee_id, []).append({
            "item_id": e.item_id, "raw_record_id": e.raw_record_id,
            "work_unit_id": e.work_unit_id, "source_type": e.source_type,
            "record_kind": e.record_kind, "actor_role": e.actor_role,
            "ceiling_basis": e.ceiling_basis, "occurred_at": e.occurred_at.isoformat(),
            "age_label": c.age_label, "certainty": e.certainty,
            "binding_cap": c.binding_cap, "ceiling": c.band.name,
        })

    people = []
    for p in sorted(by_person):
        br = _band_of(bands, p, capability_id)
        people.append({
            "employee_id": p, "display_name": w.employees[p]["display_name"],
            "status": w.employees[p]["status"], "band": br.band.name,
            "removed": exclude_employee is not None and p == exclude_employee,
            "unit_count": br.unit_count,
            "items": sorted(by_person[p], key=lambda i: i["occurred_at"], reverse=True),
        })

    # Scoped to THIS capability, by SIGNATURE OVERLAP.
    #
    # A global list put a bot commit from an unrelated capability under
    # "Excluded from evidence" on every panel, which reads as an explanation for
    # a gap it has nothing to do with.  Membership cannot do the scoping either:
    # discovery only ever clusters ELIGIBLE items, so an excluded row has no
    # cluster to be in — joining through `cluster_membership` empties the panel
    # entirely.  The signature tokens are what the clusterer would have matched
    # on had the row survived Stage A, so they are the honest key.
    excluded = query(conn, """
        WITH sig AS (
            SELECT DISTINCT unnest(ei.feature_tokens) AS token
            FROM cluster_membership cm
            JOIN capability_descendant cd ON cd.descendant_id = cm.node_id
            JOIN extracted_item ei ON ei.item_id = cm.item_id
            WHERE cd.capability_node_id = %s
              AND ei.eligibility_state = 'eligible'
        )
        SELECT ei.item_id, ei.raw_record_id, ei.source_type, ei.record_kind,
               ei.exclusion_reason, ei.occurred_at, ei.employee_id
        FROM extracted_item ei
        WHERE ei.eligibility_state = 'excluded'
          AND ei.feature_tokens && ARRAY(SELECT token FROM sig
                                          WHERE token LIKE 'dir:%%'
                                             OR token LIKE 'component:%%'
                                             OR token LIKE 'label:%%'
                                             OR token LIKE 'service:%%')
        ORDER BY ei.item_id LIMIT 25
    """, (capability_id,))
    return {
        "capability_id": capability_id, "name": w.capabilities[capability_id],
        "by_person": people,
        "excluded_items": [{**r, "occurred_at": r["occurred_at"].isoformat()} for r in excluded],
    }


def get_raw_record(conn: psycopg.Connection, raw_record_id: int) -> dict:
    rows = query(conn, "SELECT raw_record_id, source_type, source_native_id, payload, "
                       "ingested_at FROM raw_record WHERE raw_record_id=%s", (raw_record_id,))
    if not rows:
        raise NotFoundError("raw_record", str(raw_record_id))
    r = rows[0]
    return {**r, "ingested_at": r["ingested_at"].isoformat()}


# ─────────────────────────────────────────────────────────────────────────────
# Coverage Plan (Piece 4) and capability detail (Piece 6 §2)
# ─────────────────────────────────────────────────────────────────────────────
def coverage_plan(conn: psycopg.Connection, employee_id: str | None = None,
                  capability_id: int | None = None) -> dict:
    """The Coverage Plan — team + assignments + rationale + residual gaps.

    Two entry points, one contract (open decision OD-7):
      * `{employee_id}`   — simulate that person's loss and solve for the
                            Minimum Coverage Team (Piece 4 §2.1).
      * `{capability_id}` — an Uncovered capability clicked from the baseline
                            at-risk list.  Reports the residual gap directly and
                            NEVER constructs the model (Piece 4 §2.2, §6).
    Exactly one is required; both or neither raise `InvalidRequestError`.

    Nothing here writes a row.  The solver reads bands that Piece 3 computed as
    pure functions over the database — which is what keeps SC9 true.
    """
    from app.optimizer import (
        candidates as _candidates, greedy_team, objective_tuple,
        qualifications, runner_up_objective, solve, target_set_of_departure,
    )
    from app.optimizer.rationale import rationale_for
    from app.optimizer.residual import residual_entry
    from app.optimizer.uniqueness import is_unique
    from app.core.errors import InvalidRequestError, NotInCoverageSetError

    if (employee_id is None) == (capability_id is None):
        raise InvalidRequestError(
            "exactly one of 'employee_id' or 'capability_id' is required")

    w, bands = _world(conn)
    cfg = w.cfg

    # ── Uncovered path — no solver, the honest answer is immediate ───────────
    if capability_id is not None:
        if capability_id not in w.capabilities:
            raise NotFoundError("capability", str(capability_id))
        people = sorted(w.coverage_set)
        exposure = propagate([capability_id], w)
        return {
            "basis": {"kind": "uncovered",
                      "capability_id": capability_id,
                      "capability_name": w.capabilities[capability_id],
                      "as_of": cfg.as_of_date.isoformat()},
            "target_set": [{"capability_id": capability_id,
                            "name": w.capabilities[capability_id]}],
            "team": [],
            "residual_gaps": [residual_entry(w, bands, capability_id,
                                             people, exposure)],
            "objective": {"abandoned": 1, "people": 0,
                          "switching": 0, "high_assignments": 0},
            "solver": None,
        }

    # ── Simulation path ──
    if employee_id not in w.employees:
        raise NotFoundError("employee", employee_id)
    if employee_id not in w.coverage_set:
        raise NotInCoverageSetError(employee_id)

    targets = target_set_of_departure(w, bands, employee_id)
    people = _candidates(w, employee_id)

    # A departing person who covered nothing is not a coverage problem: there
    # is no target set and no team to optimise (Piece 4 §2.3).
    if not targets:
        return {
            "basis": {"kind": "simulation", "employee_id": employee_id,
                      "display_name": w.employees[employee_id]["display_name"],
                      "as_of": cfg.as_of_date.isoformat()},
            "target_set": [], "team": [], "residual_gaps": [],
            "objective": {"abandoned": 0, "people": 0,
                          "switching": 0, "high_assignments": 0},
            "solver": None,
        }

    quals = qualifications(w, bands, people, targets)
    comps = {c: sorted(w.components_of.get(c, [])) for c in targets}
    # The default must be a BandResult, not a Band: `_Band.NONE.band` is an
    # AttributeError, and it fires the moment a candidate has no row for a
    # target capability.
    band_of = {p: {c: _band_of(bands, p, c).band for c in targets} for p in people}

    sol = solve(people, targets, quals, comps, band_of)

    # Exposure for the gaps: a pre-existing Uncovered origin does not stop
    # radiating risk because someone is now simulated too (Piece 3 §12 step 5).
    exposure = propagate(sorted(sol.uncovered), w)

    target_rows = [{"capability_id": c, "name": w.capabilities[c]}
                   for c in sorted(targets, key=lambda c: w.capabilities[c])]

    team = []
    for p in sol.team:
        assigned = sol.assignments.get(p, set())
        comps_p = sorted({k for c in assigned for k in w.components_of.get(c, [])})
        entry = rationale_for(w, bands, p, assigned)
        entry["components"] = comps_p
        team.append(entry)

    residual_gaps = [residual_entry(w, bands, c, people, exposure)
                     for c in sorted(sol.uncovered, key=lambda c: w.capabilities[c])]

    runner_up = runner_up_objective(people, targets, quals, comps, band_of, sol)
    greedy = greedy_team(people, targets, quals)

    return {
        "basis": {"kind": "simulation", "employee_id": employee_id,
                  "display_name": w.employees[employee_id]["display_name"],
                  "as_of": cfg.as_of_date.isoformat()},
        "target_set": target_rows,
        "team": team,
        "residual_gaps": residual_gaps,
        "objective": {"abandoned": sol.abandoned, "people": sol.people,
                      "switching": sol.switching,
                      "high_assignments": sol.high_assignments},
        "solver": {"engine": "ortools-cp-sat", "workers": 1, "random_seed": 20260504},
        "greedy_baseline": {"people": greedy, "size": len(greedy)},   # P4 §9
        "uniqueness": {"verified": is_unique(sol, runner_up),
                       "found": objective_tuple(sol), "runner_up": runner_up},
    }


def get_capability(conn: psycopg.Connection, capability_id: int) -> dict:
    """One capability: attributes, components, subcategories (Piece 6 §2).

    A grouping node is rejected (API-007): the frontier is where the statements
    live, and a grouping owns no status to state.
    """
    w, bands = _world(conn)
    if capability_id not in w.capabilities:
        raise NotFoundError("capability", str(capability_id))

    active = w.coverage_set
    cov = coverers(capability_id, active, bands, w.cfg)
    bb, holder = best_band(capability_id, active, bands)

    uncovered = [cap for cap in w.capabilities
                 if not coverers(cap, active, bands, w.cfg)]
    exposure = propagate(uncovered, w)

    covering, below, departed = _holders(w, bands, capability_id)

    components = query(conn, """
        SELECT cc.component_id, c.display_name, cc.is_primary
        FROM capability_component cc
        JOIN component c ON c.component_id = cc.component_id
        WHERE cc.capability_node_id=%s ORDER BY cc.component_id
    """, (capability_id,))

    subcategories = query(conn, """
        WITH RECURSIVE walk AS (
            SELECT node_id FROM cluster_node WHERE node_id=%s
            UNION ALL
            SELECT c.node_id FROM cluster_node c
            JOIN walk wk ON c.parent_id = wk.node_id)
        SELECT n.node_id, n.name, n.node_role,
               (SELECT count(*) FROM cluster_membership cm
                 WHERE cm.node_id = n.node_id) AS item_count
        FROM walk w JOIN cluster_node n ON n.node_id = w.node_id
        WHERE n.node_role='subcategory' ORDER BY n.name
    """, (capability_id,))

    return {
        "capability_id": capability_id,
        "name": w.capabilities[capability_id],
        "status": (CoverageStatus.COVERED if cov else CoverageStatus.UNCOVERED).value,
        "coverers": covering,
        "coverer_count": len(cov),
        "other_holders": below,
        "best_band": bb.name,
        "best_band_holder": holder,
        "departed_holders": departed,
        "exposure": exposure.get(capability_id, Exposure.NONE).value,
        "exposed_components": exposed_components(capability_id, w),
        "activity": activity(capability_id, w).value,
        "density": density(capability_id, w).value,
        "components": [{"component_id": c["component_id"],
                        "display_name": c["display_name"],
                        "is_primary": c["is_primary"]} for c in components],
        "subcategories": [{"node_id": s["node_id"], "name": s["name"],
                           "item_count": s["item_count"]} for s in subcategories],
        "work_units": len({e.work_unit_id for e in w.edges
                           if e.capability_id == capability_id}),
        "evidence_items": len({e.item_id for e in w.edges
                               if e.capability_id == capability_id}),
        "coverage_threshold": w.cfg.coverage_threshold.name,
        "as_of": w.cfg.as_of_date.isoformat(),
    }


def get_employee(conn: psycopg.Connection, employee_id: str) -> dict:
    """One person: every capability they hold evidence for, and what it rests on.

    The graph had person nodes you could look at and not click, which made half
    the graph decorative. This is the other half of the same question — a
    capability answers "who holds this?", a person answers "what do they hold,
    and what breaks without them?".

    It states the bus-factor finding directly: `sole_coverer_of` is the list of
    capabilities that go to zero if this person is unavailable, which is the
    single most useful thing the system knows about an individual.
    """
    w, bands = _world(conn)
    if employee_id not in w.employees:
        raise NotFoundError("employee", employee_id)

    v = w.employees[employee_id]
    active = w.coverage_set
    threshold = w.cfg.coverage_threshold

    holds, sole_of = [], []
    for cap, name in sorted(w.capabilities.items(), key=lambda kv: kv[1]):
        br = _band_of(bands, employee_id, cap)
        if br.band == Band.NONE:
            continue
        cov = coverers(cap, active, bands, w.cfg)
        entry = {**_holder(w, bands, employee_id, cap),
                 "capability_id": cap, "capability_name": name,
                 # Below the threshold this person is NOT a coverer, and the UI
                 # must be able to say so without the reader inferring it from
                 # a band name.
                 "counts_as_coverer": br.band >= threshold and employee_id in active,
                 "coverer_count": len(cov),
                 "primary_component": w.primary_component.get(cap),
                 "activity": activity(cap, w).value,
                 "density": density(cap, w).value}
        holds.append(entry)
        if entry["counts_as_coverer"] and cov == [employee_id]:
            sole_of.append({"capability_id": cap, "name": name})

    holds.sort(key=lambda h: (-h["band_code"], h["capability_name"]))
    return {
        "employee_id": employee_id,
        "display_name": v["display_name"],
        "role_title": v["role_title"],
        "status": v["status"],
        "is_simulatable": v["status"] == "active" and not v["is_service_account"],
        "in_coverage_set": employee_id in active,
        "holds": holds,
        "covers_count": sum(1 for h in holds if h["counts_as_coverer"]),
        "sole_coverer_of": sole_of,
        "work_units": len({e.work_unit_id for e in w.edges
                           if e.employee_id == employee_id}),
        "evidence_items": len({e.item_id for e in w.edges
                               if e.employee_id == employee_id}),
        "coverage_threshold": threshold.name,
        "as_of": w.cfg.as_of_date.isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Graphs
# ─────────────────────────────────────────────────────────────────────────────
def evidence_graph(conn: psycopg.Connection, simulate_employee: str | None = None) -> dict:
    """People and capabilities ONLY.

    No "current work item" nodes: the system models EVIDENCE THAT WORK HAPPENED,
    not current assignment. There is no data source for who is working on what
    right now, and inventing one would be a claim we cannot support.
    """
    w, bands = _world(conn)
    active = w.coverage_set
    uncovered = [cap for cap in w.capabilities if not coverers(cap, active, bands, w.cfg)]
    exposure = propagate(uncovered, w)

    nodes, edges = [], []
    for p, v in sorted(w.employees.items()):
        if v["is_service_account"]:
            continue
        nodes.append({"id": f"p:{p}", "type": "person", "label": v["display_name"],
                      "status": v["status"],
                      # Faded, never removed: the evidence still exists, the
                      # person is simply not available.
                      "faded": (p == simulate_employee) or v["status"] == "departed"})

    for cap, name in sorted(w.capabilities.items(), key=lambda kv: kv[1]):
        cov = coverers(cap, active, bands, w.cfg)
        nodes.append({"id": f"c:{cap}", "type": "capability", "label": name,
                      "status": ("Uncovered" if not cov else "Covered"),
                      "exposure": exposure.get(cap, Exposure.NONE).value, "faded": False,
                      # Carried so the two panels can cross-highlight. This is
                      # the only place a viewer can SEE that the graphs are
                      # joined, which makes capability_component visible rather
                      # than theoretical.
                      "component": w.primary_component.get(cap)})

    for p in sorted(w.employees):
        if w.employees[p]["is_service_account"]:
            continue
        for cap in sorted(w.capabilities):
            br = _band_of(bands, p, cap)
            if br.band == Band.NONE:
                continue
            edges.append({"source": f"p:{p}", "target": f"c:{cap}",
                          "band": br.band.name, "band_code": int(br.band),
                          "ceiling_basis": br.basis.ceiling_basis if br.basis else None,
                          "work_units": br.unit_count,
                          "faded": p == simulate_employee or w.employees[p]["status"] == "departed"})

    return {"nodes": nodes, "edges": edges,
            "layout": _demo_layout(nodes) if settings.demo_mode else None,
            "demo_mode": settings.demo_mode}


def _demo_layout(nodes: list[dict]) -> dict[str, dict[str, float]]:
    """Pre-computed node positions for demo mode (Piece 6 §5.4).

    A force graph that lands differently on every load makes rehearsal
    worthless: you cannot point at "the node over there" twice. d3-force's
    charge and link forces jiggle with `Math.random()`, so the settled shape is
    genuinely different each run — pinning it is not cosmetic.

    A deterministic BIPARTITE RING rather than a stored snapshot of one settled
    run: people inside, capabilities outside, both in the sort order the rest of
    the API already uses. It reproduces from the data alone, so it cannot go
    stale when the dataset changes — which a checked-in snapshot would.

    Coordinates are unit-circle; the client scales them to its own viewport.
    """
    import math

    people = [n["id"] for n in nodes if n["type"] == "person"]
    caps = [n["id"] for n in nodes if n["type"] == "capability"]

    def ring(ids: list[str], radius: float, phase: float) -> dict[str, dict[str, float]]:
        out = {}
        for i, node_id in enumerate(ids):
            angle = phase + (2 * math.pi * i / max(1, len(ids)))
            out[node_id] = {"x": round(radius * math.cos(angle), 4),
                            "y": round(radius * math.sin(angle), 4)}
        return out

    # Half a step of phase between the rings so a person never sits directly
    # behind a capability label.
    return {**ring(people, 0.34, 0.0),
            **ring(caps, 0.82, math.pi / max(1, len(caps)))}


def dependency_graph(conn: psycopg.Connection, simulate_employee: str | None = None) -> dict:
    w, bands = _world(conn)
    active = w.coverage_set
    after = active - {simulate_employee} if simulate_employee else active

    at_risk = []
    for cap in w.capabilities:
        cov_b = coverers(cap, active, bands, w.cfg)
        cov_a = coverers(cap, after, bands, w.cfg)
        if not cov_a or len(cov_a) < len(cov_b):
            at_risk.append(cap)
    exposure = propagate(at_risk, w)

    comp_exposure: dict[str, str] = {}
    for cap, exp in exposure.items():
        for comp in w.components_of.get(cap, []):
            if exp is not Exposure.NONE:
                cur = comp_exposure.get(comp)
                if cur != Exposure.DIRECT.value:
                    comp_exposure[comp] = exp.value

    components = query(conn, "SELECT component_id, display_name, service FROM component "
                             "ORDER BY component_id")
    edges = query(conn, "SELECT from_component, to_component, edge_source "
                        "FROM dependency_edge ORDER BY from_component, to_component")
    return {
        "components": [{**c, "exposure": comp_exposure.get(c["component_id"], "none")}
                       for c in components],
        "edges": edges,
        "capability_component": [
            {"capability_node_id": cap, "capability_name": w.capabilities[cap],
             "component_id": comp}
            for cap in sorted(w.capabilities) for comp in w.components_of.get(cap, [])
        ],
    }


def add_dependency_edge(conn: psycopg.Connection, frm: str, to: str) -> dict:
    from app.core.errors import InvalidEdgeError
    if frm == to:
        raise InvalidEdgeError("a component cannot depend on itself", frm, to)
    known = {r["component_id"] for r in query(conn, "SELECT component_id FROM component")}
    if frm not in known or to not in known:
        raise NotFoundError("component", frm if frm not in known else to)
    execute(conn, "INSERT INTO dependency_edge (from_component,to_component,edge_source) "
                  "VALUES (%s,%s,'manual') ON CONFLICT DO NOTHING", (frm, to))
    return dependency_graph(conn)


def remove_dependency_edge(conn: psycopg.Connection, frm: str, to: str) -> dict:
    n = execute(conn, "DELETE FROM dependency_edge WHERE from_component=%s AND to_component=%s",
                (frm, to))
    if not n:
        raise NotFoundError("dependency_edge", f"{frm}->{to}")
    return dependency_graph(conn)

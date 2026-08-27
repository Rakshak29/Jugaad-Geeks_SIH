"""The coverage engine — Stages C and D, attributes, baseline, simulation.

Everything here is a PURE FUNCTION over the database.  Nothing is written, no
network call is made, and no model is consulted.  That is what makes simulation
safe (a recompute over a filtered set, never an edit), the demo deterministic,
and Piece 0 §6 (SC9) structurally true rather than merely asserted.

Stage C:  ceiling = min(role, age, breadth, certainty, substance)
Stage D:  band    = the highest ceiling any single work unit reached,
                    plus the authorship exception
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

import psycopg

from app.core.bands import Band, strongest
from app.core.config_table import Config
from app.core.enums import Activity, Certainty, CoverageStatus, Density, Exposure
from app.db.conn import query


# ─────────────────────────────────────────────────────────────────────────────
# Loading
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Edge:
    employee_id: str
    capability_id: int
    work_unit_id: int
    item_id: int
    raw_record_id: int
    source_type: str
    record_kind: str
    actor_role: str
    ceiling_basis: str
    occurred_at: datetime
    effort_signal: float | None
    certainty: str


@dataclass
class World:
    """Everything the engine needs, loaded once per request."""
    edges: list[Edge]
    capabilities: dict[int, str]
    primary_component: dict[int, str]
    components_of: dict[int, list[str]]
    employees: dict[str, dict]
    dep_edges: list[tuple[str, str]]
    role_caps: dict[tuple[str, str], int]
    unit_time: dict[int, datetime]
    unit_caps: dict[int, set[int]]
    cfg: Config

    @property
    def coverage_set(self) -> set[str]:
        # Piece 3 §10.1 — active employees only. A departed employee is
        # mechanically identical to a permanent, already-applied unavailability.
        return {e for e, v in self.employees.items()
                if v["status"] == "active" and not v["is_service_account"]}


def load_world(conn: psycopg.Connection, cfg: Config) -> World:
    edges = [Edge(**{k: r[k] for k in Edge.__annotations__}) for r in query(conn, """
        SELECT employee_id, capability_node_id AS capability_id, work_unit_id, item_id,
               raw_record_id, source_type, record_kind, actor_role, ceiling_basis,
               occurred_at, effort_signal, certainty::text AS certainty
        FROM evidence_edge ORDER BY employee_id, capability_node_id, work_unit_id, item_id
    """)]

    caps = {r["node_id"]: r["name"] for r in query(conn,
        "SELECT node_id, name FROM cluster_node WHERE node_role='capability' ORDER BY node_id")}

    comps: dict[int, list[str]] = defaultdict(list)
    primary: dict[int, str] = {}
    for r in query(conn, "SELECT capability_node_id, component_id, is_primary "
                         "FROM capability_component ORDER BY capability_node_id, component_id"):
        comps[r["capability_node_id"]].append(r["component_id"])
        if r["is_primary"]:
            primary[r["capability_node_id"]] = r["component_id"]

    employees = {r["employee_id"]: r for r in query(conn,
        "SELECT employee_id, display_name, role_title, status, is_service_account "
        "FROM employee ORDER BY employee_id")}

    dep = [(r["from_component"], r["to_component"]) for r in query(conn,
        "SELECT from_component, to_component FROM dependency_edge "
        "ORDER BY from_component, to_component")]

    role_caps = {(r["source_type"], r["role"]): r["ceiling"] for r in query(conn,
        "SELECT source_type, role, ceiling FROM role_ceiling")}

    unit_time = {r["work_unit_id"]: r["occurred_at"] for r in query(conn,
        "SELECT work_unit_id, occurred_at FROM work_unit")}

    unit_caps: dict[int, set[int]] = defaultdict(set)
    for e in edges:
        unit_caps[e.work_unit_id].add(e.capability_id)

    return World(edges, caps, primary, dict(comps), employees, dep,
                 role_caps, unit_time, dict(unit_caps), cfg)


# ─────────────────────────────────────────────────────────────────────────────
# Stage C — ceilings.  Five independent caps; the MINIMUM wins.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Ceiling:
    band: Band
    binding_cap: str          # which cap actually held the result down
    ceiling_basis: str
    raw_record_id: int
    item_id: int
    occurred_at: datetime
    age_label: str
    certainty: str


def _age_cap(occurred: datetime, cfg: Config) -> tuple[Band, str]:
    """Against the pinned as_of_date, never now() (Piece 3 §13).

    Dormancy never relaxes this. "The code hasn't changed, so the knowledge
    hasn't gone stale" manufactures coverage that was never demonstrated:
    knowledge erodes because the system changes under you AND because memory
    fades, and a stable component removes only the first.
    """
    months = (cfg.as_of_date - occurred).days / 30.44
    if months <= cfg.fresh_window_months:
        return Band.HIGH, "fresh"
    if months <= cfg.aging_window_months:
        return Band.MODERATE, "aging"
    return Band.LOW, "stale"


def ceiling_for(edge: Edge, world: World) -> Ceiling:
    cfg = world.cfg

    role_cap = Band(world.role_caps.get((edge.source_type, edge.actor_role), 0))

    unit_time = world.unit_time.get(edge.work_unit_id, edge.occurred_at)
    age_cap, age_label = _age_cap(unit_time, cfg)

    # Breadth is computed over the WORK UNIT, not the item: a sweeping change is
    # one piece of work that touched many capabilities. It still counts — weakly,
    # per capability — which is the truth.
    touched = len(world.unit_caps.get(edge.work_unit_id, {edge.capability_id}))
    if touched > cfg.breadth_p98:
        breadth_cap = Band.LOW
    elif touched > cfg.breadth_p90:
        breadth_cap = Band.MODERATE
    else:
        breadth_cap = Band.HIGH

    certainty_cap = {"certain": Band.HIGH,
                     "probable": Band.MODERATE,
                     "tentative": Band.LOW}[edge.certainty]

    # Code ONLY. NULL is a NO-OP, never NONE — returning NONE here would silently
    # zero every Jira and incident record, which is the single easiest way to
    # break this engine without any test failing loudly.
    if edge.effort_signal is None:
        substance_cap = Band.HIGH
    elif float(edge.effort_signal) < cfg.effort_p10:
        substance_cap = Band.LOW
    else:
        substance_cap = Band.HIGH

    caps = [("role", role_cap), ("age", age_cap), ("breadth", breadth_cap),
            ("certainty", certainty_cap), ("substance", substance_cap)]
    binding, band = min(caps, key=lambda kv: (kv[1], kv[0]))

    return Ceiling(band=band, binding_cap=binding, ceiling_basis=edge.ceiling_basis,
                   raw_record_id=edge.raw_record_id, item_id=edge.item_id,
                   occurred_at=unit_time, age_label=age_label, certainty=edge.certainty)


# ─────────────────────────────────────────────────────────────────────────────
# Stage D — band assignment.  Two rules, no counts, no tuned thresholds.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class BandResult:
    band: Band
    basis: Ceiling | None
    via_authorship: bool = False
    unit_count: int = 0


AUTHORSHIP_ROLES = {"author", "pr_author"}


def assign_bands(world: World) -> dict[str, dict[int, BandResult]]:
    """Bands for EVERY employee x capability — including departed employees.

    Restricting this to active people would discard exactly the information that
    explains a gap: if a departed person's band is never computed, nothing in the
    system knows they held it, and the dashboard cannot say why the capability is
    uncovered. Filtering happens later, at the coverage set (Piece 3 §11).
    """
    by_person_cap: dict[tuple[str, int], list[Edge]] = defaultdict(list)
    for e in world.edges:
        by_person_cap[(e.employee_id, e.capability_id)].append(e)

    # Fresh AUTHORED units per (capability, person) — both sides of the
    # dominance test count the same thing: authored units against authored units.
    fresh_authored: dict[int, dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
    for e in world.edges:
        if e.actor_role not in AUTHORSHIP_ROLES:
            continue
        unit_time = world.unit_time.get(e.work_unit_id, e.occurred_at)
        if _age_cap(unit_time, world.cfg)[1] == "fresh":
            fresh_authored[e.capability_id][e.employee_id].add(e.work_unit_id)

    out: dict[str, dict[int, BandResult]] = defaultdict(dict)
    for person in sorted(world.employees):
        for cap in sorted(world.capabilities):
            edges = by_person_cap.get((person, cap), [])
            if not edges:
                out[person][cap] = BandResult(Band.NONE, None)
                continue

            # Rule 1 — the band is the highest ceiling ANY SINGLE unit reached.
            # A max, never a sum: two MODERATE units are two MODERATE units.
            per_unit: dict[int, Ceiling] = {}
            for e in edges:
                c = ceiling_for(e, world)
                if e.work_unit_id not in per_unit or c.band > per_unit[e.work_unit_id].band:
                    per_unit[e.work_unit_id] = c
            best = max(per_unit.values(), key=lambda c: (c.band, -c.item_id))
            band, via = best.band, False

            # Rule 2 — the authorship exception. Dominance, not volume: "more
            # than everyone else COMBINED, and more than one". At most one person
            # per capability can hold HIGH by this route, which keeps it scarce.
            if band < Band.HIGH:
                mine = len(fresh_authored[cap].get(person, set()))
                others = sum(len(v) for p, v in fresh_authored[cap].items() if p != person)
                if mine > 1 and mine > others:
                    band, via = Band.HIGH, True

            out[person][cap] = BandResult(band, best, via, len(per_unit))
    return dict(out)


def coverers(cap: int, people: set[str], bands, cfg: Config) -> list[str]:
    return sorted(p for p in people if bands.get(p, {}).get(cap, BandResult(Band.NONE, None)).band
                  >= cfg.coverage_threshold)


def best_band(cap: int, people: set[str], bands) -> tuple[Band, str | None]:
    best, holder = Band.NONE, None
    for p in sorted(people):
        b = bands.get(p, {}).get(cap, BandResult(Band.NONE, None)).band
        if b > best:
            best, holder = b, p
    return best, holder


# ─────────────────────────────────────────────────────────────────────────────
# Orthogonal attributes.  None of these modifies a band or a status.
# ─────────────────────────────────────────────────────────────────────────────
def activity(cap: int, world: World) -> Activity:
    """Counts units from ANYONE, departed included. Filtering to the coverage set
    here would make a capability look dormant because its expert left, which
    conflates two different findings."""
    cutoff_months = world.cfg.fresh_window_months
    for e in world.edges:
        if e.capability_id != cap:
            continue
        t = world.unit_time.get(e.work_unit_id, e.occurred_at)
        if (world.cfg.as_of_date - t).days / 30.44 <= cutoff_months:
            return Activity.ACTIVE
    return Activity.DORMANT


def density(cap: int, world: World) -> Density:
    """Changes NO band. It flags the CONCLUSION as low-certainty, which is what
    stops the system stating a confident band from two data points."""
    units = {e.work_unit_id for e in world.edges if e.capability_id == cap}
    return Density.THIN if len(units) < world.cfg.density_min else Density.ADEQUATE


def _reach(origins: list[int], world: World) -> tuple[set[str], set[str], set[str]]:
    """(origin components, one hop out, two hops out) against the arrow.

    Shared by `propagate` and `exposed_components` so the badge on a card and
    the count in the at-risk headline can never disagree about how far risk
    travels.
    """
    origin_components = {c for cap in origins for c in world.components_of.get(cap, [])}

    d1 = {frm for frm, to in world.dep_edges if to in origin_components}
    d1 -= origin_components                      # never exposed via its own origin

    d2 = {frm for frm, to in world.dep_edges if to in d1}
    d2 -= (origin_components | d1)               # shortest path wins
    return origin_components, d1, d2


def exposed_components(cap: int, world: World) -> list[str]:
    """The components that carry risk when THIS capability is at risk — direct
    dependents and second-degree, sorted.

    The at-risk headline counts these, not the one-hop edges: bounding at two
    hops is the system's own definition of how far a dependency failure
    travels (`propagation_max_hops`), so counting one hop there while drawing
    two on the card states two different numbers for one fact.
    """
    _origin, d1, d2 = _reach([cap], world)
    return sorted(d1 | d2)


def propagate(origins: list[int], world: World) -> dict[int, Exposure]:
    """Exposure flows AGAINST the dependency arrow, bounded at two hops.

    If `payment-api DEPENDS_ON payment-db` and a capability on payment-db is at
    risk, payment-api is exposed — its dependency is now unmaintained.

    This takes origin capabilities and graph data. It does NOT take bands, and it
    returns a separate mapping that is joined to capabilities at presentation
    time. There is no code path by which exposure can alter a band or a status:
    a band means "what evidence exists", and architecture cannot change what
    someone has done.
    """
    origin_components, d1, d2 = _reach(origins, world)

    out: dict[int, Exposure] = {}
    for cap in world.capabilities:
        mine = set(world.components_of.get(cap, []))
        if mine & d1:
            out[cap] = Exposure.DIRECT           # strongest wins
        elif mine & d2:
            out[cap] = Exposure.SECOND_DEGREE
        else:
            out[cap] = Exposure.NONE
    return out

"""Records and pipeline results — the "show your working" facade.

`services.py` answers *what the system concluded*.  This answers *what it read,
and how it got there* — and until now that only existed in the terminal, which
meant the strongest part of the project (the Round 1 feedback answer: how
heterogeneous sources are actually accessed, normalized and linked) was
invisible to anyone looking at the UI.

Everything here is read-only.  It sits right of the freeze line with the rest of
the engine: no writes, no network, no model.
"""

from __future__ import annotations

import psycopg

from app.db.conn import query, query_one

#: Human-readable prose for a record, whatever source it came from.  Title and
#: body only — never a diff, never a person's name.
_TITLE_SQL = """
    trim(coalesce(
        rr.payload #>> '{fields,summary}',
        split_part(rr.payload #>> '{commit,message}', E'\\n', 1),
        rr.payload ->> 'title',
        rr.source_native_id))
"""


def list_records(conn: psycopg.Connection, source_type: str | None = None,
                 eligibility: str | None = None, capability_id: int | None = None,
                 search: str | None = None, limit: int = 200) -> dict:
    """Every raw record, with what the pipeline made of it.

    The row is the join a reader actually wants: the source record on one side,
    and on the other which actors it produced, which ladder rung fired, whether
    Stage A kept it, and which capability it ended up under. Reading those from
    four separate places is how you lose the thread.
    """
    where, params = ["1=1"], []
    if source_type:
        where.append("rr.source_type = %s")
        params.append(source_type)
    if eligibility in ("eligible", "excluded"):
        # A record is 'excluded' only if NO actor row survived Stage A — one
        # eligible actor makes the record evidence.
        where.append(
            "EXISTS (SELECT 1 FROM extracted_item x WHERE x.raw_record_id = rr.raw_record_id"
            "        AND x.eligibility_state = %s)")
        params.append(eligibility)
    if capability_id is not None:
        where.append("""EXISTS (
            SELECT 1 FROM extracted_item x
            JOIN cluster_membership cm ON cm.item_id = x.item_id
            JOIN capability_descendant cd ON cd.descendant_id = cm.node_id
            WHERE x.raw_record_id = rr.raw_record_id AND cd.capability_node_id = %s)""")
        params.append(capability_id)
    if search:
        where.append(f"({_TITLE_SQL} ILIKE %s OR rr.source_native_id ILIKE %s)")
        params += [f"%{search}%", f"%{search}%"]

    rows = query(conn, f"""
        SELECT rr.raw_record_id, rr.source_type, rr.source_native_id, rr.ingested_at,
               {_TITLE_SQL} AS title,
               (SELECT min(x.record_kind::text) FROM extracted_item x
                 WHERE x.raw_record_id = rr.raw_record_id) AS record_kind,
               (SELECT min(x.occurred_at) FROM extracted_item x
                 WHERE x.raw_record_id = rr.raw_record_id) AS occurred_at,
               (SELECT count(*) FROM extracted_item x
                 WHERE x.raw_record_id = rr.raw_record_id) AS actor_count,
               (SELECT count(*) FROM extracted_item x
                 WHERE x.raw_record_id = rr.raw_record_id
                   AND x.eligibility_state = 'eligible') AS eligible_count,
               (SELECT min(x.extraction_method::text) FROM extracted_item x
                 WHERE x.raw_record_id = rr.raw_record_id) AS extraction_method,
               (SELECT min(x.certainty::text) FROM extracted_item x
                 WHERE x.raw_record_id = rr.raw_record_id) AS certainty,
               (SELECT array_agg(DISTINCT e.display_name ORDER BY e.display_name)
                  FROM extracted_item x JOIN employee e ON e.employee_id = x.employee_id
                 WHERE x.raw_record_id = rr.raw_record_id) AS people,
               (SELECT array_agg(DISTINCT n.name ORDER BY n.name)
                  FROM extracted_item x
                  JOIN cluster_membership cm ON cm.item_id = x.item_id
                  JOIN capability_descendant cd ON cd.descendant_id = cm.node_id
                  JOIN cluster_node n ON n.node_id = cd.capability_node_id
                 WHERE x.raw_record_id = rr.raw_record_id) AS capabilities,
               (SELECT array_agg(DISTINCT x.exclusion_reason)
                  FROM extracted_item x
                 WHERE x.raw_record_id = rr.raw_record_id
                   AND x.exclusion_reason IS NOT NULL) AS exclusion_reasons
        FROM raw_record rr
        WHERE {' AND '.join(where)}
        ORDER BY occurred_at DESC NULLS LAST, rr.raw_record_id DESC
        LIMIT %s
    """, (*params, limit))

    total = query_one(conn, "SELECT count(*) n FROM raw_record")["n"]
    facets = query(conn, "SELECT source_type, count(*) n FROM raw_record "
                         "GROUP BY 1 ORDER BY 1")
    return {
        "records": [{**r,
                     "ingested_at": r["ingested_at"].isoformat(),
                     "occurred_at": r["occurred_at"].isoformat() if r["occurred_at"] else None,
                     "people": r["people"] or [],
                     "capabilities": r["capabilities"] or [],
                     "exclusion_reasons": r["exclusion_reasons"] or []}
                    for r in rows],
        "shown": len(rows),
        "total": total,
        "facets": {f["source_type"]: f["n"] for f in facets},
    }


def get_record(conn: psycopg.Connection, raw_record_id: int) -> dict:
    """One record, plus every row the pipeline derived from it.

    This is the traceability claim running BACKWARDS. Everywhere else the reader
    goes conclusion → record; here they go record → conclusion, and can check
    that the ladder fired the way the drill-down said it did.
    """
    from app.core.errors import NotFoundError

    rr = query_one(conn, """
        SELECT rr.raw_record_id, rr.source_type, rr.source_native_id, rr.payload,
               rr.content_hash, rr.ingested_at
        FROM raw_record rr WHERE rr.raw_record_id = %s
    """, (raw_record_id,))
    if not rr:
        raise NotFoundError("raw_record", str(raw_record_id))

    items = query(conn, """
        SELECT ei.item_id, ei.record_kind::text, ei.native_actor_id, ei.employee_id,
               e.display_name, e.status AS employee_status,
               ei.occurred_at, ei.actor_role, ei.ceiling_basis,
               ei.extraction_method::text, ei.certainty::text,
               ei.eligibility_state, ei.exclusion_reason, ei.effort_signal,
               ei.feature_tokens,
               rc.rung, rc.ceiling AS role_ceiling, rc.rationale AS rung_rationale,
               wm.work_unit_id
        FROM extracted_item ei
        LEFT JOIN employee e ON e.employee_id = ei.employee_id
        LEFT JOIN role_ceiling rc
               ON rc.source_type = ei.source_type AND rc.role = ei.actor_role
        LEFT JOIN work_unit_member wm ON wm.item_id = ei.item_id
        WHERE ei.raw_record_id = %s
        ORDER BY rc.rung NULLS LAST, ei.item_id
    """, (raw_record_id,))

    caps = query(conn, """
        SELECT DISTINCT n.node_id, n.name, cm.merge_method, cm.review_state,
               cm.certainty::text AS link_certainty
        FROM extracted_item ei
        JOIN cluster_membership cm ON cm.item_id = ei.item_id
        JOIN capability_descendant cd ON cd.descendant_id = cm.node_id
        JOIN cluster_node n ON n.node_id = cd.capability_node_id
        WHERE ei.raw_record_id = %s ORDER BY n.name
    """, (raw_record_id,))

    band = {0: "NONE", 1: "LOW", 2: "MODERATE", 3: "HIGH"}
    return {
        **{k: rr[k] for k in ("raw_record_id", "source_type", "source_native_id", "payload")},
        "content_hash": rr["content_hash"],
        "ingested_at": rr["ingested_at"].isoformat(),
        "items": [{**i,
                   "occurred_at": i["occurred_at"].isoformat(),
                   "effort_signal": float(i["effort_signal"]) if i["effort_signal"] is not None else None,
                   "role_ceiling": band.get(i["role_ceiling"]) if i["role_ceiling"] is not None else None}
                  for i in items],
        "capabilities": caps,
    }


def list_work_units(conn: psycopg.Connection, limit: int = 200) -> dict:
    """Work units, multi-record ones first.

    The claim this exists to make visible: one ticket, one commit and one PR are
    ONE piece of work. Counting them as three inflates an afternoon into a
    pattern, so every count in the band engine is over units — and here you can
    see which records got collapsed and what joined them.
    """
    rows = query(conn, """
        SELECT wu.work_unit_id, wu.member_count, wu.occurred_at,
               array_agg(DISTINCT rr.source_type ORDER BY rr.source_type) AS sources,
               array_agg(DISTINCT rr.source_native_id ORDER BY rr.source_native_id) AS members,
               array_agg(DISTINCT rr.raw_record_id) AS record_ids,
               (SELECT array_agg(DISTINCT n.name ORDER BY n.name)
                  FROM work_unit_member w2
                  JOIN cluster_membership cm ON cm.item_id = w2.item_id
                  JOIN capability_descendant cd ON cd.descendant_id = cm.node_id
                  JOIN cluster_node n ON n.node_id = cd.capability_node_id
                 WHERE w2.work_unit_id = wu.work_unit_id) AS capabilities,
               (SELECT array_agg(DISTINCT e.display_name ORDER BY e.display_name)
                  FROM work_unit_member w3
                  JOIN extracted_item x ON x.item_id = w3.item_id
                  JOIN employee e ON e.employee_id = x.employee_id
                 WHERE w3.work_unit_id = wu.work_unit_id) AS people
        FROM work_unit wu
        JOIN work_unit_member wm ON wm.work_unit_id = wu.work_unit_id
        JOIN extracted_item ei ON ei.item_id = wm.item_id
        JOIN raw_record rr ON rr.raw_record_id = ei.raw_record_id
        GROUP BY wu.work_unit_id, wu.member_count, wu.occurred_at
        ORDER BY wu.member_count DESC, wu.occurred_at DESC
        LIMIT %s
    """, (limit,))
    total = query_one(conn, "SELECT count(*) n FROM work_unit")["n"]
    multi = query_one(conn, "SELECT count(*) n FROM work_unit WHERE member_count > 1")["n"]
    items = query_one(conn, "SELECT count(*) n FROM work_unit_member")["n"]
    return {
        "units": [{**r,
                   "occurred_at": r["occurred_at"].isoformat(),
                   "capabilities": r["capabilities"] or [],
                   "people": r["people"] or []} for r in rows],
        "total": total, "multi_record": multi, "items": items,
    }


def pipeline_report(conn: psycopg.Connection) -> dict:
    """Everything the terminal prints about how the numbers were produced.

    Config with its basis, the ladder rungs with what fired, and the ingestion
    counts. `ece report config` / `ece report ladders` answered "why is that
    number what it is?" for anyone at a keyboard; there was no answer at all for
    anyone looking at the screen.
    """
    from app.validation.validate import UNEXERCISED_RUNGS

    config = query(conn, "SELECT key, value, kind, basis, rationale, owned_by "
                         "FROM config ORDER BY kind, key")

    rungs = query(conn, "SELECT source_type, rung, role, ceiling, availability, rationale "
                        "FROM role_ceiling ORDER BY source_type, rung")
    fired = {r["actor_role"]: r["n"] for r in query(
        conn, "SELECT actor_role, count(*) n FROM extracted_item "
              "WHERE actor_role IS NOT NULL GROUP BY actor_role")}
    band = {0: "NONE", 1: "LOW", 2: "MODERATE", 3: "HIGH"}

    sources = query(conn, """
        SELECT rr.source_type,
               count(DISTINCT rr.raw_record_id) AS records,
               count(ei.item_id) AS items,
               count(ei.item_id) FILTER (WHERE ei.eligibility_state = 'eligible') AS eligible
        FROM raw_record rr
        LEFT JOIN extracted_item ei ON ei.raw_record_id = rr.raw_record_id
        GROUP BY rr.source_type ORDER BY rr.source_type
    """)
    excluded = query(conn, "SELECT exclusion_reason, count(*) n FROM extracted_item "
                           "WHERE exclusion_reason IS NOT NULL GROUP BY 1 ORDER BY n DESC")
    tiers = query(conn, "SELECT extraction_method::text AS method, certainty::text, count(*) n "
                        "FROM extracted_item GROUP BY 1,2 ORDER BY 1")
    unmapped = query_one(conn, "SELECT count(*) n FROM extracted_item "
                               "WHERE employee_id IS NULL AND eligibility_state='eligible'")["n"]
    tree = query_one(conn, """
        SELECT (SELECT count(*) FROM cluster_node WHERE node_role='capability') AS capabilities,
               (SELECT count(*) FROM cluster_node WHERE node_role='subcategory') AS subcategories,
               (SELECT count(*) FROM cluster_membership) AS memberships,
               (SELECT count(*) FROM cluster_membership
                 WHERE review_state='pending_review') AS pending_review,
               (SELECT label FROM tree_version WHERE status='frozen'
                 ORDER BY tree_version_id DESC LIMIT 1) AS frozen_label,
               (SELECT frozen_at FROM tree_version WHERE status='frozen'
                 ORDER BY tree_version_id DESC LIMIT 1) AS frozen_at
    """)

    return {
        "config": config,
        "ladders": [{**r,
                     "ceiling": band[r["ceiling"]],
                     "fired": fired.get(r["role"], 0),
                     # A rung the data never reaches is UNTESTED, and saying so
                     # beats a claim of "16 rungs" nobody can check.
                     "unexercised_reason": UNEXERCISED_RUNGS.get(
                         (r["source_type"], r["role"]))}
                    for r in rungs],
        "sources": sources,
        "excluded": excluded,
        "tiers": tiers,
        "unmapped_eligible": unmapped,
        "tree": {**tree,
                 "frozen_at": tree["frozen_at"].isoformat() if tree["frozen_at"] else None},
    }

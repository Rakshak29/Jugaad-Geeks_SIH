"""Work-unit collapse — Stage B of band assignment (Piece 2 §6.5, Piece 3 §5).

One piece of real work leaves a ticket, a commit and a PR.  Counting those as
three pieces of evidence inflates an afternoon's work into a pattern.  Work
units collapse them back into the single thing they describe, and **all
counting in the band engine happens over units**.

The linking data already exists — it is the same explicit-reference evidence
cross-source cluster merging uses (`Closes PAY-501`, PR->issue links, incident
`service_id` -> repository mapping).  Only `certain`-tier references form units.
Embedding similarity never merges two records into one work unit — an uncertain
guess that *collapses* evidence is more dangerous than one that spreads it.
"""

from __future__ import annotations

from collections import defaultdict

import psycopg

from app.clustering.references import item_reference_index
from app.db.conn import execute, query, query_one


def build_work_units(conn: psycopg.Connection) -> int:
    """Union-find over certain-tier references.  Idempotent: truncates and
    rebuilds, so re-freezing never accumulates units."""
    execute(conn, "TRUNCATE work_unit_member, work_unit CASCADE")
    refs = item_reference_index(conn)

    rows = query(conn, "SELECT item_id, occurred_at FROM extracted_item "
                       "WHERE eligibility_state='eligible' ORDER BY item_id")
    items = [r["item_id"] for r in rows]
    when = {r["item_id"]: r["occurred_at"] for r in rows}
    parent = {i: i for i in items}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    # Only TICKET and PR keys collapse items. A service key is capability-wide
    # rather than task-specific, so collapsing on it would merge every incident
    # on a service into one unit — and an uncertain guess that COLLAPSES evidence
    # is more dangerous than one that spreads it (Piece 3 §5.2).
    by_key: dict[str, list[int]] = defaultdict(list)
    for item_id in items:
        for key in refs.get(item_id, set()):
            if not key.startswith("SVC:"):
                by_key[key].append(item_id)
    for key in sorted(by_key):
        members = sorted(by_key[key])
        for other in members[1:]:
            union(members[0], other)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in items:
        groups[find(i)].append(i)

    created = 0
    for _root, members in sorted(groups.items()):
        members = sorted(members)
        unit_id = query_one(conn, """
            INSERT INTO work_unit (occurred_at, member_count) VALUES (%s,%s)
            RETURNING work_unit_id
        """, (max(when[m] for m in members), len(members)))["work_unit_id"]
        for m in members:
            execute(conn, "INSERT INTO work_unit_member (work_unit_id,item_id) VALUES (%s,%s)",
                    (unit_id, m))
        created += 1
    return created
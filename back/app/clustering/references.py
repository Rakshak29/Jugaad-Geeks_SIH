"""Explicit references — the linking signal, extracted once and used twice.

Piece 3 §5.2: *"No new mechanism and no new ingestion."*  The same explicit
references that merge CLUSTERS across sources (Piece 2 stage 4) also collapse
ITEMS into work units (stage 7).  One extractor, two granularities.

This is the linking claim, and it rests on a literal string match rather than on
a model's opinion:

    commit message "Restore replica after failover. Closes PAY-501"
    +  ticket       PAY-501
    -> certain-tier reference
"""

from __future__ import annotations

import re
from collections import defaultdict

import psycopg

from app.db.conn import query

TICKET_RE = re.compile(r"\b(?:PAY|JIRA|ENG|OPS)-\d+\b")


def ticket_keys(text: str) -> set[str]:
    return set(TICKET_RE.findall(text or ""))


def service_to_path_prefix(conn: psycopg.Connection) -> dict[str, str]:
    """`service_id` -> repository path prefix.

    An incident naming `payment-db` and a commit under `payment-db/...` are
    linked by a literal mapping, not by similarity.  In a real deployment this
    is a service catalogue; here it is derived from the paths actually present
    in the repository, so it is data rather than a hand-written table.
    """
    rows = query(conn, """
        SELECT DISTINCT unnest(feature_tokens) AS token
        FROM extracted_item WHERE source_type = 'github'
    """)
    prefixes = {r["token"][4:] for r in rows if r["token"].startswith("dir:")}
    roots = {p.split("/")[0] for p in prefixes if p}
    return {root: root for root in roots}


def item_reference_index(conn: psycopg.Connection) -> dict[int, set[str]]:
    """item_id -> the set of external keys that item explicitly references.

    Two items sharing a key are joined by a `certain`-tier reference.
    """
    index: dict[int, set[str]] = defaultdict(set)

    rows = query(conn, """
        SELECT ei.item_id, ei.source_type, ei.record_kind, ei.feature_tokens,
               rr.source_native_id, rr.payload
        FROM extracted_item ei
        JOIN raw_record rr ON rr.raw_record_id = ei.raw_record_id
        ORDER BY ei.item_id
    """)

    for r in rows:
        item_id = r["item_id"]
        payload = r["payload"] or {}

        if r["source_type"] == "jira":
            # A ticket IS its key.
            index[item_id].add(r["source_native_id"])

        elif r["source_type"] == "github":
            if r["record_kind"] == "commit":
                text = ((payload.get("commit") or {}).get("message")) or ""
            else:
                text = f"{payload.get('title','')} {payload.get('body','')}"
            index[item_id] |= ticket_keys(text)
            # A PR and its reviews describe the same change.
            pr_number = payload.get("number") or payload.get("_pr_number")
            if pr_number:
                index[item_id].add(f"PR#{pr_number}")

            # A pull request and the commits INSIDE it are one piece of work.
            # Piece 3 §5.1's canonical case is exactly this: a ticket, a commit
            # and a PR describing one afternoon. Without this the PR and its own
            # commit stay separate units, and every pull request quietly adds an
            # extra authored unit for its author — which is enough to tip the
            # authorship exception, since that test counts units.
            own_sha = payload.get("sha")
            if own_sha:
                index[item_id].add(f"SHA:{own_sha}")
            for commit in payload.get("_commits") or []:
                sha = commit.get("sha")
                if sha:
                    index[item_id].add(f"SHA:{sha}")
            # The service the code lives under. An incident naming `payment-db`
            # and a commit under `payment-db/...` are joined by this literal
            # mapping — the same one Piece 2 §14 walks through.
            for token in r["feature_tokens"] or []:
                if token.startswith("dir:"):
                    root = token[4:].split("/")[0]
                    if root:
                        index[item_id].add(f"SVC:{root}")

        elif r["source_type"] == "incident":
            service = (payload.get("service_id")
                       or (payload.get("service") or {}).get("id") or "")
            if service:
                index[item_id].add(f"SVC:{service}")
            tracking = (payload.get("tracking_ticket") or "").strip()
            if tracking:
                index[item_id].add(tracking)

    return dict(index)

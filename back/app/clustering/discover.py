"""Capability discovery — within-source clustering, then cross-source linking.

Piece 1 §3.3–3.4.  Clustering does not understand meaning.  It measures overlap,
and it works because real engineering work leaves a correlated footprint: people
working on one responsibility touch the same files, file under the same Jira
component, and respond to incidents on the same service.  The algorithm exploits
that pattern; it does not reason about it.

    1. turn each item into a feature set
    2. compute pairwise overlap
    3. draw an edge where overlap exceeds the threshold
    4. connected components -> leaf clusters

The justification is that this is COUNTING, not inference: two commits that both
touch `payment-db/recovery/` are objectively related by that shared fact.  The
real risk is therefore not that the method is unsound but that the THRESHOLD is
miscalibrated — too loose merges unrelated work, too tight fragments it.  That
is why the threshold is swept against the dataset rather than left at a library
default, and why the fix for a missed grouping is more overlap in the DATA, never
a looser threshold.

One structural detail worth stating, because it is where a naive implementation
goes wrong: **a sweeping change belongs to every capability it touched.**  A
refactor across six directories has low Jaccard similarity with everything (its
token set is huge), so connected components would strand it in a cluster of one
and it would produce no evidence at all.  The second pass fixes that with a
SUBSET test rather than a second threshold — an item joins any leaf whose shared
directory signature it contains.  It then counts weakly for each capability via
the breadth cap, which is the truth.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import psycopg

from app.core.enums import Certainty, MergeMethod, NodeRole, ReviewState
from app.db.conn import execute, query
from app.clustering.references import item_reference_index


# ─────────────────────────────────────────────────────────────────────────────
# Similarity
# ─────────────────────────────────────────────────────────────────────────────
def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    return inter / len(a | b)


def signature(tokens: list[str]) -> frozenset[str]:
    """The clustering signature: directory tokens for code, the explicit field
    token for everything else.  Full file paths are deliberately excluded —
    two engineers working on one capability rarely touch the identical file, so
    filename overlap fragments work that directory overlap groups correctly."""
    dirs = {t for t in tokens if t.startswith("dir:")}
    fields = {t for t in tokens if t.startswith(("component:", "label:", "project:",
                                                 "service:", "ticket:"))}
    return frozenset(dirs or fields)


@dataclass
class DiscoveryReport:
    leaves: int = 0
    parents: int = 0
    memberships: int = 0
    auto_applied: int = 0
    pending_review: int = 0
    unclassified: int = 0
    similarity_matches: list = field(default_factory=list)
    per_source: dict[str, int] = field(default_factory=dict)

    def lines(self) -> list[str]:
        out = [
            f"leaf clusters    : {self.leaves}  ({', '.join(f'{k}={v}' for k, v in sorted(self.per_source.items()))})",
            f"parent clusters  : {self.parents}",
            f"memberships      : {self.memberships} "
            f"(auto_applied={self.auto_applied}, pending_review={self.pending_review})",
            f"unclassified     : {self.unclassified}",
        ]
        if self.similarity_matches:
            out.append(f"jira tier 4      : {len(self.similarity_matches)} ticket(s) matched "
                       f"by TF-IDF cosine — ALL pending_review, contributing nothing "
                       f"to any band until approved")
            for m in self.similarity_matches[:6]:
                out.append(f"    item {m.item_id} -> node {m.node_id}  cosine {m.score}")
        return out


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1 — within source
# ─────────────────────────────────────────────────────────────────────────────
def _components(item_ids: list[int], sigs: dict[int, frozenset[str]],
                threshold: float) -> list[list[int]]:
    """Threshold graph + connected components.  Deterministic: items are
    processed in id order and components are emitted sorted by their minimum
    member id, so two runs produce identical clusters."""
    parent = {i: i for i in item_ids}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    ordered = sorted(item_ids)
    for idx, a in enumerate(ordered):
        for b in ordered[idx + 1:]:
            if jaccard(sigs[a], sigs[b]) >= threshold:
                union(a, b)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in ordered:
        groups[find(i)].append(i)
    return [sorted(v) for _, v in sorted(groups.items())]


def discover(conn: psycopg.Connection, threshold: float,
             tree_version_id: int) -> DiscoveryReport:
    report = DiscoveryReport()

    rows = query(conn, """
        SELECT item_id, source_type, feature_tokens, extraction_method
        FROM extracted_item
        WHERE eligibility_state = 'eligible'
        ORDER BY item_id
    """)

    sigs = {r["item_id"]: signature(r["feature_tokens"]) for r in rows}
    by_source: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        if r["extraction_method"] == "unclassified" or not sigs[r["item_id"]]:
            report.unclassified += 1
            continue
        by_source[r["source_type"]].append(r["item_id"])

    # ── Phase 1: leaves, one set per source, never crossing sources ──────────
    leaf_nodes: list[tuple[int, str, frozenset[str], list[int]]] = []
    for source in sorted(by_source):
        for members in _components(by_source[source], sigs, threshold):
            # The leaf's shared signature: what every member has in common.
            common = frozenset.intersection(*[sigs[m] for m in members]) if members else frozenset()
            if not common:
                common = sigs[members[0]]
            label = sorted(common)[0] if common else f"{source}-leaf"
            node_id = execute_returning(conn, """
                INSERT INTO cluster_node
                    (tree_version_id, parent_id, node_role, name, name_source)
                VALUES (%s, NULL, 'subcategory', %s, 'llm')
                RETURNING node_id
            """, (tree_version_id, f"{source}: {label}"))
            leaf_nodes.append((node_id, source, common, members))
            report.per_source[source] = report.per_source.get(source, 0) + 1
    report.leaves = len(leaf_nodes)

    # ── Membership, including the sweeping-change second pass ────────────────
    for node_id, source, common, members in leaf_nodes:
        assigned = set(members)

        # A wide change joins every leaf whose shared signature it contains.
        # A SUBSET test, not a second threshold — nothing new to calibrate.
        if common:
            for r in rows:
                iid = r["item_id"]
                if iid in assigned or r["source_type"] != source:
                    continue
                if common and common <= sigs[iid]:
                    assigned.add(iid)

        for item_id in sorted(assigned):
            execute(conn, """
                INSERT INTO cluster_membership
                    (node_id, item_id, certainty, merge_method, review_state)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (node_id, item_id, Certainty.CERTAIN.value,
                  MergeMethod.WITHIN_SOURCE.value, ReviewState.AUTO_APPLIED.value))
            report.memberships += 1
            report.auto_applied += 1

    # ── Phase 2: cross-source merge, by EXPLICIT REFERENCE ───────────────────
    report.parents = _merge_cross_source(conn, tree_version_id, leaf_nodes, report)

    # ── Phase 3: Jira ladder tier 4 — TF-IDF cosine against cluster summaries.
    #
    # It runs HERE and not in normalization because it compares a ticket against
    # cluster summaries, which do not exist until the leaves above do. Every
    # match lands as `pending_review`, so nothing it decides reaches a band
    # until a human approves it (Piece 1 §3.2, §3.4).
    from app.clustering.similarity import apply_similarity_tier

    matches = apply_similarity_tier(conn, tree_version_id)
    report.similarity_matches = matches
    report.memberships += len(matches)
    report.pending_review += len(matches)
    report.unclassified -= len(matches)
    return report


def execute_returning(conn: psycopg.Connection, sql: str, params) -> int:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()["node_id"]


def _merge_cross_source(conn: psycopg.Connection, tree_version_id: int,
                        leaf_nodes: list, report: DiscoveryReport) -> int:
    """Merge leaves from different sources that are joined by explicit
    references, and roll them up under a parent node.

    `certain`-tier references apply automatically.  Anything weaker would go to
    `pending_review` and contribute nothing until a human approves it — the
    gating is enforced by the `evidence_edge` view, not by discipline.
    """
    refs = item_reference_index(conn)

    # leaf -> the union of external keys its members reference
    leaf_keys: dict[int, set[str]] = {}
    leaf_by_id = {n[0]: n for n in leaf_nodes}
    for node_id, source, _common, members in leaf_nodes:
        keys: set[str] = set()
        for m in members:
            keys |= refs.get(m, set())
        leaf_keys[node_id] = keys

    # A DIRECT star, not a transitive union.
    #
    # Transitive merging chains: leaf A shares a ticket with B, B shares a
    # different ticket with C, and one union-find pass collapses six unrelated
    # capabilities into a single cluster. The spec's "connected directly or
    # through a chain" governs items WITHIN a source, where the shared signal is
    # the same kind of thing throughout. Across sources the links are
    # heterogeneous — a ticket key and a service id are not interchangeable — so
    # each cross-source group is anchored on ONE source leaf and admits only the
    # leaves that reference it directly.
    #
    # The anchor is the code leaf, because the repository is the only source
    # whose granularity matches a capability: Jira components and incident
    # services are coarser and legitimately span several.
    groups: dict[int, list[int]] = {}
    claimed: set[int] = set()

    code_leaves = [n for n in leaf_nodes if n[1] == "github"]
    other_leaves = [n for n in leaf_nodes if n[1] != "github"]

    for node_id, _source, _common, _members in sorted(code_leaves):
        keys = leaf_keys[node_id]
        if not keys:
            continue
        members = [node_id]
        for other_id, other_source, _c, _m in sorted(other_leaves):
            if other_id in claimed:
                continue
            shared = keys & leaf_keys[other_id]
            if not shared:
                continue
            # A ticket key is capability-specific; a service key is not, so a
            # service-only link is accepted only when nothing sharper exists.
            if any(not k.startswith("SVC:") for k in shared):
                members.append(other_id)
                claimed.add(other_id)
        if len(members) > 1:
            groups[node_id] = members

    # Second pass: incident leaves that matched nothing on a ticket key attach
    # to the code leaf they share a service with. An incident on `payment-db`
    # is evidence for work on `payment-db/...` even with no ticket in between.
    for other_id, other_source, _c, _m in sorted(other_leaves):
        if other_id in claimed:
            continue
        best = None
        for node_id, _s, _c2, _m2 in sorted(code_leaves):
            if leaf_keys[other_id] & leaf_keys[node_id]:
                best = node_id
                break
        if best is not None:
            groups.setdefault(best, [best]).append(other_id)
            claimed.add(other_id)

    created = 0
    for root, children in sorted(groups.items()):
        if len(children) < 2:
            continue                          # nothing merged; leaf stands alone
        parent_id = execute_returning(conn, """
            INSERT INTO cluster_node
                (tree_version_id, parent_id, node_role, name, name_source)
            VALUES (%s, NULL, 'capability', %s, 'llm')
            RETURNING node_id
        """, (tree_version_id, f"candidate-{root}"))
        for child in sorted(children):
            execute(conn, "UPDATE cluster_node SET parent_id = %s WHERE node_id = %s",
                    (parent_id, child))
        created += 1
    return created

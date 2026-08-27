"""Tier 4 of the Jira fallback ladder — TF-IDF cosine against cluster summaries.

Piece 1 §3.2 specifies the fourth rung as text similarity: *"embed ticket title
+ description and compare against existing cluster summaries"*.  The demo scope
plan substitutes TF-IDF cosine for a neural embedding (DEMO_SCOPE_PLAN §2) —
same interface, deterministic, offline, no model download, and a neural encoder
drops in behind the same `score()` call with nothing downstream changing.

**Why this cannot live in `extractors.py`.**  The rung compares a ticket against
*cluster summaries*, and clusters do not exist during normalization.  So the
first three rungs are decided per-record at extraction time, and this one is a
narrow, named write-back applied AFTER within-source clustering.

**Why the result is `tentative` and `pending_review`.**  The first three rungs
read a field a human filled in; this one reads a guess about prose.  A
similarity match is exactly the kind of link the certainty gate exists for: the
`evidence_edge` view filters `review_state <> 'human_approved'` out of the
evidence graph, so a tier-4 membership contributes NOTHING to any band until a
human approves it.  That gating is enforced by the view, not by discipline —
which is why this rung can exist at all without weakening a single claim.

Nothing here merges records into a work unit.  Work units require a `certain`
reference (`app/workunits`): an uncertain guess that COLLAPSES evidence is more
dangerous than one that spreads it.
"""

from __future__ import annotations

from dataclasses import dataclass
import psycopg

from app.core.enums import Certainty, ExtractionMethod, MergeMethod, ReviewState
from app.db.conn import execute, query

# 1. Import your neural model dependencies safely
from sentence_transformers import SentenceTransformer, util

MATCH_FLOOR = 0.25

# Global variable to load the model lazily (prevents startup lag)
_MODEL = None

def _get_model():
    global _MODEL
    if _MODEL is None:
        _MODEL = SentenceTransformer('all-MiniLM-L6-v2')
    return _MODEL


@dataclass(frozen=True)
class SimilarityMatch:
    item_id: int
    node_id: int
    score: float


# 2. REPLACE THE OLD TF-IDF `score()` WITH THIS NEURAL VERSION:
def score(unclassified: list[str], summaries: list[str]) -> list[list[float]]:
    """Neural cosine similarity matching the exact signature required by his code."""
    if not unclassified or not summaries:
        return [[0.0] * len(summaries) for _ in unclassified]

    model = _get_model()

    # Encode texts into dense neural embeddings
    unclassified_embeddings = model.encode(unclassified, convert_to_tensor=True)
    summary_embeddings = model.encode(summaries, convert_to_tensor=True)

    # Compute cosine similarity matrix using sentence-transformers util
    cos_scores = util.cos_sim(unclassified_embeddings, summary_embeddings)

    return cos_scores.tolist()


# The prose of a record, whatever source it came from.  Title and body only —
# never a diff, never a person's name — which is the same bounded input the
# namer receives, for the same reason.
_TEXT_SQL = """
    trim(concat_ws(' ',
        rr.payload #>> '{fields,summary}',
        rr.payload #>> '{fields,description}',
        rr.payload #>> '{commit,message}',
        rr.payload ->> 'title',
        rr.payload ->> 'description'))
"""


def _cluster_summaries(conn: psycopg.Connection,
                       tree_version_id: int) -> list[tuple[int, str]]:
    """One text per leaf cluster: the prose of the items already in it.

    A description of an already-formed group — the same boundary the namer
    works within.  Nothing here decides membership on its own; it produces the
    text a comparison is made against.
    """
    rows = query(conn, f"""
        SELECT n.node_id,
               string_agg({_TEXT_SQL}, ' ' ORDER BY ei.item_id) AS summary
        FROM cluster_node n
        JOIN cluster_membership cm ON cm.node_id = n.node_id
        JOIN extracted_item ei ON ei.item_id = cm.item_id
        JOIN raw_record rr ON rr.raw_record_id = ei.raw_record_id
        WHERE n.tree_version_id = %s
        GROUP BY n.node_id ORDER BY n.node_id
    """, (tree_version_id,))
    return [(r["node_id"], r["summary"]) for r in rows if (r["summary"] or "").strip()]


def _unclassified_items(conn: psycopg.Connection) -> list[tuple[int, str]]:
    """Tickets that fell through components, labels and project — the ones
    tier 4 exists for.  Anything already in a cluster is left alone."""
    rows = query(conn, f"""
        SELECT ei.item_id, {_TEXT_SQL} AS text
        FROM extracted_item ei
        JOIN raw_record rr ON rr.raw_record_id = ei.raw_record_id
        WHERE ei.source_type = 'jira'
          AND ei.eligibility_state = 'eligible'
          AND ei.extraction_method = 'unclassified'
          AND NOT EXISTS (SELECT 1 FROM cluster_membership cm
                           WHERE cm.item_id = ei.item_id)
        ORDER BY ei.item_id
    """)
    return [(r["item_id"], r["text"] or "") for r in rows if (r["text"] or "").strip()]


def apply_similarity_tier(conn: psycopg.Connection, tree_version_id: int,
                          floor: float = MATCH_FLOOR) -> list[SimilarityMatch]:
    """Attach unclassified tickets to their best-matching leaf, for review.

    Best match only — never every cluster above the floor.  A ticket describes
    one piece of work, and spreading it across three clusters because its prose
    is generic manufactures evidence in places nobody worked.  Returns the
    matches so the CLI can print what a human is being asked to decide.
    """
    items = _unclassified_items(conn)
    summaries = _cluster_summaries(conn, tree_version_id)
    if not items or not summaries:
        return []

    scores = score([t for _, t in items], [s for _, s in summaries])

    matches: list[SimilarityMatch] = []
    for (item_id, _text), row in zip(items, scores):
        best_idx = max(range(len(row)), key=lambda i: (row[i], -summaries[i][0]))
        best = row[best_idx]
        if best < floor:
            continue                      # parked as unclassified, never forced
        node_id = summaries[best_idx][0]
        execute(conn, """
            INSERT INTO cluster_membership
                (node_id, item_id, certainty, merge_method, review_state)
            VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING
        """, (node_id, item_id, Certainty.TENTATIVE.value,
              MergeMethod.SIMILARITY.value, ReviewState.PENDING_REVIEW.value))
        execute(conn, "UPDATE extracted_item SET extraction_method=%s, certainty=%s "
                      "WHERE item_id=%s",
                (ExtractionMethod.SIMILARITY.value, Certainty.TENTATIVE.value, item_id))
        matches.append(SimilarityMatch(item_id, node_id, round(float(best), 3)))
    return matches

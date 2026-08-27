"""
Okapi BM25 over Confluence sections.

Implemented here rather than pulled in as a dependency: it is ~60 lines of
arithmetic, it keeps the RAG installable with no extra packages, and every
score stays inspectable -- each result carries the terms that produced it,
which is what makes a retrieved section defensible in the transfer package.

Every hit carries two independent numbers:

    score   RELATIVE -- 1.0 is the best-matching section for this query.
            Good for ranking and for finding where quality falls off.

    mass    ABSOLUTE -- the share of the query's total IDF weight that this
            section actually matched. Good for asking whether a section is
            worth anything at all, independent of what else scored.

Both are needed. An earlier version reported only an absolute score computed
against the ceiling of every query term saturating; with ~50 vocabulary terms
and sections matching 5 or 6, everything collapsed into a band near zero and
no threshold could separate good from bad. Switching to a purely relative
score fixed ranking but created the opposite problem: the best section of a
worthless set also scores 1.0.

`mass` is the answer to that. It cannot be inflated by weak competition,
because it is measured against the query rather than against other results.
See cutoff.py for how the two are combined.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from backend.rag import config as cfg


@dataclass
class ScoredDoc:
    doc_id: str
    score: float                                  # 0..1, relative to the best hit
    raw_score: float                              # unnormalized BM25
    mass: float = 0.0                             # 0..1, share of query IDF mass matched
    matched_terms: list[str] = field(default_factory=list)

    @property
    def match_count(self) -> int:
        return len(self.matched_terms)


class BM25Index:
    """An in-memory BM25 index. Rebuilt per query batch; the corpus is small."""

    def __init__(
        self,
        documents: dict[str, list[str]],
        k1: float | None = None,
        b: float | None = None,
    ):
        """`documents` maps a document id to its already-tokenized text."""
        self.k1 = k1 if k1 is not None else cfg.BM25_K1
        self.b = b if b is not None else cfg.BM25_B

        self.doc_ids: list[str] = list(documents.keys())
        self.doc_len: dict[str, int] = {}
        self.term_freq: dict[str, dict[str, int]] = {}   # doc_id -> term -> count
        self.doc_freq: dict[str, int] = {}               # term -> docs containing it

        for doc_id, tokens in documents.items():
            self.doc_len[doc_id] = len(tokens)
            counts: dict[str, int] = {}
            for token in tokens:
                counts[token] = counts.get(token, 0) + 1
            self.term_freq[doc_id] = counts
            for term in counts:
                self.doc_freq[term] = self.doc_freq.get(term, 0) + 1

        self.n_docs = len(self.doc_ids)
        self.avg_len = (sum(self.doc_len.values()) / self.n_docs) if self.n_docs else 0.0

    def _idf(self, term: str) -> float:
        """Standard BM25+ IDF -- always positive, so common terms shrink rather than flip sign."""
        df = self.doc_freq.get(term, 0)
        return math.log(1.0 + (self.n_docs - df + 0.5) / (df + 0.5))

    def term_mass(self, query: dict[str, float]) -> dict[str, float]:
        """
        Each query term's share of what the query is asking about: weight x IDF.

        A term the corpus never uses has a high IDF but no way to match; a
        term in every document has a low one. Multiplying by the caller's
        weight folds in how much the capability itself cares about the term.
        cutoff.mass_floor() turns this into the absolute quality bar.
        """
        return {term: weight * self._idf(term) for term, weight in query.items()}

    def search(self, query: dict[str, float], top_k: int = 20) -> list[ScoredDoc]:
        """
        Score every document against a weighted query.

        `query` maps term -> weight, as produced by CapabilityVocabulary.
        """
        if not self.n_docs or not query:
            return []

        term_mass = self.term_mass(query)
        total_mass = sum(term_mass.values()) or 1.0

        results: list[ScoredDoc] = []
        for doc_id in self.doc_ids:
            counts = self.term_freq[doc_id]
            length = self.doc_len[doc_id] or 1
            norm = self.k1 * (1.0 - self.b + self.b * (length / self.avg_len)) if self.avg_len else self.k1

            total = 0.0
            matched: list[str] = []
            for term, weight in query.items():
                freq = counts.get(term, 0)
                if not freq:
                    continue
                total += weight * self._idf(term) * (freq * (self.k1 + 1.0)) / (freq + norm)
                matched.append(term)

            if total > 0:
                results.append(
                    ScoredDoc(
                        doc_id=doc_id,
                        score=0.0,  # filled in below, once the best score is known
                        raw_score=round(total, 4),
                        mass=sum(term_mass[t] for t in matched) / total_mass,
                        matched_terms=sorted(matched),
                    )
                )

        if not results:
            return []

        results.sort(key=lambda r: r.raw_score, reverse=True)

        best = results[0].raw_score or 1.0
        for result in results:
            result.score = min(1.0, result.raw_score / best)

        return results[:top_k]

"""
Central configuration for the Evidence & Skill Intelligence Engine.

Every tunable parameter used by the scoring pipeline lives here. Nothing in
engine/*.py should hardcode a threshold, weight, or decay constant -- they
should all be read from this module so the whole engine can be re-tuned by
editing a single file.
"""

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# 1. SKILL RELEVANCE (evidence -> skill mapping)
# ---------------------------------------------------------------------------
# Relevance for an Evidence x Skill pair is built from two signals that are
# blended together (see engine/relevance.py):
#
#   (a) STRUCTURAL signal -- the evidence's module_id declares this skill
#       in modules.json -> capability_ids. This is authoritative/deterministic
#       and gets a high base relevance.
#
#   (b) TEXTUAL signal -- keyword overlap between the evidence description
#       and a keyword set derived from the capability's name/description
#       (plus optional manual overrides below). This lets evidence surface
#       a *secondary* skill even when the owning module doesn't declare it
#       (e.g. a DB-recovery module also mentioning "reconciliation").

# Base relevance granted when the evidence's module declares the capability.
STRUCTURAL_BASE_RELEVANCE = 0.75

# Maximum bonus added on top of the structural base when textual keyword
# overlap is strong for the SAME (structurally-linked) capability.
STRUCTURAL_KEYWORD_BONUS_CAP = 0.25

# Relevance ceiling for a skill that has NO structural link (i.e. the
# evidence's module doesn't declare that capability) but is picked up
# purely from keyword overlap in the description. Kept lower than the
# structural base because it's a weaker, less authoritative signal.
TEXTUAL_ONLY_RELEVANCE_CAP = 0.60

# Minimum keyword overlap score (0-1) required before a textual-only skill
# match is recorded at all. Prevents noisy single-word coincidences.
TEXTUAL_ONLY_MIN_OVERLAP = 0.12

# Manually curated extra keywords per capability ID, merged with keywords
# auto-derived from the capability's name + description. Use this to add
# domain synonyms without touching capabilities.json.
CAPABILITY_KEYWORD_OVERRIDES: dict[str, list[str]] = {
    "C001": ["api", "endpoint", "middleware", "gateway", "webhook", "auth", "routing"],
    "C002": ["reconciliation", "reconcile", "settlement", "transaction", "matching", "currency", "ledger"],
    "C003": ["recovery", "restore", "wal", "pitr", "point-in-time", "corruption", "backup", "integrity", "database", "postgresql", "postgres"],
    "C004": ["incident", "outage", "escalation", "on-call", "oncall", "pagerduty", "postmortem", "disruption", "troubleshoot"],
    "C005": ["deploy", "deployment", "rollback", "release", "canary", "blue-green", "pipeline", "ci/cd", "cicd"],
}

# Generic English stopwords stripped before keyword extraction/matching.
STOPWORDS = {
    "a", "an", "the", "and", "or", "for", "of", "to", "in", "on", "with",
    "is", "are", "was", "were", "be", "been", "this", "that", "it", "as",
    "at", "by", "from", "into", "across", "during", "after", "over", "up",
}


# ---------------------------------------------------------------------------
# 2. RECENCY (time decay)
# ---------------------------------------------------------------------------
# recency_factor = exp(-DECAY_LAMBDA * age_in_days / DECAY_TIME_UNIT_DAYS)
#
# With DECAY_TIME_UNIT_DAYS = 365 and DECAY_LAMBDA = 0.35, evidence loses
# about 30% of its influence per year and roughly halves every ~2 years.
DECAY_LAMBDA = 0.35
DECAY_TIME_UNIT_DAYS = 365.0

# Evidence contribution below this recency factor is still stored (never
# silently discarded) but is treated as effectively negligible in summaries.
RECENCY_NEGLIGIBLE_THRESHOLD = 0.05


# ---------------------------------------------------------------------------
# 3. EVIDENCE CONTRIBUTION
# ---------------------------------------------------------------------------
# evidence_contribution = evidence_strength * skill_relevance * recency_factor
#
# `evidence_strength` is derived from the normalized record's existing
# `score` field. Based on inspection of the provided evidence records,
# `score` consistently falls in [0, 1] and correlates with how substantial /
# high-confidence the individual evidence item is (e.g. "led incident
# response" = 0.95 vs "minor cleanup, no functional changes" = 0.40). We
# therefore treat it as EVIDENCE STRENGTH and use it directly, without
# reinterpreting or overwriting it. It is preserved verbatim as
# `original_score` in all output.
EVIDENCE_STRENGTH_FIELD = "score"

# If evidence_strength is missing entirely, fall back to this neutral value
# rather than dropping the record.
DEFAULT_EVIDENCE_STRENGTH = 0.5


# ---------------------------------------------------------------------------
# 4. AGGREGATION (Employee x Skill)
# ---------------------------------------------------------------------------
# "noisy_or": score = 1 - product(1 - contribution_i)
#   Each additional piece of evidence pushes the score toward 1 but can
#   never exceed it, and a single very strong item can already dominate.
#   This is the standard way to combine independent probabilistic signals
#   of "the skill has been demonstrated at least once" and is the default.
#
# "capped_sum": score = min(1, sum(contribution_i) * SUM_DAMPING_FACTOR)
#   Simpler, more linear alternative kept for comparison/testing.
AGGREGATION_METHOD = "noisy_or"  # "noisy_or" | "capped_sum"
SUM_DAMPING_FACTOR = 0.5


# ---------------------------------------------------------------------------
# 5. EVIDENCE BANDS
# ---------------------------------------------------------------------------
# Initial configuration values only -- not scientifically validated
# thresholds. Tune freely; downstream code only ever reads this list.
BAND_THRESHOLDS = [
    ("HIGH", 0.75),
    ("MODERATE", 0.45),
    ("LOW", 0.20),
    ("NONE", 0.0),
]


# ---------------------------------------------------------------------------
# 6. MISC / VALIDATION
# ---------------------------------------------------------------------------
# Reference date used for recency calculations. None => use current date/time.
# Overridable (e.g. in tests) to get deterministic, reproducible output.
REFERENCE_DATETIME_OVERRIDE = None

# Accepted evidence "type" values are NOT restricted -- unknown types are
# logged as warnings but never dropped, per spec section 13.
KNOWN_EVIDENCE_TYPES = {"Git Commit", "Jira Ticket", "Pull Request", "Code Review"}

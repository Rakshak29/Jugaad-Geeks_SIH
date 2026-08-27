-- Engineering Continuity Engine — schema
-- Authority: Piece 2 (Data Model Reference). 14 tables, 4 enums, 2 views.
-- Bands, coverage status, exposure, activity and density are COMPUTED, never stored.

-- ─────────────────────────────────────────────────────────────────────────────
-- Enums.  Declaration order of certainty_t is load-bearing: Postgres orders an
-- enum by declaration, so `certain` is the SMALLEST value and the WEAKER of two
-- links is GREATEST(a, b).  Inverting this silently overstates every mixed
-- certainty edge (Piece 2 §8).
-- ─────────────────────────────────────────────────────────────────────────────
DROP VIEW  IF EXISTS evidence_edge          CASCADE;
DROP VIEW  IF EXISTS capability_descendant  CASCADE;
DROP TABLE IF EXISTS capability_component   CASCADE;
DROP TABLE IF EXISTS dependency_edge        CASCADE;
DROP TABLE IF EXISTS component              CASCADE;
DROP TABLE IF EXISTS work_unit_member       CASCADE;
DROP TABLE IF EXISTS work_unit              CASCADE;
DROP TABLE IF EXISTS cluster_membership     CASCADE;
DROP TABLE IF EXISTS cluster_node           CASCADE;
DROP TABLE IF EXISTS tree_version           CASCADE;
DROP TABLE IF EXISTS extracted_item         CASCADE;
DROP TABLE IF EXISTS raw_record             CASCADE;
DROP TABLE IF EXISTS source_identity        CASCADE;
DROP TABLE IF EXISTS employee               CASCADE;
DROP TABLE IF EXISTS role_ceiling           CASCADE;
DROP TABLE IF EXISTS config                 CASCADE;
DROP TYPE  IF EXISTS node_role_t            CASCADE;
DROP TYPE  IF EXISTS certainty_t            CASCADE;
DROP TYPE  IF EXISTS extraction_method_t    CASCADE;
DROP TYPE  IF EXISTS record_kind_t          CASCADE;

CREATE TYPE record_kind_t AS ENUM ('commit', 'pr_review', 'ticket', 'incident');

CREATE TYPE extraction_method_t AS ENUM (
    'file_path',          -- github
    'component',          -- jira tier 1
    'label',              -- jira tier 2
    'project',            -- jira tier 3
    'affected_service',   -- incident
    'similarity',         -- jira tier 4  (TF-IDF cosine text similarity)
    'unclassified'        -- jira tier 5  (parked, never force-fitted)
);

CREATE TYPE certainty_t AS ENUM ('certain', 'probable', 'tentative');

CREATE TYPE node_role_t AS ENUM ('grouping', 'capability', 'subcategory');


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. raw_record — untouched API payloads.  The bottom of every trace (SC6).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE raw_record (
    raw_record_id     BIGSERIAL PRIMARY KEY,
    source_type       TEXT        NOT NULL,   -- 'github' | 'jira' | 'incident'
    source_native_id  TEXT        NOT NULL,   -- commit SHA | 'PAY-501' | 'INC-88'
    payload           JSONB       NOT NULL,   -- byte-identical API response
    content_hash      TEXT        NOT NULL,   -- sha256, for idempotent re-ingest
    ingested_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_type, source_native_id, content_hash)
);
CREATE INDEX raw_record_source_idx ON raw_record (source_type);


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. employee — note the column that is deliberately absent.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE employee (
    employee_id         TEXT PRIMARY KEY,
    display_name        TEXT NOT NULL,
    role_title          TEXT,
    status              TEXT NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active','departed')),
    is_service_account  BOOLEAN NOT NULL DEFAULT false
    -- DELIBERATE OMISSION: no score, rating, level, seniority or ranking column.
    -- The system never produces a numeric expertise value for a person.
    -- Piece 0 §6 (SC1).  Do not add one.
);


-- 3. source_identity — manual mapping, 6 people x 3 sources = 18 rows.
CREATE TABLE source_identity (
    source_identity_id  BIGSERIAL PRIMARY KEY,
    employee_id         TEXT NOT NULL REFERENCES employee (employee_id),
    source_type         TEXT NOT NULL,
    native_actor_id     TEXT NOT NULL,
    UNIQUE (source_type, native_actor_id)
);


-- ─────────────────────────────────────────────────────────────────────────────
-- 4. extracted_item — structural normalization output.
--    Three payload shapes become one row shape: who, when, what kind,
--    what it touched, how sure we are.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE extracted_item (
    item_id                BIGSERIAL PRIMARY KEY,
    raw_record_id          BIGINT NOT NULL REFERENCES raw_record (raw_record_id),
    source_type            TEXT   NOT NULL,
    record_kind            record_kind_t NOT NULL,

    native_actor_id        TEXT   NOT NULL,
    employee_id            TEXT   REFERENCES employee (employee_id),  -- NULL = unmapped

    occurred_at            TIMESTAMPTZ NOT NULL,   -- AUTHORED time (Piece 5 §3.4 / D3)
    feature_tokens         TEXT[] NOT NULL DEFAULT '{}',
    extraction_method      extraction_method_t NOT NULL,
    certainty              certainty_t NOT NULL,    -- OBSERVED: which rung fired

    -- Stage A (eligibility)
    eligibility_state      TEXT NOT NULL DEFAULT 'eligible'
                             CHECK (eligibility_state IN ('eligible','excluded')),
    exclusion_reason       TEXT,

    -- Stage C (ceiling inputs)
    actor_role             TEXT,
    ceiling_basis          TEXT,
    effort_signal          NUMERIC,      -- lines changed; code records only, NULL elsewhere
    capabilities_touched   INTEGER,      -- denormalised backfill, drill-down only

    UNIQUE (raw_record_id, native_actor_id),
    CHECK (eligibility_state = 'eligible' OR exclusion_reason IS NOT NULL)
);
CREATE INDEX extracted_item_employee_idx    ON extracted_item (employee_id);
CREATE INDEX extracted_item_tokens_idx      ON extracted_item USING GIN (feature_tokens);
CREATE INDEX extracted_item_occurred_idx    ON extracted_item (occurred_at);
CREATE INDEX extracted_item_eligibility_idx ON extracted_item (eligibility_state);


-- ─────────────────────────────────────────────────────────────────────────────
-- 5. role_ceiling — the signal ladders, stored as data so a band explanation
--    is a row the UI can render.  Piece 3 §6.1 owns the rungs.
--    `ceiling` is an ORDINAL band code (0 NONE, 1 LOW, 2 MODERATE, 3 HIGH),
--    used only for comparison — never summed, never averaged.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE role_ceiling (
    source_type   TEXT    NOT NULL,
    rung          INTEGER NOT NULL,        -- 1 = strongest signal
    role          TEXT    NOT NULL,
    ceiling       INTEGER NOT NULL CHECK (ceiling BETWEEN 0 AND 3),
    availability  TEXT    NOT NULL CHECK (availability IN ('always','bonus')),
    rationale     TEXT    NOT NULL,
    PRIMARY KEY (source_type, role)
);
CREATE INDEX role_ceiling_rung_idx ON role_ceiling (source_type, rung);


-- ─────────────────────────────────────────────────────────────────────────────
-- 6. config — every value the system reads.  "Why is that number what it is?"
--    is answerable by pointing at a row.  No tuned constants (SC7).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE config (
    key         TEXT PRIMARY KEY,
    value       JSONB NOT NULL,
    kind        TEXT  NOT NULL CHECK (kind IN
                  ('derived','natural_unit','definitional','mapping','operational')),
    basis       TEXT  NOT NULL,   -- percentile that produced a derived value, or '-'
    rationale   TEXT  NOT NULL,   -- the sentence said out loud
    owned_by    TEXT  NOT NULL
);


-- ─────────────────────────────────────────────────────────────────────────────
-- 7. tree_version + 8. cluster_node — the capability tree.
--    Adjacency list + recursive CTE.  No graph database (Piece 2 §1).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE tree_version (
    tree_version_id  BIGSERIAL PRIMARY KEY,
    label            TEXT,
    status           TEXT NOT NULL CHECK (status IN ('draft','frozen','superseded')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    frozen_at        TIMESTAMPTZ,
    CHECK (status <> 'frozen' OR frozen_at IS NOT NULL)
);

CREATE TABLE cluster_node (
    node_id            BIGSERIAL PRIMARY KEY,
    tree_version_id    BIGINT NOT NULL REFERENCES tree_version (tree_version_id),
    parent_id          BIGINT,
    node_role          node_role_t NOT NULL,

    name               TEXT NOT NULL,
    llm_proposed_name  TEXT,                 -- retained after a human edit, for audit
    name_source        TEXT NOT NULL CHECK (name_source IN ('llm','human')),
    approved_at        TIMESTAMPTZ,

    UNIQUE (node_id, tree_version_id),
    -- Composite FK: structurally impossible for a node in one tree version to
    -- parent a node in another (invariant I4 — enforced, not checked).
    FOREIGN KEY (parent_id, tree_version_id)
        REFERENCES cluster_node (node_id, tree_version_id),
    CHECK (parent_id IS DISTINCT FROM node_id)
);
CREATE INDEX cluster_node_parent_idx ON cluster_node (parent_id);
CREATE INDEX cluster_node_role_idx   ON cluster_node (tree_version_id, node_role);


-- 9. cluster_membership — item to leaf node, and the certainty gate.
CREATE TABLE cluster_membership (
    node_id           BIGINT NOT NULL REFERENCES cluster_node (node_id),
    item_id           BIGINT NOT NULL REFERENCES extracted_item (item_id),
    certainty         certainty_t NOT NULL,
    similarity_score  NUMERIC(4,3),          -- ranks the human review queue ONLY.
                                             -- Never reaches a band.
    merge_method      TEXT NOT NULL CHECK (merge_method IN
                        ('within_source','explicit_reference','similarity')),
    review_state      TEXT NOT NULL CHECK (review_state IN
                        ('auto_applied','pending_review','human_approved','human_rejected')),
    PRIMARY KEY (node_id, item_id)
);
CREATE INDEX cluster_membership_item_idx   ON cluster_membership (item_id);
CREATE INDEX cluster_membership_review_idx ON cluster_membership (review_state);


-- ─────────────────────────────────────────────────────────────────────────────
-- 10. work_unit + 11. work_unit_member — one piece of real work, not four
--     records.  ALL counting in band assignment is over units (Piece 3 §5).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE work_unit (
    work_unit_id   BIGSERIAL PRIMARY KEY,
    occurred_at    TIMESTAMPTZ NOT NULL,   -- LATEST member timestamp
    member_count   INTEGER NOT NULL
);

CREATE TABLE work_unit_member (
    work_unit_id   BIGINT NOT NULL REFERENCES work_unit (work_unit_id),
    item_id        BIGINT NOT NULL REFERENCES extracted_item (item_id),
    PRIMARY KEY (work_unit_id, item_id),
    UNIQUE (item_id)                        -- an item belongs to exactly one unit
);


-- ─────────────────────────────────────────────────────────────────────────────
-- 12. component + 13. dependency_edge + 14. capability_component
--     A capability is NOT a component.  Components are architecture;
--     capabilities are responsibilities performed ON them (Piece 2 §3).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE component (
    component_id   TEXT PRIMARY KEY,
    service        TEXT NOT NULL,
    display_name   TEXT NOT NULL
);

CREATE TABLE dependency_edge (
    from_component  TEXT NOT NULL REFERENCES component (component_id),
    to_component    TEXT NOT NULL REFERENCES component (component_id),
    edge_source     TEXT NOT NULL DEFAULT 'manual'
                      CHECK (edge_source IN ('manual','extracted')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (from_component, to_component),
    CHECK (from_component <> to_component)
    -- Cycles are PERMITTED. Real architectures contain them; propagation is
    -- bounded at two hops, which terminates regardless (Piece 2 §7.3).
);
CREATE INDEX dependency_edge_to_idx ON dependency_edge (to_component);

CREATE TABLE capability_component (
    capability_node_id  BIGINT  NOT NULL REFERENCES cluster_node (node_id),
    component_id        TEXT    NOT NULL REFERENCES component (component_id),
    is_primary          BOOLEAN NOT NULL DEFAULT false,
    PRIMARY KEY (capability_node_id, component_id)
);
-- Invariant I5, structural: at most one primary component per capability.
CREATE UNIQUE INDEX capability_component_one_primary_idx
    ON capability_component (capability_node_id)
    WHERE is_primary;


-- ─────────────────────────────────────────────────────────────────────────────
-- View 1: capability_descendant — every node beneath (and including) each
-- capability.  The walk starts ONLY at capability nodes, so grouping nodes
-- never accumulate evidence.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE VIEW capability_descendant AS
WITH RECURSIVE walk AS (
    SELECT node_id AS capability_node_id,
           node_id AS descendant_id,
           tree_version_id
    FROM cluster_node
    WHERE node_role = 'capability'
  UNION ALL
    SELECT w.capability_node_id,
           c.node_id,
           c.tree_version_id
    FROM walk w
    JOIN cluster_node c ON c.parent_id = w.descendant_id
)
SELECT * FROM walk;


-- ─────────────────────────────────────────────────────────────────────────────
-- View 2: evidence_edge — the evidence graph.  A VIEW, not a table, so it
-- cannot drift from the raw data.  Bands are NOT here: edges are facts, a band
-- is an interpretation of those facts under Piece 3's rules.
--
-- Four filters do real work:
--   employee_id IS NOT NULL   unmapped actors produce no evidence, for free
--   eligibility_state         bots/merges/reverts never reach a band
--   review_state              a tentative merge contributes nothing until approved
--   the recursive walk        starts only at capability nodes
--
-- Departed employees are NOT filtered here.  Their evidence explains the gap.
-- They are excluded from the COVERAGE SET instead (Piece 3 §10.1).
--
-- GREATEST, not LEAST: certainty_t is declared certain -> probable -> tentative,
-- so `certain` is the smallest and the WEAKER of two links is the greater value.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE VIEW evidence_edge AS
SELECT
    ei.employee_id,
    cd.capability_node_id,
    cd.tree_version_id,
    wm.work_unit_id,
    ei.item_id,
    ei.raw_record_id,
    ei.source_type,
    ei.record_kind,
    ei.actor_role,
    ei.ceiling_basis,
    ei.occurred_at,
    ei.effort_signal,
    ei.capabilities_touched,
    GREATEST(ei.certainty, cm.certainty) AS certainty
FROM extracted_item        ei
JOIN work_unit_member      wm ON wm.item_id = ei.item_id
JOIN cluster_membership    cm ON cm.item_id = ei.item_id
JOIN capability_descendant cd ON cd.descendant_id = cm.node_id
WHERE ei.employee_id IS NOT NULL
  AND ei.eligibility_state = 'eligible'
  AND cm.review_state IN ('auto_applied', 'human_approved');

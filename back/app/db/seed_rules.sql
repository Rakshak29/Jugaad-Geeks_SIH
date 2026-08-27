-- Rules, not data.  These are the specification stored as rows: the signal
-- ladders of Piece 3 §6.1 and the non-derived config values of Piece 3 §14.
-- Derived values (as_of_date, breadth_p90/p98, effort_p10, density_min,
-- clustering_overlap_threshold) are written by calibration at dataset freeze
-- and are NOT seeded here.

TRUNCATE role_ceiling;

-- ── GitHub ────────────────────────────────────────────────────────────────────
-- No GitHub rung reaches HIGH.  Writing code proves you changed the system;
-- it does not prove you can operate it under pressure.  The single route from
-- code to HIGH is the authorship exception (Piece 3 §7).
INSERT INTO role_ceiling (source_type, rung, role, ceiling, availability, rationale) VALUES
('github', 1, 'author',                2, 'always', 'authored the commit'),
('github', 2, 'pr_author',             2, 'always', 'authored the merged pull request'),
('github', 3, 'reviewer_substantive',  1, 'always', 'reviewed it with substantive comments'),
('github', 4, 'reviewer_approval',     1, 'always', 'approved it without comments'),
('github', 5, 'merger_only',           0, 'always', 'pressed merge without authoring or reviewing');

-- ── Jira ──────────────────────────────────────────────────────────────────────
-- No Jira rung reaches HIGH.  Closing a ticket is neither operating something
-- under real conditions nor building most of it.  Rung 1 is the workhorse and
-- rests on the changelog, which is core Jira behaviour rather than an optional
-- field.  Worklogs are used nowhere in this system.
INSERT INTO role_ceiling (source_type, rung, role, ceiling, availability, rationale) VALUES
('jira', 1, 'transition_actor',        2, 'always', 'moved it through In Progress to Done'),
('jira', 2, 'assignee_at_resolution',  2, 'always', 'was the assignee when it was resolved'),
('jira', 3, 'commenter_substantive',   1, 'always', 'commented substantively on it'),
('jira', 4, 'assignee_only',           1, 'always', 'was assigned it but never moved it'),
('jira', 5, 'reporter_only',           0, 'always', 'filed it and nothing more');

-- ── Incidents ─────────────────────────────────────────────────────────────────
-- The only source that reaches HIGH.  Rung 2 is the strongest signal in the
-- entire system and is invisible to Git: being the person others escalate to is
-- a direct organisational statement about who holds the knowledge.
INSERT INTO role_ceiling (source_type, rung, role, ceiling, availability, rationale) VALUES
('incident', 1, 'postmortem_author',        3, 'bonus',  'wrote the postmortem'),
('incident', 2, 'escalation_target',        3, 'always', 'was escalated to — someone else chose them'),
('incident', 3, 'resolver',                 3, 'always', 'resolved the incident'),
('incident', 4, 'ack_then_escalated_away',  2, 'always', 'acknowledged it, then escalated it away'),
('incident', 5, 'assigned_no_detail',       2, 'always', 'was assigned it, with no log detail available'),
('incident', 6, 'notified_only',            0, 'always', 'was on the paging list and nothing more');


-- ── Config ────────────────────────────────────────────────────────────────────
DELETE FROM config WHERE kind <> 'derived';

INSERT INTO config (key, value, kind, basis, rationale, owned_by) VALUES

('coverage_threshold', '2'::jsonb, 'definitional', '-',
 'LOW means someone has touched it but has not demonstrated they can operate it alone. We only count people we would actually page.',
 'Piece 3'),

('fresh_window_months', '12'::jsonb, 'natural_unit', '-',
 'Within the last year. A natural boundary, and it keeps five-month and seven-month work on the same side.',
 'Piece 3'),

('aging_window_months', '24'::jsonb, 'natural_unit', '-',
 'Over two years ago is a real distinction a person already makes when speaking.',
 'Piece 3'),

('revert_window_days', '30'::jsonb, 'natural_unit', '-',
 'A revert within the month is an undo; later is a new decision.',
 'Piece 3'),

('propagation_max_hops', '2'::jsonb, 'definitional', '-',
 'Direct, and one step removed. Bounding at two hops also makes dependency cycles safe.',
 'Piece 2'),

('unclassified_rediscovery_threshold', '15'::jsonb, 'operational', '-',
 'Bucket size that triggers re-running discovery. Affects maintenance scheduling only — no conclusion the system states depends on it.',
 'Piece 3'),

('issue_type_map',
 '{"Bug":"hands_on","Task":"hands_on","Story":"hands_on","Sub-task":"hands_on","Epic":"coordination","Initiative":"coordination"}'::jsonb,
 'mapping', '-',
 'Jira issue-type names are org-customisable. Epic and coordination tickets cap at LOW: managing an epic is not hands-on knowledge.',
 'Piece 3'),

('excluded_path_patterns',
 '["package-lock.json","yarn.lock","poetry.lock","Pipfile.lock","go.sum","*.min.js","*.min.css","vendor/*","node_modules/*","*_pb2.py","*.generated.*","dist/*","build/*"]'::jsonb,
 'mapping', '-',
 'Machine-authored content. A version bump or regenerated file demonstrates nothing.',
 'Piece 3'),

('bot_actor_patterns',
 '["*[bot]","dependabot*","github-actions*","renovate*","*-ci","codecov*",
   "ci@*","cd@*","build@*","builds@*","pipeline@*","deploy@*","deployer@*",
   "release@*","release-bot@*","automation@*","bot@*","robot@*","jenkins@*",
   "actions@*","svc@*","service@*","noreply@*","no-reply@*"]'::jsonb,
 'mapping', '-',
 'Service, CI and automation accounts. A Dependabot commit is not evidence of human knowledge, and neither is a release pipeline''s. Kept as PATTERNS rather than an enumerated set, because a real deployment meets jenkins@, argocd@ and friends that nobody listed in advance.',
 'Piece 3'),

('non_work_resolutions',
 '["Duplicate","Won''t Do","Won''t Fix","Cannot Reproduce","Incomplete","Declined"]'::jsonb,
 'mapping', '-',
 'Closed without work being done.',
 'Piece 3');

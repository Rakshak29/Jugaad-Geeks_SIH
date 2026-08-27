"""Seed the organisation: people, identities, components, dependency edges.

`source_identity` is the manual mapping from a source's own actor id to an
employee — 6 people x 3 sources.  Piece 2 §6.2 defends the manual approach:
real organisations solve identity resolution with an SSO/SCIM directory plus a
manual override table, and the override table always exists because the
automated match never reaches 100%.  Doing the manual half only is an honest
subset of the real answer, not a shortcut around it.

For GitHub we register the commit-author EMAIL as the native actor id, not the
login.  That is not a stylistic choice — the live API returns `author: null` for
every commit in this repository, because the fictional engineers' addresses are
on the reserved `.invalid` TLD and belong to no GitHub account.  The login is
registered too, so a repository whose authors *do* have accounts resolves
without a code change.
"""

from __future__ import annotations

import psycopg

from app.dataset.spec import (
    COMPONENTS,
    DEPENDENCY_EDGES,
    PEOPLE,
    SERVICE_ACCOUNTS,
)


def seed_organisation(conn: psycopg.Connection) -> dict[str, int]:
    counts = {"employee": 0, "source_identity": 0, "component": 0, "dependency_edge": 0}

    with conn.cursor() as cur:
        for p in (*PEOPLE, *SERVICE_ACCOUNTS):
            cur.execute(
                """
                INSERT INTO employee
                    (employee_id, display_name, role_title, status, is_service_account)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (employee_id) DO UPDATE
                  SET display_name = EXCLUDED.display_name,
                      role_title   = EXCLUDED.role_title,
                      status       = EXCLUDED.status,
                      is_service_account = EXCLUDED.is_service_account
                """,
                (p.employee_id, p.display_name, p.role_title, p.status,
                 p.employee_id in {s.employee_id for s in SERVICE_ACCOUNTS}),
            )
            counts["employee"] += 1

            # Three sources, plus the GitHub email — which is the id that
            # actually resolves for this repository.
            identities = [
                ("github", f"{p.employee_id}@sih26.invalid"),
                ("github", p.github_login),
                ("jira", p.jira_account_id),
                ("incident", p.pagerduty_id),
            ]
            for source_type, native in identities:
                cur.execute(
                    """
                    INSERT INTO source_identity (employee_id, source_type, native_actor_id)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (source_type, native_actor_id) DO NOTHING
                    """,
                    (p.employee_id, source_type, native),
                )
                counts["source_identity"] += 1

        for c in COMPONENTS:
            cur.execute(
                """
                INSERT INTO component (component_id, service, display_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (component_id) DO UPDATE
                  SET service = EXCLUDED.service, display_name = EXCLUDED.display_name
                """,
                (c.component_id, c.service, c.display_name),
            )
            counts["component"] += 1

        # edge_source = 'manual', and the UI says so. Nothing is claimed
        # automatic that is manual (Piece 0 §6, SC8).
        for frm, to, _why in DEPENDENCY_EDGES:
            cur.execute(
                """
                INSERT INTO dependency_edge (from_component, to_component, edge_source)
                VALUES (%s, %s, 'manual')
                ON CONFLICT (from_component, to_component) DO NOTHING
                """,
                (frm, to),
            )
            counts["dependency_edge"] += 1

    return counts

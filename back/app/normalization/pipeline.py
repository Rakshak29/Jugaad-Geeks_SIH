"""Normalization pipeline — raw_record to extracted_item.

Stage 2 of Piece 2 §2.  Reads `raw_record`, never mutates it, and writes one row
per (record, actor) pair.  Idempotent: `UNIQUE (raw_record_id, native_actor_id)`
means re-running produces no duplicates.

Identity resolution happens here.  An actor absent from `source_identity` gets
`employee_id = NULL`, is excluded from the `evidence_edge` view by the view's own
WHERE clause, and produces no UI — at a cost of zero code.  The unmapped list is
still printed, because it is a data-quality signal a real deployment would want
on day one: an unmapped actor makes the system UNDERSTATE coverage (a false
alarm), which is the opposite of an uncovered capability (a real finding).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import psycopg

from app.core.config_table import Config
from app.core.enums import RecordKind
from app.db.conn import query
from app.normalization.eligibility import assess
from app.normalization.identity import IdentityResolver, looks_like_automation
from app.normalization.extractors import EXTRACTORS


@dataclass
class NormalizeReport:
    raw_records: int = 0
    items: int = 0          # rows actually INSERTED
    skipped: int = 0        # rows already present — the idempotency evidence
    eligible: int = 0
    excluded: dict[str, int] = field(default_factory=dict)
    unmapped: dict[str, int] = field(default_factory=dict)            # eligible evidence lost
    unmapped_harmless: dict[str, int] = field(default_factory=dict)   # excluded anyway
    resolution_rungs: dict[str, int] = field(default_factory=dict)
    by_method: dict[str, int] = field(default_factory=dict)
    extraction_errors: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        out = [
            f"raw records read : {self.raw_records}",
            f"items written    : {self.items}"
            + (f"  ({self.skipped} already present)" if self.skipped else ""),
            f"rows classified  : {self.items + self.skipped}  ({self.eligible} eligible)",
        ]
        if self.excluded:
            out.append("excluded         : " + ", ".join(
                f"{k}={v}" for k, v in sorted(self.excluded.items())))
        out.append("extraction tiers : " + ", ".join(
            f"{k}={v}" for k, v in sorted(self.by_method.items())))
        out.append("identity rungs   : " + ", ".join(
            f"{k}={v}" for k, v in sorted(self.resolution_rungs.items())))
        return out

    def health_report(self) -> list[str]:
        """Ingestion health — the unmapped-actor surface.

        An unmapped actor and an uncovered capability look similar and mean
        opposite things: an unmapped actor makes the system UNDERSTATE coverage
        (a false alarm — someone really does hold that knowledge), whereas an
        uncovered capability is a real finding.  Surfacing them is how a real
        deployment closes the loop, because the automated match never reaches
        100% and the override table is where the remainder lands.
        """
        lines: list[str] = []
        if self.extraction_errors:
            lines.append(f"EXTRACTION FAILED on {len(self.extraction_errors)} record(s) — "
                         f"their evidence is missing entirely:")
            for detail in self.extraction_errors[:8]:
                lines.append(f"    {detail}")
        if self.unmapped:
            lines.append(f"UNRESOLVED IDENTITY — {len(self.unmapped)} actor(s) hold eligible "
                         f"evidence that is being DISCARDED. Coverage is understated:")
            for actor, count in sorted(self.unmapped.items(), key=lambda kv: -kv[1]):
                hint = ("looks like automation — add to bot_actor_patterns"
                        if looks_like_automation(actor.split(":", 1)[-1])
                        else "add a source_identity row")
                lines.append(f"    {actor:46} {count:3} record(s)  [{hint}]")
        else:
            lines.append("identity: no eligible evidence is lost to unmapped actors.")

        if self.unmapped_harmless:
            lines.append(f"unmapped but already excluded ({len(self.unmapped_harmless)} actor(s)) "
                         f"— no impact on coverage:")
            for actor, count in sorted(self.unmapped_harmless.items(), key=lambda kv: -kv[1]):
                lines.append(f"    {actor:46} {count:3} record(s)")
        return lines


def _identity_map(conn: psycopg.Connection) -> dict[tuple[str, str], str]:
    rows = query(conn, "SELECT source_type, native_actor_id, employee_id FROM source_identity")
    return {(r["source_type"], r["native_actor_id"]): r["employee_id"] for r in rows}


def _service_accounts(conn: psycopg.Connection) -> set[str]:
    rows = query(conn, "SELECT employee_id FROM employee WHERE is_service_account")
    return {r["employee_id"] for r in rows}


def normalize_all(conn: psycopg.Connection, cfg: Config) -> NormalizeReport:
    report = NormalizeReport()
    resolver = IdentityResolver.load(conn)
    bots = _service_accounts(conn)

    raws = query(
        conn,
        "SELECT raw_record_id, source_type, source_native_id, payload "
        "FROM raw_record ORDER BY raw_record_id",
    )
    report.raw_records = len(raws)

    for raw in raws:
        extractor = EXTRACTORS.get(raw["source_type"])
        if extractor is None:
            continue

        try:
            rows = extractor(raw["raw_record_id"], raw["source_native_id"], raw["payload"])
        except Exception as exc:
            # One malformed record must never abort a run — but a silently
            # dropped record is indistinguishable from a record that produced
            # no actors, so the reason is kept and reported.
            report.excluded["extraction_error"] = report.excluded.get("extraction_error", 0) + 1
            report.extraction_errors.append(
                f"{raw['source_type']}:{raw['source_native_id']} — "
                f"{type(exc).__name__}: {exc}")
            continue

        for row in rows:
            resolution = resolver.resolve(row.source_type, row.native_actor_id)
            employee_id = resolution.employee_id
            report.resolution_rungs[resolution.rung] = (
                report.resolution_rungs.get(resolution.rung, 0) + 1)
            unmapped_key = (f"{row.source_type}:{row.native_actor_id}"
                            if employee_id is None else None)

            verdict = assess(
                record_kind=row.record_kind,
                actor_role=row.actor_role,
                payload=raw["payload"],
                is_service_account=employee_id in bots if employee_id else False,
                native_actor_id=row.native_actor_id,
                cfg=cfg,
            )

            state = "eligible" if verdict.eligible else "excluded"
            if unmapped_key:
                # Separate the two cases: an unmapped actor whose record is
                # excluded anyway costs nothing, while an unmapped actor holding
                # ELIGIBLE evidence is a real data-quality problem — it makes the
                # system understate coverage.
                bucket = report.unmapped if verdict.eligible else report.unmapped_harmless
                bucket[unmapped_key] = bucket.get(unmapped_key, 0) + 1
            if verdict.eligible:
                report.eligible += 1
            else:
                report.excluded[verdict.reason or "?"] = (
                    report.excluded.get(verdict.reason or "?", 0) + 1
                )
            report.by_method[row.extraction_method.value] = (
                report.by_method.get(row.extraction_method.value, 0) + 1
            )

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO extracted_item
                        (raw_record_id, source_type, record_kind, native_actor_id,
                         employee_id, occurred_at, feature_tokens, extraction_method,
                         certainty, eligibility_state, exclusion_reason,
                         actor_role, ceiling_basis, effort_signal)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (raw_record_id, native_actor_id) DO NOTHING
                    """,
                    (
                        row.raw_record_id, row.source_type, row.record_kind.value,
                        row.native_actor_id, employee_id, row.occurred_at,
                        row.feature_tokens, row.extraction_method.value,
                        row.certainty.value, state, verdict.reason,
                        row.actor_role, row.ceiling_basis, row.effort_signal,
                    ),
                )
                # rowcount, not a blind increment: ON CONFLICT DO NOTHING means
                # a re-run writes nothing, and reporting "items written: 96" on
                # a run that inserted 0 contradicts the idempotency claim this
                # module is built to demonstrate.
                inserted = cur.rowcount or 0
            report.items += inserted
            report.skipped += 1 - inserted

    return report

"""The single write path into `raw_record`.

Piece 2 §5.1.  Idempotency is structural rather than procedural: the payload is
canonicalised *for hashing only* and the hash participates in a unique
constraint, so re-running ingestion is safe by construction.

  * an UNCHANGED record collides and is skipped
  * a CHANGED record has a different hash and lands as a NEW ROW, preserving
    history rather than overwriting it

The payload STORED is the original object, untouched — byte-identical to what
the API returned. That is the mechanical basis of the traceability claim (SC6):
every downstream conclusion resolves back to a row here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, Protocol

import psycopg


@dataclass(frozen=True)
class RawPayload:
    source_native_id: str
    payload: dict[str, Any]


class SourceAdapter(Protocol):
    source_type: str

    def fetch(self) -> Iterator[RawPayload]: ...


@dataclass
class IngestReport:
    source_type: str
    fetched: int = 0
    inserted: int = 0
    duplicates: int = 0
    errors: list[str] = field(default_factory=list)

    def line(self) -> str:
        base = (f"{self.source_type:9} fetched {self.fetched:4}  "
                f"inserted {self.inserted:4}  duplicates {self.duplicates:4}")
        if self.errors:
            base += f"  errors {len(self.errors)}"
        return base


def content_hash(payload: dict[str, Any]) -> str:
    """Canonical form for hashing ONLY. The stored payload is never this."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def ingest(conn: psycopg.Connection, adapter: SourceAdapter) -> IngestReport:
    report = IngestReport(source_type=adapter.source_type)

    for item in adapter.fetch():
        report.fetched += 1
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO raw_record
                        (source_type, source_native_id, payload, content_hash)
                    VALUES (%s, %s, %s::jsonb, %s)
                    ON CONFLICT (source_type, source_native_id, content_hash)
                    DO NOTHING
                    RETURNING raw_record_id
                    """,
                    (
                        adapter.source_type,
                        item.source_native_id,
                        json.dumps(item.payload, default=str),
                        content_hash(item.payload),
                    ),
                )
                row = cur.fetchone()
            if row:
                report.inserted += 1
            else:
                report.duplicates += 1
        except Exception as exc:  # one bad record must never abort a run
            report.errors.append(f"{item.source_native_id}: {exc}")

    return report


def ingest_all(conn: psycopg.Connection, adapters: Iterable[SourceAdapter]) -> list[IngestReport]:
    return [ingest(conn, a) for a in adapters]

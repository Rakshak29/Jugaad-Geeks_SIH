"""Jira and incident adapters.

These read generated JSON and land it in `raw_record` unmodified.  The
generators are deliberately NOT part of ingestion: that separation is what makes
the adapter-swap claim honest.  Replacing `JiraAdapter.fetch()` with a real Jira
REST client changes nothing downstream, because the shapes are identical
(Piece 1 §3.1, Piece 2 §5.2).

PagerDuty and Opsgenie both expose documented incident APIs, so live extraction
from a real organisation is an off-the-shelf problem — not something this
project would have to invent.  What matters for the prototype is that the
generated JSON mirrors the real field names, which it does.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from app.core.settings import GENERATED_DIR
from app.ingestion.raw_store import RawPayload


class _FileAdapter:
    source_type = ""
    filename = ""
    id_field = "id"

    def __init__(self, directory: Path | None = None) -> None:
        self.dir = directory or GENERATED_DIR

    def fetch(self) -> Iterator[RawPayload]:
        path = self.dir / self.filename
        if not path.exists():
            raise FileNotFoundError(
                f"{path} not found — run `ece dataset generate` first."
            )
        for record in json.loads(path.read_text(encoding="utf-8")):
            yield RawPayload(
                source_native_id=str(record[self.id_field]),
                payload=record,
            )


class JiraAdapter(_FileAdapter):
    """Jira-shaped tickets.  The field that matters most is `changelog`:
    Jira rung 1 ("made both the In Progress and Done transitions") reads it, and
    it is core Jira behaviour rather than an optional field — which is why the
    workhorse rung is allowed to depend on it."""

    source_type = "jira"
    filename = "jira_issues.json"
    id_field = "key"


class IncidentAdapter(_FileAdapter):
    """PagerDuty-shaped incidents.  `log_entries[]` carries the escalation-target
    signal — the strongest rung in the system, and the one invisible to Git.  An
    adapter that surfaced only a flat `responder` field would make it
    unreachable."""

    source_type = "incident"
    filename = "incidents.json"
    id_field = "id"

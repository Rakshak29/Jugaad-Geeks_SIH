"""
Skill taxonomy loading.

Builds convenient in-memory lookups over the skill taxonomy (capabilities /
modules / services) and derives a keyword set per capability for
transparent, inspectable keyword matching (see relevance.py). This module
does not invent a new taxonomy format -- it consumes plain dict rows in the
same shape as capabilities.json / modules.json / services.json, regardless
of whether those rows came from JSON files (demo data / tests) or from
PostgreSQL (production -- see db/repository.py).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from backend.engine.config import scoring_config as cfg


@dataclass
class Capability:
    id: str
    name: str
    description: str
    keywords: set[str] = field(default_factory=set)


@dataclass
class Module:
    id: str
    name: str
    service_id: str | None
    description: str
    capability_ids: list[str]
    jira_component: str | None
    path_prefixes: list[str]


@dataclass
class Service:
    id: str
    name: str
    description: str


_WORD_RE = re.compile(r"[a-zA-Z0-9+/#.\-]+")


def _tokenize(text: str) -> set[str]:
    """Lowercase, strip punctuation-adjacent noise, drop stopwords."""
    if not text:
        return set()
    tokens = {t.strip(".,;:()").lower() for t in _WORD_RE.findall(text)}
    tokens = {t for t in tokens if t and t not in cfg.STOPWORDS and len(t) > 2}
    return tokens


class SkillTaxonomy:
    """
    In-memory view over the skill taxonomy.

    Exposes:
      - capabilities: dict[capability_id -> Capability] (with derived keywords)
      - modules: dict[module_id -> Module]
      - services: dict[service_id -> Service]
      - module_to_capabilities(module_id) -> list[capability_id]
    """

    def __init__(self, capabilities: list[Capability], modules: list[Module], services: list[Service]):
        self.capabilities: dict[str, Capability] = {c.id: c for c in capabilities}
        self.modules: dict[str, Module] = {m.id: m for m in modules}
        self.services: dict[str, Service] = {s.id: s for s in services}

    def module_to_capabilities(self, module_id: str) -> list[str]:
        mod = self.modules.get(module_id)
        if not mod:
            return []
        return list(mod.capability_ids)

    def capability_name(self, capability_id: str) -> str:
        cap = self.capabilities.get(capability_id)
        return cap.name if cap else capability_id


def build_taxonomy(
    capabilities_raw: list[dict],
    modules_raw: list[dict],
    services_raw: list[dict],
) -> SkillTaxonomy:
    """
    Build a SkillTaxonomy from already-parsed rows (list[dict]) in the same
    shape as capabilities.json / modules.json / services.json.

    This is the single shared taxonomy-construction path. Both the JSON
    loader below (`load_taxonomy`, used for local demo data and tests) and
    the PostgreSQL loader (`db.repository.load_taxonomy_from_db`, the real
    production path) funnel through here, so keyword derivation and
    taxonomy shape stay identical regardless of where the rows came from.
    """
    capabilities: list[Capability] = []
    for c in capabilities_raw:
        base_text = f"{c.get('name', '')} {c.get('description', '')}"
        keywords = _tokenize(base_text)
        keywords |= {kw.lower() for kw in cfg.CAPABILITY_KEYWORD_OVERRIDES.get(c["id"], [])}
        capabilities.append(
            Capability(
                id=c["id"],
                name=c.get("name", c["id"]),
                description=c.get("description", ""),
                keywords=keywords,
            )
        )

    modules: list[Module] = []
    for m in modules_raw:
        modules.append(
            Module(
                id=m["id"],
                name=m.get("name", m["id"]),
                service_id=m.get("service_id"),
                description=m.get("description", ""),
                capability_ids=list(m.get("capability_ids", [])),
                jira_component=m.get("jira_component"),
                path_prefixes=list(m.get("path_prefixes", [])),
            )
        )

    services: list[Service] = []
    for s in services_raw:
        services.append(
            Service(id=s["id"], name=s.get("name", s["id"]), description=s.get("description", ""))
        )

    return SkillTaxonomy(capabilities, modules, services)


def load_taxonomy(input_dir: str | Path) -> SkillTaxonomy:
    """
    JSON-file taxonomy loader.

    Used for the bundled demo data (`input/*.json`) and for tests, which
    both want a fast, self-contained, file-based taxonomy. The production
    CLI path does NOT use this -- `app.py` loads the taxonomy from
    PostgreSQL via `db.repository.load_taxonomy_from_db`, which also calls
    `build_taxonomy` above so both paths stay in sync.
    """
    input_dir = Path(input_dir)

    caps_raw = json.loads((input_dir / "capabilities.json").read_text())
    mods_raw = json.loads((input_dir / "modules.json").read_text())
    svcs_raw = json.loads((input_dir / "services.json").read_text())

    return build_taxonomy(caps_raw, mods_raw, svcs_raw)

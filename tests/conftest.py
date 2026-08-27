# tests/conftest.py
"""
Shared fixtures for the Capability Gap RAG tests.

Only adds new, RAG-prefixed fixtures -- nothing here overrides or changes a
fixture the existing test modules define for themselves.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base
from backend.models.core import Capability, CapabilityScore, Employee, Module, Service
import backend.rag.models  # noqa: F401  -- registers the RAG tables on Base


@pytest.fixture
def rag_session(tmp_path, monkeypatch):
    """
    In-memory database seeded with a taxonomy shaped like the real one.

    Coverage is deliberately uneven so absence simulation has something to
    find: C003 is a single point of failure, C005 degrades to LOW, C001 stays
    covered.
    """
    monkeypatch.setattr("backend.rag.config.MAPPING_FILE", tmp_path / "mapping.json")
    monkeypatch.setattr("backend.rag.config.OUTPUT_DIR", tmp_path / "packages")
    monkeypatch.setattr("backend.rag.config.CONFLUENCE_BASE_URL", "https://acme.atlassian.net/wiki")

    # StaticPool + check_same_thread keeps the one in-memory database alive and
    # reachable from FastAPI's TestClient, which serves requests on a different
    # thread than the test body.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    services = [
        Service(id="S001", name="Payments Platform",
                description="Core payment processing and settlement services."),
        Service(id="S002", name="Data & Reliability Infrastructure",
                description="Database reliability, recovery, and data integrity systems."),
        Service(id="S003", name="Platform Operations",
                description="Deployment automation and incident response infrastructure."),
    ]

    capabilities = {
        "C001": Capability(id="C001", name="API Logic",
                           description="Designing and maintaining backend API logic."),
        "C003": Capability(id="C003", name="Database Recovery",
                           description="Recovering databases and restoring data availability "
                                       "after failures, corruption, or incidents."),
        "C005": Capability(id="C005", name="Deployment & Rollback",
                           description="Deploying software changes safely and rolling back "
                                       "releases when deployment issues occur."),
    }

    modules = [
        Module(id="M001", service_id="S001", name="API Gateway",
               description="Routing, auth middleware and rate limiting."),
        Module(id="M003", service_id="S002", name="Database Recovery",
               description="WAL archiving, point-in-time recovery and integrity verification."),
        Module(id="M004", service_id="S003", name="Deployment System",
               description="CI/CD pipelines, blue-green deployment and automated rollback."),
    ]
    modules[0].capabilities.append(capabilities["C001"])
    modules[1].capabilities.append(capabilities["C003"])
    modules[2].capabilities.append(capabilities["C005"])

    employees = [
        Employee(id="E001", name="Rahul", role="Backend"),
        Employee(id="E002", name="Amit", role="Backend"),
        Employee(id="E003", name="Sneha", role="SRE"),
    ]

    scores = [
        # C001 -- two strong holders, survives any single absence.
        CapabilityScore(employee_id="E001", capability_id="C001", score=0.98, evidence_count=9),
        CapabilityScore(employee_id="E002", capability_id="C001", score=0.91, evidence_count=7),
        # C003 -- Sneha only. Single point of failure.
        CapabilityScore(employee_id="E003", capability_id="C003", score=0.97, evidence_count=12),
        # C005 -- Sneha strong, Amit residual. Degrades to LOW without her.
        CapabilityScore(employee_id="E003", capability_id="C005", score=0.95, evidence_count=8),
        CapabilityScore(employee_id="E002", capability_id="C005", score=0.26, evidence_count=2),
    ]

    db.add_all(services + list(capabilities.values()) + modules + employees + scores)
    db.commit()

    yield db
    db.close()

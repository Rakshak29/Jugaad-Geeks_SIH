# tests/test_process_evidence.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models.core import Base, Employee, Module, Capability, EvidenceRecord
from backend.mapper import resolve_modules_from_files, resolve_modules_from_labels
from backend.process_evidence import process_event_to_evidence

def test_mapper_logic():
    """Verify that file paths and labels map to the correct module IDs."""
    # Test files
    assert "M001" in resolve_modules_from_files(["services/api/router.go"])
    assert "M004" in resolve_modules_from_files(["deployments/api.yaml"])
    
    # Test labels
    assert "M001" in resolve_modules_from_labels(["api-gateway", "bug"])
    assert "M003" in resolve_modules_from_labels(["database-recovery"])

def test_process_pr_event(db_session):
    """Verify that a PR with files creates an EvidenceRecord."""
    mock_pr_event = {
        "employee_id": "E001",
        "source": "github",
        "source_type": "pull_request",
        "source_record_id": "PR-101",
        "provenance_type": "Demonstrated",
        "context": {"files": ["services/api/router.go"]}
    }

    new_records = process_event_to_evidence(db_session, mock_pr_event)
    assert len(new_records) == 1
    
    saved_record = db_session.query(EvidenceRecord).filter_by(source_ref="PR-101").first()
    assert saved_record is not None
    assert saved_record.module_id == "M001"
    assert saved_record.weight == 1.0

def test_process_issue_event(db_session):
    """Verify that an Issue with labels creates an EvidenceRecord."""
    mock_issue_event = {
        "employee_id": "E002",
        "source": "github",
        "source_type": "issue",
        "source_record_id": "GH-ISSUE-301",
        "provenance_type": "Proposed",
        "context": {"labels": ["api-gateway", "bug"]}
    }

    new_records = process_event_to_evidence(db_session, mock_issue_event)
    assert len(new_records) == 1
    
    saved_record = db_session.query(EvidenceRecord).filter_by(source_ref="GH-ISSUE-301").first()
    assert saved_record is not None
    assert saved_record.module_id == "M001"
    assert saved_record.weight == 0.5  # Proposed weight

def test_process_evidence_idempotency(db_session):
    """Verify that processing the same event twice produces 0 new records on second run."""
    mock_pr_event = {
        "employee_id": "E001",
        "source": "github",
        "source_type": "pull_request",
        "source_record_id": "PR-101",
        "provenance_type": "Demonstrated",
        "context": {"files": ["services/api/router.go"]}
    }

    first_run = process_event_to_evidence(db_session, mock_pr_event)
    assert len(first_run) == 1

    second_run = process_event_to_evidence(db_session, mock_pr_event)
    assert len(second_run) == 0

    count = db_session.query(EvidenceRecord).filter_by(source_ref="PR-101").count()
    assert count == 1


# --- Pytest Fixture for DB Setup ---
@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # Seed test data
    emp1 = Employee(id="E001", name="Test Eng 1", role="Backend")
    emp2 = Employee(id="E002", name="Test Eng 2", role="Backend")
    cap = Capability(id="C001", name="Payment Routing")
    mod = Module(id="M001", name="API Gateway")
    mod.capabilities.append(cap)
    
    db.add_all([emp1, emp2, cap, mod])
    db.commit()
    
    yield db
    db.close()
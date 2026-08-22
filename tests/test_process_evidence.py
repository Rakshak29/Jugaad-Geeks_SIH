# tests/test_process_evidence.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models.core import Base, Employee, Module, Capability, EvidenceRecord
from backend.mapper import resolve_modules_from_files
from backend.process_evidence import process_event_to_evidence

# 1. Test the Mapper logic entirely on its own
def test_resolve_modules_from_files():
    """Verify that file paths map to the correct module IDs."""
    # Assuming FILE_TO_MODULE_MAP has "services/api/": "M001"
    files = ["services/api/router.go", "unknown/folder/file.txt"]
    
    modules = resolve_modules_from_files(files)
    
    assert "M001" in modules
    # It shouldn't map the unknown file to a known module
    assert len(modules) == 1 

# 2. Test the DB insertion (Integration Test)
def test_process_event_to_evidence():
    """Verify that a normalized event correctly creates an EvidenceRecord in the DB."""
    # Setup in-memory SQLite database for testing
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # Seed test data
    emp = Employee(id="E001", name="Test Eng", role="Backend")
    cap = Capability(id="C001", name="Test Cap")
    mod = Module(id="M001", name="API")
    mod.capabilities.append(cap)
    db.add_all([emp, cap, mod])
    db.commit()

    # Mock an event coming from your friend's extractor
    mock_event = {
        "employee_id": "E001",
        "source": "github",
        "source_type": "pull_request",
        "source_record_id": "PR-101",
        "timestamp": "2026-05-02T10:00:00Z",
        "context": {"files": ["services/api/router.go"]},
        "provenance_type": "Demonstrated"
    }

    # Run the processor
    new_records = process_event_to_evidence(db, mock_event)

    # Assertions
    assert len(new_records) == 1
    
    # Query DB to ensure it was actually saved
    saved_record = db.query(EvidenceRecord).first()
    assert saved_record is not None
    assert saved_record.employee_id == "E001"
    assert saved_record.capability_id == "C001"
    assert saved_record.weight == 1.0
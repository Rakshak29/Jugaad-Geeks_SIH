import sys
import json
from pathlib import Path

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.database import SessionLocal
from backend.process_evidence import process_event_to_evidence

# Import dedicated extractors
from backend.ingestion.github.commit_extractor import extract_commit_events
from backend.ingestion.github.pr_extractor import extract_pr_events
from backend.ingestion.github.review_extractor import extract_review_events
from backend.ingestion.github.issue_extractor import extract_issue_events
from backend.ingestion.jira.jira_extractor import extract_jira_issue_events
from backend.ingestion.incidents.incident_extractor import extract_batch_incident_events
from backend.ingestion.deployments.deployment_extractor import extract_deployment_events
from backend.ingestion.documentation.documentation_extractor import extract_documentation_events

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_RAW_DIR = BASE_DIR / "data" / "raw"


def load_raw_json(filepath: Path):
    if not filepath.exists():
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def run_ingestion_pipeline():
    """
    Executes the end-to-end synthetic data ingestion pipeline:
    Raw JSON -> Dedicated Extractor -> Normalized Events -> process_event_to_evidence() -> EvidenceRecords
    """
    db_session = SessionLocal()

    sources_config = [
        {
            "name": "github_commits",
            "file": DATA_RAW_DIR / "github" / "commits.json",
            "extractor": extract_commit_events
        },
        {
            "name": "github_pull_requests",
            "file": DATA_RAW_DIR / "github" / "pull_requests.json",
            "extractor": extract_pr_events
        },
        {
            "name": "github_reviews",
            "file": DATA_RAW_DIR / "github" / "reviews.json",
            "extractor": extract_review_events
        },
        {
            "name": "github_issues",
            "file": DATA_RAW_DIR / "github" / "issues.json",
            "extractor": extract_issue_events
        },
        {
            "name": "jira_issues",
            "file": DATA_RAW_DIR / "jira" / "issues.json",
            "extractor": extract_jira_issue_events
        },
        {
            "name": "incidents",
            "file": DATA_RAW_DIR / "incidents" / "incidents.json",
            "extractor": extract_batch_incident_events
        },
        {
            "name": "deployments",
            "file": DATA_RAW_DIR / "deployments" / "deployments.json",
            "extractor": extract_deployment_events
        },
        {
            "name": "documentation",
            "file": DATA_RAW_DIR / "documentation" / "docs.json",
            "extractor": extract_documentation_events
        }
    ]

    total_raw_records = 0
    total_normalized_events = 0
    total_evidence_created = 0
    total_unresolved_events = 0

    print("=== STARTING INGESTION PIPELINE ===")

    try:
        for src in sources_config:
            raw_records = load_raw_json(src["file"])
            raw_count = len(raw_records)
            total_raw_records += raw_count

            # Extract normalized events using dedicated extractor
            normalized_events = src["extractor"](raw_records)
            norm_count = len(normalized_events)
            total_normalized_events += norm_count

            src_evidence_count = 0
            src_unresolved_count = 0

            # Process each normalized event through process_event_to_evidence()
            for event in normalized_events:
                # Validate expected schema keys
                required_keys = ["employee_id", "source", "source_type", "source_record_id", "action", "timestamp", "context", "provenance_type"]
                if not all(k in event for k in required_keys):
                    print(f"Warning: Skipping event missing required keys: {event}")
                    continue

                new_records = process_event_to_evidence(db_session, event)
                if new_records:
                    src_evidence_count += len(new_records)
                else:
                    src_unresolved_count += 1

            total_evidence_created += src_evidence_count
            total_unresolved_events += src_unresolved_count

            print(f"[{src['name']}] Raw: {raw_count} | Normalized: {norm_count} | Evidence Created: {src_evidence_count} | Unresolved: {src_unresolved_count}")

        print("\n=== INGESTION PIPELINE COMPLETE ===")
        print(f"Total Raw Records Processed: {total_raw_records}")
        print(f"Total Normalized Events Produced: {total_normalized_events}")
        print(f"Total Evidence Records Inserted: {total_evidence_created}")
        print(f"Total Unresolved Events (No module match): {total_unresolved_events}")

        return {
            "raw": total_raw_records,
            "normalized": total_normalized_events,
            "evidence": total_evidence_created,
            "unresolved": total_unresolved_events
        }

    except Exception as e:
        db_session.rollback()
        print(f"Pipeline Execution Error: {e}")
        raise
    finally:
        db_session.close()


if __name__ == "__main__":
    run_ingestion_pipeline()

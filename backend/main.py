import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from project root .env
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


from backend.database import get_db
from backend.models.core import Employee, CapabilityScore, EvidenceRecord, Capability, Service, Module
from backend.ingestion.pagerduty.client import PagerDutyClient, PagerDutyClientError
from backend.ingestion.pagerduty.storage import save_raw_pagerduty_incidents
from backend.ingestion.pagerduty.normalizer import normalize_pagerduty_dataset


app = FastAPI(title="Engineering Continuity Engine API")

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/employees")
def get_employees(db: Session = Depends(get_db)):
    """Fetch all employees with their capability scores."""
    employees = db.query(Employee).all()
    
    result = []
    for emp in employees:
        scores = db.query(CapabilityScore).filter(CapabilityScore.employee_id == emp.id).all()
        
        skills = []
        for s in scores:
            cap = db.query(Capability).filter(Capability.id == s.capability_id).first()
            skills.append({
                "skill_id": s.capability_id,
                "skill_name": cap.name if cap else "Unknown",
                "score": s.score,
                "evidence_count": s.evidence_count
            })
            
        result.append({
            "id": emp.id,
            "name": emp.name,
            "role": emp.role,
            "skills": skills
        })
        
    return result

@app.get("/employees/{employee_id}/evidence")
def get_employee_evidence(employee_id: str, db: Session = Depends(get_db)):
    """Fetch detailed evidence records for a specific employee."""
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
        
    evidence_records = db.query(EvidenceRecord).filter(EvidenceRecord.employee_id == employee_id).all()
    
    result = []
    for ev in evidence_records:
        cap = db.query(Capability).filter(Capability.id == ev.capability_id).first()
        result.append({
            "id": ev.id,
            "capability_id": ev.capability_id,
            "capability_name": cap.name if cap else "Unknown",
            "source": ev.source,
            "source_ref": ev.source_ref,
            "event_date": ev.event_date.isoformat() if ev.event_date else None,
            "weight": ev.weight
        })
        
    return result

@app.get("/api/graph/technical")
def get_technical_graph(db: Session = Depends(get_db)):
    nodes = []
    links = []
    
    services = db.query(Service).all()
    for sys in services:
        nodes.append({
            "id": f"system:{sys.id}",
            "type": "SYSTEM",
            "label": sys.name,
            "data": {"system_id": sys.id, "name": sys.name, "description": sys.description}
        })
        
    modules = db.query(Module).all()
    for comp in modules:
        nodes.append({
            "id": f"component:{comp.id}",
            "type": "COMPONENT",
            "label": comp.name,
            "data": {"component_id": comp.id, "name": comp.name, "description": comp.description}
        })
        links.append({
            "source": f"component:{comp.id}",
            "target": f"system:{comp.service_id}",
            "type": "BELONGS_TO",
            "data": {"weight": 1.0}
        })
        
    # TODO: if we need system_dependencies or component_dependencies, we can query them if they exist
    # but the core schema doesn't seem to have them in this local db yet, so we'll just skip deps for now
        
    return {
        "success": True,
        "graphType": "technical",
        "nodes": nodes,
        "links": links
    }

@app.get("/api/graph/knowledge")
def get_knowledge_graph(db: Session = Depends(get_db)):
    nodes = []
    links = []
    
    employees = db.query(Employee).all()
    for emp in employees:
        nodes.append({
            "id": f"employee:{emp.id}",
            "type": "EMPLOYEE",
            "label": emp.name,
            "data": {"employee_id": emp.id, "name": emp.name, "role": emp.role, "team_id": emp.role}
        })
        
    capabilities = db.query(Capability).all()
    for cap in capabilities:
        nodes.append({
            "id": f"capability:{cap.id}",
            "type": "CAPABILITY",
            "label": cap.name,
            "data": {"capability_id": cap.id, "name": cap.name, "description": cap.description}
        })
        
    seen_links = set()
    scores = db.query(CapabilityScore).all()
    for ec in scores:
        if ec.score > 0:
            link_key = (f"employee:{ec.employee_id}", f"capability:{ec.capability_id}")
            seen_links.add(link_key)
            links.append({
                "source": link_key[0],
                "target": link_key[1],
                "type": "HAS_CAPABILITY",
                "data": {
                    "evidence_strength": round(float(ec.score), 3),
                    "evidence_recency": 1.0
                }
            })
            
    # Also verify direct EvidenceRecords for newly ingested dynamic contributors
    direct_evs = db.query(EvidenceRecord.employee_id, EvidenceRecord.capability_id).distinct().all()
    for emp_id, cap_id in direct_evs:
        link_key = (f"employee:{emp_id}", f"capability:{cap_id}")
        if link_key not in seen_links and emp_id and cap_id:
            seen_links.add(link_key)
            links.append({
                "source": link_key[0],
                "target": link_key[1],
                "type": "HAS_CAPABILITY",
                "data": {
                    "evidence_strength": 0.5,
                    "evidence_recency": 1.0
                }
            })
        
    return {
        "success": True,
        "graphType": "knowledge",
        "nodes": nodes,
        "links": links
    }

@app.get("/api/setup/sources")
def get_setup_sources(db: Session = Depends(get_db)):
    """Fetch active data source integration states from database evidence."""
    github_count = db.query(EvidenceRecord).filter(
        EvidenceRecord.source.in_(["github", "commit", "pull_request", "issue", "review", "git_commit"])
    ).count()
    
    jira_count = db.query(EvidenceRecord).filter(
        EvidenceRecord.source.in_(["jira", "jira_issue"])
    ).count()

    return {
        "success": True,
        "data": [
            {
                "id": "github",
                "name": "GitHub",
                "type": "github",
                "status": "connected" if github_count > 0 else "disconnected",
                "action": "COLLECTING" if github_count > 0 else "SET UP",
                "records": github_count
            },
            {
                "id": "jira",
                "name": "Jira Cloud",
                "type": "jira",
                "status": "connected" if jira_count > 0 else "disconnected",
                "action": "COLLECTING" if jira_count > 0 else "SET UP",
                "records": jira_count
            },
            {
                "id": "pd",
                "name": "PagerDuty",
                "type": "incident",
                "status": "disconnected",
                "action": "SET UP",
                "records": 0
            },
            {
                "id": "self",
                "name": "Self-hosted incidents",
                "type": "incident",
                "status": "disconnected",
                "action": "SET UP",
                "records": 0
            }
        ]
    }

@app.get("/api/setup/contributors")
def get_setup_contributors(db: Session = Depends(get_db)):
    """Fetch real mapped contributors from the database."""
    employees = db.query(Employee).all()
    result = []
    for emp in employees:
        # Count their evidence records
        records = db.query(EvidenceRecord).filter(EvidenceRecord.employee_id == emp.id).count()
        result.append({
            "id": emp.id,
            "name": emp.name,
            "email": f"{emp.name.lower().replace(' ', '.')}@acmepay.io",
            "records": records
        })
    return {
        "success": True,
        "data": result
    }

@app.get("/api/setup/capabilities")
def get_setup_capabilities(db: Session = Depends(get_db)):
    """Fetch real capability clusters from the database."""
    capabilities = db.query(Capability).all()
    result = []
    for cap in capabilities:
        records = db.query(EvidenceRecord).filter(EvidenceRecord.capability_id == cap.id).count()
        
        sample_evidence = db.query(EvidenceRecord).filter(
            EvidenceRecord.capability_id == cap.id
        ).limit(3).all()
        
        commits = [f"{ev.source}: {ev.source_ref}" for ev in sample_evidence] if sample_evidence else []
            
        result.append({
            "id": cap.id,
            "tag": f"services/{cap.id.lower()}",
            "records": records,
            "source": "github" if records > 0 else "unmapped",
            "name": cap.name,
            "domain": cap.name.split(' ')[0],
            "key": cap.id.lower(),
            "commits": commits
        })
    return {
        "success": True,
        "data": result
    }

from pydantic import BaseModel
from typing import Optional


class CollectSourcePayload(BaseModel):
    url: Optional[str] = None
    token: Optional[str] = None
    base_url: Optional[str] = None
    email: Optional[str] = None
    api_token: Optional[str] = None
    issue_key: Optional[str] = None


@app.post("/api/setup/sources/{source_id}/collect")
def collect_source_data(
    source_id: str,
    payload: Optional[CollectSourcePayload] = None,
    db: Session = Depends(get_db)
):
    """Trigger dynamic data collection for a specific source using submitted or configured parameters."""
    import os

    if source_id == "github":
        try:
            from backend.integrations.github_connector import parse_github_url
            from backend.integrations.github_adapter import GitHubAdapter
            from backend.integrations.github_mapper import map_commit, map_issue, map_pull_request, map_review
            from backend.ingestion.github.commit_extractor import extract_commit_event
            from backend.ingestion.github.issue_extractor import extract_issue_event
            from backend.ingestion.github.pr_extractor import extract_pr_event
            from backend.ingestion.github.review_extractor import extract_review_event
            from backend.process_evidence import process_event_to_evidence

            repo_input = (payload.url if payload and payload.url else os.getenv("GITHUB_REPO", "https://github.com/Rakshak29/acmepay-engineering-monorepo"))
            custom_token = (payload.token if payload and payload.token else os.getenv("GITHUB_TOKEN"))

            repo = parse_github_url(repo_input)
            adapter = GitHubAdapter(repo=repo, token=custom_token)
            records = list(adapter.fetch())

            if len(records) == 0:
                if getattr(adapter, "rate_limited", False):
                    return {
                        "success": False,
                        "message": "GitHub API rate limit reached (60 requests/hr for unauthenticated IP). Please paste a valid GitHub Personal Access Token in the token field to get 5,000 req/hr.",
                        "source": "github"
                    }
                return {
                    "success": False,
                    "message": f"No telemetry records found for repository {repo}. Please verify repository URL and access.",
                    "source": "github"
                }

            # 1. Save Raw GitHub JSON
            raw_github_data = adapter.raw_data
            for raw_path in ["github_raw_data.json", "data/github_raw_data.json"]:
                try:
                    with open(raw_path, "w", encoding="utf-8") as f:
                        json.dump(raw_github_data, f, indent=2, ensure_ascii=False, default=str)
                except Exception as save_err:
                    print("Notice saving raw GitHub JSON:", save_err)

            # 2. Extract and Save Normalized GitHub JSON
            normalized_github_events = []
            evidence_count = 0
            for record in records:
                event = None
                native_id = getattr(record, "source_native_id", "")
                if native_id.startswith("pr-") and "-review-" in native_id:
                    raw = map_review(record)
                    event = extract_review_event(raw)
                elif native_id.startswith("pr-"):
                    raw = map_pull_request(record)
                    event = extract_pr_event(raw)
                elif getattr(record, "record_type", None) == "issue":
                    raw = map_issue(record)
                    event = extract_issue_event(raw)
                else:
                    raw = map_commit(record)
                    event = extract_commit_event(raw)

                if event:
                    normalized_github_events.append(event)
                    if event.get("employee_id"):
                        emp_id = event["employee_id"]
                        emp = db.query(Employee).filter(Employee.id == emp_id).first()
                        if not emp:
                            emp = Employee(id=emp_id, name=emp_id, role="Engineering")
                            db.add(emp)
                            db.commit()

                        res = process_event_to_evidence(db, event)
                        if res:
                            evidence_count += len(res)

            for norm_path in ["github_normalized_data.json", "data/github_normalized_data.json", "normalized_output.json"]:
                try:
                    with open(norm_path, "w", encoding="utf-8") as f:
                        json.dump(normalized_github_events, f, indent=2, ensure_ascii=False, default=str)
                except Exception as save_err:
                    print("Notice saving normalized GitHub JSON:", save_err)

            try:
                from backend.calculate_scores_local import calculate_and_save
                calculate_and_save()
            except Exception as calc_err:
                print("Notice during score calculation:", calc_err)

            return {
                "success": True,
                "message": f"Successfully connected to {repo} and ingested {len(records)} GitHub telemetry records ({evidence_count} evidence records mapped)!",
                "source": "github",
                "records_count": len(records),
                "evidence_count": evidence_count,
            }
        except Exception as e:
            return {"success": False, "message": str(e), "source": "github"}

    elif source_id == "jira":
        try:
            from backend.integrations.jira_adapter import JiraAdapter
            from backend.ingestion.jira.jira_extractor import extract_jira_issue_event
            from backend.process_evidence import process_event_to_evidence

            base_url = (payload.base_url or payload.url if payload and (payload.base_url or payload.url) else os.getenv("JIRA_BASE_URL", "https://acmepay-engineering.atlassian.net")).rstrip("/")
            email = (payload.email if payload and payload.email else os.getenv("JIRA_EMAIL"))
            token = (payload.api_token or payload.token if payload and (payload.api_token or payload.token) else os.getenv("JIRA_API_TOKEN"))
            issue_key = (payload.issue_key if payload and payload.issue_key else "").strip()

            adapter = JiraAdapter(base_url, email=email, api_token=token)
            if issue_key and "-" in issue_key:
                jira_records = list(adapter.fetch_issue(issue_key))
            else:
                jira_records = list(adapter.fetch_all_issues(max_results=100))

            # 1. Save Raw Jira JSON
            raw_jira_data = adapter.raw_data
            for raw_path in ["jira_raw_data.json", "data/jira_raw_data.json"]:
                try:
                    with open(raw_path, "w", encoding="utf-8") as f:
                        json.dump(raw_jira_data, f, indent=2, ensure_ascii=False, default=str)
                except Exception as save_err:
                    print("Notice saving raw Jira JSON:", save_err)

            # 2. Extract and Save Normalized Jira JSON
            normalized_jira_events = []
            evidence_count = 0
            for rec in jira_records:
                event = extract_jira_issue_event(rec)
                if event:
                    normalized_jira_events.append(event)
                    if event.get("employee_id"):
                        emp_id = event["employee_id"]
                        emp = db.query(Employee).filter(Employee.id == emp_id).first()
                        if not emp:
                            emp = Employee(id=emp_id, name=emp_id, role="Engineering")
                            db.add(emp)
                            db.commit()
                        res = process_event_to_evidence(db, event)
                        if res:
                            evidence_count += len(res)

            for norm_path in ["jira_normalized_data.json", "data/jira_normalized_data.json"]:
                try:
                    with open(norm_path, "w", encoding="utf-8") as f:
                        json.dump(normalized_jira_events, f, indent=2, ensure_ascii=False, default=str)
                except Exception as save_err:
                    print("Notice saving normalized Jira JSON:", save_err)

            try:
                from backend.calculate_scores_local import calculate_and_save
                calculate_and_save()
            except Exception as calc_err:
                print("Notice during score calculation:", calc_err)

            return {
                "success": True,
                "message": f"Successfully connected to Jira at {base_url} and fetched {len(jira_records)} issue records ({evidence_count} evidence records created)!",
                "source": "jira",
                "records_count": len(jira_records),
                "evidence_count": evidence_count,
            }
        except Exception as e:
            return {"success": False, "message": str(e), "source": "jira"}

    return {"success": True, "message": f"Source {source_id} configured."}


@app.post("/api/setup/reset")
def reset_pipeline_data(db: Session = Depends(get_db)):
    """Reset the database to clean zero-state (wipes all evidence records and scores)."""
    try:
        from backend.database import drop_db, init_db, SessionLocal
        from backend.seed import load_json, DATA_CONFIG_DIR

        drop_db()
        init_db()

        # Seed core taxonomy definitions (capabilities, services, modules) with 0 employees and 0 evidence
        seed_db = SessionLocal()
        try:
            for item in load_json(DATA_CONFIG_DIR / "capabilities.json"):
                seed_db.add(Capability(id=item["id"], name=item["name"], description=item.get("description")))

            for item in load_json(DATA_CONFIG_DIR / "services.json"):
                seed_db.add(Service(id=item["id"], name=item["name"], description=item.get("description")))

            for item in load_json(DATA_CONFIG_DIR / "modules.json"):
                mod = Module(
                    id=item["id"],
                    service_id=item.get("service_id"),
                    name=item["name"],
                    description=item.get("description")
                )
                seed_db.add(mod)
                seed_db.flush()
                for cap_id in item.get("capabilities", []):
                    cap = seed_db.query(Capability).filter_by(id=cap_id).first()
                    if cap:
                        mod.capabilities.append(cap)

            seed_db.commit()
        finally:
            seed_db.close()

        return {
            "success": True,
            "message": "All pipeline telemetry, evidence records, and scores have been reset to zero."
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Reset failed: {str(e)}"
        }


def health_check():
    return {"status": "healthy"}


# =====================================================================
# PAGERDUTY INGESTION ENDPOINT
# =====================================================================

class PagerDutyIngestionRequest(BaseModel):
    pagerduty_url: str = Field(
        ...,
        description="PagerDuty service URL (e.g. https://acmepay.pagerduty.com/service-directory/PK9U7OK/activity)"
    )
    api_token: str = Field(
        ...,
        description="PagerDuty REST API read token (User or Account token)"
    )


class PagerDutyIngestionResponse(BaseModel):
    success: bool
    service_id: str
    pagerduty_url: str
    total_incidents_fetched: int
    incidents: List[Dict[str, Any]]
    message: str


@app.post("/api/ingestion/pagerduty", response_model=PagerDutyIngestionResponse)
def ingest_pagerduty(request: PagerDutyIngestionRequest):
    """
    PagerDuty Ingestion API Endpoint.
    
    Accepts a PagerDuty service URL and a PagerDuty REST API read token.
    Extracts the service ID, queries PagerDuty REST API v2, and returns fetched incidents.
    """
    url = request.pagerduty_url.strip() if request.pagerduty_url else ""
    token = request.api_token.strip() if request.api_token else ""

    if not url:
        raise HTTPException(status_code=400, detail="pagerduty_url must be provided")

    if not token:
        raise HTTPException(status_code=400, detail="api_token must be provided")

    service_id = PagerDutyClient.extract_service_id_from_url(url)
    if not service_id:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid PagerDuty URL '{url}'. Unable to extract PagerDuty Service ID. "
                "Expected format like 'https://acmepay.pagerduty.com/service-directory/PK9U7OK/activity'."
            )
        )

    try:
        client = PagerDutyClient(api_token=token)
        incidents = client.get_incidents(service_ids=[service_id])
        
        # Step 4: Atomic Raw JSON Ingestion Storage (Overwrites previous dataset)
        save_raw_pagerduty_incidents(service_id=service_id, pagerduty_url=url, incidents=incidents)
        
        # Step 5: Atomic Normalized JSON Ingestion Storage (Overwrites previous dataset)
        normalize_pagerduty_dataset()
    except PagerDutyClientError as e:


        err_str = str(e)
        if "HTTP 401" in err_str or "HTTP 403" in err_str:
            raise HTTPException(
                status_code=401,
                detail="PagerDuty REST API authentication failed. Verify that your API token is a valid REST API read token."
            )
        elif "HTTP 404" in err_str:
            raise HTTPException(
                status_code=404,
                detail=f"PagerDuty service ID '{service_id}' was not found."
            )
        else:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to communicate with PagerDuty API: {e}"
            )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error during PagerDuty ingestion: {e}"
        )

    return PagerDutyIngestionResponse(
        success=True,
        service_id=service_id,
        pagerduty_url=url,
        total_incidents_fetched=len(incidents),
        incidents=incidents,
        message=f"Successfully fetched {len(incidents)} incidents for service '{service_id}' via PagerDuty REST API."
    )

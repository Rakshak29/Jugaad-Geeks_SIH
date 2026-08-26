from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List

from backend.database import get_db
from backend.models.core import Employee, CapabilityScore, EvidenceRecord, Capability, Service, Module

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
        
    scores = db.query(CapabilityScore).all()
    for ec in scores:
        links.append({
            "source": f"employee:{ec.employee_id}",
            "target": f"capability:{ec.capability_id}",
            "type": "HAS_CAPABILITY",
            "data": {
                "evidence_strength": ec.score,
                "evidence_recency": 1.0  # The Engine already bakes recency into ec.score
            }
        })
        
    return {
        "success": True,
        "graphType": "knowledge",
        "nodes": nodes,
        "links": links
    }

@app.get("/api/setup/sources")
def get_setup_sources():
    """Mock endpoint for data source integrations."""
    return {
        "success": True,
        "data": [
            { "id": "github", "name": "GitHub", "type": "github", "status": "connected", "action": "COLLECTING" },
            { "id": "jira", "name": "Jira Cloud", "type": "jira", "status": "not connected", "action": "SET UP" },
            { "id": "pd", "name": "PagerDuty", "type": "incident", "status": "not connected", "action": "SET UP" },
            { "id": "self", "name": "Self-hosted incidents", "type": "incident", "status": "not connected", "action": "SET UP" }
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
        # Count evidence for this capability
        records = db.query(EvidenceRecord).filter(EvidenceRecord.capability_id == cap.id).count()
        
        # Get 3 sample commit messages (source_refs)
        sample_evidence = db.query(EvidenceRecord).filter(
            EvidenceRecord.capability_id == cap.id, 
            EvidenceRecord.source == 'git_commit'
        ).limit(3).all()
        
        commits = [ev.source_ref for ev in sample_evidence]
        if not commits:
            commits = [f"setup({cap.id}): initialized {cap.name}"]
            
        result.append({
            "id": cap.id,
            "tag": f"services/{cap.id.lower()}",
            "records": records,
            "source": "github",
            "name": cap.name,
            "domain": cap.name.split(' ')[0],
            "key": cap.id.lower(),
            "commits": commits
        })
    return {
        "success": True,
        "data": result
    }

@app.get("/")
def health_check():
    return {"status": "healthy"}

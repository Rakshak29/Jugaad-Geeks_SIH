import os
from pathlib import Path
import sys

# Ensure backend module can be found
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.database import SessionLocal, engine

from backend.models.core import Capability, Module, Service, EvidenceRecord, CapabilityScore
from backend.engine.skills import build_taxonomy
from backend.engine.engine import Engine

def calculate_and_save():
    print("Connecting to local database...")
    db = SessionLocal()
    try:
        print("Loading taxonomy from local DB...")
        
        # Load capabilities
        caps = db.query(Capability).all()
        caps_raw = [{"id": c.id, "name": c.name, "description": c.description} for c in caps]
        
        # Load modules
        mods = db.query(Module).all()
        
        # We need the capability mapping for modules
        module_cap_rows = db.execute(text("SELECT module_id, capability_id FROM module_capabilities")).fetchall()
        comp_to_caps = {}
        for row in module_cap_rows:
            comp_to_caps.setdefault(row.module_id, []).append(row.capability_id)
            
        mods_raw = [
            {
                "id": m.id, 
                "name": m.name, 
                "service_id": m.service_id, 
                "description": m.description,
                "capability_ids": comp_to_caps.get(m.id, [])
            } for m in mods
        ]
        
        # Load services
        svcs = db.query(Service).all()
        svcs_raw = [{"id": s.id, "name": s.name, "description": s.description} for s in svcs]
        
        # Build Taxonomy
        taxonomy = build_taxonomy(caps_raw, mods_raw, svcs_raw)
        
        print("Loading evidence records from local DB...")
        ev_records = db.query(EvidenceRecord).all()
        
        records = []
        for r in ev_records:
            records.append({
                "id": r.id,
                "employee_id": r.employee_id,
                "type": r.source,
                "module_id": r.module_id,
                "date": r.event_date.isoformat() if r.event_date else None,
                "score": float(r.weight) if r.weight else 1.0,
                "source": r.source,
                "source_ref": r.source_ref,
                "explicit_capability_ids": [r.capability_id]
            })
            
        print("Running Evidence Engine calculations...")
        engine_obj = Engine(taxonomy)
        engine_obj.process_evidence(records)
        
        print("Saving calculated capability scores back to local DB...")
        
        # engine_obj.employee_skill_results contains the final scores
        for result in engine_obj.employee_skill_results:
            # Upsert into capability_scores
            db.execute(
                text("""
                    INSERT INTO capability_scores (employee_id, capability_id, score, evidence_count)
                    VALUES (:emp, :cap, :score, :count)
                    ON CONFLICT (employee_id, capability_id) 
                    DO UPDATE SET 
                        score = EXCLUDED.score,
                        evidence_count = EXCLUDED.evidence_count
                """),
                {
                    "emp": result.employee_id,
                    "cap": result.skill_id,
                    "score": result.credibility_score,
                    "count": result.evidence_count
                }
            )
        
        db.commit()
        print("Success! All scores have been bridged and updated in local PostgreSQL.")
        
    except Exception as e:
        db.rollback()
        print("Error during bridge calculation:", e)
    finally:
        db.close()

if __name__ == "__main__":
    calculate_and_save()

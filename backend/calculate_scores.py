import os
from pathlib import Path
import sys

# Ensure backend module can be found
sys.path.insert(0, str(Path(__file__).parent.parent))
from sqlalchemy import text
from backend.database import SessionLocal

from backend.engine.skills import build_taxonomy
from backend.engine.engine import Engine

def calculate_and_save():
    print("Connecting to database...")
    db = SessionLocal()
    try:
        print("Loading taxonomy from Supabase...")
        
        # Load capabilities
        caps_rows = db.execute(text("SELECT capability_id as id, name, description FROM capabilities")).fetchall()
        caps_raw = [{"id": str(r.id), "name": r.name, "description": r.description} for r in caps_rows]
        
        # Load components (modules)
        mods_rows = db.execute(text("SELECT component_id as id, system_id as service_id, name, description FROM components")).fetchall()
        # To link capabilities to modules, we need to find which capabilities belong to which module.
        # In our Supabase schema, `capabilities` has `component_id`.
        cap_mapping = db.execute(text("SELECT capability_id, component_id FROM capabilities")).fetchall()
        comp_to_caps = {}
        for row in cap_mapping:
            comp_to_caps.setdefault(str(row.component_id), []).append(str(row.capability_id))
            
        mods_raw = [
            {
                "id": str(r.id), 
                "name": r.name, 
                "service_id": str(r.service_id), 
                "description": r.description,
                "capability_ids": comp_to_caps.get(str(r.id), [])
            } for r in mods_rows
        ]
        
        # Load systems (services)
        sys_rows = db.execute(text("SELECT system_id as id, name, description FROM systems")).fetchall()
        svcs_raw = [{"id": str(r.id), "name": r.name, "description": r.description} for r in sys_rows]
        
        # Build Taxonomy
        taxonomy = build_taxonomy(caps_raw, mods_raw, svcs_raw)
        
        print("Loading evidence records from Supabase...")
        ev_rows = db.execute(text("SELECT evidence_id, employee_id, capability_id, evidence_type, observed_at, strength, source_reference, description FROM evidence")).fetchall()
        
        records = []
        for r in ev_rows:
            records.append({
                "id": str(r.evidence_id),
                "employee_id": str(r.employee_id),
                "type": r.evidence_type.lower(),
                # We don't have explicit module_id on evidence, we map it via capability
                "module_id": None,
                "date": r.observed_at.isoformat() if r.observed_at else None,
                "score": float(r.strength) if r.strength else 1.0,
                "source": "database",
                "description": r.description or "",
                "explicit_capability_ids": [str(r.capability_id)]
            })
            
        print("Running Evidence Engine calculations...")
        engine = Engine(taxonomy)
        engine.process_evidence(records)
        
        print("Saving calculated capability scores to Supabase...")
        # engine.employee_skill_results contains the final scores
        for result in engine.employee_skill_results:
            # Upsert into employee_capabilities
            db.execute(
                text("""
                    INSERT INTO employee_capabilities (employee_id, capability_id, evidence_strength, evidence_recency, confidence)
                    VALUES (:emp, :cap, :strength, :recency, :conf)
                    ON CONFLICT (employee_id, capability_id) 
                    DO UPDATE SET 
                        evidence_strength = EXCLUDED.evidence_strength,
                        evidence_recency = EXCLUDED.evidence_recency,
                        confidence = EXCLUDED.confidence
                """),
                {
                    "emp": int(result.employee_id),
                    "cap": int(result.skill_id),
                    "strength": result.credibility_score,
                    "recency": 1.0,  # Engine already factors recency into credibility_score
                    "conf": result.credibility_score
                }
            )
        
        db.commit()
        print("Success! All scores have been bridged and updated in Supabase.")
        
    except Exception as e:
        db.rollback()
        print("Error during bridge calculation:", e)
    finally:
        db.close()

if __name__ == "__main__":
    calculate_and_save()

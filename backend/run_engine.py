import os
import sys
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# --- THE MAGIC FIX ---
# This adds the 'backend' folder to Python's path so your friend's 
# 'from engine...' imports work perfectly without editing her files!
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# ---------------------

# Import your models
from backend.models.core import EvidenceRecord, CapabilityScore

# Import your friend's exact classes based on her test file
from backend.engine.engine import Engine
from backend.engine.skills import load_taxonomy

DB_URL = os.environ.get("DATABASE_URL", "sqlite:///fallback.db")
db_engine = create_engine(DB_URL)
SessionLocal = sessionmaker(bind=db_engine)

def execute_scoring_pipeline():
    db = SessionLocal()
    
    print("🧠 Loading taxonomy and initializing Engine...")
    # NOTE: You must have the skills/taxonomy JSON file in this directory!
    taxonomy = load_taxonomy("backend/input") 
    scoring_engine = Engine(taxonomy)
    
    print("📥 Fetching 106 ingested evidence records...")
    evidence_records = db.query(EvidenceRecord).all()
    
    # Convert your database records into her exact expected dictionary format
    engine_input = []
    for record in evidence_records:
        engine_input.append({
            "id": record.id,                    # Your DB already formats this nicely (e.g., EV0001)
            "employee_id": record.employee_id,
            "module_id": record.module_id,
            "type": record.source,              # Using your 'source' column for the event type
            "description": record.source_ref,   # Using 'source_ref' since there is no description column
            "score": record.weight,             # Grabbing your exact weight column
            "date": record.event_date.strftime("%Y-%m-%d") if record.event_date else None
        })

    print("⚙️ Processing evidence through the math engine...")
    scoring_engine.process_evidence(engine_input, reference_date=date.today())
    
    # Retrieve the final aggregated results
    final_scores = scoring_engine.employee_skill_summary_output()
    print(f"💾 Saving {len(final_scores)} final capability scores to the database...")
    
    for employee_data in final_scores:
        emp_id = employee_data["employee_id"]
        
        # Unpack the nested skills list for this specific employee
        for skill_data in employee_data["skills"]:
            db.merge(CapabilityScore(
                employee_id=emp_id,
                # Grab the ID safely
                capability_id=skill_data.get("skill_id", skill_data.get("capability_id")), 
                score=skill_data["credibility_score"], 
                evidence_count=skill_data.get("evidence_count", 1)
            ))
        
    db.commit()
    db.close()
    print("🎉 Scoring complete! Database is officially ready for the frontend.")

if __name__ == "__main__":
    execute_scoring_pipeline()
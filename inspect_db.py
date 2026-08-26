"""
Script to inspect and print live PostgreSQL database records.
Run anytime using:
    python inspect_db.py
"""

from collections import Counter
from backend.database import SessionLocal
from backend.models.core import Employee, EvidenceRecord, CapabilityScore, Capability, Module, Service

def inspect():
    db = SessionLocal()
    try:
        print("\n" + "=" * 65)
        print("         DATABASE TELEMETRY & INGESTION INSPECTION")
        print("=" * 65)

        # 1. Total Table Counts
        emp_count = db.query(Employee).count()
        ev_count = db.query(EvidenceRecord).count()
        score_count = db.query(CapabilityScore).count()
        cap_count = db.query(Capability).count()
        mod_count = db.query(Module).count()
        svc_count = db.query(Service).count()

        print("\n[TABLE RECORD COUNTS]")
        print(f"  - Employees (Teammates):     {emp_count}")
        print(f"  - Evidence Records:          {ev_count}")
        print(f"  - Computed Capability Scores:{score_count}")
        print(f"  - Capabilities (Taxonomy):   {cap_count}")
        print(f"  - Modules (Taxonomy):        {mod_count}")
        print(f"  - Services (Taxonomy):       {svc_count}")

        # 2. Evidence breakdown by source
        ev_records = db.query(EvidenceRecord).all()
        source_counts = Counter(r.source for r in ev_records)
        print("\n[EVIDENCE RECORDS BY SOURCE]")
        if source_counts:
            for src, count in source_counts.items():
                print(f"  - {src.upper():<12}: {count} records")
        else:
            print("  (No evidence records injected yet - database is in zero-state)")

        # 3. Discovered Employees & Top Evidence Contributors
        print(f"\n[DISCOVERED TEAMMATES ({emp_count} Total)]")
        emp_evidence_counts = Counter(r.employee_id for r in ev_records)
        if emp_evidence_counts:
            for emp_id, count in emp_evidence_counts.most_common(12):
                scores = db.query(CapabilityScore).filter_by(employee_id=emp_id).all()
                top_scores = [f"{s.capability_id}:{round(s.score, 2)}" for s in sorted(scores, key=lambda x: x.score, reverse=True)[:3]]
                print(f"  - {emp_id:<20} | {count:>3} evidence records | Top scores: {', '.join(top_scores)}")
        else:
            print("  (No teammates registered yet)")

        # 4. Recent Sample Injected Records
        print("\n[RECENT SAMPLE INJECTED EVIDENCE]")
        recent = db.query(EvidenceRecord).order_by(EvidenceRecord.id.desc()).limit(6).all()
        if recent:
            for r in recent:
                print(f"  - [{r.source.upper()}] ID={r.id:<4} Emp='{r.employee_id}' Cap='{r.capability_id}' Mod='{r.module_id}' Ref='{r.source_ref}'")
        else:
            print("  (None)")

        print("\n" + "=" * 65 + "\n")

    finally:
        db.close()

if __name__ == "__main__":
    inspect()

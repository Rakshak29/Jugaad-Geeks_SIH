import json
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'backend', '.env'))

DB_URL = os.environ.get('DATABASE_URL')
if not DB_URL:
    print("No DATABASE_URL found in ../backend/.env")
    exit(1)

conn = psycopg2.connect(DB_URL)
cur = conn.cursor()

def parse_id(str_id):
    import re
    m = re.search(r'\d+', str_id)
    return int(m.group()) if m else 1

try:
    print("Clearing tables...")
    cur.execute("TRUNCATE TABLE evidence, employee_capabilities, component_dependencies, system_dependencies, capabilities, components, systems, employees CASCADE;")
    
    config_dir = os.path.join(os.path.dirname(__file__), 'data', 'config')
    
    print("Loading employees...")
    with open(os.path.join(config_dir, 'employees.json')) as f:
        emps = json.load(f)
        for e in emps:
            cur.execute("INSERT INTO employees (employee_id, name, department, role) VALUES (%s, %s, %s, %s)",
                        (parse_id(e['id']), e['name'], 'Engineering', e['role']))

    print("Loading services (systems)...")
    with open(os.path.join(config_dir, 'services.json')) as f:
        svcs = json.load(f)
        for s in svcs:
            cur.execute("INSERT INTO systems (system_id, name, description, criticality) VALUES (%s, %s, %s, %s)",
                        (parse_id(s['id']), s['name'], s['description'], 1.0))

    print("Loading modules (components)...")
    with open(os.path.join(config_dir, 'modules.json')) as f:
        mods = json.load(f)
        for m in mods:
            cur.execute("INSERT INTO components (component_id, system_id, name, component_type, description, criticality) VALUES (%s, %s, %s, %s, %s, %s)",
                        (parse_id(m['id']), parse_id(m['service_id']), m['name'], 'Service', m['description'], 1.0))

    print("Loading capabilities...")
    with open(os.path.join(config_dir, 'capabilities.json')) as f:
        caps = json.load(f)
        for c in caps:
            # We assign them to component 1 by default, as the JSON doesn't map them
            cur.execute("INSERT INTO capabilities (capability_id, component_id, name, description, criticality) VALUES (%s, %s, %s, %s, %s)",
                        (parse_id(c['id']), 1, c['name'], c['description'], 1.0))

    print("Loading employee capabilities and evidence...")
    with open(os.path.join(config_dir, 'employee_skill_details.json')) as f:
        details = json.load(f)
        for d in details:
            emp_id = parse_id(d['employee_id'])
            cap_id = parse_id(d['skill_id'])
            
            cur.execute("INSERT INTO employee_capabilities (employee_id, capability_id, evidence_strength, evidence_recency, confidence) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                        (emp_id, cap_id, d['credibility_score'], 1.0, d['credibility_score']))
            
            for ev in d['supporting_evidence']:
                # handle evidence_id EV001 -> 1, EV099_NEW -> 99, etc.
                ev_id_match = __import__('re').search(r'\d+', ev['evidence_id'])
                if ev_id_match:
                     # just auto increment or use the parsed id? Postgres evidence_id is SERIAL, so we can omit it!
                     cur.execute("INSERT INTO evidence (employee_id, capability_id, evidence_type, description, strength, observed_at, source_reference) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                            (emp_id, cap_id, ev['evidence_type'].upper().replace(' ', '_'), ev['source'] + ' / ' + ev['evidence_id'], ev['evidence_contribution'], ev['date'], ev['evidence_id']))

    conn.commit()
    print("Successfully loaded test data into Supabase!")
    
except Exception as e:
    conn.rollback()
    print("Error:", e)
finally:
    cur.close()
    conn.close()

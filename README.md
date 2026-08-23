# Engineering Continuity Platform
### Graph Intelligence for Knowledge Risk — Jugaad Geeks | SIH 2026

A real-time dashboard that quantifies **who knows what** across your engineering team, detects single points of failure, and simulates coverage impact when an engineer becomes unavailable — all driven by mathematical evidence from GitHub commits, Jira tickets, and incident records.

---

## How it works

Raw developer activity (commits, PRs, incidents) is ingested and passed through a **V2 Evidence Mass Engine**:

```
E = Σ -ln(1 - cᵢ)      (Evidence Mass — additive, no double-counting)
S = 1 - e⁻ᴱ            (Final Score — bounded 0 to 1)
```

Each piece of evidence decays over time with a **2-year half-life** so stale knowledge doesn't inflate scores.

Final scores are painted on an interactive **D3 force graph** as HIGH / MODERATE / LOW / NONE bands.

---

## Setup (from scratch)

### Prerequisites
- Python 3.10+
- Node.js 18+
- PostgreSQL running locally

---

### 1. Clone the repo
```bash
git clone https://github.com/Rakshak29/Jugaad-Geeks_SIH.git
cd Jugaad-Geeks_SIH
```

### 2. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 3. Create the database
Open pgAdmin or psql and run:
```sql
CREATE DATABASE engineering_continuity;
```

### 4. Configure environment
Create a `.env` file in the project root:
```
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/engineering_continuity
```

### 5. Run migrations (creates all tables)
```bash
alembic upgrade head
```

### 6. Load data and compute scores
```bash
python -m backend.run_pipeline
python -m backend.run_engine
```

### 7. Start the backend
```bash
uvicorn backend.main:app --reload --port 8000
```

### 8. Start the frontend
```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**

---

## Features

- **Knowledge Graph** — D3 force-directed graph of employees → capabilities with evidence-weighted edges
- **Technical Graph** — Service → Module dependency map
- **Simulation Engine** — Mark any engineer UNAVAILABLE and instantly see:
  - Before / After coverage bands per capability
  - Per-employee remaining evidence with exact scores
  - Minimum Coverage Team (optimizer finds smallest team to plug gaps)
  - Residual gaps where no backup exists
- **Evidence Analysis** — Click any capability in the simulation to see exactly who loses what score and who remains

---

## Project Structure

```
Jugaad-Geeks_SIH/
├── backend/
│   ├── engine/          # V2 Evidence Mass scoring engine
│   ├── ingestion/       # GitHub, Jira, Incident, Deployment extractors
│   ├── models/          # SQLAlchemy ORM models
│   ├── migrations/      # Alembic DB migrations
│   ├── input/           # Seed data (employees, capabilities, evidence)
│   ├── main.py          # FastAPI app — /api/graph/knowledge, /api/graph/technical
│   ├── run_pipeline.py  # Ingest raw data → evidence records
│   └── run_engine.py    # Score evidence records → capability_scores
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # Main app, graph switching, simulation tab
│   │   ├── components/
│   │   │   ├── GraphCanvas.jsx  # D3 force graph renderer
│   │   │   └── DetailsPanel.jsx # Node intelligence panel + simulation logic
│   │   └── services/
│   │       ├── api.js           # Axios calls to FastAPI
│   │       └── coverageEngine.js # Band thresholds + minimum coverage optimizer
│   └── package.json
├── data/raw/            # Raw GitHub/Jira/Incident JSON files
└── requirements.txt
```

---

## Band Thresholds

| Band | Score | Meaning |
|------|-------|---------|
| HIGH | ≥ 0.75 | Deep, recent, proven knowledge |
| MODERATE | ≥ 0.45 | Solid working familiarity |
| LOW | ≥ 0.20 | Residual context — rampable |
| NONE | < 0.20 | No meaningful coverage |

---

*Built for Smart India Hackathon 2026 — Jugaad Geeks*

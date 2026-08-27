"""FastAPI app.

Route handlers contain ZERO business logic (Piece 1 §3.16).  Each one resolves a
connection, calls exactly one domain function, and returns.  That is not style:
it is what keeps the intelligence testable without a web server, and it is why
the engine was demoable from a script before this file existed.
"""

from __future__ import annotations

from typing import Iterator

import psycopg
from fastapi import Body, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.errors import (
    ECEError, InvalidEdgeError, InvalidRequestError, MissingConfigError,
    NoFrozenTreeError, NotFoundError, NotInCoverageSetError,
)
from app.db.conn import connect
from app.domain import records, services

app = FastAPI(title="Engineering Continuity Engine", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)


def db() -> Iterator[psycopg.Connection]:
    with connect() as conn:
        yield conn


# ── Errors are mapped centrally; no handler raises HTTP itself ───────────────
@app.exception_handler(ECEError)
async def _domain_error(request: Request, exc: ECEError) -> JSONResponse:
    status = {
        NotFoundError: 404,
        NotInCoverageSetError: 422,
        InvalidEdgeError: 400,
        InvalidRequestError: 400,
        NoFrozenTreeError: 503,
        MissingConfigError: 503,
    }.get(type(exc), 500)
    return JSONResponse(status_code=status, content={"detail": str(exc)})


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/service/{service_id}/overview")
def overview(service_id: str, conn=Depends(db)) -> dict:
    return services.get_overview(conn, service_id)


@app.get("/at-risk")
def at_risk(conn=Depends(db)) -> dict:
    return services.get_at_risk(conn)


@app.get("/employees")
def employees(conn=Depends(db)) -> dict:
    return services.list_employees(conn)


@app.get("/employees/{employee_id}")
def employee_detail(employee_id: str, conn=Depends(db)) -> dict:
    return services.get_employee(conn, employee_id)


@app.get("/capabilities/{capability_id}/evidence")
def evidence(capability_id: int, exclude_employee: str | None = None,
             conn=Depends(db)) -> dict:
    return services.get_evidence(conn, capability_id, exclude_employee)


@app.get("/capabilities/{capability_id}")
def capability_detail(capability_id: int, conn=Depends(db)) -> dict:
    return services.get_capability(conn, capability_id)


@app.get("/raw-record/{raw_record_id}")
def raw_record(raw_record_id: int, conn=Depends(db)) -> dict:
    return records.get_record(conn, raw_record_id)


# ── Records and pipeline results — "show your working" ───────────────────────
@app.get("/records")
def record_list(source_type: str | None = None, eligibility: str | None = None,
                capability_id: int | None = None, search: str | None = None,
                conn=Depends(db)) -> dict:
    return records.list_records(conn, source_type, eligibility, capability_id, search)


@app.get("/work-units")
def work_units(conn=Depends(db)) -> dict:
    return records.list_work_units(conn)


@app.get("/pipeline")
def pipeline(conn=Depends(db)) -> dict:
    return records.pipeline_report(conn)


def _required(payload: dict, *keys: str) -> tuple:
    """Pull required body keys, or raise the domain error that maps to 400.

    Indexing the body directly turned a malformed request into a 500, which
    reports a server fault for a client mistake and tells the caller nothing
    about which field was missing.
    """
    missing = [k for k in keys if payload.get(k) in (None, "")]
    if missing:
        raise InvalidRequestError(
            f"missing required field{'s' if len(missing) != 1 else ''}: "
            f"{', '.join(missing)}")
    return tuple(payload[k] for k in keys)


@app.post("/simulate-unavailability")
def simulate(payload: dict = Body(...), conn=Depends(db)) -> dict:
    (employee_id,) = _required(payload, "employee_id")
    return services.simulate(conn, employee_id)


@app.post("/generate-coverage-team")
def generate_coverage_team(payload: dict = Body(...), conn=Depends(db)) -> dict:
    return services.coverage_plan(
        conn,
        employee_id=payload.get("employee_id"),
        capability_id=payload.get("capability_id"),
    )


@app.get("/graph/evidence")
def graph_evidence(simulate: str | None = None, conn=Depends(db)) -> dict:
    return services.evidence_graph(conn, simulate)


@app.get("/graph/dependency")
def graph_dependency(simulate: str | None = None, conn=Depends(db)) -> dict:
    return services.dependency_graph(conn, simulate)


@app.post("/graph/dependency/edge")
def add_edge(payload: dict = Body(...), conn=Depends(db)) -> dict:
    frm, to = _required(payload, "from_component", "to_component")
    return services.add_dependency_edge(conn, frm, to)


@app.delete("/graph/dependency/edge")
def remove_edge(payload: dict = Body(...), conn=Depends(db)) -> dict:
    frm, to = _required(payload, "from_component", "to_component")
    return services.remove_dependency_edge(conn, frm, to)

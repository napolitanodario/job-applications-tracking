"""Minimal FastAPI UI for job application tracking."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from shared.db import connect, init_db, list_applications

DB_PATH = Path(os.environ.get("JOBTRACK_DB_PATH", "/data/jobtrack.db"))
WEB_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(WEB_DIR / "templates"))

app = FastAPI(title="Job Application Tracker")
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")


def _display(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    text = str(value).strip()
    return text


@app.on_event("startup")
def startup() -> None:
    # Ensure schema exists even if worker has not started yet.
    # Web volume is often mounted read-only; init only when writable.
    try:
        conn = connect(DB_PATH, read_only=False)
        init_db(conn)
        conn.close()
    except Exception:
        # Read-only mount: worker owns schema creation.
        pass


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    applications = []
    try:
        conn = connect(DB_PATH, read_only=True)
        try:
            rows = list_applications(conn)
        finally:
            conn.close()
    except Exception:
        rows = []

    for row in rows:
        internship = row["is_internship"]
        if internship is None:
            internship_display = ""
        else:
            internship_display = "yes" if int(internship) == 1 else "no"
        applications.append(
            {
                "company": _display(row["company"]),
                "position_title": _display(row["position_title"]),
                "is_internship": internship_display,
                "location": _display(row["location"]),
                "contract_type": _display(row["contract_type"]),
                "applied_on": _display(row["applied_on"]),
                "rejected_on": _display(row["rejected_on"]),
                "invitation_on": _display(row["invitation_on"]),
                "next_steps": _display(row["next_steps"]),
                "notes": _display(row["notes"]),
                "status": _display(row["status"]),
            }
        )

    return TEMPLATES.TemplateResponse(
        "index.html",
        {
            "request": request,
            "applications": applications,
        },
    )

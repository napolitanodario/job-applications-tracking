"""Apply extraction results into the applications table."""

from __future__ import annotations

import logging
from typing import Any, Optional

from shared.db import (
    find_application_by_identity,
    find_application_by_thread,
    update_application,
    upsert_application,
)
from shared.models import ExtractionResult, identity_key
from worker.gmail_client import utc_now_iso

logger = logging.getLogger(__name__)


def _prefer(existing: Any, new: Any) -> Any:
    if new is None:
        return existing
    if existing is None:
        return new
    if isinstance(existing, str) and not str(existing).strip():
        return new
    return existing


def _merge_notes(existing: Optional[str], new: Optional[str]) -> Optional[str]:
    if not new:
        return existing
    if not existing:
        return new
    if new in existing:
        return existing
    return f"{existing}\n{new}"


def apply_extraction(conn, result: ExtractionResult) -> None:
    """Upsert or merge one extraction into applications."""
    if not result.relevant:
        return

    now = utc_now_iso()
    row = find_application_by_thread(conn, result.thread_id)
    if row is None:
        key = identity_key(result.company, result.position_title)
        if key and result.company and result.position_title:
            row = find_application_by_identity(
                conn, result.company, result.position_title
            )
            if row is not None:
                logger.info(
                    "Merging thread %s into application %s via company+title",
                    result.thread_id,
                    row["id"],
                )

    status = result.derived_status()
    rejected_on = result.event_on if result.event_type == "rejection" else None
    invitation_on = result.event_on if result.event_type == "invitation" else None
    next_steps = result.next_steps if result.event_type == "invitation" else None
    applied_on = result.applied_on
    if result.event_type == "confirmation" and not applied_on:
        applied_on = result.event_on

    if row is None:
        fields = {
            "thread_id": result.thread_id,
            "company": result.company,
            "position_title": result.position_title,
            "is_internship": (
                None if result.is_internship is None else int(result.is_internship)
            ),
            "location": result.location,
            "contract_type": result.contract_type,
            "applied_on": applied_on,
            "rejected_on": rejected_on,
            "invitation_on": invitation_on,
            "next_steps": next_steps,
            "notes": result.notes,
            "status": status,
            "updated_at": now,
        }
        upsert_application(conn, fields)
        return

    # Merge into existing row
    new_status = row["status"]
    if status == "rejected":
        new_status = "rejected"
    elif status == "next_steps" and row["status"] != "rejected":
        new_status = "next_steps"

    fields = {
        "company": _prefer(row["company"], result.company),
        "position_title": _prefer(row["position_title"], result.position_title),
        "is_internship": (
            row["is_internship"]
            if result.is_internship is None
            else int(result.is_internship)
        ),
        "location": _prefer(row["location"], result.location),
        "contract_type": _prefer(row["contract_type"], result.contract_type),
        "applied_on": _prefer(row["applied_on"], applied_on),
        "rejected_on": _prefer(row["rejected_on"], rejected_on),
        "invitation_on": _prefer(row["invitation_on"], invitation_on),
        "next_steps": _merge_notes(row["next_steps"], next_steps)
        if next_steps
        else row["next_steps"],
        "notes": _merge_notes(row["notes"], result.notes),
        "status": new_status,
        "updated_at": now,
    }
    update_application(conn, int(row["id"]), fields)
    if row["thread_id"] != result.thread_id:
        logger.debug(
            "Cross-thread merge kept primary thread_id=%s for message thread=%s",
            row["thread_id"],
            result.thread_id,
        )

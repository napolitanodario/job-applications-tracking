"""Shared Pydantic models and sanitizers for job application extraction."""

from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator


PLACEHOLDER_VALUES = frozenset(
    {
        "",
        "n/a",
        "na",
        "none",
        "null",
        "unknown",
        "not specified",
        "not available",
        "unavailable",
        "-",
        "--",
    }
)

EventType = Literal["confirmation", "rejection", "invitation", "other_job"]
ApplicationStatus = Literal["applied", "rejected", "next_steps"]


def _normalize_blank(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.casefold() in PLACEHOLDER_VALUES:
        return None
    return text


def _normalize_whitespace(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return re.sub(r"\s+", " ", value).strip() or None


def identity_key(company: Optional[str], position_title: Optional[str]) -> Optional[str]:
    """Build a merge key from company + title when both are present."""
    c = _normalize_whitespace(company)
    p = _normalize_whitespace(position_title)
    if not c or not p:
        return None
    return f"{c.casefold()}|{p.casefold()}"


class ExtractionResult(BaseModel):
    """One model output for a single email message."""

    model_config = ConfigDict(extra="forbid")

    message_id: str
    thread_id: str
    relevant: bool = False
    company: Optional[str] = None
    position_title: Optional[str] = None
    is_internship: Optional[bool] = None
    location: Optional[str] = None
    contract_type: Optional[str] = None
    applied_on: Optional[str] = None
    event_type: Optional[EventType] = None
    event_on: Optional[str] = None
    next_steps: Optional[str] = None
    notes: Optional[str] = None

    @field_validator(
        "company",
        "position_title",
        "location",
        "contract_type",
        "applied_on",
        "event_on",
        "next_steps",
        "notes",
        mode="before",
    )
    @classmethod
    def strip_placeholders(cls, value: Any) -> Optional[str]:
        return _normalize_blank(value)

    @field_validator("is_internship", mode="before")
    @classmethod
    def coerce_internship(cls, value: Any) -> Optional[bool]:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            if value == 1:
                return True
            if value == 0:
                return False
            return None
        text = _normalize_blank(value)
        if text is None:
            return None
        lowered = text.casefold()
        if lowered in {"true", "yes", "1", "internship"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
        return None

    def derived_status(self) -> ApplicationStatus:
        if self.event_type == "rejection":
            return "rejected"
        if self.event_type == "invitation":
            return "next_steps"
        return "applied"


class ApplicationRow(BaseModel):
    """Row shape used by the web UI."""

    id: int
    thread_id: str
    company: Optional[str] = None
    position_title: Optional[str] = None
    is_internship: Optional[bool] = None
    location: Optional[str] = None
    contract_type: Optional[str] = None
    applied_on: Optional[str] = None
    rejected_on: Optional[str] = None
    invitation_on: Optional[str] = None
    next_steps: Optional[str] = None
    notes: Optional[str] = None
    status: ApplicationStatus = "applied"
    updated_at: str

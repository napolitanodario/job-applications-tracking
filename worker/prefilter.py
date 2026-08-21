"""Hardcoded ATS/recruiting gate for CATEGORY_UPDATES messages."""

from __future__ import annotations

import re
from typing import Mapping

ATS_DOMAINS = (
    "greenhouse.io",
    "greenhouse-mail.io",
    "lever.co",
    "hire.lever.co",
    "myworkday.com",
    "myworkdayjobs.com",
    "workday.com",
    "smartrecruiters.com",
    "ashbyhq.com",
    "bamboohr.com",
    "icims.com",
    "jobvite.com",
    "taleo.net",
    "successfactors.com",
    "linkedin.com",
    "indeed.com",
    "teamtailor.com",
    "personio.de",
    "personio.com",
    "recruitee.com",
    "rippling.com",
    "gem.com",
    "ashby.comms.ashbyhq.com",
    "mail.greenhouse.io",
    "notifications.google.com",
)

KEYWORD_PATTERN = re.compile(
    r"("
    r"application\s+(received|submitted|confirmation)|"
    r"thank\s+you\s+for\s+(applying|your\s+application)|"
    r"we\s+received\s+your\s+application|"
    r"your\s+application\s+(for|to|has)|"
    r"interview|"
    r"next\s+steps?|"
    r"hiring\s+(manager|team|process)|"
    r"recruit(er|ing)|"
    r"candidat(e|ure)|"
    r"rejection|"
    r"not\s+moving\s+forward|"
    r"unfortunately|"
    r"offer\s+(letter|of\s+employment)|"
    r"assessment|"
    r"take[- ]home|"
    r"coding\s+challenge|"
    r"internship|"
    r"job\s+alert|"
    r"new\s+application"
    r")",
    re.IGNORECASE,
)


def _extract_email_domain(from_header: str) -> str:
    match = re.search(r"<([^>]+)>", from_header)
    address = match.group(1) if match else from_header
    address = address.strip().casefold()
    if "@" not in address:
        return ""
    return address.rsplit("@", 1)[-1]


def passes_recruiting_gate(message: Mapping[str, str]) -> bool:
    """Return True if From/Subject/snippet looks recruiting-related."""
    from_header = message.get("from_header", "") or ""
    subject = message.get("subject", "") or ""
    snippet = message.get("snippet", "") or ""
    domain = _extract_email_domain(from_header)

    for ats in ATS_DOMAINS:
        if domain == ats or domain.endswith("." + ats):
            return True

    haystack = f"{from_header}\n{subject}\n{snippet}"
    return KEYWORD_PATTERN.search(haystack) is not None

"""Gmail API client for CATEGORY_UPDATES polling and backfill."""

from __future__ import annotations

import base64
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterator, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
UPDATES_LABEL = "CATEGORY_UPDATES"
BODY_CHAR_LIMIT = 8000


class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def get_text(self) -> str:
        return " ".join(self._chunks)


def strip_html(html: str) -> str:
    stripper = _HTMLStripper()
    try:
        stripper.feed(html)
        text = stripper.get_text()
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def run_oauth_flow(credentials_path: Path, token_path: Path) -> Credentials:
    """Interactive desktop OAuth; writes token_path."""
    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
    creds = flow.run_local_server(port=0)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def load_credentials(credentials_path: Path, token_path: Path) -> Credentials:
    creds: Optional[Credentials] = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds
    raise RuntimeError(
        "Gmail token missing or invalid. Run: "
        "docker compose run --rm -it worker python -m worker.gmail_auth"
    )


class GmailClient:
    def __init__(self, credentials_path: Path, token_path: Path) -> None:
        creds = load_credentials(credentials_path, token_path)
        self._service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    def get_profile_history_id(self) -> str:
        profile = self._service.users().getProfile(userId="me").execute()
        return str(profile["historyId"])

    def list_updates_message_ids(self, newer_than_days: int) -> list[str]:
        query = f"category:updates newer_than:{newer_than_days}d"
        return list(self._list_ids(query=query))

    def list_history_message_ids(
        self, start_history_id: str
    ) -> tuple[list[str], Optional[str]]:
        """Return (message_ids, new_history_id). new_history_id is None if stale."""
        message_ids: list[str] = []
        page_token: Optional[str] = None
        latest_history_id = start_history_id
        try:
            while True:
                request = (
                    self._service.users()
                    .history()
                    .list(
                        userId="me",
                        startHistoryId=start_history_id,
                        historyTypes=["messageAdded"],
                        labelId=UPDATES_LABEL,
                        pageToken=page_token,
                    )
                )
                response = request.execute()
                for history in response.get("history", []):
                    for added in history.get("messagesAdded", []):
                        msg = added.get("message") or {}
                        mid = msg.get("id")
                        if mid:
                            message_ids.append(mid)
                    if "id" in history:
                        latest_history_id = str(history["id"])
                if "historyId" in response:
                    latest_history_id = str(response["historyId"])
                page_token = response.get("nextPageToken")
                if not page_token:
                    break
        except HttpError as exc:
            if exc.resp is not None and exc.resp.status in (404, 400):
                logger.warning("Gmail history stale (%s); falling back to date query", exc)
                return [], None
            raise
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for mid in message_ids:
            if mid not in seen:
                seen.add(mid)
                unique.append(mid)
        return unique, latest_history_id

    def fetch_message(self, message_id: str) -> dict[str, str]:
        raw = (
            self._service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        headers = {
            h["name"].lower(): h["value"]
            for h in raw.get("payload", {}).get("headers", [])
        }
        body = self._extract_body(raw.get("payload") or {})
        if len(body) > BODY_CHAR_LIMIT:
            body = body[:BODY_CHAR_LIMIT]
        date_header = headers.get("date", "")
        date_iso = self._header_date_to_iso(date_header)
        return {
            "message_id": message_id,
            "thread_id": str(raw.get("threadId") or ""),
            "from_header": headers.get("from", ""),
            "subject": headers.get("subject", ""),
            "date_header": date_header,
            "date_iso": date_iso or "",
            "snippet": raw.get("snippet") or "",
            "body": body,
        }

    def _list_ids(self, query: str) -> Iterator[str]:
        page_token: Optional[str] = None
        while True:
            response = (
                self._service.users()
                .messages()
                .list(
                    userId="me",
                    q=query,
                    labelIds=[UPDATES_LABEL],
                    pageToken=page_token,
                    maxResults=100,
                )
                .execute()
            )
            for item in response.get("messages", []):
                yield item["id"]
            page_token = response.get("nextPageToken")
            if not page_token:
                break

    def _extract_body(self, payload: dict[str, Any]) -> str:
        mime = payload.get("mimeType") or ""
        body_data = (payload.get("body") or {}).get("data")
        if body_data and mime == "text/plain":
            return self._b64decode(body_data)
        if body_data and mime == "text/html":
            return strip_html(self._b64decode(body_data))

        plain_parts: list[str] = []
        html_parts: list[str] = []
        for part in payload.get("parts") or []:
            part_mime = part.get("mimeType") or ""
            if part_mime.startswith("multipart/"):
                nested = self._extract_body(part)
                if nested:
                    plain_parts.append(nested)
                continue
            data = (part.get("body") or {}).get("data")
            if not data:
                continue
            decoded = self._b64decode(data)
            if part_mime == "text/plain":
                plain_parts.append(decoded)
            elif part_mime == "text/html":
                html_parts.append(strip_html(decoded))
        if plain_parts:
            return "\n".join(plain_parts).strip()
        if html_parts:
            return "\n".join(html_parts).strip()
        return ""

    @staticmethod
    def _b64decode(data: str) -> str:
        padded = data + "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(padded.encode("utf-8")).decode(
            "utf-8", errors="replace"
        )

    @staticmethod
    def _header_date_to_iso(date_header: str) -> Optional[str]:
        if not date_header:
            return None
        try:
            dt = parsedate_to_datetime(date_header)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).date().isoformat()
        except (TypeError, ValueError, IndexError):
            return None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

"""Worker entrypoint: Gmail backfill, 30-minute poll, Colab extraction."""

from __future__ import annotations

import logging
import os
import signal
import time
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from shared.db import (
    connect,
    get_sync_value,
    init_db,
    mark_message,
    message_already_processed,
    set_sync_value,
)
from shared.models import ExtractionResult
from worker.colab_runner import ColabError, cleanup_orphans, run_inference_batch
from worker.gmail_client import GmailClient, utc_now_iso
from worker.prefilter import passes_recruiting_gate
from worker.store import apply_extraction

logger = logging.getLogger(__name__)

STOP = False


def _handle_signal(signum: int, _frame) -> None:
    global STOP
    logger.info("Received signal %s; shutting down after current cycle", signum)
    STOP = True


def _chunk(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def process_message_ids(
    conn,
    gmail: GmailClient,
    message_ids: list[str],
    *,
    session_name: str,
    batch_size: int,
) -> bool:
    """Process messages. Returns False if Colab failed and work remains."""
    pending: list[dict[str, str]] = []

    for mid in message_ids:
        if message_already_processed(conn, mid):
            continue
        try:
            msg = gmail.fetch_message(mid)
        except Exception:
            logger.exception("Failed to fetch message %s", mid)
            continue

        if not passes_recruiting_gate(msg):
            mark_message(conn, mid, msg["thread_id"], "prefilter", utc_now_iso())
            continue
        pending.append(msg)

    if not pending:
        logger.info("No recruiting-like messages to send to Colab")
        return True

    for batch in _chunk(pending, batch_size):
        if STOP:
            return False
        try:
            raw_results = run_inference_batch(batch, session_name=session_name)
        except ColabError:
            logger.exception(
                "Colab inference failed for %s messages; will retry next tick",
                len(batch),
            )
            return False
        except Exception:
            logger.exception("Unexpected Colab failure; will retry next tick")
            return False

        by_id = {str(item.get("message_id")): item for item in raw_results}

        for msg in batch:
            mid = msg["message_id"]
            raw = by_id.get(mid)
            if raw is None:
                logger.warning(
                    "No model output for message %s; leaving unprocessed", mid
                )
                continue
            try:
                result = ExtractionResult.model_validate(raw)
            except ValidationError:
                logger.exception("Invalid extraction for %s: %s", mid, raw)
                mark_message(conn, mid, msg["thread_id"], "not_job", utc_now_iso())
                continue

            if not result.relevant:
                mark_message(
                    conn,
                    mid,
                    result.thread_id or msg["thread_id"],
                    "not_job",
                    utc_now_iso(),
                )
                continue

            apply_extraction(conn, result)
            mark_message(
                conn,
                mid,
                result.thread_id or msg["thread_id"],
                "extracted",
                utc_now_iso(),
            )
    return True


def run_backfill(
    conn,
    gmail: GmailClient,
    *,
    session_name: str,
    batch_size: int,
) -> None:
    logger.info("Starting 30-day CATEGORY_UPDATES backfill")
    ids = gmail.list_updates_message_ids(newer_than_days=30)
    logger.info("Backfill found %s messages", len(ids))
    ok = process_message_ids(
        conn, gmail, ids, session_name=session_name, batch_size=batch_size
    )
    if ok and not STOP:
        set_sync_value(conn, "backfill_done", "1")
        set_sync_value(conn, "gmail_history_id", gmail.get_profile_history_id())
        logger.info("Backfill complete")
    else:
        logger.warning("Backfill incomplete; will resume on next start/poll")


def run_incremental(
    conn,
    gmail: GmailClient,
    *,
    session_name: str,
    batch_size: int,
) -> None:
    history_id = get_sync_value(conn, "gmail_history_id")
    message_ids: list[str] = []
    new_history: Optional[str] = None

    if history_id:
        message_ids, new_history = gmail.list_history_message_ids(history_id)
        if new_history is None:
            logger.info("History stale; falling back to newer_than:1d")
            message_ids = gmail.list_updates_message_ids(newer_than_days=1)
            new_history = gmail.get_profile_history_id()
    else:
        message_ids = gmail.list_updates_message_ids(newer_than_days=1)
        new_history = gmail.get_profile_history_id()

    logger.info("Incremental poll: %s candidate message ids", len(message_ids))
    process_message_ids(
        conn, gmail, message_ids, session_name=session_name, batch_size=batch_size
    )
    if new_history and not STOP:
        set_sync_value(conn, "gmail_history_id", new_history)


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    db_path = Path(os.environ.get("JOBTRACK_DB_PATH", "/data/jobtrack.db"))
    credentials_path = Path(
        os.environ.get("GMAIL_CREDENTIALS_PATH", "/secrets/credentials.json")
    )
    token_path = Path(os.environ.get("GMAIL_TOKEN_PATH", "/secrets/token.json"))
    session_name = os.environ.get("COLAB_SESSION_NAME", "jobtrack")
    batch_size = int(os.environ.get("BATCH_SIZE", "20"))
    poll_interval = int(os.environ.get("POLL_INTERVAL_SECONDS", "1800"))

    conn = connect(db_path)
    init_db(conn)
    cleanup_orphans(session_name)

    try:
        gmail = GmailClient(credentials_path, token_path)
    except Exception:
        logger.exception("Gmail auth failed")
        return 1

    while not STOP:
        try:
            if get_sync_value(conn, "backfill_done") != "1":
                run_backfill(
                    conn, gmail, session_name=session_name, batch_size=batch_size
                )
            else:
                run_incremental(
                    conn, gmail, session_name=session_name, batch_size=batch_size
                )
        except Exception:
            logger.exception("Poll cycle failed")

        # Sleep in short slices so SIGTERM is responsive.
        slept = 0
        while slept < poll_interval and not STOP:
            time.sleep(min(5, poll_interval - slept))
            slept += 5

    cleanup_orphans(session_name)
    logger.info("Worker stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

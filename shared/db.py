"""SQLite helpers shared by worker and web containers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable, Optional

SCHEMA_PATH = Path(__file__).with_name("jobtrack_schema.sql")


def connect(db_path: str | Path, *, read_only: bool = False) -> sqlite3.Connection:
    path = Path(db_path)
    if read_only:
        uri = f"file:{path.resolve()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    if not read_only:
        conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema)
    conn.commit()


def get_sync_value(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute(
        "SELECT value FROM sync_state WHERE key = ?",
        (key,),
    ).fetchone()
    return None if row is None else str(row["value"])


def set_sync_value(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO sync_state(key, value) VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    conn.commit()


def message_already_processed(conn: sqlite3.Connection, message_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM messages WHERE message_id = ?",
        (message_id,),
    ).fetchone()
    return row is not None


def mark_message(
    conn: sqlite3.Connection,
    message_id: str,
    thread_id: str,
    skip_reason: str,
    processed_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO messages(message_id, thread_id, processed_at, skip_reason)
        VALUES(?, ?, ?, ?)
        ON CONFLICT(message_id) DO UPDATE SET
            thread_id = excluded.thread_id,
            processed_at = excluded.processed_at,
            skip_reason = excluded.skip_reason
        """,
        (message_id, thread_id, processed_at, skip_reason),
    )
    conn.commit()


def find_application_by_thread(
    conn: sqlite3.Connection, thread_id: str
) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM applications WHERE thread_id = ?",
        (thread_id,),
    ).fetchone()


def find_application_by_identity(
    conn: sqlite3.Connection, company: str, position_title: str
) -> Optional[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT * FROM applications
        WHERE company IS NOT NULL AND position_title IS NOT NULL
        """
    ).fetchall()
    target = f"{company.casefold().strip()}|{position_title.casefold().strip()}"
    for row in rows:
        key = f"{str(row['company']).casefold().strip()}|{str(row['position_title']).casefold().strip()}"
        if key == target:
            return row
    return None


def list_applications(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT * FROM applications
            ORDER BY
                CASE WHEN applied_on IS NULL THEN 1 ELSE 0 END,
                applied_on DESC,
                updated_at DESC
            """
        ).fetchall()
    )


def upsert_application(conn: sqlite3.Connection, fields: dict[str, Any]) -> None:
    cols = list(fields.keys())
    placeholders = ", ".join("?" for _ in cols)
    col_list = ", ".join(cols)
    updates = ", ".join(
        f"{c} = excluded.{c}" for c in cols if c not in {"id", "thread_id"}
    )
    conn.execute(
        f"""
        INSERT INTO applications({col_list})
        VALUES({placeholders})
        ON CONFLICT(thread_id) DO UPDATE SET {updates}
        """,
        tuple(fields[c] for c in cols),
    )
    conn.commit()


def update_application(
    conn: sqlite3.Connection, app_id: int, fields: dict[str, Any]
) -> None:
    if not fields:
        return
    assignments = ", ".join(f"{k} = ?" for k in fields)
    values: Iterable[Any] = list(fields.values()) + [app_id]
    conn.execute(
        f"UPDATE applications SET {assignments} WHERE id = ?",
        tuple(values),
    )
    conn.commit()

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL UNIQUE,
    company TEXT,
    position_title TEXT,
    is_internship INTEGER,
    location TEXT,
    contract_type TEXT,
    applied_on TEXT,
    rejected_on TEXT,
    invitation_on TEXT,
    next_steps TEXT,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'applied',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    skip_reason TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_applications_applied_on ON applications(applied_on);
CREATE INDEX IF NOT EXISTS idx_messages_thread_id ON messages(thread_id);

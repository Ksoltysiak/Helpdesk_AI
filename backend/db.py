import sqlite3
import os
from flask import g

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "helpdesk.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    username  TEXT UNIQUE NOT NULL,
    password  TEXT NOT NULL,
    name      TEXT NOT NULL,
    role      TEXT NOT NULL CHECK(role IN ('pracownik','technik','admin')),
    email     TEXT
);

CREATE TABLE IF NOT EXISTS tickets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    category        TEXT,
    priority        TEXT,
    status          TEXT NOT NULL DEFAULT 'Nowe',
    created_by      INTEGER NOT NULL REFERENCES users(id),
    assigned_to     INTEGER REFERENCES users(id),
    ai_categorized  INTEGER DEFAULT 0,
    sla_deadline    TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    closed_at       TEXT
);

CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id   INTEGER NOT NULL REFERENCES tickets(id),
    author_id   INTEGER NOT NULL REFERENCES users(id),
    content     TEXT NOT NULL,
    internal    INTEGER DEFAULT 1,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id   INTEGER NOT NULL REFERENCES tickets(id),
    user_id     INTEGER REFERENCES users(id),
    action      TEXT NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    timestamp   TEXT DEFAULT (datetime('now'))
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def log_audit(db, ticket_id, user_id, action, old=None, new=None):
    db.execute(
        "INSERT INTO audit_log (ticket_id, user_id, action, old_value, new_value) VALUES (?,?,?,?,?)",
        (ticket_id, user_id, action, old, new),
    )

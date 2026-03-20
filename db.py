"""ColdCraft — SQLite database setup and helpers."""

import sqlite3
from config import Config


def get_db():
    """Get a database connection."""
    Config.ensure_dirs()
    conn = sqlite3.connect(Config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS user_profile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            phone TEXT,
            linkedin_url TEXT,
            github_url TEXT,
            portfolio_url TEXT,
            skills TEXT,          -- JSON array
            interests TEXT,       -- JSON array
            experience TEXT,      -- JSON summary
            target_roles TEXT,    -- JSON array
            resume_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            website TEXT,
            industry TEXT,
            description TEXT,
            research_summary TEXT,
            verified INTEGER DEFAULT 0,
            verification_score INTEGER DEFAULT 0,
            verification_notes TEXT,
            source TEXT DEFAULT 'manual',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            role TEXT,
            company_id INTEGER,
            linkedin_url TEXT,
            github_url TEXT,
            source TEXT DEFAULT 'manual',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'email',  -- email, linkedin, github
            status TEXT DEFAULT 'draft',          -- draft, active, paused, completed
            total_contacts INTEGER DEFAULT 0,
            sent_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS outreach_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER,
            contact_id INTEGER,
            company_id INTEGER,
            action TEXT NOT NULL,       -- email_sent, comment_drafted, etc.
            subject TEXT,
            content TEXT,
            status TEXT DEFAULT 'sent', -- sent, failed, drafted
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
            FOREIGN KEY (contact_id) REFERENCES contacts(id),
            FOREIGN KEY (company_id) REFERENCES companies(id)
        );

        CREATE TABLE IF NOT EXISTS linkedin_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_url TEXT,
            post_author TEXT,
            post_summary TEXT,
            comment_draft TEXT,
            status TEXT DEFAULT 'pending',  -- pending, used, skipped
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()


# --- Helper functions ---

def query_db(sql, args=(), one=False):
    """Execute a query and return results as dicts."""
    conn = get_db()
    cur = conn.execute(sql, args)
    rows = cur.fetchall()
    conn.close()
    if one:
        return dict(rows[0]) if rows else None
    return [dict(r) for r in rows]


def execute_db(sql, args=()):
    """Execute an INSERT/UPDATE/DELETE and return lastrowid."""
    conn = get_db()
    cur = conn.execute(sql, args)
    conn.commit()
    last_id = cur.lastrowid
    conn.close()
    return last_id


def execute_many(sql, args_list):
    """Execute a batch of INSERT/UPDATE/DELETE."""
    conn = get_db()
    conn.executemany(sql, args_list)
    conn.commit()
    conn.close()

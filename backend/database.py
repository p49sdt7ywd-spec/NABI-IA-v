"""
Nabi AI — SQLite Database Module
Manages projects, settings, and pipeline state.
"""

import sqlite3
import os
import json
import uuid
from datetime import datetime
from pathlib import Path

DB_DIR = Path.home() / "nabi-ai"
DB_PATH = DB_DIR / "nabi.db"
PROJECTS_DIR = DB_DIR / "projects"


def get_connection() -> sqlite3.Connection:
    """Get a SQLite connection with row factory."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Initialize the database schema."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            source_video_path TEXT,
            output_video_path TEXT,
            duration_seconds REAL,
            transcription TEXT,
            edit_decision_list TEXT,
            settings TEXT,
            current_step TEXT,
            progress REAL DEFAULT 0,
            error_message TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


# ── Project CRUD ──────────────────────────────

def create_project(title: str, source_video_path: str, settings: dict = None) -> dict:
    """Create a new project."""
    project_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    # Create project directory
    project_dir = PROJECTS_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "images").mkdir(exist_ok=True)
    (project_dir / "broll").mkdir(exist_ok=True)

    conn = get_connection()
    conn.execute(
        """INSERT INTO projects (id, title, source_video_path, settings, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (project_id, title, source_video_path, json.dumps(settings or {}), now),
    )
    conn.commit()
    conn.close()

    return get_project(project_id)


def get_project(project_id: str) -> dict | None:
    """Get a project by ID."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return _row_to_dict(row)


def list_projects() -> list[dict]:
    """List all projects, most recent first."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def update_project(project_id: str, **kwargs) -> dict | None:
    """Update project fields."""
    allowed = {
        "status", "source_video_path", "output_video_path", "duration_seconds",
        "transcription", "edit_decision_list", "current_step",
        "progress", "error_message", "completed_at",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return get_project(project_id)

    # Serialize JSON fields
    for json_field in ("transcription", "edit_decision_list"):
        if json_field in fields and not isinstance(fields[json_field], str):
            fields[json_field] = json.dumps(fields[json_field])

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [project_id]

    conn = get_connection()
    conn.execute(f"UPDATE projects SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()

    return get_project(project_id)


def delete_project(project_id: str):
    """Delete a project and its files."""
    import shutil
    project_dir = PROJECTS_DIR / project_id
    if project_dir.exists():
        shutil.rmtree(project_dir)

    conn = get_connection()
    conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()


# ── Settings ──────────────────────────────────

def get_setting(key: str, default: str = "") -> str:
    """Get a setting value."""
    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    """Set a setting value."""
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()
    conn.close()


def get_all_settings() -> dict:
    """Get all settings as a dict."""
    conn = get_connection()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


# ── Helpers ───────────────────────────────────

def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a Row to a dict, parsing JSON fields."""
    d = dict(row)
    for json_field in ("transcription", "edit_decision_list", "settings"):
        if d.get(json_field):
            try:
                d[json_field] = json.loads(d[json_field])
            except (json.JSONDecodeError, TypeError):
                pass
    return d


def get_project_dir(project_id: str) -> Path:
    """Get the project directory path."""
    return PROJECTS_DIR / project_id

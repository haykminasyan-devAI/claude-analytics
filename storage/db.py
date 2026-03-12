"""
Storage layer: SQLite connection management and all write operations.

Responsibilities:
- get_connection()      context manager — always safely opens/commits/closes
- init_db()             creates all tables and indexes (idempotent)
- load_employees()      loads employees.csv into the employees table
- bulk_insert_events()  inserts batches of parsed events using executemany
"""

import csv
import logging
import sqlite3
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from config.settings import (
    DB_PATH,
    EMPLOYEES_CSV,
    EVENT_API_ERROR,
    EVENT_API_REQUEST,
    EVENT_TOOL_DECISION,
    EVENT_TOOL_RESULT,
    EVENT_USER_PROMPT,
)
from storage.schema import ALL_DDL

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Connection context manager
# ---------------------------------------------------------------------------

@contextmanager
def get_connection(db_path: Path = DB_PATH) -> Generator[sqlite3.Connection, None, None]:
    """
    Yield an open SQLite connection, commit on success, rollback on error.

    Usage:
        with get_connection() as conn:
            conn.execute("INSERT INTO ...")
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row          # rows accessible by column name
    conn.execute("PRAGMA journal_mode=WAL") # better write concurrency
    conn.execute("PRAGMA synchronous=NORMAL")

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

def init_db(db_path: Path = DB_PATH) -> None:
    """
    Create all tables and indexes defined in schema.ALL_DDL.
    Safe to call multiple times — all statements use IF NOT EXISTS.
    """
    with get_connection(db_path) as conn:
        for ddl_block in ALL_DDL:
            # each block may contain multiple statements separated by semicolons
            for statement in ddl_block.strip().split(";"):
                statement = statement.strip()
                if statement:
                    conn.execute(statement)

    logger.info("Database initialised at %s", db_path)


# ---------------------------------------------------------------------------
# Table + column mapping for each event type
# ---------------------------------------------------------------------------

# Maps event_type → (table_name, ordered list of columns to insert)
_TABLE_MAP: dict[str, tuple[str, list[str]]] = {
    EVENT_API_REQUEST: (
        "api_requests",
        [
            "event_timestamp", "session_id", "user_email", "user_id",
            "organization_id", "terminal_type", "practice", "os_type",
            "host_arch", "service_version",
            "model", "input_tokens", "output_tokens",
            "cache_read_tokens", "cache_creation_tokens",
            "cost_usd", "duration_ms",
        ],
    ),
    EVENT_TOOL_DECISION: (
        "tool_decisions",
        [
            "event_timestamp", "session_id", "user_email", "user_id",
            "organization_id", "terminal_type", "practice", "os_type",
            "host_arch", "service_version",
            "tool_name", "decision", "source",
        ],
    ),
    EVENT_TOOL_RESULT: (
        "tool_results",
        [
            "event_timestamp", "session_id", "user_email", "user_id",
            "organization_id", "terminal_type", "practice", "os_type",
            "host_arch", "service_version",
            "tool_name", "success", "duration_ms",
            "decision_type", "decision_source", "result_size_bytes",
        ],
    ),
    EVENT_USER_PROMPT: (
        "user_prompts",
        [
            "event_timestamp", "session_id", "user_email", "user_id",
            "organization_id", "terminal_type", "practice", "os_type",
            "host_arch", "service_version",
            "prompt_length",
        ],
    ),
    EVENT_API_ERROR: (
        "api_errors",
        [
            "event_timestamp", "session_id", "user_email", "user_id",
            "organization_id", "terminal_type", "practice", "os_type",
            "host_arch", "service_version",
            "model", "error", "status_code", "attempt", "duration_ms",
        ],
    ),
}


def _build_insert_sql(table: str, columns: list[str]) -> str:
    cols         = ", ".join(columns)
    placeholders = ", ".join("?" * len(columns))
    return f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"


# ---------------------------------------------------------------------------
# Bulk insert
# ---------------------------------------------------------------------------

def bulk_insert_events(
    rows_by_type: dict[str, list[dict]],
    db_path: Path = DB_PATH,
) -> None:
    """
    Insert a batch of parsed rows grouped by event type.

    Args:
        rows_by_type: { event_type_string: [flat_row_dict, ...], ... }

    Uses executemany for performance — a single round-trip per event type.
    """
    with get_connection(db_path) as conn:
        for event_type, rows in rows_by_type.items():
            if not rows:
                continue

            table, columns = _TABLE_MAP[event_type]
            sql    = _build_insert_sql(table, columns)
            tuples = [tuple(row.get(col) for col in columns) for row in rows]

            conn.executemany(sql, tuples)
            logger.debug("Inserted %d rows into '%s'", len(rows), table)


# ---------------------------------------------------------------------------
# Load employees CSV
# ---------------------------------------------------------------------------

def load_employees(
    csv_path: Path = EMPLOYEES_CSV,
    db_path:  Path = DB_PATH,
) -> int:
    """
    Read employees.csv and load all rows into the employees table.
    Clears the table first so this function can be re-run safely.

    Returns:
        Number of employees inserted.
    """
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for rec in reader:
            rows.append((
                rec["email"].strip(),
                rec["full_name"].strip(),
                rec["practice"].strip(),
                rec["level"].strip(),
                rec["location"].strip(),
            ))

    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM employees")   # full reload every time
        conn.executemany(
            "INSERT INTO employees (email, full_name, practice, level, location) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )

    logger.info("Loaded %d employees into database", len(rows))
    return len(rows)

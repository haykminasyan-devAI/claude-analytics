"""
SQLite schema definitions — all CREATE TABLE and CREATE INDEX statements.

Design decisions:
- One table per event type for clean separation and efficient filtering.
- All event tables share 10 common columns (session_id, user_email, etc.).
- Indexes on event_timestamp, user_email, session_id for fast analytics queries.
- employees table joined to event tables via user_email.
- No foreign-key enforcement (SQLite default) to maximise ingestion speed.
- All DDL collected in ALL_DDL so init_db() can iterate once and create everything.
"""

# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------

DDL_EMPLOYEES = """
CREATE TABLE IF NOT EXISTS employees (
    email      TEXT PRIMARY KEY,
    full_name  TEXT,
    practice   TEXT,
    level      TEXT,
    location   TEXT
);
"""

# ---------------------------------------------------------------------------
# api_requests
# ---------------------------------------------------------------------------

DDL_API_REQUESTS = """
CREATE TABLE IF NOT EXISTS api_requests (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,

    -- common fields
    event_timestamp        TEXT NOT NULL,
    session_id             TEXT,
    user_email             TEXT,
    user_id                TEXT,
    organization_id        TEXT,
    terminal_type          TEXT,
    practice               TEXT,
    os_type                TEXT,
    host_arch              TEXT,
    service_version        TEXT,

    -- specific fields
    model                  TEXT,
    input_tokens           INTEGER DEFAULT 0,
    output_tokens          INTEGER DEFAULT 0,
    cache_read_tokens      INTEGER DEFAULT 0,
    cache_creation_tokens  INTEGER DEFAULT 0,
    cost_usd               REAL    DEFAULT 0.0,
    duration_ms            INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_api_req_ts      ON api_requests(event_timestamp);
CREATE INDEX IF NOT EXISTS idx_api_req_user    ON api_requests(user_email);
CREATE INDEX IF NOT EXISTS idx_api_req_session ON api_requests(session_id);
"""

# ---------------------------------------------------------------------------
# tool_decisions
# ---------------------------------------------------------------------------

DDL_TOOL_DECISIONS = """
CREATE TABLE IF NOT EXISTS tool_decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    -- common fields
    event_timestamp TEXT NOT NULL,
    session_id      TEXT,
    user_email      TEXT,
    user_id         TEXT,
    organization_id TEXT,
    terminal_type   TEXT,
    practice        TEXT,
    os_type         TEXT,
    host_arch       TEXT,
    service_version TEXT,

    -- specific fields
    tool_name       TEXT,
    decision        TEXT,
    source          TEXT
);
CREATE INDEX IF NOT EXISTS idx_tool_dec_ts      ON tool_decisions(event_timestamp);
CREATE INDEX IF NOT EXISTS idx_tool_dec_user    ON tool_decisions(user_email);
CREATE INDEX IF NOT EXISTS idx_tool_dec_session ON tool_decisions(session_id);
"""

# ---------------------------------------------------------------------------
# tool_results
# ---------------------------------------------------------------------------

DDL_TOOL_RESULTS = """
CREATE TABLE IF NOT EXISTS tool_results (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,

    -- common fields
    event_timestamp   TEXT NOT NULL,
    session_id        TEXT,
    user_email        TEXT,
    user_id           TEXT,
    organization_id   TEXT,
    terminal_type     TEXT,
    practice          TEXT,
    os_type           TEXT,
    host_arch         TEXT,
    service_version   TEXT,

    -- specific fields
    tool_name         TEXT,
    success           INTEGER DEFAULT 1,
    duration_ms       INTEGER DEFAULT 0,
    decision_type     TEXT,
    decision_source   TEXT,
    result_size_bytes INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tool_res_ts      ON tool_results(event_timestamp);
CREATE INDEX IF NOT EXISTS idx_tool_res_user    ON tool_results(user_email);
CREATE INDEX IF NOT EXISTS idx_tool_res_session ON tool_results(session_id);
"""

# ---------------------------------------------------------------------------
# user_prompts
# ---------------------------------------------------------------------------

DDL_USER_PROMPTS = """
CREATE TABLE IF NOT EXISTS user_prompts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    -- common fields
    event_timestamp TEXT NOT NULL,
    session_id      TEXT,
    user_email      TEXT,
    user_id         TEXT,
    organization_id TEXT,
    terminal_type   TEXT,
    practice        TEXT,
    os_type         TEXT,
    host_arch       TEXT,
    service_version TEXT,

    -- specific fields
    prompt_length   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_prompt_ts      ON user_prompts(event_timestamp);
CREATE INDEX IF NOT EXISTS idx_prompt_user    ON user_prompts(user_email);
CREATE INDEX IF NOT EXISTS idx_prompt_session ON user_prompts(session_id);
"""

# ---------------------------------------------------------------------------
# api_errors
# ---------------------------------------------------------------------------

DDL_API_ERRORS = """
CREATE TABLE IF NOT EXISTS api_errors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    -- common fields
    event_timestamp TEXT NOT NULL,
    session_id      TEXT,
    user_email      TEXT,
    user_id         TEXT,
    organization_id TEXT,
    terminal_type   TEXT,
    practice        TEXT,
    os_type         TEXT,
    host_arch       TEXT,
    service_version TEXT,

    -- specific fields
    model           TEXT,
    error           TEXT,
    status_code     TEXT,
    attempt         INTEGER DEFAULT 1,
    duration_ms     INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_api_err_ts      ON api_errors(event_timestamp);
CREATE INDEX IF NOT EXISTS idx_api_err_user    ON api_errors(user_email);
CREATE INDEX IF NOT EXISTS idx_api_err_session ON api_errors(session_id);
"""

# ---------------------------------------------------------------------------
# ALL_DDL — used by init_db() to create everything in one pass
# ---------------------------------------------------------------------------

ALL_DDL = [
    DDL_EMPLOYEES,
    DDL_API_REQUESTS,
    DDL_TOOL_DECISIONS,
    DDL_TOOL_RESULTS,
    DDL_USER_PROMPTS,
    DDL_API_ERRORS,
]

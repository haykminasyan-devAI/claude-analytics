"""
Entry point for the Claude Analytics ingestion pipeline.

Run this script once to populate the SQLite database from the raw data files.

Usage:
    cd claude_analytics
    python run_pipeline.py

Steps:
    1. Set up logging
    2. Initialise the SQLite database (create tables + indexes)
    3. Load employees.csv into the employees table
    4. Stream events from telemetry_logs.jsonl one at a time
    5. Parse and buffer events into batches of 1000
    6. Flush each batch to the database
    7. Print a final summary
"""

import logging
import sys
import time
from collections import defaultdict

from config.settings import (
    DB_PATH,
    EMPLOYEES_CSV,
    JSONL_BATCH_SIZE,
    TELEMETRY_JSONL,
)
from ingestion.jsonl_reader import iter_events
from processing.event_parser import parse_event
from storage.db import bulk_insert_events, init_db, load_employees


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run() -> None:
    setup_logging()
    logger = logging.getLogger("pipeline")

    logger.info("========== Claude Analytics Pipeline ==========")
    start_time = time.time()

    # --- Step 1: initialise database ---
    logger.info("Initialising database at %s", DB_PATH)
    init_db()

    # --- Step 2: load employees ---
    logger.info("Loading employees from %s", EMPLOYEES_CSV)
    num_employees = load_employees()
    logger.info("  → %d employees loaded", num_employees)

    # --- Step 3: stream + parse + buffer + flush ---
    logger.info("Starting event ingestion from %s", TELEMETRY_JSONL)

    buffer: dict[str, list[dict]] = defaultdict(list)
    total_parsed   = 0
    total_skipped  = 0
    total_flushed  = 0
    counts_by_type: dict[str, int] = defaultdict(int)

    for raw_event in iter_events(TELEMETRY_JSONL):
        result = parse_event(raw_event)

        if result is None:
            total_skipped += 1
            continue

        event_type, row = result
        buffer[event_type].append(row)
        counts_by_type[event_type] += 1
        total_parsed += 1

        # flush buffer to DB every JSONL_BATCH_SIZE events
        current_buffer_size = sum(len(v) for v in buffer.values())
        if current_buffer_size >= JSONL_BATCH_SIZE:
            bulk_insert_events(dict(buffer))
            total_flushed += current_buffer_size
            buffer.clear()

            if total_flushed % 50_000 == 0:
                logger.info("  → %d events inserted so far ...", total_flushed)

    # flush any remaining events in the buffer
    remaining = sum(len(v) for v in buffer.values())
    if remaining > 0:
        bulk_insert_events(dict(buffer))
        total_flushed += remaining
        buffer.clear()

    # --- Step 4: summary ---
    elapsed = time.time() - start_time
    logger.info("================================================")
    logger.info("Pipeline complete in %.1f seconds", elapsed)
    logger.info("  Total events parsed:  %d", total_parsed)
    logger.info("  Total events skipped: %d", total_skipped)
    logger.info("  Total rows inserted:  %d", total_flushed)
    logger.info("------------------------------------------------")
    logger.info("  Rows inserted per table:")
    for event_type, count in sorted(counts_by_type.items()):
        logger.info("    %-35s %d", event_type, count)
    logger.info("================================================")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run()

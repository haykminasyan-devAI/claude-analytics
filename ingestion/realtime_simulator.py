"""
Real-time streaming simulator for Claude Code telemetry data.

Demonstrates how the platform would handle live event ingestion —
events are fed in small batches with a configurable delay between
each batch, mimicking a real-time data stream from CloudWatch.

In production this module would be replaced by an actual Kinesis/Kafka
consumer or a CloudWatch Logs subscription. The interface (batch → insert
→ yield status) would remain identical.

Usage:
    from ingestion.realtime_simulator import simulate_live_stream
    from config.settings import TELEMETRY_JSONL

    for status in simulate_live_stream(TELEMETRY_JSONL, batch_size=100, sleep_seconds=2):
        print(status)
"""

import logging
import time
from collections import defaultdict
from pathlib import Path
from typing import Generator

from config.settings import DB_PATH, EVENT_API_REQUEST, TELEMETRY_JSONL
from ingestion.jsonl_reader import iter_events
from processing.event_parser import parse_event
from storage.db import bulk_insert_events

logger = logging.getLogger(__name__)


def simulate_live_stream(
    jsonl_path:    Path  = TELEMETRY_JSONL,
    batch_size:    int   = 100,
    sleep_seconds: float = 1.0,
    db_path:       Path  = DB_PATH,
) -> Generator[dict, None, None]:
    """
    Simulate a live event stream by reading the JSONL file in small batches.

    After each batch:
        1. Parse all events in the batch
        2. Insert them into SQLite
        3. Pause for `sleep_seconds` to simulate real-time delay
        4. Yield a status dict with progress metrics

    Args:
        jsonl_path:    path to the telemetry JSONL file
        batch_size:    number of events per batch (default 100)
        sleep_seconds: pause between batches in seconds (default 1.0)
        db_path:       path to SQLite database

    Yields:
        dict with keys:
            batch_number      — which batch this is (1-indexed)
            events_processed  — total events successfully parsed and inserted so far
            events_skipped    — total events skipped (unknown type / invalid) so far
            total_cost_so_far — cumulative API cost (USD) from api_request events
            last_event_time   — timestamp of the last event in this batch (str)
            is_done           — True only on the final yield after all events consumed
    """
    batch_number      = 0
    total_processed   = 0
    total_skipped     = 0
    total_cost        = 0.0
    last_event_time   = ""

    buffer: dict[str, list[dict]] = defaultdict(list)
    buffer_size = 0

    logger.info(
        "Starting live stream simulation | batch_size=%d | sleep=%.1fs",
        batch_size,
        sleep_seconds,
    )

    for raw_event in iter_events(jsonl_path):
        result = parse_event(raw_event)

        if result is None:
            total_skipped += 1
            continue

        event_type, row = result

        # track cost from api_request events
        if event_type == EVENT_API_REQUEST:
            total_cost += row.get("cost_usd", 0.0)

        # track latest timestamp
        last_event_time = row.get("event_timestamp", last_event_time)

        buffer[event_type].append(row)
        buffer_size += 1
        total_processed += 1

        # --- flush batch when it reaches batch_size ---
        if buffer_size >= batch_size:
            bulk_insert_events(dict(buffer), db_path=db_path)
            batch_number += 1

            status = {
                "batch_number":      batch_number,
                "events_processed":  total_processed,
                "events_skipped":    total_skipped,
                "total_cost_so_far": round(total_cost, 4),
                "last_event_time":   last_event_time,
                "is_done":           False,
            }

            logger.debug(
                "Batch %d | processed: %d | cost: $%.4f | last: %s",
                batch_number,
                total_processed,
                total_cost,
                last_event_time,
            )

            yield status

            # reset buffer
            buffer.clear()
            buffer_size = 0

            # simulate real-time delay
            time.sleep(sleep_seconds)

    # --- flush any remaining events ---
    if buffer_size > 0:
        bulk_insert_events(dict(buffer), db_path=db_path)
        batch_number += 1
        total_processed += buffer_size

    logger.info(
        "Stream simulation complete | batches: %d | events: %d | cost: $%.4f",
        batch_number,
        total_processed,
        total_cost,
    )

    # final status
    yield {
        "batch_number":      batch_number,
        "events_processed":  total_processed,
        "events_skipped":    total_skipped,
        "total_cost_so_far": round(total_cost, 4),
        "last_event_time":   last_event_time,
        "is_done":           True,
    }

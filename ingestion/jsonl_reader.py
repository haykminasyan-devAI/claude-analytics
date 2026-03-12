"""
Ingestion layer: reads the raw JSONL telemetry file line by line.

Each line in the file is a CloudWatch log batch shaped like:
{
    "messageType": "DATA_MESSAGE",
    "logEvents": [
        {
            "id": "...",
            "timestamp": 1234567890000,
            "message": "{\"body\": \"claude_code.api_request\", ...}"
        },
        ...
    ],
    ...
}

This module unwraps those batches and yields individual event dicts
one at a time — memory-efficient regardless of file size.
"""

import json
import logging
from pathlib import Path
from typing import Generator

logger = logging.getLogger(__name__)


def iter_events(jsonl_path: Path) -> Generator[dict, None, None]:
    """
    Lazily iterate over every individual event in the JSONL file.

    Reads one line (one CloudWatch batch) at a time, unwraps the
    logEvents array, and yields each parsed event dict.

    Args:
        jsonl_path: Path to the telemetry_logs.jsonl file.

    Yields:
        dict with keys: body, attributes, scope, resource

    Raises:
        FileNotFoundError: if the file does not exist.
    """
    path = Path(jsonl_path)
    if not path.exists():
        raise FileNotFoundError(f"Telemetry file not found: {path}")

    total_batches  = 0
    total_events   = 0
    skipped_lines  = 0
    skipped_events = 0

    with path.open("r", encoding="utf-8") as fh:
        for line_num, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue

            # --- Step 1: parse the outer CloudWatch batch ---
            try:
                batch = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning("Malformed JSON on line %d — skipping. Error: %s", line_num, exc)
                skipped_lines += 1
                continue

            # only process real data messages
            if batch.get("messageType") != "DATA_MESSAGE":
                continue

            total_batches += 1

            # --- Step 2: iterate over logEvents inside the batch ---
            for entry in batch.get("logEvents", []):
                raw_message = entry.get("message", "")
                if not raw_message:
                    skipped_events += 1
                    continue

                # --- Step 3: parse the inner event (message is a JSON string) ---
                try:
                    event = json.loads(raw_message)
                except json.JSONDecodeError as exc:
                    logger.warning(
                        "Malformed event message in batch at line %d — skipping. Error: %s",
                        line_num,
                        exc,
                    )
                    skipped_events += 1
                    continue

                total_events += 1
                yield event  # hand one event to the caller, then pause

    logger.info(
        "Ingestion finished | batches: %d | events yielded: %d | "
        "skipped lines: %d | skipped events: %d",
        total_batches,
        total_events,
        skipped_lines,
        skipped_events,
    )

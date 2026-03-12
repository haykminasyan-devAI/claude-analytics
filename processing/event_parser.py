"""
Processing layer: validates and flattens raw event dicts into typed rows
ready for insertion into SQLite tables.

Each parse_* function receives the full raw event dict and returns a flat
dict (or None if the event is missing required fields).

The parse_event() dispatcher routes each event to the correct parser
based on the body field.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from config.settings import (
    EVENT_API_ERROR,
    EVENT_API_REQUEST,
    EVENT_TOOL_DECISION,
    EVENT_TOOL_RESULT,
    EVENT_USER_PROMPT,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Type-casting helpers
# ---------------------------------------------------------------------------

def _parse_timestamp(ts_str: str) -> Optional[str]:
    """Convert '2025-12-03T00:06:00.000Z' → '2025-12-03 00:06:00' (UTC string)."""
    if not ts_str:
        return None
    try:
        dt = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc
        )
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _to_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_bool(value) -> int:
    """Store booleans as integers (1/0) for SQLite compatibility."""
    if isinstance(value, bool):
        return int(value)
    return 1 if str(value).lower() in ("true", "1", "yes") else 0


# ---------------------------------------------------------------------------
# Shared fields present in every event type
# ---------------------------------------------------------------------------

def _common_fields(attrs: dict, resource: dict) -> Optional[dict]:
    """
    Extract the fields shared across all event types.
    Returns None if the timestamp is missing (event is invalid).
    """
    ts = _parse_timestamp(attrs.get("event.timestamp", ""))
    if ts is None:
        return None

    return {
        "event_timestamp": ts,
        "session_id":      attrs.get("session.id", ""),
        "user_email":      attrs.get("user.email", ""),
        "user_id":         attrs.get("user.id", ""),
        "organization_id": attrs.get("organization.id", ""),
        "terminal_type":   attrs.get("terminal.type", ""),
        "practice":        resource.get("user.practice", ""),
        "os_type":         resource.get("os.type", ""),
        "host_arch":       resource.get("host.arch", ""),
        "service_version": resource.get("service.version", ""),
    }


# ---------------------------------------------------------------------------
# Per-event-type parsers
# ---------------------------------------------------------------------------

def parse_api_request(event: dict) -> Optional[dict]:
    attrs    = event.get("attributes", {})
    resource = event.get("resource", {})

    row = _common_fields(attrs, resource)
    if row is None:
        return None

    row.update({
        "model":                 attrs.get("model", ""),
        "input_tokens":          _to_int(attrs.get("input_tokens", 0)),
        "output_tokens":         _to_int(attrs.get("output_tokens", 0)),
        "cache_read_tokens":     _to_int(attrs.get("cache_read_tokens", 0)),
        "cache_creation_tokens": _to_int(attrs.get("cache_creation_tokens", 0)),
        "cost_usd":              _to_float(attrs.get("cost_usd", 0.0)),
        "duration_ms":           _to_int(attrs.get("duration_ms", 0)),
    })
    return row


def parse_tool_decision(event: dict) -> Optional[dict]:
    attrs    = event.get("attributes", {})
    resource = event.get("resource", {})

    row = _common_fields(attrs, resource)
    if row is None:
        return None

    row.update({
        "tool_name": attrs.get("tool_name", ""),
        "decision":  attrs.get("decision", ""),
        "source":    attrs.get("source", ""),
    })
    return row


def parse_tool_result(event: dict) -> Optional[dict]:
    attrs    = event.get("attributes", {})
    resource = event.get("resource", {})

    row = _common_fields(attrs, resource)
    if row is None:
        return None

    row.update({
        "tool_name":          attrs.get("tool_name", ""),
        "success":            _to_bool(attrs.get("success", True)),
        "duration_ms":        _to_int(attrs.get("duration_ms", 0)),
        "decision_type":      attrs.get("decision_type", ""),
        "decision_source":    attrs.get("decision_source", ""),
        "result_size_bytes":  _to_int(attrs.get("tool_result_size_bytes", 0)),
    })
    return row


def parse_user_prompt(event: dict) -> Optional[dict]:
    attrs    = event.get("attributes", {})
    resource = event.get("resource", {})

    row = _common_fields(attrs, resource)
    if row is None:
        return None

    row.update({
        "prompt_length": _to_int(attrs.get("prompt_length", 0)),
    })
    return row


def parse_api_error(event: dict) -> Optional[dict]:
    attrs    = event.get("attributes", {})
    resource = event.get("resource", {})

    row = _common_fields(attrs, resource)
    if row is None:
        return None

    row.update({
        "model":       attrs.get("model", ""),
        "error":       attrs.get("error", ""),
        "status_code": attrs.get("status_code", ""),
        "attempt":     _to_int(attrs.get("attempt", 1)),
        "duration_ms": _to_int(attrs.get("duration_ms", 0)),
    })
    return row


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_PARSERS = {
    EVENT_API_REQUEST:   parse_api_request,
    EVENT_TOOL_DECISION: parse_tool_decision,
    EVENT_TOOL_RESULT:   parse_tool_result,
    EVENT_USER_PROMPT:   parse_user_prompt,
    EVENT_API_ERROR:     parse_api_error,
}


def parse_event(event: dict) -> Optional[tuple[str, dict]]:
    """
    Dispatch a raw event to the correct parser based on its body field.

    Returns:
        (event_type_string, flat_row_dict)  — if parsing succeeds
        None                                — if unknown type or invalid data
    """
    body = event.get("body", "")
    parser = _PARSERS.get(body)

    if parser is None:
        logger.debug("Unknown event body '%s' — skipped", body)
        return None

    row = parser(event)
    if row is None:
        logger.debug("Parser returned None for body '%s' — skipped", body)
        return None

    return body, row

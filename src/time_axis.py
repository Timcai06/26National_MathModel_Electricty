"""Explicit time-label interpretations; no Excel I/O or implicit date shift."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import re
from zoneinfo import ZoneInfo


SLOTS_PER_DAY = 144
SLOT_MINUTES = 10
LOCAL_ZONE = ZoneInfo("Asia/Shanghai")


def minute_offset(value):
    """Parse a clock label including explicit next-day markers. Reject guesses."""
    if isinstance(value, time):
        if value.second or value.microsecond or value.tzinfo is not None:
            raise ValueError(f"Unsupported time: {value!r}")
        return value.hour * 60 + value.minute
    if not isinstance(value, str):
        raise ValueError(f"Expected time or explicit clock string: {value!r}")
    match = re.fullmatch(r"(\d{1,2}):(\d{1,2})(?::00)?(?:\+(\d+))?", value)
    if match is None:
        raise ValueError(f"Invalid clock label: {value!r}")
    hour, minute, extra_days = map(int, (match[1], match[2], match[3] or "0"))
    if minute >= 60 or hour > 24 or (hour == 24 and (minute or extra_days)):
        raise ValueError(f"Invalid clock label: {value!r}")
    return extra_days * 1440 + hour * 60 + minute


@dataclass(frozen=True)
class Slot:
    slot_id: int
    input_label: str
    start: datetime
    end: datetime


def build_day_slots(day, input_labels, *, semantics):
    """Require the caller to choose interval_end or interval_start explicitly.

    Source labels must be the ordered 00:10..24:00 sequence. The start-label
    interpretation intentionally exposes a 00:10..next-day 00:10 horizon.
    """
    if not isinstance(day, date) or isinstance(day, datetime):
        raise ValueError("day must be a date, not a datetime")
    if semantics not in {"interval_end", "interval_start"}:
        raise ValueError("An explicit supported semantics is required")
    offsets = [minute_offset(value) for value in input_labels]
    expected = list(range(SLOT_MINUTES, 1441, SLOT_MINUTES))
    if offsets != expected:
        raise ValueError("Expected exactly 144 ordered labels from 00:10 to 24:00")
    midnight = datetime.combine(day, time.min, LOCAL_ZONE)
    shift = SLOT_MINUTES if semantics == "interval_end" else 0
    return tuple(
        Slot(
            slot_id=i,
            input_label=str(input_labels[i]),
            start=midnight + timedelta(minutes=offset - shift),
            end=midnight + timedelta(minutes=offset - shift + SLOT_MINUTES),
        )
        for i, offset in enumerate(offsets)
    )


def future_slot_ids(slots, decision_time):
    """Only whole, not-yet-started slots are eligible for a plan update."""
    if decision_time.tzinfo is None or decision_time.utcoffset() is None:
        raise ValueError("decision_time must include a timezone")
    return tuple(slot.slot_id for slot in slots if slot.start >= decision_time)


# The time semantics were frozen after the official templates were shown to
# contradict themselves; see docs/data/TIME_SEMANTICS.md for the evidence chain.
# This records ONLY the time contract. Observation policy, the Q3 refund reading
# and the Q4 price-knowability assumption remain unaccepted and are tracked by
# the separate, still-false semantic_acceptance flag.
TIME_SEMANTICS = {
    "version": "interval-end-v1",
    "accepted": True,
    "accepted_by": "tim",
    "accepted_on": "2026-09-12",
    "record": "docs/data/TIME_SEMANTICS.md",
    "evidence": "analysis/time_semantics_v1/",
    "still_open": ["observation_policy", "q3_refund_interpretation", "q4_price_knowability"],
}


def time_semantics_attestation():
    """Return the frozen time contract for embedding in a result payload."""
    return dict(TIME_SEMANTICS)

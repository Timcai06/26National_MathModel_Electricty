import unittest
from pathlib import Path
from datetime import date, datetime, time, timedelta

from src.time_axis import LOCAL_ZONE, build_day_slots, future_slot_ids, minute_offset, time_semantics_attestation


def labels():
    return [time(m // 60, m % 60) for m in range(10, 1440, 10)] + ["0:00+1"]


class TimeAxisTests(unittest.TestCase):
    def setUp(self):
        self.day = date(2025, 12, 31)
        self.slots = build_day_slots(self.day, labels(), semantics="interval_end")

    def test_clock_types_and_explicit_day_marker(self):
        for value, expected in [(time(0, 10), 10), ("6:00", 360),
                                ("00:10:00", 10), ("7:0", 420), ("24:00", 1440),
                                ("0:00+1", 1440), ("0:10+1", 1450)]:
            with self.subTest(value=value):
                self.assertEqual(minute_offset(value), expected)

    def test_reject_ambiguous_or_invalid_clock(self):
        for value in [None, "", 0.5, "24:10", "25:00", "6:60", "24:00+1",
                      "00:10:01", time(0, 10, 1), "0:10-0:20"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                minute_offset(value)

    def test_full_civil_day_and_year_boundary(self):
        self.assertEqual(len(self.slots), 144)
        self.assertEqual(self.slots[0].start, datetime(2025, 12, 31, tzinfo=LOCAL_ZONE))
        self.assertEqual(self.slots[-1].end, datetime(2026, 1, 1, tzinfo=LOCAL_ZONE))
        for left, right in zip(self.slots, self.slots[1:]):
            self.assertEqual(left.end, right.start)
        self.assertTrue(all(s.end - s.start == timedelta(minutes=10) for s in self.slots))

    def test_paper_and_four_hour_group_anchors(self):
        self.assertEqual(self.slots[60].start.hour, 10)
        self.assertEqual(self.slots[60].start.minute, 0)
        self.assertEqual(self.slots[60].end.minute, 10)
        for group in range(6):
            self.assertEqual(self.slots[group * 24].start.hour, group * 4)
        boundaries = [s.start for s in self.slots] + [self.slots[-1].end]
        self.assertEqual(len(set(boundaries)), 145)

    def test_rolling_updates_lock_started_slots(self):
        for hour, first in [(0, 0), (6, 36), (12, 72), (18, 108)]:
            decision = datetime(2025, 12, 31, hour, tzinfo=LOCAL_ZONE)
            ids = future_slot_ids(self.slots, decision)
            self.assertEqual(ids[0], first)
            self.assertEqual(len(ids), 144 - first)
        self.assertEqual(future_slot_ids(self.slots, self.slots[-1].end), ())
        midway = datetime(2025, 12, 31, 6, 5, tzinfo=LOCAL_ZONE)
        self.assertEqual(future_slot_ids(self.slots, midway)[0], 37)
        with self.assertRaises(ValueError):
            future_slot_ids(self.slots, datetime(2025, 12, 31, 6))

    def test_start_interpretation_exposes_shift_without_wrapping(self):
        alternative = build_day_slots(self.day, labels(), semantics="interval_start")
        self.assertEqual(alternative[0].start.minute, 10)
        self.assertEqual(alternative[-1].end, datetime(2026, 1, 1, 0, 10, tzinfo=LOCAL_ZONE))

    def test_reject_missing_duplicate_reordered_and_zero_last_label(self):
        original = labels()
        for invalid in [original[:-1], original + ["0:10+1"],
                        [original[1], original[0]] + original[2:],
                        [original[0]] + original[:-1], original[:-1] + [time(0)]]:
            with self.subTest(size=len(invalid)), self.assertRaises(ValueError):
                build_day_slots(self.day, invalid, semantics="interval_end")

    def test_semantics_must_be_explicit(self):
        with self.assertRaises(TypeError):
            build_day_slots(self.day, labels())
        with self.assertRaises(ValueError):
            build_day_slots(self.day, labels(), semantics="auto")

    def test_frozen_time_contract_is_recorded_and_scoped(self):
        """The time contract is accepted; the broader semantics are not."""
        attestation = time_semantics_attestation()
        self.assertEqual(attestation["version"], "interval-end-v1")
        self.assertTrue(attestation["accepted"])
        self.assertTrue(Path(attestation["record"]).exists())
        for pending in ("observation_policy", "q3_refund_interpretation", "q4_price_knowability"):
            self.assertIn(pending, attestation["still_open"])
        attestation["version"] = "tampered"
        self.assertEqual(time_semantics_attestation()["version"], "interval-end-v1")


if __name__ == "__main__":
    unittest.main()

from datetime import date, timedelta
import unittest

from scripts.run_real_q2_forecast import load_rows, parse_days
from src.q2.forecast import history_as_of, midnight, predict_day


class RealForecastInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, _, _ = load_rows()

    def test_annual_coverage_and_midnight_availability_boundary(self):
        days = parse_days(self.rows, delay_minutes=0)
        self.assertEqual(len(days), 365)
        self.assertEqual(days[-1].day, date(2025, 12, 31))
        target = date(2025, 1, 8)
        history = history_as_of(days, midnight(target))
        self.assertEqual(len(history), 7)
        forecast = predict_day(history, target_day=target, method='yesterday')
        self.assertEqual(forecast.status, 'ready')
        self.assertEqual(forecast.source_available_at, midnight(target))

    def test_delayed_real_data_blocks_yesterday_without_fallback(self):
        days = parse_days(self.rows, delay_minutes=10)
        target = date(2025, 1, 8)
        history = history_as_of(days, midnight(target))
        self.assertEqual(predict_day(history, target_day=target, method='yesterday').status,
                         'insufficient_history')
        self.assertEqual(predict_day(history, target_day=target, method='last_week').status, 'ready')
        self.assertEqual(days[6].available_at, midnight(target)+timedelta(minutes=10))

    def test_reject_missing_or_reordered_real_rows(self):
        with self.assertRaises(ValueError):
            parse_days(self.rows[:-1], delay_minutes=0)
        rows = self.rows.copy()
        rows[0], rows[1] = rows[1], rows[0]
        with self.assertRaises(ValueError):
            parse_days(rows, delay_minutes=0)

    def test_reject_units_nonfinite_and_bad_endpoint_without_cleaning(self):
        for key, value in [('load_kwh', '1'), ('pv_actual_kw', 'nan'), ('time_str', '00:00:00')]:
            rows = self.rows.copy()
            rows[0] = dict(rows[0], **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                parse_days(rows, delay_minutes=0)

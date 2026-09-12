from datetime import date, timedelta
import unittest
import numpy as np

from src.core import BatteryParams
from src.q2.forecast import ActualDay, history_as_of, midnight, predict_day
from src.q2.backtest import walk_forward
from src.q2.dispatch import plan_from_forecast

META = dict(input_kind='synthetic',data_version='test',mapping_version='test',assumptions_version='test')


def day_record(day, value, delay=0):
    return ActualDay(day, np.full(144,value), np.full(144,value/2),
                     midnight(day)+timedelta(days=1,minutes=delay))


class CausalForecastTests(unittest.TestCase):
    def setUp(self):
        self.start = date(2025,12,25)
        self.days = [day_record(self.start+timedelta(days=i), i+1) for i in range(12)]
        self.target = self.start+timedelta(days=7)

    def test_exact_calendar_lags_across_year(self):
        history = history_as_of(self.days,midnight(self.target))
        for method,value in [('yesterday',7),('last_week',1)]:
            forecast = predict_day(history,target_day=self.target,method=method)
            np.testing.assert_array_equal(forecast.load_kwh,np.full(144,value))
            self.assertEqual(forecast.issue_time.year,2026)

    def test_future_and_target_actual_changes_do_not_change_prediction(self):
        changed = [d if d.day < self.target else day_record(d.day,999999) for d in self.days]
        for method in ['yesterday','last_week']:
            a = predict_day(history_as_of(self.days,midnight(self.target)),target_day=self.target,method=method)
            b = predict_day(history_as_of(changed,midnight(self.target)),target_day=self.target,method=method)
            np.testing.assert_array_equal(a.load_kwh,b.load_kwh)

    def test_future_history_is_rejected_by_predictor(self):
        with self.assertRaises(ValueError): predict_day(self.days,target_day=self.target,method='yesterday')

    def test_publication_at_cutoff_allowed_after_cutoff_excluded(self):
        source = self.target-timedelta(days=1)
        for delay,status in [(0,'ready'),(1,'insufficient_history')]:
            history = history_as_of([day_record(source,10,delay)],midnight(self.target))
            self.assertEqual(predict_day(history,target_day=self.target,method='yesterday').status,status)

    def test_missing_calendar_day_does_not_use_previous_row(self):
        history = history_as_of(self.days,midnight(self.target))[:-1]
        forecast = predict_day(history,target_day=self.target,method='yesterday')
        self.assertEqual(forecast.status,'insufficient_history')
        self.assertIsNone(forecast.load_kwh)

    def test_invalid_actuals_and_dates_are_rejected(self):
        with self.assertRaises(ValueError): ActualDay(self.start,[1]*143,[1]*144,midnight(self.start)+timedelta(days=1))
        with self.assertRaises(ValueError): ActualDay(self.start,[-1]*144,[1]*144,midnight(self.start)+timedelta(days=1))
        with self.assertRaises(ValueError): ActualDay(self.start,[1]*144,[1]*144,midnight(self.start))
        with self.assertRaises(ValueError): history_as_of(self.days[::-1],midnight(self.target))
        with self.assertRaises(ValueError): history_as_of([self.days[0],self.days[0]],midnight(self.target))
        with self.assertRaises(ValueError): history_as_of(self.days,midnight(self.target).replace(tzinfo=None))

    def test_copies_do_not_share_caller_arrays(self):
        load = np.ones(144)
        actual = ActualDay(self.start,load,load,midnight(self.start)+timedelta(days=1))
        load[:] = 999
        self.assertEqual(actual.load_kwh[0],1)
        forecast = predict_day([actual],target_day=self.start+timedelta(days=1),method='yesterday')
        self.assertFalse(np.shares_memory(forecast.load_kwh,actual.load_kwh))
        self.assertFalse(forecast.load_kwh.flags.writeable)

    def test_metrics_equal_hand_calculation(self):
        report = walk_forward(self.days,start_day=self.target,end_day=self.target+timedelta(days=1),metadata=META)
        self.assertEqual(report['status'],'complete')
        for method,error in [('yesterday',1),('last_week',7)]:
            self.assertEqual(report['summary'][method]['scored_days'],2)
            self.assertEqual(report['summary'][method]['load']['mae_kwh_per_slot'],error)
            self.assertEqual(report['summary'][method]['load']['rmse_kwh_per_slot'],error)

    def test_backtest_truth_changes_scores_not_forecasts(self):
        changed = [d if d.day < self.target else day_record(d.day,1000) for d in self.days]
        a = walk_forward(self.days,start_day=self.target,end_day=self.target,metadata=META)
        b = walk_forward(changed,start_day=self.target,end_day=self.target,metadata=META)
        for old,new in zip(a['rows'],b['rows']):
            self.assertEqual(old['load_forecast_kwh'],new['load_forecast_kwh'])
            self.assertNotEqual(old['load_metrics'],new['load_metrics'])

    def test_partial_and_missing_truth_are_explicit(self):
        report = walk_forward(self.days,start_day=self.start,end_day=self.start,metadata=META)
        self.assertEqual(report['status'],'partial')
        self.assertIsNone(report['summary']['yesterday']['load'])
        with self.assertRaises(ValueError):
            walk_forward(self.days,start_day=self.start-timedelta(days=1),end_day=self.start,metadata=META)

    def test_forecast_to_planning_and_unavailable_price(self):
        f = predict_day(history_as_of(self.days,midnight(self.target)),target_day=self.target,method='yesterday')
        args = dict(price_yuan_per_kwh=np.ones(144),price_available_at=f.issue_time,
                    battery_params=BatteryParams(.9,.9,'bus'),initial_energy_kwh=6000,terminal_energy_kwh=6000)
        result = plan_from_forecast(f,**args)
        self.assertEqual(result.status,'optimal')
        self.assertTrue(result.diagnostics['passed'])
        self.assertAlmostEqual(result.objective_yuan,144*3.5)
        args['price_available_at'] += timedelta(seconds=1)
        with self.assertRaises(ValueError): plan_from_forecast(f,**args)

    def test_missing_forecast_cannot_be_planned(self):
        f = predict_day([],target_day=self.target,method='yesterday')
        with self.assertRaises(ValueError):
            plan_from_forecast(f,price_yuan_per_kwh=np.ones(144),price_available_at=f.issue_time,
                              battery_params=BatteryParams(.9,.9,'bus'),initial_energy_kwh=6000,terminal_energy_kwh=6000)

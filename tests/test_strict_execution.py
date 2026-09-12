import unittest
from datetime import date, timedelta
from dataclasses import FrozenInstanceError
import numpy as np
from src.core.model import BatteryParams
from src.q2.forecast import midnight
from src.q2.strict_execution import StrictExecutor


class StrictExecutionTests(unittest.TestCase):
    def make(self, mode='B0', **overrides):
        values = dict(day=date(2025, 2, 1), commitment=np.full(144, 120.), price=np.full(144, .5),
            forecast_load=np.full(144, 120.), forecast_pv=np.zeros(144),
            forecast_available_at=midnight(date(2025, 2, 1)), battery=BatteryParams(.9, .9, 'bus'), mode=mode)
        values.update(overrides)
        return StrictExecutor(**values)

    def replay(self, mode, actual):
        c = self.make(mode, forecast_load=120.+100.*np.sin(np.arange(144)*2*np.pi/144))
        for i in range(144):
            c.decide(c.start+timedelta(minutes=10*i))
            c.settle(load_kwh=float(actual[i]), pv_kwh=0., available_at=c.start+timedelta(minutes=10*(i+1)))
        return c.finish()

    def test_current_and_future_actual_cannot_change_commands(self):
        for mode in ('B0', 'B1'):
            base = np.full(144, 120.)
            changed = base.copy()
            changed[20:] = np.linspace(0, 2000, 124)
            a, b = self.replay(mode, base), self.replay(mode, changed)
            # With frozen forecasts and fixed commands, even subsequent SOC is
            # unchanged by net-load actuals. Only emergency/surplus may change.
            self.assertEqual(a['commands'], b['commands'])
            self.assertGreater(sum(a['schedule']['C']), 0.)
            self.assertGreater(sum(a['schedule']['D']), 0.)
            np.testing.assert_array_equal(a['schedule']['E'], b['schedule']['E'])
            self.assertGreater(b['costs']['emergency_yuan'], a['costs']['emergency_yuan'])
            self.assertAlmostEqual(b['costs']['emergency_yuan'], .5*5*sum(b['schedule']['U']))
            self.assertEqual(len(b['solves']), 24 if mode == 'B1' else 0)

    def test_settlement_requires_prior_command(self):
        c = self.make()
        with self.assertRaises(ValueError):
            c.settle(load_kwh=120, pv_kwh=0, available_at=c.start+timedelta(minutes=10))
        command = c.decide(c.start)
        with self.assertRaises(FrozenInstanceError):
            command.C = 1
        with self.assertRaises(ValueError):
            c.decide(c.start)
        with self.assertRaises(ValueError):
            c.settle(load_kwh=120, pv_kwh=0, available_at=c.start)
        c.settle(load_kwh=120, pv_kwh=0, available_at=c.start+timedelta(minutes=10))
        with self.assertRaises(ValueError):
            c.finish()

    def test_forecast_must_be_published(self):
        with self.assertRaises(ValueError):
            self.make(forecast_available_at=midnight(date(2025, 2, 1))+timedelta(minutes=1))
        with self.assertRaises(ValueError):
            self.make(mode='legacy')

    def test_terminal_recovery_and_power_limits(self):
        for mode in ('B0', 'B1'):
            c = self.make(mode, commitment=np.zeros(144), forecast_load=np.full(144, 1000.))
            for i in range(144):
                c.decide(c.start+timedelta(minutes=10*i))
                c.settle(load_kwh=1000., pv_kwh=0., available_at=c.start+timedelta(minutes=10*(i+1)))
            row = c.finish()
            self.assertAlmostEqual(row['schedule']['E'][-1], 6000.)
            self.assertTrue(row['diagnostics']['passed'])
            self.assertGreater(row['costs']['emergency_yuan'], 0.)


if __name__ == '__main__':
    unittest.main()

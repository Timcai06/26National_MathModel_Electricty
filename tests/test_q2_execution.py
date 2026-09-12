from datetime import date,timedelta
import unittest
import numpy as np

from src.core import BatteryParams
from src.q2.forecast import midnight
from src.q2.execution import CausalExecutor,OBSERVATION_POLICY


def executor(**overrides):
    args = dict(day=date(2026,2,1),commitment_kwh=np.zeros(144),price_yuan_per_kwh=np.ones(144),
        price_available_at=midnight(date(2026,2,1)),battery_params=BatteryParams(.9,.9,'bus'),
        initial_energy_kwh=6000,terminal_energy_kwh=None,emergency_multiplier=5,
        observation_policy=OBSERVATION_POLICY)
    args.update(overrides)
    return CausalExecutor(**args)


def step(e,i,load=0,pv=0):
    return e.step(slot_id=i,load_kwh=load,pv_kwh=pv,
                  available_at=midnight(e.day)+timedelta(minutes=10*(i+1)))


class ExecutionTests(unittest.TestCase):
    def test_hand_settlement_without_storage(self):
        e = executor(commitment_kwh=np.full(144,10),battery_params=BatteryParams(.9,.9,'bus',max_charge_kw=0,max_discharge_kw=0))
        for i in range(144): step(e,i,load=12)
        r=e.finish()
        self.assertEqual(r['costs'],{'normal_purchase_yuan':1440,'emergency_purchase_yuan':1440,'total_yuan':2880})
        self.assertEqual(r['status'],'validated')

    def test_surplus_has_no_sale_credit_and_commitment_stays_paid(self):
        e=executor(commitment_kwh=np.full(144,10),initial_energy_kwh=10800)
        for i in range(144): step(e,i)
        r=e.finish()
        self.assertEqual(sum(r['schedule']['W']),1440)
        self.assertEqual(r['costs']['total_yuan'],1440)

    def test_battery_loss_and_no_simultaneous_actions(self):
        e=executor()
        a=step(e,0,pv=100)
        b=step(e,1,load=81)
        self.assertAlmostEqual(a.C,100)
        self.assertAlmostEqual(b.D,81)
        self.assertAlmostEqual(e.energy_kwh,6000)
        self.assertEqual(a.D+b.C,0)

    def test_future_suffix_cannot_change_prefix(self):
        a,b=executor(),executor()
        for i in range(144):
            step(a,i,load=10)
            step(b,i,load=10 if i<72 else 10000)
        self.assertEqual(a.records[:72],b.records[:72])
        self.assertNotEqual(a.records[-1],b.records[-1])

    def test_terminal_restoration_is_real_charging(self):
        e=executor(terminal_energy_kwh=6000)
        for i in range(144): step(e,i,load=100)
        r=e.finish()
        self.assertEqual(r['status'],'validated')
        self.assertAlmostEqual(e.energy_kwh,6000)
        self.assertGreater(sum(r['schedule']['C']),0)
        self.assertGreater(r['costs']['emergency_purchase_yuan'],14400*5)
        for a,b in zip(e.records,e.records[1:]):
            self.assertEqual(a.terminal_energy_kwh,b.initial_energy_kwh)

    def test_cross_day_state_is_carried_explicitly(self):
        a=executor()
        for i in range(144):step(a,i,load=5)
        nextday=a.day+timedelta(days=1)
        b=executor(day=nextday,price_available_at=midnight(nextday),initial_energy_kwh=a.energy_kwh)
        self.assertEqual(step(b,0).initial_energy_kwh,a.records[-1].terminal_energy_kwh)
        self.assertNotEqual(b.energy_kwh,6000)

    def test_bad_slot_or_observation_does_not_advance_state(self):
        e=executor()
        for i,value,time in [(1,0,10),(0,float('nan'),10),(0,1,11),(0,1,0)]:
            with self.assertRaises(ValueError):
                e.step(slot_id=i,load_kwh=value,pv_kwh=0,available_at=midnight(e.day)+timedelta(minutes=time))
            self.assertEqual(e.records,())
            self.assertEqual(e.energy_kwh,6000)
        step(e,0)
        with self.assertRaises(ValueError):step(e,0)
        with self.assertRaises(ValueError):e.finish()

    def test_seeded_days_obey_power_bounds_and_physics(self):
        for side in ['bus','battery']:
            for target in [None,6000]:
                rng=np.random.default_rng(17)
                e=executor(commitment_kwh=rng.uniform(0,300,144),battery_params=BatteryParams(.9,.9,side),terminal_energy_kwh=target)
                for i in range(144):step(e,i,load=float(rng.uniform(0,1500)),pv=float(rng.uniform(0,1500)))
                self.assertEqual(e.finish()['status'],'validated')

    def test_inputs_are_copied_and_invalid_policy_rejected(self):
        g=np.ones(144)
        e=executor(commitment_kwh=g)
        g[:]=999
        self.assertEqual(step(e,0).G,1)
        with self.assertRaises(ValueError):executor(observation_policy='assumed')
        with self.assertRaises(ValueError):executor(emergency_multiplier=float('nan'))
        with self.assertRaises(ValueError):executor(terminal_energy_kwh=10800,battery_params=BatteryParams(.9,.9,'bus',max_charge_kw=0))

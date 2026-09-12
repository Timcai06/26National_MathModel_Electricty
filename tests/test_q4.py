import unittest
from datetime import date
import numpy as np
from scripts.run_real_q4 import PRICE_POLICY, parse_prices
from scripts.run_real_q23 import audited_csv
from src.q3.planning import adjustment_cost
from src.q2.forecast import midnight
from scripts.deliver_real_q23 import Q4_SPEC, DEFAULT_SPEC, verify


class DynamicPriceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, _ = audited_csv('data/processed/team_delivery/dynamic_price.csv')

    def test_complete_year_and_explicit_known_price_candidate(self):
        prices = parse_prices(self.rows,policy=PRICE_POLICY)
        self.assertEqual(len(prices),365)
        self.assertEqual(prices[31].day,date(2025,2,1))
        self.assertEqual(prices[31].available_at,midnight(date(2025,2,1)))
        self.assertEqual(prices[-1].day,date(2025,12,31))
        self.assertFalse(prices[0].price_yuan_per_kwh.flags.writeable)
        self.assertNotEqual(prices[0].price_yuan_per_kwh.tolist(),prices[1].price_yuan_per_kwh.tolist())

    def test_reject_unstated_or_realtime_only_information(self):
        for policy in ('','real_time_only'):
            with self.assertRaises(ValueError):parse_prices(self.rows,policy=policy)

    def test_reject_missing_shuffled_and_nonfinite_prices(self):
        with self.assertRaises(ValueError):parse_prices(self.rows[:-1],policy=PRICE_POLICY)
        rows = self.rows.copy();rows[0],rows[1] = rows[1],rows[0]
        with self.assertRaises(ValueError):parse_prices(rows,policy=PRICE_POLICY)
        for field,value in [('price','nan'),('price','-1'),('time_str','00:00:00')]:
            rows = self.rows.copy();rows[0] = dict(rows[0],**{field:value})
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):parse_prices(rows,policy=PRICE_POLICY)

    def test_dynamic_contract_uses_each_target_slot_price(self):
        old, new, price = [100,100],[80,120],[.2,1.4]
        # Refund 20 kWh at the first slot, buy 20 more at the second.
        cost = adjustment_cost(old,new,price)
        self.assertAlmostEqual(cost,-.5*.2*20+1.5*1.4*20)
        self.assertAlmostEqual(np.dot(old,price)+cost,
            np.dot(new,price)+.5*np.dot(np.abs(np.array(new)-old),price))

    def test_q4_2_saved_workbook_and_isolated_paths(self):
        self.assertNotEqual(Q4_SPEC.out,DEFAULT_SPEC.out)
        result = verify(2,spec=Q4_SPEC)
        self.assertEqual(result['numeric_cells_verified'],54404)
        self.assertTrue(result['template_styles_preserved'])
        self.assertFalse(result['semantic_acceptance'])

    def test_q4_3_saved_workbook_and_isolated_paths(self):
        self.assertEqual(Q4_SPEC.stem(3),'q4_3')
        result = verify(3,spec=Q4_SPEC)
        self.assertEqual(result['numeric_cells_verified'],102959)
        self.assertTrue(result['template_styles_preserved'])
        self.assertFalse(result['semantic_acceptance'])

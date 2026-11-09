import unittest
from datetime import date
from decimal import Decimal
from mall.pricing import trial_end, commission
class PricingTests(unittest.TestCase):
    def test_three_calendar_months(self):
        self.assertEqual(trial_end(date(2026,11,6)),date(2027,2,6))
    def test_month_end(self):
        self.assertEqual(trial_end(date(2026,11,30)),date(2027,2,28))
    def test_leap_year(self):
        self.assertEqual(trial_end(date(2023,11,30)),date(2024,2,29))
    def test_trial_is_free(self):
        self.assertEqual(commission(Decimal('200'),Decimal('.03'),date(2026,11,6),date(2027,2,5)),Decimal('0.00'))
    def test_anniversary_is_chargeable(self):
        self.assertEqual(commission(Decimal('200'),Decimal('.03'),date(2026,11,6),date(2027,2,6)),Decimal('6.00'))
    def test_half_up_rounding(self):
        self.assertEqual(commission(Decimal('1.50'),Decimal('.03'),date(2026,1,1),date(2026,6,1)),Decimal('.05'))
    def test_negative_sale_rejected(self):
        with self.assertRaises(ValueError):commission(Decimal('-1'),Decimal('.03'),date(2026,1,1),date(2026,6,1))
    def test_invalid_rate_rejected(self):
        with self.assertRaises(ValueError):commission(Decimal('1'),Decimal('1.01'),date(2026,1,1),date(2026,6,1))
if __name__=='__main__':unittest.main()

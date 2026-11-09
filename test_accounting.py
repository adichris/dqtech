import unittest
from mall.accounting import validate_entries
class AccountingTests(unittest.TestCase):
    def test_balanced_receipt(self):self.assertEqual(len(validate_entries([('cash',100,0),('sales',0,100)])),2)
    def test_unbalanced_rejected(self):
        with self.assertRaises(ValueError):validate_entries([('cash',100,0),('sales',0,99)])
    def test_negative_rejected(self):
        with self.assertRaises(ValueError):validate_entries([('cash',-100,0),('sales',0,-100)])
    def test_zero_rejected(self):
        with self.assertRaises(ValueError):validate_entries([('cash',0,0),('sales',0,0)])
    def test_double_sided_rejected(self):
        with self.assertRaises(ValueError):validate_entries([('cash',100,100)])
    def test_fractional_cent_rejected(self):
        with self.assertRaises(ValueError):validate_entries([('cash','1.001',0),('sales',0,'1.001')])
if __name__=='__main__':unittest.main()

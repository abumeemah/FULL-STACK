import unittest

from ficore_mobile_backend.utils import payment_utils as pu


class TestPaymentUtils(unittest.TestCase):
    def test_normalize_payment_method(self):
        self.assertEqual(pu.normalize_payment_method('Cash'), 'cash')
        self.assertEqual(pu.normalize_payment_method('CREDIT_card'), 'card')
        self.assertEqual(pu.normalize_payment_method('momo'), 'mobile_money')
        self.assertIsNone(pu.normalize_payment_method(None))
        self.assertFalse(pu.validate_payment_method('unknown_method'))

    def test_sales_type(self):
        self.assertEqual(pu.normalize_sales_type('CASH'), 'cash')
        self.assertTrue(pu.validate_sales_type('credit'))
        self.assertIsNone(pu.normalize_sales_type(None))
        self.assertFalse(pu.validate_sales_type('notatype'))


if __name__ == '__main__':
    unittest.main()

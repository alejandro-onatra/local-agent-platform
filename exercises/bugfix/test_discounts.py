from decimal import Decimal
import unittest
from discounts import discounted_total


class DiscountTests(unittest.TestCase):
    def test_no_discount(self):
        self.assertEqual(discounted_total(Decimal("12.50"), Decimal("0")), Decimal("12.50"))

    def test_ten_percent(self):
        self.assertEqual(discounted_total(Decimal("100"), Decimal("10")), Decimal("90.00"))

    def test_quarter_discount(self):
        self.assertEqual(discounted_total(Decimal("80"), Decimal("25")), Decimal("60.00"))

    def test_full_discount(self):
        self.assertEqual(discounted_total(Decimal("19.99"), Decimal("100")), Decimal("0.00"))

    def test_invalid_inputs(self):
        for subtotal, rate in (("-1", "10"), ("100", "-1"), ("100", "101")):
            with self.subTest(subtotal=subtotal, rate=rate):
                with self.assertRaises(ValueError):
                    discounted_total(Decimal(subtotal), Decimal(rate))


if __name__ == "__main__":
    unittest.main()

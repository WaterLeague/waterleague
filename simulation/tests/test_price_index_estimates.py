"""공식 지수 환산의 유리수 대조와 가격 시점 가정 보존 검사."""
import importlib.util
import json
from pathlib import Path
from fractions import Fraction
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('price_estimates', ROOT/'scripts/build_game_price_estimates.py')
prices = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prices)


class PriceIndexEstimateTests(unittest.TestCase):
    def test_public_inputs_match_exact_fraction_and_preserve_scope(self):
        result = prices.build()
        self.assertEqual(result, json.loads(prices.OUTPUT.read_text()))
        original = json.loads(prices.BASE.read_text())['facilities']
        self.assertEqual(set(result['facilities']), {'RAIN_GARDEN', 'BIORETENTION',
            'VEGETATIVE_SWALE', 'PERMEABLE_PAVEMENT'})
        self.assertEqual(set(result['facilities']) | set(result['notAdjusted']), set(original))
        for kind, row in result['facilities'].items():
            a = row['priceAdjustment']
            monthly = [Fraction(str(c['value'])) for c in a['baseMonthlyIndices']]
            current = Fraction(str(a['targetIndex']['value']))
            unit = original[kind]['unitCost']
            rational = unit * current * 12 / sum(monthly)
            ceil = lambda value: -(-value.numerator // value.denominator)
            self.assertEqual(row['unitCost'], ceil(rational))
            sensitivity = [ceil(unit * current / value) for value in monthly]
            self.assertEqual(a['baseMonthSensitivityKrwPerM2'], [min(sensitivity), max(sensitivity)])
            self.assertIsNone(a['observedBasePriceYear'])
            self.assertEqual(a['assumedBasePriceYear'], 2022)
            self.assertTrue(a['targetProvisional'])
            self.assertEqual(a['originalUnitCostKrw'], unit)
            for field in ('includes', 'excludes', 'sourceUrl', 'sourceSha256', 'referenceYear', 'scope'):
                self.assertEqual(row[field], original[kind][field])

    def test_one_final_rounding_and_exact_integer_boundary(self):
        self.assertEqual(prices.estimate(100, [120] * 12, 132), (110, [110, 110]))
        self.assertEqual(prices.estimate(1, [100] * 12, 100.01), (2, [2, 2]))
        self.assertEqual(prices.estimate(100, [132] * 12, 120), (91, [91, 91]))

    def test_missing_nonpositive_and_nonfinite_index_rejected(self):
        for months in ([100] * 11, [100] * 13, [100] * 11 + [0],
                       [100] * 11 + [-1], [100] * 11 + ['NaN'], [100] * 11 + ['Infinity']):
            with self.assertRaises(ValueError):
                prices.estimate(100, months, 132)
        for unit, target in [(0, 132), (-1, 132), (1, 0), (1, 'NaN')]:
            with self.assertRaises(ValueError):
                prices.estimate(unit, [100] * 12, target)


if __name__ == '__main__':
    unittest.main()

import copy
from decimal import Decimal
import json
import os
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.reference.epa import (
    MANIFEST, ROOT, ReferenceValidationError, compare_published, compare_units,
    execute_case, read_sources, report_depths, transform_input,
)


class ReferenceComparisonTests(unittest.TestCase):
    def test_print_precision_and_source_conflict_are_not_promoted(self):
        case = {'published': {'runoffIn': '0.22', 'peakCfs': '4.14'},
                'sourceConflicts': {'runoffIn': {'value': '0.24'}}}
        result = {'depthsIn': {'runoffIn': 0.22}, 'peakM3s': 99, 'outletComparison': {'outletPeakM3s': 4.14 * 0.3048 ** 3}}
        checks = compare_published(case, result)
        self.assertEqual(checks[0]['status'], 'SOURCE_CONFLICT')
        self.assertEqual(checks[0]['conflictingSource']['value'], '0.24')
        self.assertEqual(checks[1]['status'], 'WITHIN_PRINT_PRECISION')
        result['outletComparison']['outletPeakM3s'] = 4.146 * 0.3048 ** 3
        self.assertEqual(compare_published(case, result)[1]['status'], 'REFERENCE_DIFFERENCE')

    def test_depth_rounding_tolerance_is_derived_from_printed_digits(self):
        case = {'published': {'runoffIn': '0.047'}}
        result = {'depthsIn': {'runoffIn': 0.048}, 'outletComparison': {'outletPeakM3s': 1}}
        check = compare_published(case, result)[0]
        self.assertAlmostEqual(check['absoluteTolerance'], 0.001)
        self.assertEqual(check['status'], 'WITHIN_PRINT_PRECISION')
        result['depthsIn']['runoffIn'] = 0.04801
        self.assertEqual(compare_published(case, result)[0]['status'], 'REFERENCE_DIFFERENCE')

    def test_unit_violation_is_preserved_in_diagnostic_mode(self):
        a = {'areaM2': 1000, 'reportCount': 720, 'seriesM3s': [1.0]*720,
             'runoffM3': 10.0, 'infiltrationM3': 5.0}
        b = copy.deepcopy(a)
        b['seriesM3s'][300] = 1.001
        with self.assertRaisesRegex(ReferenceValidationError, 'FLOW_UNIT_MISMATCH'):
            compare_units(a, b)
        result = compare_units(a, b, diagnostic=True)
        self.assertEqual(result['status'], 'REVIEW_REQUIRED')
        self.assertEqual(result['flowMismatches'][0]['period'], 301)
        self.assertEqual(a['seriesM3s'][300], 1.0)
        b['seriesM3s'][300] = float('nan')
        with self.assertRaisesRegex(ReferenceValidationError, 'FLOW_VALUE_INVALID'):
            compare_units(a, b, diagnostic=True)

    def test_report_units_fields_and_duplicate_rows_are_checked(self):
        part = 'Runoff Quantity Continuity\n hectare-m mm\n Total Precipitation ... 1 25.400\n Surface Runoff ... 1 12.700\n Infiltration Loss ... 1 12.700\nContinuity Error (%) 0'
        self.assertEqual(report_depths(part, 'CMS'), {'precipitationIn': 1.0, 'runoffIn': 0.5, 'infiltrationIn': 0.5})
        for invalid in [part.replace('mm', 'inches'), part.replace('12.700', 'NaN'), part.replace(' Surface Runoff ... 1 12.700', ''), part.replace(' Surface Runoff ... 1 12.700', ' Surface Runoff ... 1 12.700\n Surface Runoff ... 1 12.700')]:
            with self.assertRaises(ReferenceValidationError):
                report_depths(invalid, 'CMS')

    def test_six_cases_keep_legacy_reference_and_non_operating_scope(self):
        contract = json.loads(MANIFEST.read_text())
        self.assertFalse(contract['official'])
        self.assertFalse(contract['modelPromotionAllowed'])
        self.assertEqual(len(contract['cases']), 6)
        case = next(c for c in contract['cases'] if c['id'] == 'pre-10-yr')
        self.assertEqual(case['published']['runoffIn'], '0.22')
        self.assertEqual(case['sourceConflicts']['runoffIn']['value'], '0.24')
        self.assertEqual(contract['acceptance']['unitRelativeTolerance'], 0.0002)


class RegisteredSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cache = ROOT/'tmp/epa-reference/applications.zip'
        if not cls.cache.exists():
            raise unittest.SkipTest('고정 EPA ZIP 취득 후 실행')
        cls.manifest, cls.sources = read_sources(cls.cache)

    def test_relative_native_paths_and_byte_length_limit(self):
        source = transform_input(self.sources['Example1-Pre.inp'], '2-yr')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            # ASCII 경계 성공과 다중 바이트 경로 초과를 실제 엔진 앞에서 구분한다.
            length = 259 - len(os.fsencode(root)) - len('/input.inp') - 1
            boundary = root / ('a' * length)
            relative = Path(os.path.relpath(boundary))
            self.assertFalse(relative.is_absolute())
            result = execute_case(source, relative, 'CFS')
            self.assertTrue(result['apiCliBinaryEqual'])
            self.assertEqual(result['reportCount'], 720)
            too_long = root / ('a' * (length - 1) + '가')
            with self.assertRaisesRegex(ReferenceValidationError, 'ENGINE_PATH_TOO_LONG'):
                execute_case(source, too_long, 'CFS')
            self.assertFalse(too_long.exists())

    def test_unit_conversion_preserves_hydrologic_fields_and_original(self):
        source = self.sources['Example1-Pre.inp']
        before = bytes(source)
        text = transform_input(source, '10-yr', metric=True)
        self.assertIn('FLOW_UNITS CMS', text)
        self.assertIn('RainGage INTENSITY 0:05 1.0 TIMESERIES 10-yr', text)
        self.assertIn('S1 RainGage O1 11.7116024864256 5 768.4008 0.5 0.0000', text)
        self.assertIn('S1 0.015 0.24 1.524 7.62 25 OUTLET', text)
        self.assertIn('S1 114.30 5.08 6.5 7 0.0', text)
        self.assertIn('O1 1513.9416 FREE NO', text)
        self.assertIn('2-yr 0:00 7.366', text)
        self.assertEqual(source, before)
        engine = transform_input(source, '10-yr', metric=True, engine_area=True)
        line = next(line for line in engine.splitlines() if line.startswith('S1 RainGage'))
        factor = Decimal('0.92903e-5') / Decimal('2.2956e-5')
        self.assertEqual(Decimal(line.split()[3]), Decimal('28.94') * factor)

    def test_tampered_and_unregistered_sources_fail_before_execution(self):
        source = self.sources['Example1-Pre.inp']
        with self.assertRaisesRegex(ReferenceValidationError, 'INPUT_UNREGISTERED'):
            transform_input(source + b'\n', '2-yr')
        with self.assertRaisesRegex(ReferenceValidationError, 'STORM_UNSUPPORTED'):
            transform_input(source, '../unknown')
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'source.zip'
            data = bytearray(self.cache.read_bytes())
            data[-1] ^= 1
            path.write_bytes(data)
            with self.assertRaisesRegex(ReferenceValidationError, 'SOURCE_HASH_MISMATCH'):
                read_sources(path)
            link = Path(temporary)/'link.zip'
            link.symlink_to(self.cache)
            with self.assertRaisesRegex(ReferenceValidationError, 'SOURCE_LINK_REJECTED'):
                read_sources(link)

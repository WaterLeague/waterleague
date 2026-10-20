"""시설 단면·집수 중복·원본 보존과 실제 EPA 연결 계산 검사."""
from copy import deepcopy
import json
import math
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine.connected_facilities import compile_design, orifice
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.engine import facility_network
from waterleague_sim.ingestion.network_variant import derive
from waterleague_sim.ingestion.published_network import records, digest, load_archive

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((Path(__file__).parent / 'fixtures/connected-facilities-v1.json').read_text())
SOURCE = b'''[OPTIONS]\r\nFLOW_UNITS CMS\r\nFLOW_ROUTING DYNWAVE\r\n[SUBCATCHMENTS]\r\nS1 G J1 1 80 100 2 0 ; preserved\r\n[SUBAREAS]\r\nS1 .01 .1 1 2 0 OUTLET\r\n[JUNCTIONS]\r\nJ1 10 3 0 0 0\r\n[OUTFALLS]\r\nO 9 FREE NO\r\n[CONDUITS]\r\nC J1 O 20 .014 0 0\r\n'''
PROFILE = {'id': 'slot-62-5ms', 'options': {'SURCHARGE_METHOD': 'SLOT', 'MAX_TRIALS': 200,
                                         'ROUTING_STEP': .0625, 'MINIMUM_STEP': .025}}


def baseline():
    _, _, inputs = load_archive(ROOT, ROOT / 'data/manifests/mendeley-seocho-network-v3.json')
    row = next(row for row in inputs if row['member'].endswith('/Baseline/seocho2_baseline.inp'))
    return derive(row['raw'], PROFILE)[0]


class ConnectedFacilityTests(unittest.TestCase):
    def test_fully_impervious_decimal_area_has_no_artificial_negative_pervious_remainder(self):
        design = deepcopy(FIXTURE)
        design['placements'] = design['placements'][:1]
        raw = SOURCE.replace(b'1 80 100', b'1.371703 100 100')
        _, metadata = compile_design(raw, design)
        value = metadata['catchmentChanges'][0]
        self.assertEqual(value['remainingImperviousM2'], value['remainingAreaM2'])

    def test_land_replacement_and_capture_use_remaining_impervious_area(self):
        design = deepcopy(FIXTURE)
        design['placements'] = design['placements'][:1]
        raw, metadata = compile_design(SOURCE, design)
        change = metadata['catchmentChanges'][0]
        self.assertEqual(change['remainingAreaM2'], 9900)
        self.assertEqual(change['remainingImperviousM2'], 7900)
        tokens = records(raw)[1]['LID_USAGE'][0]['tokens']
        self.assertAlmostEqual(float(tokens[6]), 100 * 1000 / 7900)
        self.assertEqual(tokens[7:], ['0', '*', 'J1', '0'])
        before, after = records(SOURCE)[1], records(raw)[1]
        for section, rows in before.items():
            if section != 'SUBCATCHMENTS':
                self.assertEqual(rows, after[section])
        self.assertIn(b'; preserved\r\n', raw)
        self.assertFalse(metadata['rankingEligible'])
        self.assertEqual(compile_design(SOURCE, design), (raw, metadata))
        self.assertEqual(design, {**FIXTURE, 'placements': FIXTURE['placements'][:1]})

    def test_capture_overlap_replacement_overflow_and_existing_lid_rejected(self):
        for field, value, error in (
            ('treatedImperviousM2', 8000, 'CAPTURE_AREA_EXCEEDED'),
            ('areaM2', 11000, 'REPLACEMENT_AREA_EXCEEDED'),
            ('replacedImperviousM2', 101, 'NUMBER_INVALID'),
        ):
            design = deepcopy(FIXTURE)
            design['placements'] = design['placements'][:1]
            design['placements'][0][field] = value
            with self.assertRaisesRegex(FloodModelError, error):
                compile_design(SOURCE, design)
        a = deepcopy(FIXTURE['placements'][0])
        a['treatedImperviousM2'] = 4000
        b = deepcopy(a)
        b['id'] = 'Second'
        with self.assertRaisesRegex(FloodModelError, 'CAPTURE_AREA_EXCEEDED'):
            compile_design(SOURCE, {**FIXTURE, 'placements': [a, b]})
        with self.assertRaisesRegex(FloodModelError, 'UNMODIFIED_BASELINE_REQUIRED'):
            compile_design(SOURCE + b'[LID_USAGE]\nS1 Old 1 10 0 0 0 0\n', FIXTURE)

    def test_orifice_si_units_match_independent_volume_flow_equation(self):
        drain = {'diameterMm': 19.05, 'dischargeCoefficient': .6, 'offsetMm': 152.4, 'delayHours': 6}
        area = math.pi * (.6096 / 2) ** 2
        coefficient, _ = orifice(drain, area, 1219.2, True)
        head_m = .4
        swmm_flow_m3_s = coefficient * math.sqrt(head_m * 1000) / 1000 / 3600 * area
        physical_flow = .6 * math.pi * (.01905 / 2) ** 2 * math.sqrt(2 * 9.80665 * head_m)
        self.assertAlmostEqual(swmm_flow_m3_s, physical_flow, places=14)
        self.assertAlmostEqual(coefficient / math.sqrt(25.4), 58.5, delta=.3)
        with self.assertRaisesRegex(FloodModelError, 'DELAY_ONLY_CISTERN'):
            orifice(drain, area, 1219.2, False)

    def test_geometry_and_unsafe_or_unconnected_inputs(self):
        design = deepcopy(FIXTURE)
        design['placements'] = [design['placements'][2]]
        _, metadata = compile_design(SOURCE, design)
        self.assertAlmostEqual(metadata['facilities'][0]['topWidthM'], 3.048)
        self.assertAlmostEqual(metadata['facilities'][0]['lengthM'], 200 / 3.048)
        bad = deepcopy(design)
        bad['placements'][0]['initialSaturationPercent'] = 100
        with self.assertRaisesRegex(FloodModelError, 'SWALE_SATURATION_NOT_APPLICABLE'):
            compile_design(SOURCE, bad)
        for key, value in (('id', 'a\n[FILES]'), ('areaM2', True), ('initialSaturationPercent', float('nan'))):
            bad = deepcopy(design)
            bad['placements'][0][key] = value
            with self.assertRaises(FloodModelError):
                compile_design(SOURCE, bad)
        for changed in (SOURCE.replace(b' G J1 ', b' G Missing '),
                        SOURCE.replace(b' G J1 ', b' G O '),
                        SOURCE.replace(b'OUTLET', b'PERV'),
                        SOURCE.replace(b'FLOW_UNITS CMS', b'FLOW_UNITS CFS')):
            with self.assertRaises(FloodModelError):
                compile_design(changed, design)

    @unittest.skipUnless((ROOT / 'data/raw/mendeley-seocho-v3/dataset.zip').exists(), '보관 공개 원본 필요')
    def test_public_catchments_network_rain_and_external_inputs_preserved(self):
        source = baseline()
        raw, metadata = compile_design(source, FIXTURE)
        before, after = records(source)[1], records(raw)[1]
        for section in before:
            if section == 'SUBCATCHMENTS':
                continue
            self.assertEqual([r['tokens'] for r in before[section]], [r['tokens'] for r in after[section]])
        self.assertEqual(metadata['originalSha256'], digest(source))
        self.assertEqual(len(metadata['facilities']), 4)
        self.assertEqual({r['outletNodeId'] for r in metadata['facilities']}, {'J4'})
        self.assertIn(b'WL_Cistern STORAGE 2000 1 0 0 YES', raw)
        self.assertIn(b'WL_Trench STORAGE 914.4 0.428571428571429 4 0', raw)

    @unittest.skipUnless(facility_network.library_path().exists(), '연결 시설 네이티브 빌드 필요')
    def test_native_observer_preserves_binary_and_four_facilities_fill_overflow_drain(self):
        source = baseline()
        designed, _ = compile_design(source, FIXTURE)
        open_design = deepcopy(FIXTURE)
        open_design['placements'][-1]['parameters']['drain']['delayHours'] = 0
        open_input, _ = compile_design(source, open_design)
        with tempfile.TemporaryDirectory(dir=ROOT / 'tmp', prefix='lid-') as temporary:
            root = Path(temporary)
            results = {}
            for case, engine, raw in (('base', 'network', source),
                                     ('observed', 'facility_network', source),
                                     ('design', 'facility_network', designed),
                                     ('repeat', 'facility_network', designed),
                                     ('open', 'facility_network', open_input)):
                with EngineProcess(engine, raw.decode(), root / case, native_duration=True) as process:
                    results[case] = process.call('run', 300)['result']
            self.assertEqual((root / 'base/network.out').read_bytes(), (root / 'observed/network.out').read_bytes())
            self.assertEqual((root / 'design/network.out').read_bytes(), (root / 'repeat/network.out').read_bytes())
            self.assertEqual(results['design']['final'], results['repeat']['final'])
            self.assertEqual(results['design']['numericalStatus'], 'PASSED')
            units = {r['swmmId']: r for r in results['design']['final']['facilities']}
            self.assertEqual(len(units), 4)
            for unit in units.values():
                self.assertGreater(unit['inflowM3'], 0)
                self.assertGreater(unit['surfaceOutflowM3'], 0)
                self.assertEqual(unit['numericalStatus'], 'PASSED')
            self.assertGreater(units['WL_Trench']['infiltrationM3'], 0)
            self.assertEqual(units['WL_Trench']['drainOutflowM3'], 0)
            self.assertGreater(units['WL_Bioretention']['drainOutflowM3'], 0)
            self.assertEqual(units['WL_Cistern']['drainOutflowM3'], 0)
            self.assertEqual(units['WL_Cistern']['infiltrationM3'], 0)
            opened = next(r for r in results['open']['final']['facilities'] if r['swmmId'] == 'WL_Cistern')
            self.assertGreater(opened['drainOutflowM3'], 0)
            self.assertLess(opened['finalStorageM3'], units['WL_Cistern']['finalStorageM3'])
            self.assertEqual(results['open']['numericalStatus'], 'PASSED')


if __name__ == '__main__':
    unittest.main()

"""관측/효과를 생성하지 않는 시험 입력으로 공통 평가 근거의 위조·불일치 거부 검사."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine.direct_surface_contract import archive, build, digest, DirectSurfaceContractError


class DirectSurfaceContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.model = {
            'testOnly': 'NO_OBSERVATIONS_OR_EFFECT_CALCULATION',
            'rainfall': {'testOnly': True}, 'hydrology': {'testOnly': True},
            'cells': [{'id': 'C' + 'a' * 24, 'allowedTypes': ['GREEN_ROOF'], 'maxAreaM2': 100,
                       'areaM2': 100, 'physicalInputs': {'testOnly': True},
                       'geometryCrs': 'EPSG:5186', 'geometrySha256': 'b' * 64,
                       'sourceObjectId': 'test-only-object', 'districtId': '11200'}],
            'geometrySource': {'coordinateSystem': 'EPSG:5186', 'geometrySha256': 'b' * 64,
                               'sourceObjectId': 'test-only-object', 'playCatalogSha256': 'c' * 64,
                               'sitesSha256': 'd' * 64, 'objectsSha256': 'e' * 64},
            'sharedSiteSource': {'siteCatalogHash': 'c' * 64, 'districtId': '11200',
                                 'inflowPolicy': 'DIRECT_RAINFALL_ONLY'},
            'facilityDesignSet': {'id': 'TEST_ONLY'}, 'referenceScenario': {'testOnly': True},
            'costSourceSha256': 'f' * 64, 'budgetPolicy': {'testOnly': True},
        }
        self.placement = {'cellId': 'C' + 'a' * 24, 'facilityType': 'GREEN_ROOF', 'areaM2': 20}
        run = {'initial': {'at': '2022-08-08T09:00:17+00:00'}, 'final': {'at': '2022-08-08T09:02:00+00:00'},
               'engine': {'testOnly': True}, 'routingStatus': 'NOT_APPLICABLE_NO_CONVEYANCE_NETWORK',
               'runoffMetrics': {'start': '2022-08-08T09:00:17+00:00', 'end': '2022-08-08T09:02:00+00:00',
                                 'maximumStepSeconds': 1}}
        self.result = {'baseline': deepcopy(run), 'strategy': deepcopy(run), 'scoreRule': 'TEST_ONLY',
                       'runoffComparison': {'method': 'TEST_ONLY'},
                       'installedAt': '2022-08-08T09:00:17+00:00'}
        self.cost = {'status': 'NOT_RECORDED', 'sha256': None, 'estimate': None}
        self.save_inputs()
        inp = '[OPTIONS]\nFLOW_UNITS CMS\n[RAINGAGES]\nTEST_ONLY\n[EVAPORATION]\nTEST_ONLY\n[TIMESERIES]\nTEST_ONLY\n'
        for label in ('baseline', 'strategy'):
            (self.root / (label + '.inp')).write_text(inp)

    def save_inputs(self):
        for name, value in (('model', self.model), ('placement', self.placement)):
            (self.root / (name + '.json')).write_text(json.dumps(value))

    def build(self):
        return build(self.model, self.placement, self.result, self.root, self.cost)

    def test_records_exact_inputs_utc_area_units_and_explicit_unconnected_missing_cost(self):
        value = self.build()
        self.assertEqual(value['evaluation']['start'], '2022-08-08T09:00:17+00:00')
        self.assertEqual(value['spatial']['evaluationSurfaceAreaM2'], 100)
        self.assertEqual(value['connection']['directRainAreaM2'], 20)
        self.assertIsNone(value['connection']['drainageNode'])
        self.assertIsNone(value['connection']['externalCatchment'])
        self.assertIsNone(value['cost']['snapshotSha256'])
        self.assertEqual(value['cost']['status'], 'NOT_RECORDED')
        self.assertEqual(value['units']['flow'], 'm3/s')
        self.assertEqual(value['inputFiles']['model.json'], digest((self.root / 'model.json').read_bytes()))

    def test_rejects_changed_rain_clock_engine_crs_lineage_and_cost_without_rewriting_inputs(self):
        original = (self.root / 'strategy.inp').read_bytes()
        for kind in ('rain', 'clock', 'engine', 'crs', 'lineage', 'saved-model', 'cost', 'nonfinite'):
            with self.subTest(kind=kind):
                model, result, cost = deepcopy(self.model), deepcopy(self.result), deepcopy(self.cost)
                if kind == 'rain':
                    (self.root / 'strategy.inp').write_bytes(original.replace(b'[TIMESERIES]\nTEST_ONLY', b'[TIMESERIES]\nCHANGED'))
                elif kind == 'clock':
                    result['strategy']['initial']['at'] = '2022-08-08T09:00:18+00:00'
                elif kind == 'engine':
                    result['strategy']['engine']['testOnly'] = False
                elif kind == 'crs':
                    model['geometrySource']['coordinateSystem'] = 'EPSG:4326'
                elif kind == 'lineage':
                    model['geometrySource']['geometrySha256'] = '0' * 64
                elif kind == 'saved-model':
                    model['referenceScenario']['testOnly'] = False
                elif kind == 'cost':
                    cost['sha256'] = '0' * 64
                else:
                    self.placement['areaM2'] = float('nan')
                with self.assertRaisesRegex(DirectSurfaceContractError, '^LIVE_COMPARISON_CONTRACT_INVALID$'):
                    build(model, self.placement, result, self.root, cost)
                (self.root / 'strategy.inp').write_bytes(original)

    def test_archive_is_deterministic_and_binds_result_and_manifest(self):
        first = archive(self.model, self.placement, self.result, self.root, self.cost)
        raw = (self.root / 'design-contract.json').read_bytes()
        second = archive(self.model, self.placement, self.result, self.root, self.cost)
        self.assertEqual(first, second)
        self.assertEqual(first['sha256'], digest(raw))
        self.assertEqual(raw, (self.root / 'design-contract.json').read_bytes())
        self.assertEqual(json.loads((self.root / 'result.json').read_text())['designContract'], first)
        for name, sha in json.loads((self.root / 'manifest.json').read_text()).items():
            self.assertEqual(digest((self.root / name).read_bytes()), sha)

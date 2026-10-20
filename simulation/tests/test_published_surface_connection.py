"""교환 가정 결속·원 관망 보존·실제 엔진 대조. 합성 입력은 현장 근거가 아님."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from pyproj import CRS
from shapely.geometry import box, mapping
from waterleague_sim.engine.published_surface_connection import compile_connection, validate, METHOD
from waterleague_sim.engine.coupled_flood import run_coupled, _validate
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.ingestion.published_network import records
from waterleague_sim.reference.flood_cases import mesh
from waterleague_sim.terrain.rainfall_coverage import bind, METHOD as RAIN_METHOD
from waterleague_sim.evaluation.coupled_adapter import read_coupled_record, engine_signature, file_digest
from waterleague_sim.evaluation.exception import EvaluationError
from waterleague_sim.evaluation.values import digest
from test_flood_attribution import policy


def request():
    text = '''[TITLE]
NUMERICAL_TEST_ONLY_NOT_A_PUBLIC_ASSET
[OPTIONS]
FLOW_UNITS CMS
FLOW_ROUTING DYNWAVE
INFILTRATION GREEN_AMPT
START_DATE 01/01/2020
START_TIME 00:00:00
REPORT_START_DATE 01/01/2020
REPORT_START_TIME 00:00:00
END_DATE 01/01/2020
END_TIME 00:02:01
REPORT_STEP 00:00:01
WET_STEP 00:00:01
DRY_STEP 00:00:01
ROUTING_STEP 0.1
MINIMUM_STEP 0.01
VARIABLE_STEP 0.75
ALLOW_PONDING NO
[RAINGAGES]
G INTENSITY 1:00 1.0 TIMESERIES RAIN
[TIMESERIES]
RAIN 0 60
RAIN 1 0
[SUBCATCHMENTS]
S G J 0.01 100 10 1 0
[SUBAREAS]
S 0.013 0.15 0 0 100 OUTLET
[INFILTRATION]
S 50 4 0.3
[JUNCTIONS]
J 0 1 1.5 0 0
[OUTFALLS]
O 0 FREE NO
[CONDUITS]
C J O 100 0.014 0 0 0 0
[XSECTIONS]
C CIRCULAR 0.15 0 0 0 1
[COORDINATES]
J 4 4
O 12 4
[REPORT]
NODES ALL
LINKS ALL
'''
    surface = mesh(4, 2, 20, 10, bed=lambda x, y: np.ones_like(x))
    surface.update(schemaVersion=2, terrainProvenance={
        'absoluteVerticalReferenceVerified': False, 'coordinateWkt': CRS(5186).to_wkt(),
        'originProjected': [0, 0]})
    spec = {'schemaVersion': 1, 'method': RAIN_METHOD, 'coordinateSystem': surface['coordinateSystem'],
        'evidence': 'NUMERICAL_TEST_ONLY', 'source': {'reference': 'TEST_ONLY', 'sha256': '1'*64},
        'catchments': [{'id': 'S', 'geometry': mapping(box(0, 0, 9.9, 10))}]}
    surface, coverage = bind(surface, {'inputText': text, 'coordinateSystem': surface['coordinateSystem']}, spec)
    location = {'sourceOriginalSha256': hashlib.sha256(text.encode()).hexdigest(),
        'horizontalCrs': 'EPSG:5186', 'sourceCrsVerified': False, 'rankingEligible': False,
        'nodes': [{'id': 'J', 'coordinate': [4, 4]}, {'id': 'O', 'coordinate': [12, 4]}]}
    return {'schemaVersion': 1, 'method': METHOD, 'sourceNetworkText': text,
        'sourceSurface': surface, 'sourceLocation': location, 'sourceCoverage': coverage,
        'evidence': 'NUMERICAL_TEST_ONLY_NOT_A_PUBLIC_ASSET',
        'parameters': {'openingDiameterM': .6, 'dischargeCoefficient': .62, 'surchargeHeadM': 100.,
            'surfaceOffsetM': 0., 'boundaryType': 'REFLECTIVE', 'durationSeconds': 120,
            'maximumExchangeMilliseconds': 100, 'frameIntervalMilliseconds': 1000,
            'networkNumericalProfile': {'id': 'test-slot', 'options': {'SURCHARGE_METHOD': 'SLOT',
                'ROUTING_STEP': .03, 'MINIMUM_STEP': .01, 'MAX_TRIALS': 200}}}}


class PublishedConnectionTests(unittest.TestCase):
    def test_original_forcing_pipes_and_rims_preserved_with_explicit_datum(self):
        value = request(); before = deepcopy(value)
        model = compile_connection(value)
        self.assertEqual(value, before)
        a = records(value['sourceNetworkText'].encode())[1]
        b = records(model['network']['inputText'].encode())[1]
        for section in ('INFLOWS', 'TIMESERIES', 'CONDUITS', 'SUBCATCHMENTS', 'OPTIONS'):
            self.assertEqual([r['tokens'] for r in a.get(section, [])], [r['tokens'] for r in b.get(section, [])])
        self.assertEqual(a['JUNCTIONS'][0]['tokens'][:4], b['JUNCTIONS'][0]['tokens'][:4])
        self.assertEqual(float(b['JUNCTIONS'][0]['tokens'][4]), 100)
        self.assertFalse(model['surface']['terrainProvenance']['absoluteVerticalReferenceVerified'])
        self.assertFalse(validate(model)['rankingEligible'])
        _validate(model)
        orphan = deepcopy(model); orphan.pop('publishedSurfaceConnection')
        with self.assertRaisesRegex(FloodModelError, 'VERTICAL_REFERENCE_UNVERIFIED'):
            _validate(orphan)

    def test_height_offset_changes_only_assumed_surface_and_exchange_crest(self):
        source = request(); source['parameters']['surfaceOffsetM'] = 1.25
        model = compile_connection(source)
        detail = model['publishedSurfaceConnection']['summary']['ports'][0]
        self.assertEqual(detail['sourceRimM'], 1)
        self.assertEqual(detail['surfaceCentroidBedM'], 2.25)
        self.assertEqual(detail['exchangeCrestM'], 2.25)
        self.assertEqual(detail['gridCrestRaiseM'], 1.25)
        self.assertEqual(source['sourceSurface']['elevationM'], [1]*len(model['surface']['elevationM']))

    def test_unbound_changes_and_forcing_overrides_are_rejected(self):
        model = compile_connection(request())
        for key, value in (('durationSeconds', 119), ('ports', []), ('networkForcing', [])):
            changed = deepcopy(model); changed[key] = value
            with self.assertRaisesRegex(FloodModelError, 'BINDING_MISMATCH'):
                _validate(changed)
        for key in ('surface', 'network'):
            changed = deepcopy(model); changed[key]['verticalDatum'] = 'VERIFIED'
            with self.assertRaisesRegex(FloodModelError, 'BINDING_MISMATCH'):
                _validate(changed)

    def test_missing_source_outside_node_and_nonfinite_parameter_rejected(self):
        for mode in ('hash', 'outside', 'diameter', 'offset'):
            value = request()
            if mode == 'hash': value['sourceLocation']['sourceOriginalSha256'] = '0'*64
            if mode == 'outside': value['sourceLocation']['nodes'][0]['coordinate'] = [-1, -1]
            if mode == 'diameter': value['parameters']['openingDiameterM'] = True
            if mode == 'offset': value['parameters']['surfaceOffsetM'] = float('nan')
            with self.subTest(mode=mode), self.assertRaises(FloodModelError):
                compile_connection(value)

    def test_native_exchange_and_rehashed_physical_input_tampering(self):
        model = compile_connection(request())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'run'
            result = run_coupled(model, root)
            network = json.loads((root/'network/network-result.json').read_bytes())
            surface = json.loads((root/'surface/surface-result.json').read_bytes())
            context = policy()['context'] | {'engineSha256': engine_signature(network, surface, result),
                'metricSpecificationSha256': digest(model['evaluationMetrics'])}
            record = read_coupled_record(root, file_digest(root/'coupled-result.json'), context)
            self.assertTrue(record['complete'])
            self.assertEqual(record['numericalStatus'], 'FAILED')
            self.assertEqual(result['networkNumericalStatus'], 'FAILED')
            self.assertEqual(result['surfaceNumericalStatus'], 'PASSED')
            self.assertEqual(network['final']['totals']['floodingM3'], 0)
            self.assertLess(abs(result['balance']['exchangeCancellationResidualM3']), 1e-8)
            self.assertGreater(result['balance']['networkToSurfaceM3'], 0)
            self.assertGreater(result['balance']['surfaceToNetworkM3'], 0)
            for changed in ({'modelGrade': 'SITE_VALIDATED'}, {'comparisonKind': 'HISTORICAL_RECONSTRUCTION'}):
                with self.assertRaisesRegex(EvaluationError, 'PUBLIC_CONNECTION_GRADE_MISMATCH'):
                    read_coupled_record(root, file_digest(root/'coupled-result.json'), context | changed)
            path = root/'network/network.inp'
            path.write_text(path.read_text().replace('WL_PORT_J CIRCULAR 0.6', 'WL_PORT_J CIRCULAR 0.9'))
            network['files']['network.inp'] = file_digest(path)
            (root/'network/network-result.json').write_text(json.dumps(network))
            for name in ('network/network.inp', 'network/network-result.json'):
                result['files'][name] = file_digest(root/name)
            (root/'coupled-result.json').write_text(json.dumps(result))
            with self.assertRaisesRegex(EvaluationError, 'PUBLIC_CONNECTION_NATIVE_MISMATCH'):
                read_coupled_record(root, file_digest(root/'coupled-result.json'), context)


if __name__ == '__main__':
    unittest.main()

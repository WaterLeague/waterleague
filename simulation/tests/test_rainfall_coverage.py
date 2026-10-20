"""경계 격자의 공개 면적 보존·강우/토양 원장·결합 재생 검사."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from shapely.geometry import box, mapping
from waterleague_sim.engine.coupled_flood import _validate, run_coupled
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.terrain.rainfall_coverage import bind, validate, METHOD, surface_fractions
from waterleague_sim.terrain.coverage import infiltration_from_assignment
from waterleague_sim.forcing.observed_rainfall import compile_rainfall
from waterleague_sim.evaluation.coupled_adapter import engine_signature, file_digest, read_coupled_record
from waterleague_sim.evaluation.exception import EvaluationError
from waterleague_sim.evaluation.values import digest
from test_live_network_rainfall import case
from test_flood_attribution import policy
from test_surface_infiltration import soils
from test_surface_evaporation import numerical


def partitioned():
    model = case()
    specification = {'schemaVersion': 1, 'method': METHOD,
        'coordinateSystem': model['surface']['coordinateSystem'], 'evidence': 'NUMERICAL_TEST_ONLY',
        'source': {'reference': 'NUMERICAL_TEST_ONLY', 'sha256': '1'*64},
        'catchments': [{'id': 'S1', 'geometry': mapping(box(0, 0, 9.9, 10))}]}
    model['surface'], model['networkRainfallCoverage'] = bind(model['surface'], model['network'], specification)
    model.pop('networkRainfallTriangles')
    model['observedRainfall']['stationByTriangle'] = [
        '421' if f else None for f in surface_fractions(model['surface'])]
    return model


class RainfallCoverageTests(unittest.TestCase):
    def test_exact_geometry_fraction_and_original_declared_area_are_separate(self):
        model = partitioned()
        before = deepcopy(model)
        value = validate(model)
        self.assertEqual(model, before)
        self.assertEqual(value['totals']['surfaceRainfallAreaM2'], 101)
        self.assertEqual(value['totals']['networkGeometryAreaM2'], 99)
        self.assertEqual(value['totals']['networkDeclaredAreaM2'], 100)
        self.assertEqual(value['totals']['combinedMinusMeshM2'], 1)
        self.assertEqual(value['totals']['geometryClosureResidualM2'], 0)
        self.assertEqual(sum(0 < v < 1 for v in value['surfaceFractions']), 4)
        _validate(model)
        schedule = compile_rainfall(model['observedRainfall'], model['surface'], 120, network_stations={'401'})
        self.assertEqual({r['stationId']: r['surfaceAreaM2'] for r in schedule.summary['stations']},
                         {'401': 0., '421': 101.})

    def test_overlap_outside_missing_shape_and_changed_area_fail(self):
        model = partitioned()
        coverage = model['networkRainfallCoverage']
        for shape in (box(-1, 0, 9.9, 10), box(0, 0, 0, 0)):
            spec = deepcopy(coverage['specification'])
            spec['catchments'][0]['geometry'] = mapping(shape)
            with self.assertRaises(FloodModelError):
                bind(model['surface'], model['network'], spec)
        spec = deepcopy(coverage['specification'])
        spec['catchments'].append({'id': 'S2', 'geometry': mapping(box(5, 0, 15, 10))})
        network = model['network'] | {'inputText': model['network']['inputText'].replace(
            '[SUBAREAS]', 'S2 G TANK 0.01 100 10 1 0\n[SUBAREAS]')}
        with self.assertRaisesRegex(FloodModelError, 'GEOMETRY_OVERLAP'):
            bind(model['surface'], network, spec)
        changed = deepcopy(model)
        changed['network']['inputText'] = changed['network']['inputText'].replace('S1 G TANK 0.01 ', 'S1 G TANK 0.02 ')
        with self.assertRaisesRegex(FloodModelError, 'BINDING_MISMATCH'):
            validate(changed)

    def test_tampered_fractions_and_legacy_combination_are_rejected(self):
        model = partitioned()
        for value in (True, float('nan'), -1., 1.1, .5):
            changed = deepcopy(model)
            changed['surface']['rainfallPartition']['surfaceFractions'][2] = value
            with self.assertRaises(FloodModelError):
                _validate(changed)
        changed = deepcopy(model)
        changed['networkRainfallTriangles'] = {'S1': [0]}
        with self.assertRaisesRegex(FloodModelError, 'CONFLICT'):
            _validate(changed)
        changed = deepcopy(model)
        changed.pop('networkRainfallCoverage')
        with self.assertRaisesRegex(FloodModelError, 'BINDING_REQUIRED'):
            _validate(changed)

    def test_whole_cell_soil_map_cannot_be_reused_as_remaining_area(self):
        with self.assertRaisesRegex(FloodModelError, 'PARTITION_GEOMETRY_REQUIRED'):
            infiltration_from_assignment(partitioned()['surface'], {}, {}, {}, initialization={})

    def test_two_disjoint_catchments_inside_one_cell_keep_exact_areas(self):
        model = partitioned()
        spec = deepcopy(model['networkRainfallCoverage']['specification'])
        spec['catchments'] = [{'id': 'S1', 'geometry': mapping(box(.1, .1, .2, .2))},
                              {'id': 'S2', 'geometry': mapping(box(.3, .1, .4, .2))}]
        network = model['network'] | {'inputText': model['network']['inputText'].replace(
            '[SUBAREAS]', 'S2 G TANK 0.01 100 10 1 0\n[SUBAREAS]')}
        surface, coverage = bind(model['surface'], network, spec)
        self.assertEqual([r['intersections'][0][0] for r in coverage['catchments']], [0, 0])
        self.assertAlmostEqual(coverage['totals']['networkGeometryAreaM2'], .02)
        self.assertAlmostEqual(coverage['totals']['surfaceRainfallAreaM2'], 199.98)
        self.assertAlmostEqual(surface['rainfallPartition']['surfaceFractions'][0], 1-.02/12.5)

    def test_native_rain_and_local_soil_intensity_preserve_volume(self):
        surface = partitioned()['surface']
        surface['infiltration'] = soils(surface, conductivity=1000., deficit=.3)
        rain = [60. if f else 0. for f in surface_fractions(surface)]
        with tempfile.TemporaryDirectory() as temporary:
            with EngineProcess('surface', surface, Path(temporary)/'soil') as session:
                session.call('set_rainfall', rain)
                final = session.call('advance', 60)
                result = session.call('finish')
            self.assertAlmostEqual(final['rainfallM3'], .101, places=9)
            self.assertAlmostEqual(final['infiltrationM3'], .101, places=9)
            self.assertLess(final['storageM3'], 1e-9)
            self.assertLess(abs(final['balanceResidualM3']), 1e-8)
            self.assertAlmostEqual(result['infiltration']['effectivePerviousAreaM2'], 101.)

    def test_native_evaporation_uses_remaining_area(self):
        surface = partitioned()['surface']
        surface['initialDepthM'] = [.01]*len(surface['triangles'])
        surface['evaporation'] = numerical(surface)
        with tempfile.TemporaryDirectory() as temporary:
            with EngineProcess('surface', surface, Path(temporary)/'evaporation') as session:
                session.call('advance', 120)
                result = session.call('finish')
            self.assertAlmostEqual(result['evaporation']['surfaceAreaM2'], 101.)
            self.assertAlmostEqual(result['evaporation']['surfaceEvaporationM3'], 101*72/1440/1000, places=10)
            self.assertEqual(result['numericalStatus'], 'PASSED')

    def test_native_coupling_replay_and_rehashed_surface_tampering(self):
        model = partitioned()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = run_coupled(model, root/'a')
            replay = run_coupled(json.loads((root/'a/coupled-input.json').read_bytes()), root/'b')
            self.assertEqual(first['numericalStatus'], 'PASSED')
            self.assertEqual(first['balance'], replay['balance'])
            self.assertEqual(first['networkRainfall'], replay['networkRainfall'])
            self.assertEqual(first['observedRainfall'], replay['observedRainfall'])
            rainfall = first['networkRainfall']
            depth = rainfall['stations'][0]['depthMm']
            self.assertAlmostEqual(rainfall['geometricAreaDifference']['declaredMinusGeometryRainfallM3'], depth/1000)
            self.assertLess(abs(rainfall['nativeVolumeResidualM3']), 1e-8)
            self.assertLess(abs(first['observedRainfall']['volumeResidualM3']), 1e-8)
            network = json.loads((root/'a/network/network-result.json').read_bytes())
            surface = json.loads((root/'a/surface/surface-result.json').read_bytes())
            context = policy()['context'] | {'metricSpecificationSha256': digest(model['evaluationMetrics']),
                'engineSha256': engine_signature(network, surface, first)}
            self.assertTrue(read_coupled_record(root/'a', file_digest(root/'a/coupled-result.json'), context)['complete'])
            path = root/'a/surface/surface-input.json'
            altered = json.loads(path.read_bytes())
            altered['rainfallPartition']['surfaceFractions'][2] = .5
            path.write_text(json.dumps(altered))
            surface['files']['surface-input.json'] = file_digest(path)
            (root/'a/surface/surface-result.json').write_text(json.dumps(surface))
            first['files']['surface/surface-input.json'] = file_digest(path)
            first['files']['surface/surface-result.json'] = file_digest(root/'a/surface/surface-result.json')
            (root/'a/coupled-result.json').write_text(json.dumps(first))
            with self.assertRaisesRegex(EvaluationError, 'PARTITION_NATIVE_MISMATCH'):
                read_coupled_record(root/'a', file_digest(root/'a/coupled-result.json'), context)

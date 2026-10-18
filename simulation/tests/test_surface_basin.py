"""설계 지형·강우 소유권·연결 수지·재현 검증."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from waterleague_sim.engine.surface_basin import compile_basin, state_summary
from waterleague_sim.engine.surface_exchange import ExchangeSurfaceSession
from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.evaluation.coupled_adapter import engine_signature, file_digest, read_coupled_record
from waterleague_sim.evaluation.exception import EvaluationError
from waterleague_sim.evaluation.values import digest
from waterleague_sim.ingestion.published_network import records
from waterleague_sim.reference.surface_basin import case, observed_case, initialized_case
from simulation.tests.test_flood_attribution import policy

ROOT = Path(__file__).resolve().parents[2]


def rebind(model):
    spec = model.pop('surfaceBasinDesign')
    spec['sourceModelSha256'] = digest(model)
    model['surfaceBasinDesign'] = spec


class SurfaceBasinContractTests(unittest.TestCase):
    def test_stage_storage_version_keeps_previous_hydraulic_model(self):
        current = case()
        previous = deepcopy(current)
        previous['surfaceBasinDesign']['schemaVersion'] = 1
        old_model, old_metadata = compile_basin(previous)
        new_model, new_metadata = compile_basin(current)
        self.assertEqual(old_model, new_model)
        self.assertEqual(old_metadata['schemaVersion'], 1)
        self.assertEqual(new_metadata['schemaVersion'], 2)
        self.assertNotIn('terrainStageStorage', old_metadata['facilities'][0])
        for old, new in zip(old_metadata['facilities'], new_metadata['facilities']):
            self.assertEqual(old, {key: value for key, value in new.items() if key != 'terrainStageStorage'})

    def test_dry_high_ground_is_not_reported_as_water_above_bank(self):
        metadata = {'facilities': [{'id': 'pond', 'triangles': [0, 1], 'areasM2': [1, 1],
            'bedElevationM': [3, 0], 'lowestBoundaryElevationM': 1}]}
        value = state_summary(metadata, {'timeSeconds': 1, 'depthM': [0, .5]})
        self.assertEqual(value['facilities'][0]['maximumStageAboveLowestBoundaryM'], 0)
        self.assertEqual(value['facilities'][0]['storageM3'], .5)

    def test_integer_exchange_clock_keeps_forcing_endpoint_and_rejects_real_drift(self):
        session = ExchangeSurfaceSession.__new__(ExchangeSurfaceSession)
        session.finished = False
        state = {'time': 119.98500000000037}
        session.domain = SimpleNamespace(get_time=lambda: state['time'])
        session._evolve_until = lambda target: state.update(time=target)
        session.port_state = lambda: dict(state)
        self.assertEqual(session.advance_exchange(15)['time'], 120.)
        state['time'] = 119.98501
        with self.assertRaisesRegex(FloodModelError, 'CLOCK_OFF_GRID'):
            session.advance_exchange(15)

    def test_geometry_ownership_source_network_and_material_partition(self):
        source = case()
        original = deepcopy(source)
        model, metadata = compile_basin(source)
        self.assertEqual(source, original)
        self.assertEqual((model, metadata), compile_basin(source))
        self.assertEqual(model['surface']['rainfallOwner'], source['surface']['rainfallOwner'])
        self.assertEqual(model['evaluationMetrics'], source['evaluationMetrics'])
        self.assertEqual(model['surface']['initialDepthM'], source['surface']['initialDepthM'])
        self.assertEqual(model['surface']['evaporation'], source['surface']['evaporation'])
        geometry = metadata['facilities'][0]
        self.assertEqual(geometry['planAreaM2'], 1.)
        self.assertAlmostEqual(geometry['excavationM3'], .45)
        self.assertAlmostEqual(geometry['storageToLowestBoundaryM3'], .45)
        curve = geometry['terrainStageStorage']
        self.assertAlmostEqual(curve['levels'][-1]['storageM3'], .45)
        self.assertEqual(curve['levels'][-1]['stageM'], geometry['lowestBoundaryElevationM'])
        self.assertTrue(any(row['linearMinusCentroidStorageM3'] > 0 for row in curve['levels']))
        self.assertEqual(metadata['additionalNetworkStorageM3'], 0)
        before = records(source['network']['inputText'].encode())[1]
        after = records(model['network']['inputText'].encode())[1]
        for section, rows in before.items():
            self.assertEqual([r['tokens'] for r in rows],
                [r['tokens'] for r in after[section] if not r['tokens'][0].startswith('WLBS_')])
        outside = set(range(len(source['surface']['triangles'])))-set(geometry['triangles'])
        for cell in outside:
            for vertex in source['surface']['triangles'][cell]:
                self.assertEqual(model['surface']['elevationM'][vertex], source['surface']['elevationM'][vertex])
        region = model['surface']['infiltration']['regions'][0]
        self.assertEqual(set(region['triangles']), set(geometry['triangles']))

    def test_unbound_boundary_water_ownership_exposure_and_drain_rejected(self):
        for kind in ('hash', 'boundary', 'water', 'ownership', 'exposure', 'missing_soil', 'outfall', 'low_crest', 'huge_drain'):
            model = case()
            design = model['surfaceBasinDesign']['placements'][0]
            cell = design['triangles'][0]
            if kind == 'hash':
                model['surface']['manningN'][0] = .1
            elif kind == 'boundary':
                design['vertexElevations'][0]['elevationM'] = .1
            elif kind == 'water':
                model['surface']['initialDepthM'][cell] = .1
            elif kind == 'ownership':
                model['surface']['rainfallOwner'][cell] = 'NETWORK'
            elif kind == 'exposure':
                model['evaluationMetrics']['exposureTriangles'].append(cell)
            elif kind == 'missing_soil':
                model['surface']['infiltration'] = None
            elif kind == 'outfall':
                design['drain']['nodeId'] = 'OUT'
            elif kind == 'low_crest':
                design['drain']['crestM'] = .1
            else:
                design['drain']['diameterM'] = 100
            if kind != 'hash':
                rebind(model)
            with self.subTest(kind=kind), self.assertRaises(FloodModelError):
                compile_basin(model)


class SurfaceBasinNativeTests(unittest.TestCase):
    def test_observed_warmup_preserves_surface_basin_state_and_excludes_prior_rain(self):
        target = os.environ.get('INITIALIZED_SURFACE_BASIN_EVIDENCE_DIR')
        if target:
            root = Path(target).resolve()
            self.assertFalse(root.exists())
        else:
            temporary = tempfile.TemporaryDirectory(dir=ROOT/'tmp', prefix='initialized-surface-basin-')
            self.addCleanup(temporary.cleanup)
            root = Path(temporary.name)/'case'
        result = run_coupled(initialized_case(), root)
        self.assertEqual(result['numericalStatus'], 'PASSED')
        basin = result['surfaceBasins']
        self.assertEqual(basin['evaluationInitial']['timeSeconds'], 7*86400)
        self.assertGreater(basin['evaluationInitial']['facilities'][0]['storageM3'], 0)
        self.assertAlmostEqual(result['initialization']['evaluationLedger']['surface']['rainfallM3'], 850.)
        self.assertGreater(result['balance']['surfaceRainfallM3'], 850.)
        network = json.loads((root/'network/network-result.json').read_bytes())
        surface = json.loads((root/'surface/surface-result.json').read_bytes())
        context = policy()['context'] | {'metricSpecificationSha256': digest(result['evaluationMetrics']['specification']),
            'engineSha256': engine_signature(network, surface, result)}
        self.assertTrue(read_coupled_record(root, file_digest(root/'coupled-result.json'), context)['complete'])

    def test_rain_losses_backflow_steps_replay_and_research_reader(self):
        target = os.environ.get('SURFACE_BASIN_EVIDENCE_DIR')
        if target:
            root = Path(target).resolve()
            self.assertFalse(root.exists())
            root.mkdir(parents=True)
        else:
            temporary = tempfile.TemporaryDirectory(dir=ROOT/'tmp', prefix='surface-basin-')
            self.addCleanup(temporary.cleanup)
            root = Path(temporary.name)
        cases = [('permeable', case()), ('sealed', case(sealed=True)),
            ('step-50ms', case(exchange_ms=50)), ('overflow', case(initial_network=4.9, route_ms=1)),
            ('replay', case()), ('observed-rain', observed_case())]
        results = {}
        for name, model in cases:
            path = root/name
            result = results[name] = run_coupled(model, path)
            self.assertEqual(result['numericalStatus'], 'PASSED', name)
            self.assertEqual(result['networkConvergence']['nonConvergedSteps'], 0, name)
            network = json.loads((path/'network/network-result.json').read_bytes())
            surface = json.loads((path/'surface/surface-result.json').read_bytes())
            context = policy()['context'] | {'metricSpecificationSha256': digest(result['evaluationMetrics']['specification']),
                'engineSha256': engine_signature(network, surface, result)}
            self.assertTrue(read_coupled_record(path, file_digest(path/'coupled-result.json'), context)['complete'])
            self.assertEqual(result['surfaceBasins']['additionalStorageInCoupledBalanceM3'], 0)
            self.assertLessEqual(result['surfaceBasins']['final']['facilities'][0]['storageM3'], surface['final']['storageM3'])
            expected_rain = .006 if name == 'observed-rain' else .008
            self.assertAlmostEqual(result['balance']['surfaceRainfallM3'], expected_rain, places=10)
            self.assertGreater(result['balance']['surfaceEvaporationM3'], 0)
            self.assertEqual(result['balance']['surfaceInfiltrationM3'], 0) if name == 'sealed' else self.assertGreater(
                result['balance']['surfaceInfiltrationM3'], 0)
            if name == 'permeable':
                transfers = [t for line in (path/'surface/surface-exchange.jsonl').read_text().splitlines()
                    for t in json.loads(line)['transfers'] if t['port'] == 'WLBS_Pond']
                self.assertTrue(any(t['appliedM3'] > 0 for t in transfers))
                self.assertTrue(any(t['appliedM3'] < 0 for t in transfers))
                original = (path/'coupled-result.json').read_bytes()
                altered = deepcopy(result)
                altered['surfaceBasins']['final']['facilities'][0]['storageM3'] += 1
                try:
                    (path/'coupled-result.json').write_text(json.dumps(altered))
                    with self.assertRaisesRegex(EvaluationError, 'BASIN_CONTEXT_MISMATCH'):
                        read_coupled_record(path, file_digest(path/'coupled-result.json'), context)
                finally:
                    (path/'coupled-result.json').write_bytes(original)
            print(name, result['numericalStatus'], flush=True)
        for file in ('network/network.out', 'surface/surface-result.json'):
            self.assertEqual((root/'permeable'/file).read_bytes(), (root/'replay'/file).read_bytes())
        self.assertEqual(results['permeable']['evaluationMetrics'], results['replay']['evaluationMetrics'])
        comparison = {'exactReplay': True, 'step100Minus50': {
            k:v-results['step-50ms']['evaluationMetrics']['raw'][k]
            for k,v in results['permeable']['evaluationMetrics']['raw'].items()}}
        (root/'comparison.json').write_text(json.dumps(comparison,indent=2)+'\n')


if __name__ == '__main__':
    unittest.main()

"""관측을 생성하지 않는 연결·면적 원장의 위조와 중복 배분 검사."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from waterleague_sim.engine import flow_connections as graph
from waterleague_sim.engine.connected_facilities import compile_design
from waterleague_sim.engine.cistern_network import compile_cistern
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.reference.cistern_network import source, design as cistern_design
from test_connected_facilities import SOURCE, FIXTURE


class FlowConnectionTests(unittest.TestCase):
    def network(self, raw=SOURCE, design=None):
        if design is None:
            design = deepcopy(FIXTURE)
            design['placements'] = design['placements'][:1]
        strategy, transformation = compile_design(raw, design)
        return self.build(raw, strategy, design, transformation), strategy

    def build(self, raw, strategy, design, transformation):
        sources = {name: graph.digest(value) for name, value in (
            ('original.inp', raw), ('baseline-input.inp', raw), ('strategy-input.inp', strategy),
            ('design.json', graph.encode(design)))}
        return graph.published_network(raw, raw, strategy, design, transformation, sources, [])

    def test_original_decimal_area_partition_and_record_lineage_are_preserved(self):
        value, strategy = self.network()
        budgets = {p['id']: p for p in value['areaBudgets']}
        impervious = budgets['source-catchment:S1:impervious']
        self.assertEqual(impervious['availableM2'], '8000')
        self.assertEqual([p['areaM2'] for p in impervious['allocations']], ['100', '1000', '6900'])
        self.assertEqual(sum(Decimal(p['areaM2']) for p in impervious['allocations']), Decimal(8000))
        self.assertEqual(value['spatialStatus']['nativeMapLink'], 'UNCONNECTED')
        self.assertEqual(value['spatialStatus']['horizontalCrs'], 'UNCONFIRMED')
        for row in value['nodes']:
            raw = SOURCE if row['source'] == 'original.inp' else strategy
            text = raw.decode().splitlines()[row['line']-1]
            self.assertEqual(graph.digest(text.encode()), row['rowSha256'])
        bind = next(b for b in value['inputBindings'] if b['role'] == 'FACILITY_INITIAL_SATURATION_AND_CAPTURE')
        self.assertEqual(bind['nodeId'], 'facility:' + FIXTURE['placements'][0]['id'].upper())
        raw = SOURCE.replace(b'1 80 100', b'0.0001234567 80 100')
        changed = self.build(raw, raw, {'placements': []}, {})
        self.assertEqual(changed['areaBudgets'][0]['availableM2'], '0.9876536')

    def test_cistern_capture_cover_and_bypass_are_disjoint_for_mixed_surface(self):
        raw = source().replace(b'0.01 100 10', b'0.01 80 10')
        strategy, metadata = compile_cistern(raw, cistern_design(raw) | {'schemaVersion': 2})
        value = self.build(raw, strategy, {'placements': []}, {'networkCistern': metadata})
        budgets = {b['id']: b for b in value['areaBudgets']}
        imp = budgets['source-catchment:S1:impervious']
        self.assertEqual(sum(Decimal(a['areaM2']) for a in imp['allocations']), Decimal(80))
        cover = next(a for a in imp['allocations'] if a['role'] == 'CISTERN_COVER_RAIN_BYPASS')
        capture = next(a for a in imp['allocations'] if a['role'] == 'CISTERN_ROUTED_RUNOFF_NOT_DIRECT_RAIN')
        self.assertEqual(cover['targetNodeId'], 'catchment:WLCT_CISTERN_B')
        self.assertEqual(capture['targetNodeId'], 'node:WLCT_CISTERN')
        self.assertNotEqual(cover['targetNodeId'], capture['targetNodeId'])
        self.assertEqual(budgets['source-catchment:S1:pervious']['availableM2'], '20')

    def test_rejects_reused_allocations_excess_area_missing_nodes_nonfinite_and_malformed_rows(self):
        valid, _ = self.network()
        mutations = (
            lambda g: g['areaBudgets'][0]['allocations'].append(deepcopy(g['areaBudgets'][0]['allocations'][0])),
            lambda g: g['areaBudgets'][0]['allocations'][0].update(areaM2='9000'),
            lambda g: g['edges'][0].update(to='MISSING'),
            lambda g: g['areaBudgets'][0]['allocations'][0].update(areaM2='NaN'),
            lambda g: g['areaBudgets'][0]['allocations'][0].update(areaM2='1e-99999999'),
            lambda g: g['edges'][0].update(to=[]),
            lambda g: g['areaBudgets'].append(None),
            lambda g: g['inputBindings'].append(None),
            lambda g: g['sourceHashes'].update({'original.inp': 'invalid'}),
            lambda g: g['nodes'].append(deepcopy(g['nodes'][0])),
            lambda g: g['areaBudgets'].append({**deepcopy(g['areaBudgets'][0]), 'id': 'REUSED_POOL'}),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                value = deepcopy(valid)
                mutate(value)
                with self.assertRaises(FloodModelError):
                    graph.validate(value)

    def test_historical_same_surface_is_rejected_even_when_facility_types_differ(self):
        first = {'districtId': '11200', 'cellId': 'C' + 'a'*24, 'facilityType': 'GREEN_ROOF'}
        graph.unique_surfaces([first])
        for value in ([first, first | {'facilityType': 'BIORETENTION'}], [None], {}):
            with self.assertRaises(FloodModelError):
                graph.unique_surfaces(value)

    def test_large_area_cannot_hide_a_small_duplicate_in_decimal_context_rounding(self):
        value, _ = self.network()
        source = value['areaBudgets'][0]['sourceNodeId']
        next(n for n in value['nodes'] if n['id'] == source)['areaM2'] = '1000000000000'
        first, second = value['areaBudgets']
        first['availableM2'] = '1000000000000'
        target = first['allocations'][0]['targetNodeId']
        first['allocations'] = [
            {'id': 'whole', 'targetNodeId': target, 'areaM2': '1000000000000'},
            {'id': 'extra', 'targetNodeId': target, 'areaM2': '0.000000000000000001'},
        ]
        second.update(availableM2='0', allocations=[])
        with self.assertRaisesRegex(FloodModelError, 'CAPTURE_AREA_EXCEEDED'):
            graph.validate(value)

    def test_worker_rejects_rehashed_duplicate_before_any_model_or_physics_lookup(self):
        from waterleague_sim.run_historical_job import calculate
        first = {'districtId': '11200', 'cellId': 'C' + 'a'*24, 'facilityType': 'GREEN_ROOF'}
        body = json.dumps([first, first | {'facilityType': 'BIORETENTION'}])
        request = {'modelHash': 'a'*64, 'placements': body,
                   'inputHash': graph.digest(('a'*64 + '\n' + body).encode())}
        with patch('waterleague_sim.run_historical_job.forcing', return_value=b'{}'), \
             patch('waterleague_sim.run_historical_job.resolve') as resolve:
            with self.assertRaisesRegex(FloodModelError, 'SURFACE_REUSED'):
                calculate(request, Path('UNUSED_TEST_PATH'))
            resolve.assert_not_called()

    def test_archive_hash_is_bound_and_tampering_cannot_be_republished(self):
        value, _ = self.network()
        with tempfile.TemporaryDirectory() as directory:
            graph.archive(value, directory)
            raw = (Path(directory)/'flow-graph.json').read_bytes()
            self.assertEqual(graph.digest(raw), value['sha256'])
            self.assertEqual(json.loads(raw), {k: v for k, v in value.items() if k != 'sha256'})
            value['unresolved'] = []
            with self.assertRaisesRegex(FloodModelError, 'HASH_MISMATCH'):
                graph.archive(value, directory)

    def test_standalone_replay_rejects_graph_and_source_path_tampering_before_engine_load(self):
        from waterleague_sim.watershed_replay import replay
        value, _ = self.network()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            graph.archive(value, folder)
            expected = {'flow-graph.json': value['sha256']}
            result = {'flowGraph': value, 'artifactFiles': expected}
            (folder/'result.json').write_text(json.dumps(result))
            original = (folder/'flow-graph.json').read_bytes()
            (folder/'flow-graph.json').write_bytes(original + b' ')
            with self.assertRaisesRegex(ValueError, 'FLOW_GRAPH_CHANGED'):
                replay(folder, folder/'replay')
            value['sourceHashes'] = {'../outside.inp': 'a'*64}
            raw = graph.encode({k:v for k,v in value.items() if k != 'sha256'})
            value['sha256'] = graph.digest(raw)
            expected['flow-graph.json'] = value['sha256']
            (folder/'flow-graph.json').write_bytes(raw)
            (folder/'result.json').write_text(json.dumps(result))
            with self.assertRaisesRegex(ValueError, 'FLOW_GRAPH_SOURCE_CHANGED'):
                replay(folder, folder/'replay')


if __name__ == '__main__':
    unittest.main()

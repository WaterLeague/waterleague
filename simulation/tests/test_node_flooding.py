import copy
import unittest
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.presentation.node_flooding import summarize
from waterleague_sim.engine.node_flood_duration import METHOD


class NodeFloodingTests(unittest.TestCase):
    def setUp(self):
        self.layout = {'nodes': [{'id': 'J1', 'kind': 'JUNCTION'}, {'id': 'Out1', 'kind': 'OUTFALL'}]}
        self.start = {'totals': {'timeSeconds': 0, 'floodingM3': 0}, 'nodes': {
            'J1': {'type': 0, 'floodingM3': 0}, 'Out1': {'type': 1, 'floodingM3': 0},
            'Tank1': {'type': 2, 'floodingM3': 0}}}
        self.end = copy.deepcopy(self.start)
        self.end['totals'] = {'timeSeconds': 60, 'floodingM3': 5}
        self.end['nodes']['J1']['floodingM3'] = 3
        self.end['nodes']['Tank1']['floodingM3'] = 2

    def test_all_volume_includes_unmapped_storage_without_inventing_location(self):
        result = summarize(self.start, self.end, self.layout)
        self.assertEqual(result['sumNodeFloodingM3'], 5)
        self.assertEqual(result['balanceDifferenceM3'], 0)
        self.assertEqual([(n['id'], n['mapped']) for n in result['nodes']],
                         [('J1', True), ('Out1', True), ('Tank1', False)])

    def test_rejects_missing_nodes_wrong_type_window_volume_and_nonfinite(self):
        variants = []
        d=copy.deepcopy(self.end);del d['nodes']['Out1'];variants.append((self.start, d))
        d=copy.deepcopy(self.end);d['nodes']['J1']['type']=1;variants.append((self.start, d))
        d=copy.deepcopy(self.end);d['nodes']['Tank1']['type']=0;variants.append((self.start, d))
        d=copy.deepcopy(self.end);d['nodes']['J1']['floodingM3']=float('nan');variants.append((self.start, d))
        d=copy.deepcopy(self.end);d['totals']['floodingM3']=6;variants.append((self.start, d))
        d=copy.deepcopy(self.start);d['totals']['timeSeconds']=1;variants.append((d, self.end))
        for start,end in variants:
            with self.assertRaises(FloodModelError): summarize(start,end,self.layout)

    def test_only_declared_cistern_inlet_is_allowed_without_inventing_coordinates(self):
        self.start['nodes']['Inlet'] = {'type': 0, 'floodingM3': 0}
        self.end['nodes']['Inlet'] = {'type': 0, 'floodingM3': 1}
        self.end['totals']['floodingM3'] += 1
        with self.assertRaisesRegex(FloodModelError, 'LOCATION_MISSING'):
            summarize(self.start, self.end, self.layout)
        report = summarize(self.start, self.end, self.layout, inlet_nodes=['Inlet'])
        self.assertEqual(report['totalFloodingM3'], 6)
        self.assertEqual(report['nodes'][-1],
            {'id': 'Inlet', 'kind': 'JUNCTION', 'mapped': False, 'floodingM3': 1})

    def test_duration_requires_complete_source_bound_native_window(self):
        old = summarize(self.start, self.end, self.layout)
        self.assertNotIn('durationMethod', old)
        self.assertTrue(all('floodingSeconds' not in n for n in old['nodes']))
        for snapshot in (self.start, self.end):
            snapshot['nodeFloodingDurationMethod'] = METHOD
            for node in snapshot['nodes'].values():
                node['floodingSeconds'] = 0.
        self.end['nodes']['J1']['floodingSeconds'] = 20.5
        self.end['nodes']['Tank1']['floodingSeconds'] = 12.5
        report = summarize(self.start, self.end, self.layout)
        self.assertEqual(report['durationMethod'], METHOD)
        self.assertEqual([n['floodingSeconds'] for n in report['nodes']], [20.5, 0., 12.5])
        for field, changed in [('floodingSeconds', None), ('floodingSeconds', -1),
                ('floodingSeconds', float('nan')), ('floodingSeconds', 60.1)]:
            end = copy.deepcopy(self.end); end['nodes']['J1'][field] = changed
            with self.assertRaises(FloodModelError): summarize(self.start, end, self.layout)
        for changed in ('missing', 'method', 'outfall', 'initial', 'partial'):
            start, end = copy.deepcopy(self.start), copy.deepcopy(self.end)
            if changed == 'missing': del end['nodeFloodingDurationMethod']
            if changed == 'method': end['nodeFloodingDurationMethod'] = 'EPA_TIME_FLOODED'
            if changed == 'outfall': end['nodes']['Out1']['floodingSeconds'] = 1
            if changed == 'initial': start['nodes']['J1']['floodingSeconds'] = 1
            if changed == 'partial': del end['nodes']['Tank1']['floodingSeconds']
            with self.subTest(changed=changed), self.assertRaises(FloodModelError):
                summarize(start, end, self.layout)

    def test_only_declared_outlet_junctions_are_retained_without_fake_coordinates(self):
        self.start['nodes']['Outlet'] = {'type': 0, 'floodingM3': 0}
        self.end['nodes']['Outlet'] = {'type': 0, 'floodingM3': 2}
        self.end['totals']['floodingM3'] += 2
        with self.assertRaisesRegex(FloodModelError, 'LOCATION_MISSING'):
            summarize(self.start, self.end, self.layout)
        report = summarize(self.start, self.end, self.layout, outlet_nodes=['Outlet'])
        self.assertEqual(report['totalFloodingM3'], 7)
        self.assertEqual(report['nodes'][-1],
            {'id': 'Outlet', 'kind': 'JUNCTION', 'mapped': False, 'floodingM3': 2})

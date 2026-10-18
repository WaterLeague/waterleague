import copy
import unittest
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.presentation.node_flooding import summarize


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

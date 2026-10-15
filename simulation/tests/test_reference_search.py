"""탐색의 비용·면적·결정성·수치 품질 경계 검사."""
import unittest
from waterleague_sim.reference.search import search, cost


class ReferenceSearchTests(unittest.TestCase):
    def model(self):
        return {'budget': 1000, 'maxPlacements': 2,
                'unitCosts': {'RAIN_GARDEN': 3, 'PERMEABLE_PAVEMENT': 2},
                'cells': [{'id': 'B', 'areaM2': 50, 'maxAreaM2': 25, 'allowedTypes': ['RAIN_GARDEN']},
                          {'id': 'A', 'areaM2': 50, 'maxAreaM2': 30, 'allowedTypes': ['PERMEABLE_PAVEMENT']} ]}

    def test_respects_budget_types_area_and_is_deterministic(self):
        model=self.model()
        def evaluate(ps):return 100-sum(p['areaM2'] for p in ps)
        a=search(model, 55, evaluate);b=search(model,55,evaluate)
        self.assertEqual(a,b)
        self.assertLessEqual(cost(model,a['placements']),55)
        self.assertEqual(a['placements'],[{'cellId':'A','facilityType':'PERMEABLE_PAVEMENT','areaM2':20}])

    def test_no_invented_gain_and_caps_work(self):
        model=self.model()
        self.assertEqual(search(model,100,lambda p:100)['placements'],[])
        report=search(model,100,lambda p:100-len(p),max_evaluations=1)
        self.assertEqual(report['stopReason'],'EVALUATION_LIMIT')
        self.assertEqual(report['evaluations'],1)
        with self.assertRaises(ValueError):search(model,100,lambda p:float('nan'))
        with self.assertRaises(ValueError):search(model,1001,lambda p:100)

    def test_rejects_duplicates_and_wrong_surface(self):
        p={'cellId':'B','facilityType':'RAIN_GARDEN','areaM2':10}
        with self.assertRaises(ValueError):cost(self.model(),[p,p])
        with self.assertRaises(ValueError):cost(self.model(),[p|{'facilityType':'PERMEABLE_PAVEMENT'}])
        with self.assertRaises(ValueError):cost(self.model(),[p|{'areaM2':25.001}])

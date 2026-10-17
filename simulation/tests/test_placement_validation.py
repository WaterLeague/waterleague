"""시설 입력의 비용·면적·중복 경계 검사."""
import unittest
from waterleague_sim.placement_validation import cost


class PlacementValidationTests(unittest.TestCase):
    def model(self):
        return {'budget': 1000, 'maxPlacements': 2,
                'unitCosts': {'RAIN_GARDEN': 3, 'PERMEABLE_PAVEMENT': 2},
                'cells': [{'id': 'B', 'areaM2': 50, 'maxAreaM2': 25, 'allowedTypes': ['RAIN_GARDEN']},
                          {'id': 'A', 'areaM2': 50, 'maxAreaM2': 30, 'allowedTypes': ['PERMEABLE_PAVEMENT']} ]}

    def test_rejects_duplicates_and_wrong_surface(self):
        p={'cellId':'B','facilityType':'RAIN_GARDEN','areaM2':10}
        with self.assertRaises(ValueError):cost(self.model(),[p,p])
        with self.assertRaises(ValueError):cost(self.model(),[p|{'facilityType':'PERMEABLE_PAVEMENT'}])
        with self.assertRaises(ValueError):cost(self.model(),[p|{'areaM2':25.001}])

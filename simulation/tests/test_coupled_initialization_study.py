"""동일 물리 조건·관측 기간·실패 보류의 비교 계약 검사."""
from copy import deepcopy
import unittest

from scripts.analyze_coupled_initialization import specifications
from waterleague_sim.evaluation.coupled_initialization_study import fixed_input, difference
from waterleague_sim.evaluation.exception import EvaluationError
from waterleague_sim.evaluation.values import digest
from waterleague_sim.forcing.coupled_initialization import prepare_initialized_coupling


class CoupledInitializationStudyTests(unittest.TestCase):
    def test_all_cases_share_physics_and_28_day_observed_coverage(self):
        models = specifications()
        before = deepcopy(models)
        self.assertEqual(len({digest(fixed_input(m)) for m in models.values()}), 1)
        prepared = prepare_initialized_coupling(models['28d-0pct-60s'])
        self.assertEqual(prepared.schedule.summary['warmupExpectedRainfallM3'], 7940.)
        self.assertEqual(prepared.network.summary['warmupSeconds'], 28*86400)
        self.assertEqual(prepared.model['evaluationMetrics']['startMilliseconds'], 28*86400*1000)
        self.assertEqual(models, before)
        for model in models.values():
            swale = next(row for row in model['connectedFacilityDesign']['placements']
                         if row['facilityType'] == 'VEGETATIVE_SWALE')
            self.assertEqual(swale['initialSaturationPercent'], 0)

    def test_material_geometry_and_initial_water_are_not_normalized_away(self):
        source = specifications()['7d-0pct-60s']
        reference = digest(fixed_input(source))
        changes = []
        altered = deepcopy(source)
        altered['surface']['infiltration']['regions'][0]['initialMoistureDeficit'] = .4
        changes.append(altered)
        altered = deepcopy(source)
        altered['network']['inputText'] = altered['network']['inputText'].replace(
            'TANK 0 10 0 FUNCTIONAL', 'TANK 0 10 1 FUNCTIONAL')
        changes.append(altered)
        altered = deepcopy(source)
        altered['connectedFacilityDesign']['placements'][0]['areaM2'] += 1
        changes.append(altered)
        for model in changes:
            self.assertNotEqual(reference, digest(fixed_input(model)))

    def test_incorrect_clock_mixed_seeds_and_unmatched_step_rejected(self):
        source = specifications()['7d-0pct-60s']
        for kind in ('clock', 'seed', 'step', 'swale'):
            model = deepcopy(source)
            if kind == 'clock':
                model['network']['inputText'] = model['network']['inputText'].replace('08/01/2022', '07/31/2022')
            elif kind == 'seed':
                model['connectedFacilityDesign']['placements'][0]['initialSaturationPercent'] = 100
            elif kind == 'swale':
                model['connectedFacilityDesign']['placements'][2]['initialSaturationPercent'] = 100
            else:
                model['surface']['maxStepSeconds'] = 30
            with self.subTest(kind=kind), self.assertRaises(EvaluationError):
                fixed_input(model)

    def test_signed_difference_nulls_failure_and_confounded_conditions(self):
        left = {'fixedInputSha256': digest('same'), 'engineSha256': digest('engine'),
            'comparableEngineSha256': digest('implementation'),
            'warmupDays': 28, 'initialSaturationPercent': 100, 'maximumExchangeMilliseconds': 60000,
            'status': 'PASSED', 'complete': True, 'observables': {'volume': 1., 'moisture': None}}
        right = deepcopy(left) | {'initialSaturationPercent': 0, 'observables': {'volume': 2., 'moisture': None}}
        result = difference(left, right, variable='initialSaturationPercent')
        self.assertEqual(result['difference'], {'volume': -1., 'moisture': None})
        for update in ({'status': 'FAILED'}, {'complete': False}):
            self.assertEqual(difference(left | update, right, variable='initialSaturationPercent')['status'], 'WITHHELD')
        for update in ({'warmupDays': 14}, {'fixedInputSha256': digest('different')}, {'engineSha256': digest('other')}):
            with self.subTest(update=update), self.assertRaises(EvaluationError):
                difference(left | update, right, variable='initialSaturationPercent')
        for update in ({'comparableEngineSha256': digest('other')},
                       {'observables': {'volume': 1., 'moisture': .3}}):
            step = left | {'initialSaturationPercent': 0, 'maximumExchangeMilliseconds': 30000} | update
            with self.subTest(update=update), self.assertRaises(EvaluationError):
                difference(step, right, variable='maximumExchangeMilliseconds')


if __name__ == '__main__':
    unittest.main()

"""시험 전용 원 지표의 0·음수·결측·경계·비율 범위 보존."""
from copy import deepcopy
import unittest

from waterleague_sim.evaluation.exception import EvaluationError
from waterleague_sim.evaluation.raw_metrics import change, surface, network
from waterleague_sim.engine.node_flood_duration import WINDOW_METHOD


class RawMetricTests(unittest.TestCase):
    def test_native_union_duration_keeps_raw_values_failure_reasons_and_missing_history(self):
        cases = []
        for name, seconds in (('baseline', 20), ('strategy', 22)):
            cases.append({'id': name, 'complete': True, 'totals': {'outflowM3': 1, 'floodingM3': 1},
                'evaluationMetrics': {'specification': {'startMilliseconds': 0, 'endMilliseconds': 60000},
                    'specificationSha256': 'a'*64, 'complete': True,
                    'combined': {'peakOutwardM3s': 1, 'coveredSeconds': 60, 'nativeSteps': 600},
                    'floodingDuration': {'schemaVersion': 1, 'method': WINDOW_METHOD, 'complete': True,
                        'startSeconds': 0, 'endSeconds': 60, 'coveredSeconds': 60, 'nativeSteps': 600,
                        'floodingSeconds': seconds}}})
        original = {'cases': cases, 'numericalStatus': 'PASSED', 'flowGraph': {'nodes': []}}
        def row(value):
            return next(m for m in network(value)['metrics'] if m['id'] == 'networkFloodingSeconds')
        self.assertEqual(row(original)['signedImprovement'], -2)
        self.assertEqual(row(original)['relativeImprovementPercent'], -10)
        for reason, mutate in (
            ('NUMERICAL_FAILURE', lambda v: v.update(numericalStatus='FAILED')),
            ('BOUNDARY_MISMATCH', lambda v: v['cases'][1]['evaluationMetrics'].update(specificationSha256='b'*64)),
            ('UNMODELED_COVER_RAIN', lambda v: v['flowGraph']['nodes'].append(
                {'kind': 'LID_FACILITY', 'facilityType': 'RAINWATER_CISTERN'}))):
            value = deepcopy(original); mutate(value); result = row(value)
            self.assertEqual(result['reason'], reason)
            self.assertIsNone(result['signedImprovement'])
            self.assertEqual((result['baseline'], result['strategy']), (20, 22))
        value = deepcopy(original)
        metrics = value['cases'][1]['evaluationMetrics']
        metrics.update(complete=False)
        metrics['combined'].update(coveredSeconds=30, nativeSteps=300)
        metrics['floodingDuration'].update(complete=False, coveredSeconds=30, nativeSteps=300)
        self.assertEqual(row(value)['reason'], 'INCOMPLETE_RUN')
        del value['cases'][1]['evaluationMetrics']['floodingDuration']
        self.assertEqual(row(value)['status'], 'WITHHELD')
        self.assertIsNone(row(value)['strategy'])
        del value['cases'][0]['evaluationMetrics']['floodingDuration']
        self.assertEqual(row(value)['reason'], 'NOT_COLLECTED')
        self.assertEqual(row(value)['status'], 'UNAVAILABLE')
        value = deepcopy(original)
        for c in value['cases']: c['evaluationMetrics']['floodingDuration']['floodingSeconds'] = 0
        self.assertEqual(row(value)['relativeStatus'], 'ZERO_BASELINE')
        for key, changed in (('floodingSeconds', -1), ('floodingSeconds', float('nan')),
                ('floodingSeconds', 61), ('coveredSeconds', 59), ('endSeconds', 61),
                ('startSeconds', 1), ('method', 'SUM_NODE_DURATIONS'), ('nativeSteps', 599),
                ('complete', False), ('schemaVersion', True)):
            value = deepcopy(original)
            value['cases'][1]['evaluationMetrics']['floodingDuration'][key] = changed
            with self.subTest(key=key), self.assertRaises(EvaluationError): row(value)

    def test_absolute_signed_change_without_clipping_or_participant_normalization(self):
        for base, after, expected in ((0, 0, 0), (0, 2, -2), (-1, -2, 1), (2, -1, 3), (1, 4, -3), (1e-18, 2e-18, -1e-18)):
            with self.subTest(base=base, after=after):
                row=change('surfaceAccountedVolumeM3',base,after)
                self.assertEqual(row['signedImprovement'],expected)
                self.assertEqual(row['status'],'COMPARABLE')
                if base <= 0:
                    self.assertIsNone(row['relativeImprovementPercent'])
                    self.assertEqual(row['relativeStatus'],'ZERO_BASELINE' if base==0 else 'NEGATIVE_BASELINE')
                else:
                    self.assertAlmostEqual(row['relativeImprovementPercent'],expected/base*100)
        self.assertEqual(change('surfaceAccountedVolumeM3',2,-1)['relativeImprovementPercent'],150)
        self.assertEqual(change('reusedVolumeM3',2,5)['signedImprovement'],3)

    def test_missing_withheld_invalid_and_unrepresentable_relative_values(self):
        for row in (change('networkFloodingM3',None,0),change('networkFloodingM3',1,0,reason='NUMERICAL_FAILURE')):
            self.assertEqual(row['status'],'WITHHELD');self.assertIsNone(row['signedImprovement'])
            self.assertIsNone(row['relativeImprovementPercent'])
        empty=change('reusedVolumeM3',reason='NO_USE_DEMAND',unavailable=True)
        self.assertEqual(empty['status'],'UNAVAILABLE');self.assertIsNone(empty['baseline'])
        for base,after in ((1e-300,1e300),(1e300,1e300-1e285)):
            row=change('surfaceAccountedVolumeM3',base,after)
            self.assertTrue(row['signedImprovement'] is not None)
        self.assertEqual(change('surfaceAccountedVolumeM3',1e-300,1e300)['relativeStatus'],'NUMERIC_RANGE_EXCEEDED')
        for bad in (True,float('nan'),float('inf'),10**400,'1'):
            with self.assertRaises(EvaluationError):change('surfaceDischargeM3',bad,0)
        with self.assertRaises(EvaluationError):change('surfaceDischargeM3',1,0,reason='METRIC_MISSING',unavailable=True)

    def test_surface_preserves_primary_raw_value_and_unconnected_metric_reasons(self):
        cases=[]
        for key,v in (('baseline',2),('strategy',3)):
            cases.append({'id':key,'dischargeM3':v,'accountedDischargeM3':v+1,
                'metrics':{'start':'2022-08-08T00:00:00+00:00','end':'2022-08-08T01:00:00+00:00','peakM3s':v/100}})
        original={'cases':cases};row=surface(original)
        self.assertEqual(row['primaryMetricId'],'surfaceAccountedVolumeM3')
        self.assertIsNone(row['compositeScore']);self.assertFalse(row['relativeUsedForRanking'])
        metrics={m['id']:m for m in row['metrics']}
        self.assertEqual(metrics['surfaceAccountedVolumeM3']['signedImprovement'],-1)
        self.assertEqual(metrics['networkFloodingM3']['reason'],'NO_CONVEYANCE_NETWORK')
        self.assertEqual(metrics['reusedVolumeM3']['reason'],'NO_USE_DEMAND')
        changed=deepcopy(original);changed['cases'][1]['metrics']['end']='2022-08-08T02:00:00+00:00'
        with self.assertRaises(EvaluationError):surface(changed)

    def test_network_native_quality_and_scientific_eligibility_are_separate(self):
        spec={'startMilliseconds':0,'endMilliseconds':60000}
        cases=[{'id':name,'complete':True,'totals':{'outflowM3':v,'floodingM3':0},
            'evaluationMetrics':{'specification':spec,'specificationSha256':'a'*64,'complete':True,'combined':{'peakOutwardM3s':v}}}
               for name,v in (('baseline',10),('strategy',12))]
        original={'cases':cases,'numericalStatus':'PASSED','flowGraph':{'nodes':[]}}
        row=network(original);metrics={m['id']:m for m in row['metrics']}
        self.assertIsNone(row['primaryMetricId']);self.assertEqual(metrics['networkOutflowM3']['signedImprovement'],-2)
        self.assertEqual(metrics['networkFloodingM3']['relativeStatus'],'ZERO_BASELINE')
        self.assertEqual(metrics['networkFloodingSeconds']['reason'],'NOT_COLLECTED')
        for reason, mutate in (
            ('NUMERICAL_FAILURE',lambda r:r.update(numericalStatus='FAILED')),
            ('INCOMPLETE_RUN',lambda r:r['cases'][1].update(complete=False)),
            ('BOUNDARY_MISMATCH',lambda r:r['cases'][1]['evaluationMetrics'].update(specificationSha256='b'*64)),
            ('UNMODELED_COVER_RAIN',lambda r:r['flowGraph']['nodes'].append({'kind':'LID_FACILITY','facilityType':'RAINWATER_CISTERN'}))):
            changed=deepcopy(original);mutate(changed)
            failed=network(changed);m=next(m for m in failed['metrics'] if m['id']=='networkOutflowM3')
            self.assertEqual(m['reason'],reason);self.assertIsNone(m['signedImprovement'])
            self.assertEqual(m['baseline'],10);self.assertEqual(m['strategy'],12)

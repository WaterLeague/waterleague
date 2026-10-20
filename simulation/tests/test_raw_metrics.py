"""시험 전용 원 지표의 0·음수·결측·경계·비율 범위 보존."""
from copy import deepcopy
import unittest

from waterleague_sim.evaluation.exception import EvaluationError
from waterleague_sim.evaluation.raw_metrics import change, surface, network


class RawMetricTests(unittest.TestCase):
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

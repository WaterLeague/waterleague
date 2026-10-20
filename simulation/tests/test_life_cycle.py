"""현금흐름 시점·결측·잔존가치·명목/실질 기준의 독립 계산 검사."""
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
import json
from pathlib import Path
import tempfile
import unittest
from waterleague_sim.costing import life_cycle as lcc
from waterleague_sim.costing.cistern_reference import snapshot


class LifeCycleTests(unittest.TestCase):
    def plan(self):
        ev={'sha256':'a'*64,'reference':'TEST_ONLY_SYNTHETIC_LEDGER_NOT_OBSERVATION'}
        p={'scenarioId':'TEST_ONLY','currency':'KRW','studyPeriodYears':2,'priceBaseYear':2026,
           'priceBasis':'CONSTANT','discountKind':'REAL','discountRates':['0.1','0.2'],
           'termsEvidence':ev,'functionalUnit':'TEST_ONLY_SERVICE','functionalUnitVerified':True,
           'classification':'TEST_ONLY','limitations':[],
           'categories':[{'id':key,'coverage':'NOT_APPLICABLE','evidence':ev} for key in lcc.CATEGORIES],
           'cashflows':[]}
        for key,year,amount in [('INITIAL',0,'2000'),('OPERATION',1,'800'),('REPLACEMENT',2,'1000'),('RESIDUAL',2,'250')]:
            next(r for r in p['categories'] if r['id']==key)['coverage']='COMPLETE'
            p['cashflows'].append({'id':key,'category':key,'year':year,'amount':amount,'evidence':ev})
        return p

    def test_variable_year_end_factors_and_residual_credit_match_exact_fraction(self):
        value=lcc.evaluate(self.plan())
        fraction=Fraction(2000)+Fraction(800,1)/Fraction(11,10)+Fraction(1000-250,1)/Fraction(33,25)
        with localcontext() as ctx:
            ctx.prec=70
            expected=(Decimal(fraction.numerator)/Decimal(fraction.denominator)).quantize(Decimal('.01'),rounding=ROUND_HALF_EVEN)
        self.assertEqual(value['lifeCycleCost'],format(expected,'f'))
        self.assertEqual(value['lifeCycleCost'],'3295.45')
        self.assertEqual(value['status'],'COMPLETE')
        self.assertEqual(value['annualCashflows'][0]['presentValue'],'2000.00')
        self.assertEqual(value['categories'][-1]['presentValue'],'-189.39')
        self.assertFalse(value['budgetChargeChanged']);self.assertFalse(value['physicalEffectAnnualized']);self.assertFalse(value['scoreUsed'])

    def test_unknown_is_not_zero_or_full_lcc_and_replacement_year_is_not_generated(self):
        p=self.plan();p['priceBaseYear']=None
        next(r for r in p['categories'] if r['id']=='DISPOSAL')['coverage']='UNPRICED'
        value=lcc.evaluate(p)
        self.assertEqual(value['status'],'PARTIAL');self.assertIsNone(value['lifeCycleCost']);self.assertIsNone(value['comparisonKey'])
        self.assertEqual(value['knownPresentValue'],'3295.45')
        self.assertIn('PRICE_BASE_YEAR_MISSING',value['missingInputs'])
        self.assertIn('INCOMPLETE_DISPOSAL',value['missingInputs'])
        self.assertIsNone(next(r for r in value['categories'] if r['id']=='DISPOSAL')['presentValue'])
        p['studyPeriodYears']=None;p['discountRates']=None
        for flow in p['cashflows']:flow['year']=0
        self.assertEqual(lcc.evaluate(p)['status'],'UNAVAILABLE')
        self.assertIsNone(lcc.evaluate(p)['knownPresentValue'])

    def test_zero_cost_and_zero_discount_are_computed_with_explicit_evidence(self):
        p=self.plan();p['discountRates']=['0','0']
        for row in p['cashflows']:row['amount']='0'
        self.assertEqual(lcc.evaluate(p)['lifeCycleCost'],'0.00')
        p['cashflows']=[]
        for row in p['categories']:row['coverage']='NOT_APPLICABLE'
        self.assertEqual(lcc.evaluate(p)['lifeCycleCost'],'0.00')

    def test_price_basis_boundaries_and_unsupported_fields_reject(self):
        for mutate in [lambda p:p.update(discountKind='NOMINAL'),lambda p:p.update(discountRates=['-1','0']),
                       lambda p:p.update(discountRates=['0.1']),lambda p:p['cashflows'][1].update(year=3),
                       lambda p:p['cashflows'][1].update(amount='-1'),lambda p:p['cashflows'][1].update(amount='NaN'),
                       lambda p:p['cashflows'][1].update(id='INITIAL'),lambda p:p.update(rainfallMm=50),
                       lambda p:p['cashflows'][0].update(year=1)]:
            p=self.plan();mutate(p)
            with self.subTest(plan=p),self.assertRaises(lcc.LifeCycleCostError):lcc.evaluate(p)
        p=self.plan();p.update(discountKind='NOMINAL',priceBasis='CURRENT')
        self.assertEqual(lcc.evaluate(p)['lifeCycleCost'],'3295.45')
        self.assertNotEqual(lcc.evaluate(p)['comparisonKey'],lcc.evaluate(self.plan())['comparisonKey'])

    def test_public_cistern_quote_assumptions_archive_and_sensitivity_remain_partial(self):
        source=snapshot([{'id':'C1','facilityType':'RAINWATER_CISTERN','capacityM3':Decimal('2.35')}])
        with tempfile.TemporaryDirectory() as folder:
            value=lcc.archive_cistern(source,Path(folder))
            for q in value['items'][0]['quotes']:
                report=q['report']
                self.assertEqual(report['studyPeriodYears'],40);self.assertEqual(report['discountRates'],['0.0089']*40)
                self.assertEqual(report['status'],'PARTIAL');self.assertIsNone(report['lifeCycleCost']);self.assertIsNone(report['comparisonKey'])
                self.assertIn('INCOMPLETE_REPLACEMENT',report['missingInputs'])
                original=next(v for v in source['items'][0]['quotes'] if v['id']==q['id'])
                self.assertEqual(report['categories'][0]['presentValue'],format(Decimal(original['quotedSubtotalKrw']),'.2f'))
                with localcontext() as ctx:
                    ctx.prec = 70
                    rate = Decimal('0.0089')
                    annuity = (1 - (1 + rate) ** -40) / rate
                    expected = (Decimal(original['quotedSubtotalKrw']) +
                                Decimal(original['annualEstimateKrw']) * annuity).quantize(
                                    Decimal('.01'), rounding=ROUND_HALF_EVEN)
                self.assertEqual(report['knownPresentValue'], format(expected, 'f'))
                self.assertEqual(len(report['sensitivity']),2)
                self.assertLess(Decimal(report['sensitivity'][0]['knownPresentValue']),Decimal(report['knownPresentValue']))
                self.assertGreater(Decimal(report['sensitivity'][1]['knownPresentValue']),Decimal(report['knownPresentValue']))
                self.assertEqual([r['year'] for r in report['annualCashflows']],list(range(41)))
            plans=list(Path(folder).glob('*-plan.json'))
            self.assertEqual(len(plans),9)
            for path in plans:
                archived=json.loads(path.read_bytes());report=lcc.evaluate(archived)
                self.assertEqual(lcc.digest(path.read_bytes()),report['planSha256'])
        self.assertNotIn('lifeCycleCost',source['items'][0]['quotes'][0])

    def test_native_missing_period_does_not_reuse_cistern_forty_year_assumption(self):
        p=lcc.native_plan({'status':'NOT_RECORDED','sha256':None,'estimate':None})
        value=lcc.evaluate(p)
        self.assertEqual(value['status'],'UNAVAILABLE');self.assertIsNone(value['studyPeriodYears'])
        self.assertIsNone(value['knownPresentValue']);self.assertIsNone(value['lifeCycleCost'])
        self.assertIn('STUDY_PERIOD_MISSING',value['missingInputs'])

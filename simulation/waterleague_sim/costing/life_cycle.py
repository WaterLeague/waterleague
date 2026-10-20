"""명시한 현금흐름만 할인하고 결측 비용을 전체 LCC와 구분."""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
POLICY_PATH = ROOT/'backend/src/main/resources/facilities/life-cycle-method-v1.json'
POLICY_SHA256 = 'ae835ccb4566f1ecb42bc58acd8cc17bf6529b351640484e1b0e7a434a1bc15b'
METHOD = 'DISCOUNTED_CASH_FLOW_V1'
CATEGORIES = ('INITIAL', 'OPERATION', 'INSPECTION_CLEANING', 'REPAIR', 'REPLACEMENT', 'DISPOSAL', 'RESIDUAL')


class LifeCycleCostError(ValueError):
    def __init__(self):
        super().__init__('LIFE_CYCLE_COST_INPUT_INVALID')


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)+'\n').encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def policy():
    raw = POLICY_PATH.read_bytes()
    if digest(raw) != POLICY_SHA256:
        raise LifeCycleCostError()
    return json.loads(raw)


def decimal(value, *, rate=False):
    if not isinstance(value, str) or not re.fullmatch(r'-?(0|[1-9]\d{0,17})(\.\d{1,12})?', value):
        raise LifeCycleCostError()
    number = Decimal(value)
    if not number.is_finite() or (not rate and number < 0) or (rate and not Decimal('-1') < number <= 1):
        raise LifeCycleCostError()
    return number


def evidence(value):
    if (not isinstance(value, dict) or not re.fullmatch('[a-f0-9]{64}', value.get('sha256', ''))
            or not isinstance(value.get('reference'), str) or not value['reference']):
        raise LifeCycleCostError()


def money(value):
    result = value.quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)
    return format(abs(result) if result == 0 else result, 'f')


def evaluate(plan):
    try:
        return _evaluate(plan)
    except (KeyError, TypeError, ValueError, ArithmeticError):
        raise LifeCycleCostError() from None


def _evaluate(plan):
    allowed = {'scenarioId', 'currency', 'studyPeriodYears', 'priceBaseYear', 'priceBasis', 'discountKind',
               'discountRates', 'termsEvidence', 'functionalUnit', 'functionalUnitVerified', 'categories',
               'cashflows', 'classification', 'limitations'}
    if (not isinstance(plan, dict) or set(plan) != allowed or not isinstance(plan['scenarioId'], str)
            or not plan['scenarioId'] or plan['currency'] not in ('KRW', 'USD')
            or plan['priceBasis'] not in ('CONSTANT', 'CURRENT')
            or plan['discountKind'] not in ('REAL', 'NOMINAL', None)
            or plan['discountKind'] == 'REAL' and plan['priceBasis'] != 'CONSTANT'
            or plan['discountKind'] == 'NOMINAL' and plan['priceBasis'] != 'CURRENT'
            or type(plan['functionalUnitVerified']) is not bool or not isinstance(plan['functionalUnit'], str)
            or not isinstance(plan['classification'], str) or not isinstance(plan['limitations'], list)):
        raise LifeCycleCostError()
    evidence(plan['termsEvidence'])
    horizon, base_year = plan['studyPeriodYears'], plan['priceBaseYear']
    if (horizon is not None and (type(horizon) is not int or not 1 <= horizon <= 100)
            or base_year is not None and (type(base_year) is not int or not 1900 <= base_year <= 2200)):
        raise LifeCycleCostError()
    rates = plan['discountRates']
    if rates is not None:
        if horizon is None or not isinstance(rates, list) or len(rates) != horizon or plan['discountKind'] is None:
            raise LifeCycleCostError()
        rates = [decimal(value, rate=True) for value in rates]
    rows = plan['categories']
    if not isinstance(rows, list) or len(rows) != len(CATEGORIES) or {r['id'] for r in rows} != set(CATEGORIES):
        raise LifeCycleCostError()
    categories = {}
    missing = []
    for row in rows:
        evidence(row['evidence'])
        if set(row) != {'id','coverage','evidence'} or row['coverage'] not in ('COMPLETE','PARTIAL','UNPRICED','NOT_APPLICABLE'):
            raise LifeCycleCostError()
        categories[row['id']] = row['coverage']
        if row['coverage'] in ('PARTIAL', 'UNPRICED'):
            missing.append('INCOMPLETE_'+row['id'])
    if horizon is None: missing.append('STUDY_PERIOD_MISSING')
    if rates is None: missing.append('DISCOUNT_RATES_MISSING')
    if base_year is None: missing.append('PRICE_BASE_YEAR_MISSING')
    if not plan['functionalUnitVerified']: missing.append('FUNCTIONAL_UNIT_UNVERIFIED')
    flows = plan['cashflows']
    if not isinstance(flows, list) or len(flows) > 10000:
        raise LifeCycleCostError()
    ids, seen = set(), set()
    can_discount = horizon is not None and rates is not None
    with localcontext() as ctx:
        ctx.prec = 50
        factors = [Decimal(1)]
        for rate in rates or []: factors.append(factors[-1] / (1+rate))
        values, annual, total = {}, {}, Decimal(0)
        for row in flows:
            if (set(row) != {'id','category','year','amount','evidence'} or not isinstance(row['id'], str)
                    or not row['id'] or row['id'] in ids or row['category'] not in CATEGORIES
                    or categories[row['category']] in ('UNPRICED','NOT_APPLICABLE')
                    or type(row['year']) is not int or not 0 <= row['year'] <= (horizon or 0)
                    or row['category'] == 'INITIAL' and row['year'] != 0):
                raise LifeCycleCostError()
            evidence(row['evidence'])
            amount = decimal(row['amount'])
            ids.add(row['id']); seen.add(row['category'])
            if can_discount:
                signed = -amount if row['category'] == 'RESIDUAL' else amount
                pv = signed*factors[row['year']]
                total += pv
                values[row['category']] = values.get(row['category'], Decimal(0))+pv
                year = annual.setdefault(row['year'], {'cost':Decimal(0),'credit':Decimal(0),'presentValue':Decimal(0)})
                year['credit' if row['category'] == 'RESIDUAL' else 'cost'] += amount
                year['presentValue'] += pv
        if any(coverage in ('COMPLETE','PARTIAL') and key not in seen for key,coverage in categories.items()):
            raise LifeCycleCostError()
        known = bool(flows) or all(v == 'NOT_APPLICABLE' for v in categories.values())
        status = 'UNAVAILABLE' if not can_discount or not known else 'PARTIAL' if missing else 'COMPLETE'
        # 중간 연차·항목을 원 단위로 자른 뒤 합하지 않아 작은 비용의 누적 손실 방지.
        category_pv = [{'id':key,'coverage':categories[key], 'presentValue':
                       '0.00' if categories[key]=='NOT_APPLICABLE' else money(values[key]) if key in values else None}
                       for key in CATEGORIES]
        annual_pv = [{'year':year,'cost':money(value['cost']),'credit':money(value['credit']),
                     'presentValue':money(value['presentValue'])} for year,value in sorted(annual.items())]
        terms = {key:plan[key] for key in ('currency','studyPeriodYears','priceBaseYear','priceBasis','discountKind',
                                          'discountRates','functionalUnit')}
        return {'version':METHOD, 'scenarioId':plan['scenarioId'], 'status':status, **terms,
                'classification':plan['classification'], 'timing':'INITIAL_AT_YEAR_ZERO_END_OF_YEAR',
                'precision':'DECIMAL_50_SUM_THEN_HALF_EVEN_2', 'planSha256':digest(encode(plan)),
                'policySha256':POLICY_SHA256, 'comparisonKey':digest(encode(terms | {'classification':plan['classification']})) if status=='COMPLETE' else None,
                'lifeCycleCost':money(total) if status=='COMPLETE' else None,
                'knownPresentValue':money(total) if can_discount and known else None,
                'annualRoundingDifference':money(total-sum((Decimal(v['presentValue']) for v in annual_pv), Decimal(0))) if can_discount and known else None,
                'categoryRoundingDifference':money(total-sum((Decimal(v['presentValue']) for v in category_pv if v['presentValue'] is not None), Decimal(0))) if can_discount and known else None,
                'missingInputs':sorted(missing), 'categories':category_pv, 'annualCashflows':annual_pv,
                'termsEvidence':plan['termsEvidence'], 'limitations':plan['limitations'],
                'budgetChargeChanged':False, 'physicalEffectAnnualized':False, 'scoreUsed':False}


def archive(directory, name, plan):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    report = evaluate(plan)
    (directory/(name+'-plan.json')).write_bytes(encode(plan))
    (directory/(name+'.json')).write_bytes(encode(report))
    (directory/'life-cycle-method.json').write_bytes(POLICY_PATH.read_bytes())
    (directory/'life_cycle.py').write_bytes(Path(__file__).read_bytes())
    return report


def native_plan(record):
    method = policy()
    source = method['methodSource']
    recorded = record.get('status') == 'RECORDED'
    value = record['estimate'] if recorded else None
    ev = {'sha256':value['costSourceSha256'] if recorded else POLICY_SHA256,
          'reference':'PUBLIC_REFERENCE_QUANTITY_V1; unpricedItems' if recorded else '설치 당시 원가 미기록'}
    return {'scenarioId':'NATIVE_COST_INPUTS_UNCONFIRMED', 'currency':'KRW', 'studyPeriodYears':None,
            'priceBaseYear':None,'priceBasis':'CONSTANT','discountKind':None,'discountRates':None,
            'termsEvidence':source, 'functionalUnit':str(value['quantityM2'])+' m2 '+value['facilityType'] if recorded else 'UNKNOWN',
            'functionalUnitVerified':False,
            'categories':[{'id':key,'coverage':'PARTIAL' if recorded and key=='INITIAL' else 'UNPRICED','evidence':ev} for key in CATEGORIES],
            'cashflows':[{'id':'REFERENCE_INSTALLATION','category':'INITIAL','year':0,'amount':str(value['referenceSubtotalKrw']),
                          'evidence':ev}] if recorded else [],
            'classification':'PUBLIC_REFERENCE_COST_INCOMPLETE',
            'limitations':['평가기간·가격 기준연도·할인율·유지/교체/처분·잔존가치 미확정',
                           '설치 예산의 공개 참고 부분합을 전체 설치비나 생애주기비용으로 전용하지 않음']}


def archive_native(record, directory):
    return archive(directory, 'life-cycle-cost', native_plan(record))


def cistern_plan(snapshot, item, quote):
    method = policy(); scenario = method['cisternScenario']; source = scenario['source']
    if snapshot['source']['sha256'] != source['sha256']:
        raise LifeCycleCostError()
    ev = {'sha256':source['sha256'],'reference':source['reference']}
    n = scenario['studyPeriodYears']
    flows = [{'id':'QUOTE_INITIAL','category':'INITIAL','year':0,'amount':str(quote['quotedSubtotalKrw']),'evidence':ev}]
    mapping = {'ELECTRICITY':'OPERATION', 'MONITORING':'OPERATION','REPAIR_LABOUR_ETC':'REPAIR','CLEANING':'INSPECTION_CLEANING'}
    for key, amount in quote['annualComponentsKrw'].items():
        for year in range(1,n+1):
            flows.append({'id':key+'_'+str(year),'category':mapping[key],'year':year,'amount':str(amount),'evidence':ev})
    return {'scenarioId':scenario['id'], 'currency':scenario['currency'], 'studyPeriodYears':n,
            'priceBaseYear':None,'priceBasis':scenario['priceBasis'],'discountKind':scenario['discountKind'],
            'discountRates':[scenario['discountRate']]*n, 'termsEvidence':ev,
            'functionalUnit':str(item['equivalentUnits'])+' x 2.35 m3 CAPACITY_EQUIVALENT_ONLY',
            'functionalUnitVerified':False,
            'categories':[{'id':key,'coverage':'PARTIAL' if key=='INITIAL' else 'UNPRICED' if key in ('REPLACEMENT','DISPOSAL','RESIDUAL') else 'COMPLETE','evidence':ev} for key in CATEGORIES],
            'cashflows':flows,'classification':source['classification'],'limitations':scenario['limitations']}


def archive_cistern(snapshot, directory):
    if snapshot is None: return None
    value = deepcopy(snapshot); method=policy()
    for item in value['items']:
        for quote in item['quotes']:
            plan = cistern_plan(snapshot,item,quote)
            name = 'cistern-'+digest(item['placementId'].encode())[:24]+'-'+quote['id']+'-life-cycle-cost'
            report = archive(directory,name,plan)
            report['sensitivity'] = []
            for case in method['cisternScenario']['sensitivity']:
                alternative = deepcopy(plan)
                alternative['scenarioId'] = case['id']
                alternative['discountRates'] = [case['rate']]*alternative['studyPeriodYears']
                alternative['termsEvidence'] = alternative['termsEvidence'] | {'reference':case['reference']}
                outcome = archive(directory,name+'-'+case['id'],alternative)
                report['sensitivity'].append({'id':case['id'],'label':case['label'],'rate':case['rate'],
                    'knownPresentValue':outcome['knownPresentValue'],'lifeCycleCost':outcome['lifeCycleCost'],
                    'status':outcome['status'],'planSha256':outcome['planSha256']})
            quote['lifeCycleCost'] = report
            (Path(directory)/(name+'.json')).write_bytes(encode(report))
    return {'version':METHOD, 'catalogHash':snapshot['catalogHash'], 'policySha256':POLICY_SHA256,
            'items':[{'placementId':item['placementId'],
                      'quotes':[{'id':q['id'],'report':q['lifeCycleCost']} for q in item['quotes']]}
                     for item in value['items']]}

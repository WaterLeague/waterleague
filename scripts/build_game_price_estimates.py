"""공개 계획 단가의 가격 시점 가정을 보존한 공사비지수 환산 입력 생성."""
import argparse
from copy import deepcopy
from decimal import Decimal, ROUND_CEILING, localcontext
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/costs/lid-reference-v6.json'
INDEX = ROOT / 'data/manifests/kict-construction-index-202608.json'
OUTPUT = ROOT / 'data/costs/lid-index-estimates-202608-v1.json'
SERIES = {'RAIN_GARDEN': '도시토목', 'BIORETENTION': '도시토목',
          'VEGETATIVE_SWALE': '도시토목', 'PERMEABLE_PAVEMENT': '도로시설'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def estimate(unit, months, target):
    values = [Decimal(str(value)) for value in months]
    amount, current = Decimal(str(unit)), Decimal(str(target))
    if (len(values) != 12 or any(not v.is_finite() or v <= 0 for v in values)
            or not amount.is_finite() or amount <= 0 or not current.is_finite() or current <= 0):
        raise ValueError('PRICE_INDEX_INPUT_INVALID')
    # 월평균 지수를 먼저 반올림하지 않고 마지막 원화 단가에서만 올림한다.
    with localcontext() as context:
        context.prec = 50
        ceiling = lambda value: int(value.to_integral_value(rounding=ROUND_CEILING))
        adjusted = ceiling(amount * current * 12 / sum(values))
        monthly = [ceiling(amount * current / value) for value in values]
    return adjusted, [min(monthly), max(monthly)]


def build():
    base_raw, index_raw = BASE.read_bytes(), INDEX.read_bytes()
    base, index = json.loads(base_raw), json.loads(index_raw)
    if (index['baseYear'] != 2020 or index['latestPeriod'] != '2026-08'
            or index['latestProvisional'] is not True or index['publishedAt'] != '2026-09-30'):
        raise ValueError('PRICE_INDEX_VERSION_INVALID')
    series = {row['label']: row['cells'] for row in index['series']}
    facilities = {}
    for facility, label in SERIES.items():
        source = deepcopy(base['facilities'][facility])
        if (source['referenceYear'] != 2022 or source['sourceSha256'] !=
                '0efc54c3c884441d810ce28abb8928d758d98eb152fb71aac38791327b2d7414'):
            raise ValueError('PRICE_REFERENCE_CHANGED')
        cells = series[label]
        if (len(cells) != 13 or [c['periodLabel'] for c in cells[:12]] !=
                [f'2022년 {month}월' for month in range(1, 13)]
                or cells[-1]['periodLabel'] != '2026년 8월\n(잠정)'):
            raise ValueError('PRICE_INDEX_PERIOD_INVALID')
        original = source['unitCost']
        adjusted, sensitivity = estimate(original, [c['value'] for c in cells[:12]], cells[-1]['value'])
        source['unitCost'] = adjusted
        source['originalNote'] = source['note']
        source['evidence'] = 'PUBLIC_PLAN_INDEX_ADJUSTED_WITH_EXPLICIT_PRICE_PERIOD_ASSUMPTION'
        source['note'] = ('2022년 사업계획 가격을 같은 해 연평균 지수의 가격으로 가정한 2026년 8월 추정. '
            '실제 기준월·서울 지역/규격·부가세 미확인. 공종 지수는 대용값이며 최신 현장 견적 아님.')
        source['priceAdjustment'] = {
            'method': 'KICT_MONTHLY_INDEX_RATIO_ANNUAL_PROXY_V1',
            'currency': 'KRW', 'targetPeriod': '2026-08', 'targetProvisional': True,
            'observedBasePriceYear': None, 'assumedBasePriceYear': 2022,
            'basePeriodBasis': 'PUBLIC_PLAN_YEAR_ANNUAL_MEAN_PROXY_NOT_VERIFIED_QUOTE_DATE',
            'originalUnitCostKrw': original, 'adjustedUnitCostKrw': adjusted,
            'formula': 'ceil(originalUnitCostKrw * targetIndex * 12 / sum(baseMonthlyIndices))',
            'rounding': 'CEILING_KRW_PER_M2_FINAL_ONLY',
            'indexSeries': label, 'seriesRole': 'CONSTRUCTION_TYPE_PROXY_NOT_BILL_OF_QUANTITIES_MATCH',
            'indexBaseYear': index['baseYear'], 'baseMonthlyIndices': cells[:12], 'targetIndex': cells[-1],
            'indexSourceUrl': index['sourceUrl'], 'indexPublishedAt': index['publishedAt'],
            'indexManifestSha256': sha(index_raw), 'indexWorkbookSha256': index['files'][0]['sha256'],
            'baseMonthSensitivityKrwPerM2': sensitivity,
            'sensitivityMeaning': '2022_MONTH_CHOICE_ONLY_NOT_MARKET_PRICE_RANGE_OR_CONFIDENCE_INTERVAL',
        }
        facilities[facility] = source
    return {
        'schemaVersion': 1, 'id': 'KICT_202608_GAME_PRICE_ESTIMATES_V1',
        'status': 'CALCULATED_INPUT_NOT_YET_ACTIVE_GAME_PRICES',
        'currency': 'KRW', 'unit': 'KRW_PER_SQUARE_METRE',
        'sourceCostCatalogSha256': sha(base_raw), 'indexManifestSha256': sha(index_raw),
        'generatorSha256': sha(Path(__file__).read_bytes()), 'facilities': facilities,
        'notAdjusted': {
            'GREEN_ROOF': '2025 서울 사업 참고액이며 2022년 가격 가정을 적용하지 않음',
            'INFILTRATION_TRENCH': '최초 설치 시점 미확인; 2022년 보고서 발행연도로 확정하지 않음',
            'RAINWATER_CISTERN': '2018년 논문 견적의 가격 시점 미확인; 다른 규격/공종 지수 전용 보류',
        },
        'limitations': ['2026-08 지수는 잠정치이며 해당 공표본을 고정',
            '실제 공사 견적·계약금액 조정·시설 간 전체 생애비용 비교가 아님',
            '기존 예산 지출·설계·제출 비용의 소급 변경 없음',
            '현재 서버 설치비 적용과 버전별 원가 재생 통합 검증이 남은 구현'],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    result = build()
    raw = (json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode()
    if args.check:
        if OUTPUT.read_bytes() != raw:
            raise SystemExit('공사비지수 환산 입력 불일치')
    else:
        OUTPUT.write_bytes(raw)
    print(json.dumps({key: value['unitCost'] for key, value in result['facilities'].items()}, ensure_ascii=False))


if __name__ == '__main__':
    main()

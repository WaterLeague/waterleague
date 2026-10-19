"""확정 배치를 사건 전체 창에 적용하고 구별 독립 표면 원 지표를 보존."""
import json
import math
import os
import resource
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from .engine.continuous import digest
from .run_historical_job import calculate as district_calculate

POLICY = 'FULL_EVENT_INDEPENDENT_SURFACES_V1'


class HistoricalSubmissionError(ValueError):
    def __init__(self):
        super().__init__('HISTORICAL_SUBMISSION_DESIGN_MISMATCH')


def verify_design(rows, rules):
    keys = {'submissionDesignRevision', 'submissionDesignSnapshotRaw', 'submissionDesignSnapshotSha256'}
    if not any(keys.intersection(row) for row in rows):
        if json.loads(rows[0]['submissionRequestRaw']).get('mode') == 'SAVED_DESIGN_SUBMISSION_V1':
            raise HistoricalSubmissionError()
        return None
    try:
        head = rows[0]
        if not keys <= head.keys() or any(keys.intersection(row) for row in rows[1:]):
            raise HistoricalSubmissionError()
        raw, sha = head['submissionDesignSnapshotRaw'], head['submissionDesignSnapshotSha256']
        if not isinstance(raw, str) or len(raw.encode()) > 16*1024**2 or digest(raw.encode()) != sha:
            raise HistoricalSubmissionError()
        saved = json.loads(raw)
        submitted = json.loads(head['submissionRequestRaw'])
        ref = submitted['request']
        if (type(head['submissionDesignRevision']) is not int or head['submissionDesignRevision'] < 1
                or submitted['mode'] != 'SAVED_DESIGN_SUBMISSION_V1' or submitted['eventId'] != rules['eventId']
                or ref['revision'] != head['submissionDesignRevision'] or ref['snapshotSha256'] != sha
                or saved['schemaVersion'] != 1 or saved['eventId'] != rules['eventId']
                or saved['budgetPolicy'] != rules['budgetPolicy']
                or saved['publicAssetPolicy'] != rules['publicAssetPolicy']
                or saved['budgetAccounting'] != head['budgetAccounting']
                or len(saved['placements']) != len(rows)):
            raise HistoricalSubmissionError()
        original = {(r['item']['districtId'], r['item']['cellId']): r for r in saved['placements']}
        if len(original) != len(rows):
            raise HistoricalSubmissionError()
        for row in rows:
            source = original[(row['districtId'], row['cellId'])]
            item = source['item']
            at = datetime.fromisoformat(item['installedAt'])
            if (any(row[k] != item[k] for k in ('facilityType', 'areaM2'))
                    or datetime.fromisoformat(row['experimentInstalledAt']) != at
                    or not datetime.fromisoformat(rules['start']) <= at < datetime.fromisoformat(rules['end'])
                    or row['siteModelHash'] != source['site']['modelHash']
                    or row['rainfallModelHash'] != source['rainfallModelHash']
                    or row['costSnapshotRaw'] != source['costSnapshotRaw']
                    or row['costSnapshotSha256'] != source['costSnapshotSha256']
                    or digest(source['costSnapshotRaw'].encode()) != source['costSnapshotSha256']
                    or Decimal(str(source['cost'])) != Decimal(str(json.loads(source['costSnapshotRaw'])['budgetChargeKrw']))
                    or row['budgetPolicy'] != saved['budgetPolicy']
                    or row['publicAssetPolicy'] != saved['publicAssetPolicy']):
                raise HistoricalSubmissionError()
        return {'revision': head['submissionDesignRevision'], 'snapshotSha256': sha,
                'placementCount': len(rows)}
    except (KeyError, TypeError, ValueError, ArithmeticError):
        raise HistoricalSubmissionError() from None


def calculate(request, directory):
    rows = json.loads(request['placements'])
    if (not 1 <= len(rows) <= 50 or digest((request['modelHash']+'\n'+request['placements']).encode()) != request['inputHash']
            or rows[0].get('submissionPolicy') != POLICY):
        raise ValueError('HISTORICAL_SUBMISSION_INVALID')
    rules_raw = rows[0]['submissionRulesRaw']
    rules_hash = digest(rules_raw.encode())
    rules = json.loads(rules_raw)
    if rules_hash != rows[0]['submissionRulesHash'] or rules['policy'] != POLICY:
        raise ValueError('HISTORICAL_SUBMISSION_RULES_INVALID')
    design = verify_design(rows, rules)
    directory.mkdir(parents=True, exist_ok=True)
    (directory/'submission-rules.json').write_text(rules_raw)
    (directory/'submission-request.json').write_text(rows[0]['submissionRequestRaw'])
    if design:
        (directory/'submission-design.json').write_text(rows[0]['submissionDesignSnapshotRaw'])
    groups = defaultdict(list)
    seen = set()
    for row in rows:
        key = (row['districtId'], row['cellId'])
        if (key in seen or not row['districtId'].isdigit() or len(row['districtId']) != 7
                or row['rainfallModelHash'] != rules['rainfallModels'].get(row['districtId'])
                or any(k in row for k in ('installedAt', 'temporalPolicy', 'initializationSensitivity'))):
            raise ValueError('HISTORICAL_SUBMISSION_PLACEMENT_INVALID')
        seen.add(key)
        groups[row['districtId']].append(row)
    districts = []
    for district, placements in sorted(groups.items()):
        model_hash = placements[0]['rainfallModelHash']
        body = json.dumps(placements, ensure_ascii=False, sort_keys=True)
        child = {'modelHash': model_hash, 'placements': body,
                 'inputHash': digest((model_hash+'\n'+body).encode())}
        folder = directory/district
        result = district_calculate(child, folder)
        if (result['disasterEvent']['id'] != rules['eventId'] or result['start'] != rules['start']
                or result['end'] != rules['end'] or result['engineVersion'] != rules['engineVersion']
                or result['scope'] != 'SELECTED_INDEPENDENT_SURFACES_ONLY'):
            raise ValueError('HISTORICAL_SUBMISSION_WINDOW_INVALID')
        (folder/'request.json').write_text(json.dumps(child, ensure_ascii=False, allow_nan=False))
        (folder/'result.json').write_text(json.dumps(result, ensure_ascii=False, allow_nan=False))
        districts.append({'districtId': district, 'modelHash': model_hash, 'result': result})
    values = {key: math.fsum(d['result'][key] for d in districts)
              for key in ('differenceM3', 'baselineAccountedM3', 'designAccountedM3')}
    if any(not math.isfinite(v) for v in values.values()):
        raise ValueError('HISTORICAL_SUBMISSION_METRICS_INVALID')
    result = {'schemaVersion': 1, 'submissionPolicy': POLICY, 'rulesHash': rules_hash,
            'eventId': rules['eventId'], 'validationLevel': 'EXPLORATORY',
            'scope': 'SELECTED_INDEPENDENT_SURFACES_ONLY', 'modelGrade': rules['modelGrade'],
            'officialTotalScore': None, 'totalScoreStatus': 'HELD_REQUIRED_INUNDATION_AND_CONNECTED_OUTLET_MISSING',
            'engineVersion': rules['engineVersion'], 'start': rules['start'], 'end': rules['end'],
            'districts': districts, **values,
            'assumptions': ['현재 공개 형상과 과거 강우의 스트레스 시험; 당시 재난 복원 아님',
                '설치 시각과 무관하게 사건 평가 창 전체에 같은 설계 적용; 선행 기간 점수 제외',
                '독립 표면 원 지표 합계; 연결 유역·지표 침수 효과 합계 아님',
                '현재 게임 예산과 공개 참고비 사용; 사건 당시 확정 예산·가격 아님',
                '미세한 효과 차이는 물수지 잔차보다 작을 수 있으며 현장 유의성 미검증']}
    if design:
        result['submittedDesign'] = design
    return result


def main():
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CPU, (540, 540))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64*1024*1024, 64*1024*1024))
    if sys.platform.startswith('linux'):
        resource.setrlimit(resource.RLIMIT_AS, (1536*1024*1024, 1536*1024*1024))
    root = Path(sys.argv[1])
    result = calculate(json.loads((root/'request.json').read_text()), root)
    (root/'result.json').write_text(json.dumps(result, ensure_ascii=False, allow_nan=False)+'\n')
    (root/'submission.py').write_bytes(Path(__file__).read_bytes())
    (root/'historical.py').write_bytes(Path(__file__).with_name('run_historical_job.py').read_bytes())
    (root/'manifest.json').write_text(json.dumps({str(p.relative_to(root)): digest(p.read_bytes())
        for p in sorted(root.rglob('*')) if p.is_file() and p != root/'manifest.json'}, indent=2)+'\n')


if __name__ == '__main__':
    main()

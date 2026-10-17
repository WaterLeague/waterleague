"""고정 정책과 원본 표본으로 Java 생성 계보를 독립 재계산."""
import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

POLICY = 'ELITE_CATEGORICAL_SEARCH_V1'
BINS = [25, 50, 75, 100]
ARMS = ['PATTERN', 'UNIFORM']
TYPES = {'RAIN_GARDEN', 'PERMEABLE_PAVEMENT', 'GREEN_ROOF'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def decoded(raw):
    require(len(raw) <= 8 * 1024 * 1024, 'JSON 크기 상한 초과')

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, '중복 JSON 키')
            result[key] = value
        return result

    def reject(value):
        raise ValueError('비유한 JSON 수치')

    return json.loads(raw, parse_float=Decimal, parse_constant=reject, object_pairs_hook=pairs)


def number(value):
    require(type(value) in (int, Decimal), '정확한 숫자 형식 필요')
    result = Decimal(value)
    require(result.is_finite(), '비유한 수치')
    require(len(result.as_tuple().digits) <= 40 and -32 <= result.as_tuple().exponent <= 32, '수치 정밀도 상한 초과')
    return result


def integer(value, low, high):
    require(type(value) is int and low <= value <= high, '정수 범위 오류')
    return value


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode('utf-8')).hexdigest()


def plain(value):
    return format(number(value).normalize(), 'f')


def placements_json(placements):
    # 해시 입력은 정렬된 필드·구역과 지수 표기 없는 숫자로 고정.
    return '[' + ','.join(
        '{"cellId":' + json.dumps(p['cellId'], ensure_ascii=False)
        + ',"facilityType":' + json.dumps(p['facilityType'])
        + ',"areaM2":' + plain(p['areaM2']) + '}'
        for p in sorted(placements, key=lambda p: p['cellId'])) + ']'


def replay(model_source, declared):
    model = decoded(model_source)
    model_hash = digest(model_source)
    require(declared['policy'] == POLICY and declared['schemaVersion'] == 1, '생성 정책 불일치')
    require(declared['modelHash'] == model_hash, '모델 원문 해시 불일치')
    settings = declared['settings']
    top = integer(settings['topK'], 2, 20)
    seed = integer(settings['seed'], 0, 2147483647)
    wanted = integer(settings['candidatesPerArm'], 1, 4)
    budget = number(settings['budgetKrw'])
    require(budget == budget.to_integral_value() and 1 <= budget <= number(model['budget']), '예산 범위 오류')
    max_count = integer(model['maxPlacements'], 0, 50)
    require(0 < len(model['cells']) <= 50, '모델 구역 수 오류')
    cells = {c['id']: c for c in model['cells']}
    require(len(cells) == len(model['cells']), '구역 ID 중복')
    costs = {key: number(model['unitCosts'][key]) for key in TYPES}
    require(all(value > 0 for value in costs.values()), '단가 범위 오류')
    for cell in cells.values():
        require(number(cell['maxAreaM2']) > 0 and set(cell['allowedTypes']) <= TYPES, '구역 설치 조건 오류')

    def canonical_and_cost(placements):
        require(type(placements) is list and len(placements) <= max_count, '설치 개수 초과')
        seen, canonical, cost = set(), [], Decimal(0)
        for p in placements:
            cell_id, facility, area = p['cellId'], p['facilityType'], number(p['areaM2'])
            require(cell_id in cells and cell_id not in seen, '구역 누락 또는 중복')
            cell = cells[cell_id]
            require(facility in cell['allowedTypes'] and 0 < area <= number(cell['maxAreaM2']), '설치 조건 오류')
            require(area.normalize().as_tuple().exponent >= -2, '면적 정밀도 오류')
            seen.add(cell_id)
            cost += area * costs[facility]
            canonical.append({'cellId': cell_id, 'facilityType': facility, 'areaM2': area})
        require(cost <= budget, '표본 또는 후보 예산 초과')
        return sorted(canonical, key=lambda p: p['cellId']), cost

    samples = [s['sample'] for s in declared['sources']]
    require(2 <= len(samples) <= 50, '표본 수 오류')
    originals, unique, ids = [], {}, set()
    for s in sorted(samples, key=lambda v: v['jobId']):
        require(str(UUID(s['jobId'])) == s['jobId'] and str(UUID(s['versionId'])) == s['versionId'], '식별자 형식 오류')
        require(s['jobId'] not in ids, '중복 요청 작업')
        ids.add(s['jobId'])
        require(digest(model_hash + '\n' + s['placementsSource']) == s['inputHash'], '원본 입력 해시 불일치')
        placements, cost = canonical_and_cost(decoded(s['placementsSource']))
        require(cost == number(s['costKrw']), '원본 비용 불일치')
        score = number(s['score'])
        require(-99999999 <= score <= 100, '점수 범위 오류')
        physical = digest(model_hash + '\n' + placements_json(placements))
        item = {'sample': s, 'physicalHash': physical, 'placements': placements, 'selected': False}
        if physical in unique:
            previous = unique[physical]['sample']
            require(number(previous['score']) == score and number(previous['costKrw']) == cost, '동일 배치 결과 불일치')
        else:
            unique[physical] = item
        originals.append(item)
    require(len(unique) >= 2, '서로 다른 물리 배치 부족')
    ranked = sorted(unique.values(), key=lambda s: (-number(s['sample']['score']), s['physicalHash']))
    cutoff = number(ranked[min(top, len(ranked)) - 1]['sample']['score'])
    elite = [s for s in ranked if number(s['sample']['score']) >= cutoff]
    elite_ids = {s['sample']['jobId'] for s in elite}
    for s in originals:
        s['selected'] = s['sample']['jobId'] in elite_ids
    distributions = []
    for cell_id, cell in sorted(cells.items()):
        counts = {}
        for s in elite:
            p = next((p for p in s['placements'] if p['cellId'] == cell_id), None)
            key = 'NONE'
            if p:
                selected_bin = min(BINS, key=lambda b: (abs(p['areaM2'] * 100 - number(cell['maxAreaM2']) * b), b))
                key = p['facilityType'] + ':' + str(selected_bin)
            counts[key] = counts.get(key, 0) + 1
        options = [{'key': 'NONE', 'facilityType': None, 'percent': 0, 'areaM2': 0, 'costKrw': 0,
                    'observedCount': counts.get('NONE', 0), 'patternWeight': counts.get('NONE', 0) + 1}]
        for facility in sorted(set(cell['allowedTypes'])):
            for percent in BINS:
                area = (number(cell['maxAreaM2']) * percent / 100).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
                if area == 0:
                    continue
                key = facility + ':' + str(percent)
                count = counts.get(key, 0)
                options.append({'key': key, 'facilityType': facility, 'percent': percent, 'areaM2': area,
                                'costKrw': area * costs[facility], 'observedCount': count, 'patternWeight': count + 1})
        distributions.append({'cellId': cell_id, 'options': options})

    def random_key(arm, attempt, purpose, cell_id):
        return digest('\n'.join((POLICY, model_hash, str(seed), arm, str(attempt), purpose, cell_id)))

    candidates, arms = [], []
    for arm in ARMS:
        accepted = set()
        attempt = empty = original = duplicate = 0
        while attempt < 128 and len(accepted) < wanted:
            current = attempt
            attempt += 1
            order = sorted(distributions, key=lambda d: (random_key(arm, current, 'ORDER', d['cellId']), d['cellId']))
            placements, remaining = [], budget
            for d in order:
                options = [o for o in d['options'] if o['facilityType'] is None or
                           (len(placements) < max_count and o['costKrw'] <= remaining)]
                weights = [o['patternWeight'] if arm == 'PATTERN' else 1 for o in options]
                ticket = int(random_key(arm, current, 'CHOICE', d['cellId']), 16) % sum(weights)
                for option, weight in zip(options, weights, strict=True):
                    ticket -= weight
                    if ticket < 0:
                        picked = option
                        break
                if picked['facilityType'] is not None:
                    placements.append({'cellId': d['cellId'], 'facilityType': picked['facilityType'], 'areaM2': picked['areaM2']})
                    remaining -= picked['costKrw']
            placements, cost = canonical_and_cost(placements)
            raw = placements_json(placements)
            key = digest(model_hash + '\n' + raw)
            if not placements:
                empty += 1
                continue
            if key in unique:
                original += 1
                continue
            if key in accepted:
                duplicate += 1
                continue
            accepted.add(key)
            candidates.append({'arm': arm, 'ordinal': len(accepted), 'attempt': current, 'inputHash': key,
                               'placementsSource': raw, 'placements': placements, 'costKrw': cost})
        require(len(accepted) == wanted, '정해진 시도 수 안에서 새 후보 생성 불가')
        arms.append({'arm': arm, 'attempts': attempt, 'emptyRejected': empty, 'sourceRejected': original, 'duplicateRejected': duplicate})
    pattern = {c['inputHash'] for c in candidates if c['arm'] == 'PATTERN'}
    shared = sum(c['inputHash'] in pattern for c in candidates if c['arm'] == 'UNIFORM')
    return {'schemaVersion': 1, 'policy': POLICY, 'modelHash': model_hash, 'settings': settings,
            'requestedCount': len(samples), 'uniquePhysicalCount': len(unique), 'trainingCount': len(elite), 'cutoffScore': cutoff,
            'smoothing': 1, 'binPercentages': BINS, 'drawLimit': 128, 'sources': originals,
            'distributions': distributions, 'arms': arms, 'candidates': candidates, 'sharedCandidateCount': shared}


def verify(model_source, declared):
    expected = replay(model_source, declared)
    for key in expected:
        require(key in declared and declared[key] == expected[key], '생성 계보 불일치: ' + key)
    require(set(declared) == set(expected), '알 수 없는 생성 계보 필드')
    return expected

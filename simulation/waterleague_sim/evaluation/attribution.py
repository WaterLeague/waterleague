"""전체 유역 조합 계산의 순열 표본 Shapley 귀속. 운영 순위 게시와 분리."""
from fractions import Fraction
import hashlib
import json
import math
import re

from .exception import EvaluationError, require
from .service import _compare, compare, validate_policy, validate_record
from .values import canonical, digest, encoded

ALGORITHM = 'SHA256_COUNTER_FISHER_YATES_V1'


def permutation(member_ids, seed, index):
    result, counter = list(member_ids), 0
    for i in range(len(result) - 1, 0, -1):
        bound = i + 1
        limit = 2 ** 256 - 2 ** 256 % bound
        while True:
            raw = canonical([ALGORITHM, seed, index, counter])
            candidate = int.from_bytes(hashlib.sha256(raw).digest(), 'big')
            counter += 1
            if candidate < limit:
                break
        j = candidate % bound
        result[i], result[j] = result[j], result[i]
    return result


def _members(rows):
    require(isinstance(rows, list) and 1 <= len(rows) <= 512, 'ATTRIBUTION_MEMBERS_INVALID')
    ids, facilities, result = set(), set(), []
    for row in rows:
        require(isinstance(row, dict) and set(row) == {'memberId', 'districtCode', 'facilityIds'},
                'ATTRIBUTION_MEMBER_INVALID')
        member, district, owned = row['memberId'], row['districtCode'], row['facilityIds']
        require(isinstance(member, str) and re.fullmatch(r'[a-zA-Z0-9_.-]{1,100}', member)
                and member not in ids and isinstance(district, str) and re.fullmatch(r'11[0-9]{3}', district)
                and isinstance(owned, list) and 1 <= len(owned) <= 10_000
                and all(isinstance(v, str) and re.fullmatch(r'[a-zA-Z0-9_.-]{1,100}', v) for v in owned)
                and len(set(owned)) == len(owned) and not facilities.intersection(owned),
                'ATTRIBUTION_OWNERSHIP_INVALID')
        ids.add(member)
        facilities.update(owned)
        result.append({'memberId': member, 'districtCode': district, 'facilityIds': sorted(owned)})
    require(len(facilities) <= 100_000, 'ATTRIBUTION_FACILITY_LIMIT')
    return sorted(result, key=lambda r: r['memberId'])


def _summary(moments, count):
    output = {}
    for key, (total, squares) in moments.items():
        mean = total / count
        variance = (squares - total * total / count) / (count - 1) if count > 1 else None
        require(variance is None or variance >= 0, 'ATTRIBUTION_VARIANCE_INVALID')
        output[key] = {'mean': encoded(mean),
                       'sampleVariance': encoded(variance) if variance is not None else None,
                       'standardError': math.sqrt(float(variance / count)) if variance is not None else None}
    return output


def attribute(policy, members, evaluate, *, seed, samples, max_evaluations, cache=None):
    """evaluate(회원 튜플, 시설 튜플)는 해당 조합의 전체 유역을 계산해야 한다."""
    policy_hash = validate_policy(policy)
    policy = json.loads(canonical(policy))
    members = _members(members)
    require(isinstance(seed, str) and re.fullmatch(r'[0-9a-f]{64}', seed)
            and type(samples) is int and 1 <= samples <= 4096
            and type(max_evaluations) is int and 0 <= max_evaluations <= 10000,
            'ATTRIBUTION_PLAN_INVALID')
    require(callable(evaluate) and (cache is None or isinstance(cache, dict)), 'ATTRIBUTION_EVALUATOR_INVALID')
    cache = {} if cache is None else cache
    binding = digest({'policy': policy, 'members': members})
    by_id = {row['memberId']: row for row in members}
    ids = list(by_id)
    used, evaluations, trace = {}, 0, []
    member_moments, district_moments = {}, {}
    whole, failure, pending, targets = None, None, None, None

    def obtain(participants):
        nonlocal evaluations, pending
        selected = sorted(participants)
        owned = sorted(f for member in selected for f in by_id[member]['facilityIds'])
        request = {'bindingSha256': binding, 'memberIds': selected, 'facilityIds': owned}
        key = digest(request)
        pending = {'coalitionKey': key, 'memberIds': selected}
        if key in cache:
            receipt = cache[key]
            require(isinstance(receipt, dict) and receipt.get('request') == request
                    and digest(receipt.get('record')) == receipt.get('recordSha256'),
                    'ATTRIBUTION_CACHE_MISMATCH')
        else:
            require(evaluations < max_evaluations, 'ATTRIBUTION_EVALUATION_LIMIT')
            evaluations += 1
            try:
                record = evaluate(tuple(selected), tuple(owned))
                validate_record(record, policy['context'])
                record = json.loads(canonical(record))
            except EvaluationError:
                raise
            except Exception:
                raise EvaluationError('COALITION_EVALUATION_FAILED') from None
            receipt = {'request': request, 'record': record, 'recordSha256': digest(record)}
            cache[key] = receipt
        validate_record(receipt['record'], policy['context'])
        used[key] = json.loads(canonical(receipt))
        return key, used[key]['record']

    def values(baseline, record):
        _, value, blockers = _compare(policy, baseline, record)
        if blockers:
            raise EvaluationError('ATTRIBUTION_COALITION_INCOMPLETE')
        return value

    def accumulate(destination, identifier, value):
        moments = destination.setdefault(identifier, {k: [Fraction(0), Fraction(0)] for k in value})
        for key, number in value.items():
            moments[key][0] += number
            moments[key][1] += number * number

    try:
        baseline_key, baseline = obtain([])
        values(baseline, baseline)
        _, full = obtain(ids)
        whole = compare(policy, baseline, full)
        targets = values(baseline, full)
        for index in range(samples):
            order = permutation(ids, seed, index)
            selected, prefix_keys = [], [baseline_key]
            previous = {key: Fraction(0) for key in targets}
            increments, district_increments = {}, {}
            for member in order:
                selected.append(member)
                coalition_key, record = obtain(selected)
                current = values(baseline, record)
                increments[member] = {key: current[key] - previous[key] for key in targets}
                district = by_id[member]['districtCode']
                district_increments.setdefault(district, {key: Fraction(0) for key in targets})
                for key in targets:
                    district_increments[district][key] += increments[member][key]
                previous = current
                prefix_keys.append(coalition_key)
            require(all(sum(row[key] for row in increments.values()) == targets[key] for key in targets),
                    'ATTRIBUTION_SUM_MISMATCH')
            # 실패한 중간 순열은 통계에 넣지 않아 참가자마다 표본 수가 달라지는 것을 막는다.
            for member, value in increments.items():
                accumulate(member_moments, member, value)
            for district, value in district_increments.items():
                accumulate(district_moments, district, value)
            trace.append({'index': index, 'memberOrder': order, 'coalitionKeys': prefix_keys})
        pending = None
    except EvaluationError as error:
        failure = error.code

    count = len(trace)
    conservation = None
    if count:
        conservation = {}
        for key, target in targets.items():
            individual = sum(row[key][0] for row in member_moments.values()) / count
            district = sum(row[key][0] for row in district_moments.values()) / count
            require(individual == district == target, 'ATTRIBUTION_SUM_MISMATCH')
            conservation[key] = {'totalEffect': encoded(target), 'memberSum': encoded(individual),
                                 'districtSum': encoded(district), 'residual': encoded(Fraction(0))}
    return {'schemaVersion': 1, 'policySha256': policy_hash, 'bindingSha256': binding,
            'context': policy['context'], 'members': members, 'algorithm': ALGORITHM, 'seed': seed,
            'requestedPermutations': samples, 'completedPermutations': count,
            'newEvaluations': evaluations, 'cachedCoalitionsUsed': len(used),
            'status': 'WITHHELD' if failure else 'ESTIMATED_DIAGNOSTIC', 'rankingEligible': False,
            'failureCode': failure, 'pendingCoalition': pending,
            'wholeGroupComparison': whole, 'conservation': conservation,
            'memberEstimates': {m: _summary(row, count) for m, row in member_moments.items()},
            'districtEstimates': {d: _summary(row, count) for d, row in district_moments.items()},
            'districtAggregation': 'MEMBER_AFFILIATION_NOT_IMPACT_LOCATION',
            'errorMethod': 'IID_PERMUTATION_SAMPLE_STANDARD_ERROR_NOT_CONFIDENCE_BOUND',
            'coalitionEvaluations': used, 'permutations': trace}

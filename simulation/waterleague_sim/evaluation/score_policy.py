"""평가 전 고정한 코드·자료 정책·실행 조건과 정밀도 검증."""
import hashlib
import importlib.metadata
import json
import platform
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
POLICY_FILE = ROOT/'backend/src/main/resources/evaluation/game-score-policy-v1.json'
VERSION = 'ABSOLUTE_ACCOUNTED_VOLUME_RANKING_V1'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()


def source_policy():
    package = ROOT/'simulation/waterleague_sim'
    paths = list(package.rglob('*.py')) + [ROOT/name for name in (
        'simulation/pyproject.toml', 'simulation/uv.lock', 'simulation/native/lid_snapshot.inc',
        'backend/src/main/resources/native-game/v2/catalog.json',
        'backend/src/main/resources/native-play/v1/manifest.json',
        'backend/src/main/resources/facilities/reference-surfaces-v1.json',
        'backend/src/main/resources/facilities/life-cycle-method-v1.json',
        'backend/src/main/resources/facilities/site-suitability-v1.json',
        'backend/src/main/resources/facilities/pavement-maintenance-v1.json',
        'backend/src/main/resources/budget/seoul-2026.json',
        'backend/src/main/resources/budget/seoul-accounting-v5.json',
        'backend/src/main/resources/facilities/cistern-game-v1.json',
        'backend/src/main/resources/facilities/cistern-demand-v1.json',
        'backend/src/main/resources/facilities/game-prices-202608-v1.json',
        'backend/src/main/java/io/waterleague/cost/repository/GamePriceCatalog.java',
        'backend/src/main/java/io/waterleague/cost/service/CostService.java',
        'backend/src/main/java/io/waterleague/historical/service/HistoricalService.java',
        'backend/src/main/java/io/waterleague/historical/service/HistoricalDesignService.java',
        'backend/src/main/java/io/waterleague/spatial/repository/NativePlayRepository.java',
        'backend/src/main/resources/facilities/epa-designs-v5.json',
        'backend/src/main/java/io/waterleague/installation/repository/CisternGameCatalog.java',
        'scripts/build_score_policy.py',
        'backend/src/main/java/io/waterleague/evaluation/service/ScorePolicyService.java',
        'backend/src/main/java/io/waterleague/installation/entity/SiteSuitability.java',
        'backend/src/main/java/io/waterleague/installation/repository/SiteCatalogRepository.java',
        'backend/src/main/java/io/waterleague/weekly/service/WeeklyService.java',
        'backend/src/main/java/io/waterleague/weekly/repository/WeeklyRepository.java',
        'backend/src/main/java/io/waterleague/historical/service/HistoricalSubmissionService.java',
        'backend/src/main/java/io/waterleague/historical/repository/HistoricalSubmissionRepository.java')]
    if any(path.is_symlink() or not path.is_file() for path in paths):
        raise ValueError('LIVE_SCORE_POLICY_SOURCE_INVALID')
    return {
        'version': VERSION, 'metric': 'surfaceAccountedVolumeM3', 'unit': 'm3',
        'direction': 'HIGHER_SIGNED_IMPROVEMENT_IS_BETTER',
        'scope': 'SELECTED_INDEPENDENT_SURFACES_ONLY', 'rounding': 'HALF_EVEN',
        'weeklyDecimalPlaces': 9, 'submissionDecimalPlaces': 18,
        'tie': 'EXACT_STORED_DECIMAL_EQUALITY', 'rank': 'COMPETITION_1_1_3',
        'weeklyPlayerTieOrder': ['playerId'],
        'weeklyDistrictTieOrder': ['districtName', 'districtId'],
        'submissionTieOrder': ['submittedAt', 'id'],
        'relativeUsedForRanking': False, 'compositeScore': None,
        'missingPolicy': 'UNAVAILABLE_WITH_REASON_NO_ZERO_OR_REDISTRIBUTION',
        'weeklyWindow': 'KST_MONDAY_INSTALLATION_AFTER_CONFIRMED_OBSERVATION',
        'submissionWindow': 'FULL_EVENT_AFTER_ANTECEDENT',
        'cohort': 'POLICY_RUNTIME_TEMPORAL_RULE_AND_FROZEN_EVENT_RULES',
        'files': {str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in sorted(paths)},
    }


def verified_policy():
    try:
        raw = POLICY_FILE.read_bytes()
        value = json.loads(raw)
        if value != source_policy() or value['files'] != _LOADED_FILES:
            raise ValueError()
        return raw, value
    except (OSError, ValueError, TypeError):
        raise ValueError('LIVE_SCORE_POLICY_INVALID') from None


def freeze(mode, binding):
    from ..engine.continuous import engine_identity
    if mode not in ('WEEKLY', 'SUBMISSION') or not isinstance(binding, str) or not binding:
        raise ValueError('LIVE_SCORE_CONTEXT_INVALID')
    raw, _ = verified_policy()
    context = {'version': VERSION, 'policySha256': digest(raw), 'mode': mode, 'binding': binding,
               'runtime': {'engine': engine_identity(), 'python': platform.python_version(),
                           'system': platform.system(), 'machine': platform.machine(),
                           'packages': {name: importlib.metadata.version(name) for name in ('pyproj', 'shapely')}}}
    return {'sha256': digest(encode(context)), **context}


def verify(context, mode, binding):
    if context != freeze(mode, binding):
        raise ValueError('LIVE_SCORE_CONTEXT_INVALID')
    return context


def archive(directory, context):
    raw, _ = verified_policy()
    directory = Path(directory)
    (directory/'score-policy.json').write_bytes(raw)
    (directory/'score-context.json').write_bytes(encode(context))
    (directory/'score_policy.py').write_bytes(Path(__file__).read_bytes())


def quantize(value, places):
    if places not in (9, 18) or isinstance(value, bool):
        raise ValueError('LIVE_SCORE_VALUE_INVALID')
    try:
        raw = Decimal(str(value))
        if not raw.is_finite() or abs(raw) >= Decimal('1e15'):
            raise ValueError()
        with localcontext() as ctx:
            ctx.prec = 50
            return raw.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN)
    except (ValueError, ArithmeticError):
        raise ValueError('LIVE_SCORE_VALUE_INVALID') from None


# 실행 중 파일만 바뀌어 이전 메모리 코드가 새 정책을 게시하는 것을 차단한다.
_LOADED_FILES = source_policy()['files']

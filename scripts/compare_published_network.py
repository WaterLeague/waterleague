"""공개 기준안·LID안의 수치 파생 입력과 시간 세분 결과 보존."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))

from waterleague_sim.engine import network
from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.ingestion.network_variant import derive
from waterleague_sim.ingestion.published_network import digest, load_archive

PROFILES = [
    {'id': 'published-extran', 'options': {'SURCHARGE_METHOD': 'EXTRAN'}},
    *[{'id': name, 'options': {'SURCHARGE_METHOD': 'SLOT', 'MAX_TRIALS': 200,
         'ROUTING_STEP': maximum, 'MINIMUM_STEP': minimum}}
      for name, maximum, minimum in [('slot-125ms', .125, .05),
                                     ('slot-62-5ms', .0625, .025), ('slot-31-25ms', .03125, .01)]]]


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n')


def compare(coarse, fine):
    require(coarse['calendarDurationSeconds'] == fine['calendarDurationSeconds']
            and coarse['durationSeconds'] == fine['durationSeconds'], 'NETWORK_COMPARISON_TIME_MISMATCH')
    changes = {}
    for key in ('outflowM3', 'floodingM3', 'storageM3', 'externalInflowM3', 'runoffInflowM3'):
        a, b = coarse['final']['totals'][key], fine['final']['totals'][key]
        changes[key] = {'coarse': a, 'fine': b, 'signedDifference': b-a,
                       'relativeToFinePercent': 100*(b-a)/abs(b) if b else None}
    return {'bothNumericallyPassed': coarse['numericalStatus'] == fine['numericalStatus'] == 'PASSED',
        'quantities': changes, 'maximumFinalNodeHeadDifferenceM': max(
            abs(coarse['final']['nodes'][key]['headM'] - row['headM'])
            for key, row in fine['final']['nodes'].items()),
        'meaning': '동일 연구 수리 입력의 두 시간 설정 비교이며 현장 정확도·운영 승인 판정이 아님'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.exists(), 'NETWORK_COMPARISON_OUTPUT_EXISTS')
    source_path = ROOT / 'data/manifests/mendeley-seocho-network-v3.json'
    source, source_hash, inputs = load_archive(ROOT, source_path)
    context_path = ROOT / 'data/manifests/seocho-study-context-v1.json'
    context = json.loads(context_path.read_text())
    require(context['sourceManifestSha256'] == source_hash and context['datasetDoi'] == source['doi']
            and context['historicalReconstructionEligible'] is False and context['rankingEligible'] is False,
            'NETWORK_STUDY_CONTEXT_INVALID')
    output.mkdir(parents=True)
    shutil.copyfile(source_path, output / 'source-manifest.json')
    shutil.copyfile(context_path, output / 'study-context.json')
    source_paths = [Path(__file__), ROOT / 'scripts/build_network_swmm.py',
        ROOT / 'scripts/build_live_swmm.py', ROOT / 'simulation/native/network_snapshot.inc',
        ROOT / 'simulation/pyproject.toml', ROOT / 'simulation/uv.lock',
        *sorted((ROOT / 'simulation/waterleague_sim').rglob('*.py'))]
    for path in source_paths:
        target = output / 'source' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    engine_identity = network.identity()
    (output / 'engine').mkdir()
    for path in (network.library_path(), network.library_path().parent / 'network-build.json',
                 ROOT / 'tmp/swmm/source.tar.gz'):
        shutil.copyfile(path, output / 'engine' / path.name)
    results, cases, summaries = {}, [], []
    for name, suffix in [('baseline', '/Baseline/seocho2_baseline.inp'),
                         ('lid', '/Baseline+LID/seocho2_baseline LID.inp')]:
        matches = [row for row in inputs if row['member'].endswith(suffix)]
        require(len(matches) == 1, 'NETWORK_COMPARISON_SOURCE_MISSING')
        source_row = matches[0]
        for profile in PROFILES:
            case_id = name + '-' + profile['id']
            case_dir = output / case_id
            case_dir.mkdir()
            (case_dir / 'original.inp').write_bytes(source_row['raw'])
            raw, transformation = derive(source_row['raw'], profile)
            (case_dir / 'variant.inp').write_bytes(raw)
            write(case_dir / 'transformation.json', transformation)
            case = {'id': case_id, 'design': name, 'profile': profile,
                    'member': source_row['member'], 'transformation': transformation}
            try:
                with EngineProcess('network', raw.decode(), case_dir / 'calculation', native_duration=True) as engine:
                    result = engine.call('run', 300)['result']
                results[case_id] = result
                case.update({key: result[key] for key in ('numericalStatus', 'convergence', 'numericalQuality',
                    'numericalConfiguration', 'calendarShortfallSeconds', 'timeWindowPolicy')})
                case['totals'] = result['final']['totals']
            except FloodModelError as error:
                case.update({'numericalStatus': 'FAILED', 'failureCode': str(error)})
            write(case_dir / 'summary.json', case)
            cases.append(case)
            print(json.dumps({'case': case_id, 'status': case['numericalStatus']}), flush=True)
        a, b = (results.get(name + '-slot-' + step) for step in ('62-5ms', '31-25ms'))
        if a is not None and b is not None:
            summaries.append({'design': name, **compare(a, b)})
    effects = []
    for profile in PROFILES:
        a, b = (results.get(name + '-' + profile['id']) for name in ('baseline', 'lid'))
        if a is None or b is None:
            continue
        effects.append({'profileId': profile['id'],
            'bothNumericallyPassed': a['numericalStatus'] == b['numericalStatus'] == 'PASSED',
            'floodingReductionM3': a['final']['totals']['floodingM3'] - b['final']['totals']['floodingM3'],
            'outflowReductionM3': a['final']['totals']['outflowM3'] - b['final']['totals']['outflowM3'],
            'rankingEligible': False})
    manifest = {'schemaVersion': 1, 'classification': 'PUBLISHED_RESEARCH_NUMERICAL_RESOLUTION_COMPARISON',
        'sourceManifestSha256': source_hash, 'contextSha256': digest(context_path.read_bytes()),
        'attribution': source['attribution'], 'licence': source['licence'], 'engine': engine_identity,
        'profiles': PROFILES, 'cases': cases, 'timeRefinement': summaries, 'designEffects': effects,
        'rankingEligible': False, 'historicalReconstructionEligible': False,
        'limitations': context['limitations'] + ['SLOT 가상 슬롯 수치 근사와 EXTRAN 결과의 차이 보존',
            '지표 결합·최대 수심/첨두·격자 수렴·독립 현장 검증 미완료',
            '기준안·LID 두 설계의 하루 계산에 한정, 다른 관망/40일 입력으로 일반화 금지'],
        'files': {str(path.relative_to(output)): digest(path.read_bytes())
                  for path in sorted(output.rglob('*')) if path.is_file()}}
    write(output / 'manifest.json', manifest)
    print(json.dumps({'cases': len(cases), 'manifestSha256': digest((output / 'manifest.json').read_bytes())}), flush=True)


if __name__ == '__main__':
    main()

"""실제 시간별 수위와 분 강우의 동시 입력·시간 세분·재현 증거."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))

from verify_observed_surface_rainfall import specification
from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.forcing.surface_run import run_observed_surface
from waterleague_sim.ingestion.wamis_stage import diagnostic_boundary, read_archive
from waterleague_sim.reference.flood_cases import mesh


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    directory = args.output.resolve()
    require(not directory.exists(), 'STAGE_VERIFICATION_OUTPUT_EXISTS')
    directory.mkdir(parents=True)
    manifest = ROOT / 'data/manifests/wamis-stage-1018662-20220725-20220820.json'
    normalized, raw_sources = read_archive(str(manifest.relative_to(ROOT)), sha(manifest))
    for name, raw in raw_sources.items():
        target = directory / 'observed-stage' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    import numpy as np
    model = mesh(4, 2, 20, 10, bed=lambda x, y: 2 + .02*x,
                 water=lambda x, z: 2.98 - z)
    rain = specification(model, minutes=60, two_stations=False)
    stage = diagnostic_boundary(normalized, rain['startUtc'], rain['endUtc'])
    model.update(schemaVersion=2, verticalDatum=stage['verticalDatum'], startUtc=rain['startUtc'],
                 durationSeconds=3600, evidence='REAL_GAUGE_AND_RAIN_ON_SYNTHETIC_DOMAIN_NOT_SEOUL')
    model['boundaryConditions']['left'] = stage
    sources = [Path(__file__), ROOT / 'scripts/verify_observed_surface_rainfall.py',
               ROOT / 'simulation/uv.lock', ROOT / 'data/manifests/anuga-4.0.1.json']
    for folder in ('forcing', 'ingestion', 'engine', 'reference'):
        sources.extend(sorted((ROOT / 'simulation/waterleague_sim' / folder).glob('*.py')))
    for source in sources:
        target = directory / 'source' / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    report = {'schemaVersion': 1, 'classification': model['evidence'], 'rankingEligible': False,
        'stageSourceManifestSha256': sha(manifest), 'stage': stage,
        'sourceCode': {str(p.relative_to(ROOT)): sha(p) for p in sources}, 'cases': [],
        'limitations': ['눈금 기준의 합성 200m² 지형; 실제 서울 지형·관망·침수 검증 아님',
            '시간 관측 사이 선형 수위·0 운동량은 명시된 경계 근사',
            '현재 영점표고를 2022년에 소급 가산하지 않음',
            '단일 강우 관측소 적용; 면적 강우 실측·전체 물순환 재현 아님']}
    results = {}
    for name, maximum_step, fixed in [('observed-01s', .1, False), ('observed-005s', .05, False),
                                       ('replay-01s', .1, False), ('fixed-start-01s', .1, True)]:
        candidate = deepcopy(model)
        candidate['maxStepSeconds'] = maximum_step
        if fixed:
            candidate['boundaryConditions']['left'] = {'type': 'FIXED_STAGE', 'stageM': 2.98}
        path = directory / name
        entry = {'name': name, 'maxStepSeconds': maximum_step}
        try:
            result = run_observed_surface(candidate, rain, path)
            results[name] = result
            entry.update(status=result['numericalStatus'], quality=result['numericalQuality'],
                final={k: v for k, v in result['final'].items()
                       if k not in ('depthM', 'velocityXMps', 'velocityYMps')},
                minimumDepthM=min(result['final']['depthM']), maximumDepthM=max(result['final']['depthM']),
                rainfall=result['observedRainfall'], resultSha256=sha(path / 'observed-surface-result.json'))
        except FloodModelError as error:
            entry.update(status='FAILED', code=str(error))
        report['cases'].append(entry)
        print(name, entry['status'], entry.get('final', entry.get('code')), flush=True)
    if all(name in results for name in ('observed-01s', 'observed-005s', 'replay-01s', 'fixed-start-01s')):
        a, b = (results[name]['final'] for name in ('observed-01s', 'observed-005s'))
        report['comparison'] = {'exactReplay': a == results['replay-01s']['final'],
            'maximumDepthDifferenceM': max(abs(x-y) for x, y in zip(a['depthM'], b['depthM'])),
            'storageDifferenceM3': a['storageM3'] - b['storageM3'],
            'variableMinusFixedStorageM3': a['storageM3'] - results['fixed-start-01s']['final']['storageM3']}
    write(directory / 'summary.json', report)
    files = {str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}
    write(directory / 'artifact-manifest.json', {'schemaVersion': 1, 'files': files})
    print(json.dumps({'manifestSha256': sha(directory / 'artifact-manifest.json'),
                      'files': len(files), 'comparison': report.get('comparison')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()

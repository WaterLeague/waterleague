"""실제 강우·기상과 공개 토성 매개변수의 지표 손실 수지 진단."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))

from verify_surface_infiltration import soil_source
from verify_observed_surface_rainfall import specification
from waterleague_sim.engine.flood_errors import require
from waterleague_sim.engine.surface_infiltration import library_path
from waterleague_sim.forcing.surface_evaporation import TRANSFER
from waterleague_sim.forcing.surface_run import run_observed_surface
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
    require(not directory.exists(), 'EVAPORATION_VERIFICATION_OUTPUT_EXISTS')
    directory.mkdir(parents=True)
    soil = soil_source(directory / 'public-soil')
    sources = [Path(__file__), ROOT / 'scripts/verify_surface_infiltration.py',
        ROOT / 'scripts/verify_observed_surface_rainfall.py', ROOT / 'scripts/prepare_site_physics.py',
        ROOT / 'scripts/build_surface_infiltration.py', ROOT / 'simulation/native/surface_infiltration.inc',
        ROOT / 'simulation/uv.lock', ROOT / 'data/manifests/anuga-4.0.1.json']
    for folder in ('engine', 'forcing', 'ingestion', 'reference'):
        sources.extend(sorted((ROOT / 'simulation/waterleague_sim' / folder).glob('*.py')))
    for source in sources:
        target = directory / 'source' / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    native = directory / 'native'
    native.mkdir()
    for source in (library_path(), library_path().parent / 'soil-build.json', ROOT / 'tmp/swmm/source.tar.gz'):
        shutil.copyfile(source, native / source.name)
    base = mesh(2, 2, 10, 10)
    rain = specification(base, minutes=359, two_stations=False)
    base.update(schemaVersion=2, evidence='OBSERVED_WEATHER_PUBLIC_TEXTURE_ON_SYNTHETIC_DOMAIN_NOT_SEOUL',
                startUtc=rain['startUtc'], durationSeconds=359 * 60)
    base['infiltration'] = {'schemaVersion': 1, 'method': 'GREEN_AMPT', 'ownershipPolicy': 'SURFACE_ONLY',
        'initialization': 'EPA_INITIAL_DEFICIT_SEED', 'recoveryFactor': 1., 'imperviousTriangles': [],
        'evidence': {'soil': soil, 'initialMoistureDeficit': '명시적 0.25 시드; 현장 수분 관측 아님'},
        'regions': [{'triangles': list(range(len(base['triangles']))), 'perviousFraction': 1.,
            'suctionMm': soil['suctionMm'], 'conductivityMmH': soil['conductivityRangeMmH'][0],
            'initialMoistureDeficit': .25, 'evidence': {'parameters': soil, 'area': '합성 전면 투수 격자'}}]}
    name = 'seoul-20220808-fao56-v1.json'
    base['evaporation'] = {'schemaVersion': 1, 'type': 'ARCHIVED_FAO56', 'ownershipPolicy': 'SURFACE_ONLY',
        'surfaceTransfer': TRANSFER,
        'reference': {'file': name, 'sha256': sha(ROOT / 'data/derived/evaporation' / name)},
        'evidence': '서울 108의 기준 잔디 증발산을 합성 지표수 잠재 손실률로 적용; 표면별 보정 미수행'}
    results, cases = {}, []
    for name, step, enabled in [('observed-1s', 1., True), ('observed-05s', .5, True),
                                ('replay-1s', 1., True), ('without-evaporation-1s', 1., False)]:
        model = deepcopy(base)
        model['maxStepSeconds'] = step
        if not enabled:
            model.pop('evaporation')
        result = run_observed_surface(model, rain, directory / name)
        results[name] = result
        final = result['final']
        surface = json.loads((directory / name / 'surface/surface-result.json').read_bytes())
        cases.append({'name': name, 'status': result['numericalStatus'], 'maximumStepSeconds': step,
            'final': {k: v for k, v in final.items() if k not in ('depthM', 'velocityXMps', 'velocityYMps')},
            'rainfall': result['observedRainfall'], 'quality': result['numericalQuality'],
            'evaporation': surface.get('evaporation'),
            'resultSha256': sha(directory / name / 'observed-surface-result.json')})
        print(name, cases[-1]['final'], flush=True)
    a, b, control = [results[name]['final'] for name in ('observed-1s', 'observed-05s', 'without-evaporation-1s')]
    comparison = {'exactReplay': a == results['replay-1s']['final'],
        'evaporationDifferenceM3': a['surfaceEvaporationM3'] - b['surfaceEvaporationM3'],
        'infiltrationDifferenceM3': a['infiltrationM3'] - b['infiltrationM3'],
        'storageDifferenceM3': a['storageM3'] - b['storageM3'],
        'maximumDepthDifferenceM': max(abs(x-y) for x, y in zip(a['depthM'], b['depthM'])),
        'withMinusWithoutEvaporationStorageM3': a['storageM3'] - control['storageM3'],
        'withMinusWithoutEvaporationInfiltrationM3': a['infiltrationM3'] - control['infiltrationM3']}
    report = {'schemaVersion': 1, 'classification': base['evidence'], 'rankingEligible': False,
        'soil': soil, 'cases': cases, 'comparison': comparison,
        'sourceCode': {str(source.relative_to(ROOT)): sha(source) for source in sources},
        'limitations': ['합성 평탄 100m²·전면 투수·차단 경계; 실제 서울 침수 재현 아님',
            '실제 강우와 관측 기반 기준 잔디 증발산의 지표수 전용 가정',
            '현장 토성·다짐·초기 수분·선행 강우·식물/토양/지하수 증발산 미확정',
            '강우·침투·가용 지표수 제한 증발의 분할 계산; 현장 검증 등급 아님']}
    write(directory / 'summary.json', report)
    files = {str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}
    write(directory / 'artifact-manifest.json', {'schemaVersion': 1, 'files': files})
    require(comparison['exactReplay'] and all(case['status'] == 'PASSED' for case in cases),
            'EVAPORATION_DIAGNOSTIC_FAILED')
    print(json.dumps({'manifestSha256': sha(directory / 'artifact-manifest.json'),
                     'files': len(files), 'comparison': comparison}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()

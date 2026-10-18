"""공개 토성의 문헌 매개변수와 실제 강우를 사용하는 지표 침투 연결 진단."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))

from prepare_site_physics import SOILS
from verify_observed_surface_rainfall import specification
from waterleague_sim.engine.flood_errors import require
from waterleague_sim.engine.surface_infiltration import library_path
from waterleague_sim.forcing.surface_run import run_observed_surface
from waterleague_sim.reference.flood_cases import mesh


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n')


def soil_source(directory):
    manifest = ROOT / 'data/manifests/seoul-soil-20261018.json'
    raw = manifest.read_bytes()
    source = json.loads(raw)
    selected = None
    for page in source['pages']:
        path = ROOT / page['file']
        require(sha(path) == page['sha256'], 'SOIL_SOURCE_HASH_MISMATCH')
        features = json.loads(path.read_bytes())['response']['result']['featureCollection']['features']
        selected = next((f for f in features if f['id'] == 'LT_C_ASITDEEPSOIL.135003'), None)
        if selected is not None:
            target = directory / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            break
    require(selected is not None and selected['properties']['label'] == '사양질', 'SOIL_FEATURE_MISSING')
    target = directory / manifest.relative_to(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    low, high, suction, texture = SOILS[selected['properties']['label']]
    return {'sourceManifestSha256': sha(manifest), 'featureId': selected['id'],
        'soilClass': selected['properties']['label'], 'conductivityRangeMmH': [low, high],
        'suctionMm': suction, 'textureReference': texture,
        'status': 'PUBLIC_TEXTURE_CLASS_LITERATURE_ESTIMATE_NOT_FIELD_MEASUREMENT',
        'referenceUrl': 'https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P10145M6.TXT',
        'referenceSection': 'Appendix A.2',
        'assignment': '공개 성동 토성의 매개변수만 합성 격자에 적용; 실제 토지형상·피복 재현 아님'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    directory = args.output.resolve()
    require(not directory.exists(), 'INFILTRATION_OUTPUT_EXISTS')
    directory.mkdir(parents=True)
    soil = soil_source(directory / 'public-soil')
    sources = [Path(__file__), ROOT / 'scripts/prepare_site_physics.py',
        ROOT / 'scripts/verify_observed_surface_rainfall.py', ROOT / 'scripts/build_surface_infiltration.py',
        ROOT / 'simulation/native/surface_infiltration.inc', ROOT / 'simulation/uv.lock',
        ROOT / 'data/manifests/anuga-4.0.1.json']
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
    base.update(schemaVersion=2, evidence='OBSERVED_RAIN_PUBLIC_TEXTURE_ON_SYNTHETIC_DOMAIN_NOT_SEOUL')
    base['infiltration'] = {'schemaVersion': 1, 'method': 'GREEN_AMPT', 'ownershipPolicy': 'SURFACE_ONLY',
        'initialization': 'EPA_INITIAL_DEFICIT_SEED', 'recoveryFactor': 1., 'imperviousTriangles': [],
        'evidence': {'soil': soil, 'initialMoistureDeficit': '명시적 0.25 시드; 선행 관측 초기화 미적용',
                     'recoveryFactor': 'EPA 기본 경험식 계수 1; 현장 회복률 아님'},
        'regions': [{'triangles': list(range(len(base['triangles']))), 'perviousFraction': 1.,
            'suctionMm': soil['suctionMm'], 'conductivityMmH': soil['conductivityRangeMmH'][0],
            'initialMoistureDeficit': .25,
            'evidence': {'parameters': soil, 'perviousFraction': '합성 전면 투수 격자 조건'}}]}
    rain = specification(base, minutes=359, two_stations=False)
    results, cases = {}, []
    for name, step, upper in [('low-1s', 1., False), ('low-05s', .5, False),
                              ('replay-1s', 1., False), ('high-1s', 1., True)]:
        model = deepcopy(base)
        model['maxStepSeconds'] = step
        if upper:
            model['infiltration']['regions'][0]['conductivityMmH'] = soil['conductivityRangeMmH'][1]
        result = run_observed_surface(model, rain, directory / name)
        results[name] = result
        final = result['final']
        cases.append({'name': name, 'status': result['numericalStatus'], 'maximumStepSeconds': step,
            'final': {k: v for k, v in final.items() if k not in ('depthM', 'velocityXMps', 'velocityYMps')},
            'rainfall': result['observedRainfall'], 'quality': result['numericalQuality'],
            'resultSha256': sha(directory / name / 'observed-surface-result.json')})
        print(name, cases[-1]['final'], flush=True)
    a, b, high = [results[name]['final'] for name in ('low-1s', 'low-05s', 'high-1s')]
    comparison = {'exactReplay': a == results['replay-1s']['final'],
        'infiltrationDifferenceM3': a['infiltrationM3'] - b['infiltrationM3'],
        'storageDifferenceM3': a['storageM3'] - b['storageM3'],
        'maximumDepthDifferenceM': max(abs(x-y) for x, y in zip(a['depthM'], b['depthM'])),
        'highMinusLowInfiltrationM3': high['infiltrationM3'] - a['infiltrationM3']}
    report = {'schemaVersion': 1, 'classification': base['evidence'], 'rankingEligible': False,
        'soil': soil, 'cases': cases, 'comparison': comparison,
        'sourceCode': {str(source.relative_to(ROOT)): sha(source) for source in sources},
        'limitations': ['100m² 합성 평탄·전면 투수·차단 경계; 실제 서울 지형·피복·침수 재현 아님',
            '실제 2022 강우와 현재 공개 토성 분류의 문헌 매개변수 결합 진단',
            '초기 부족률 0.25·회복계수 1은 명시된 입력 가정; 7일 선행·증발산·지하수 미포함',
            '투수계수 범위 비교는 민감도 시험이며 측정 불확실성의 통계 신뢰구간 아님']}
    write(directory / 'summary.json', report)
    files = {str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}
    write(directory / 'artifact-manifest.json', {'schemaVersion': 1, 'files': files})
    require(comparison['exactReplay'] and all(case['status'] == 'PASSED' for case in cases),
            'INFILTRATION_DIAGNOSTIC_FAILED')
    print(json.dumps({'manifestSha256': sha(directory / 'artifact-manifest.json'),
                      'files': len(files), 'comparison': comparison}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()

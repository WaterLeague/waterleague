"""공개 서초 연구 관망에 새 단면별·공동 설계를 연결한 재현 묶음."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))

from waterleague_sim.engine import facility_network
from waterleague_sim.engine.connected_facilities import compile_design, CATALOG_PATH, CATALOG_SHA256
from waterleague_sim.engine.priced_facilities import compile_priced_design
from waterleague_sim.costing import cistern
from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.ingestion.network_variant import derive
from waterleague_sim.ingestion.published_network import digest, load_archive

PROFILE = {'id': 'slot-62-5ms', 'options': {'SURCHARGE_METHOD': 'SLOT', 'MAX_TRIALS': 200,
                                        'ROUTING_STEP': .0625, 'MINIMUM_STEP': .025}}


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--design', type=Path)
    parser.add_argument('--costing', type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.exists(), 'CONNECTED_FACILITY_COMPARISON_EXISTS')
    source_path = ROOT / 'data/manifests/mendeley-seocho-network-v3.json'
    source, source_hash, inputs = load_archive(ROOT, source_path)
    row = next(row for row in inputs if row['member'].endswith('/Baseline/seocho2_baseline.inp'))
    original = row['raw']
    base, numerical = derive(original, PROFILE)
    design_path = args.design.resolve() if args.design else ROOT / 'simulation/tests/fixtures/connected-facilities-v1.json'
    design = json.loads(design_path.read_text())
    costing = json.loads(args.costing.read_text()) if args.costing else None
    if costing is not None:
        # 전체 설계의 잘못된 참조가 단독안 필터에서 사라지기 전에 검사한다.
        compile_priced_design(base, design, costing)
        cost_source_manifest_path = ROOT / 'data/manifests/jkswe-cistern-costs-2018.json'
        cost_source = json.loads(cost_source_manifest_path.read_text())
        cost_raw_path = ROOT / cost_source['raw']['path']
        require(digest(cost_raw_path.read_bytes()) == cistern.catalog()['source']['sha256'],
                'FACILITY_COST_RAW_SOURCE_CHANGED')
    else:
        compile_design(base, design)
    context_path = ROOT / 'data/manifests/seocho-study-context-v1.json'
    context = json.loads(context_path.read_text())
    require(context['sourceManifestSha256'] == source_hash, 'CONNECTED_FACILITY_CONTEXT_MISMATCH')
    output.mkdir(parents=True)
    (output / 'original.inp').write_bytes(original)
    (output / 'design.json').write_bytes(design_path.read_bytes())
    if costing is not None:
        write(output / 'cost-request.json', costing)
        (output / 'cost-catalog.json').write_bytes(cistern.CATALOG_PATH.read_bytes())
        shutil.copyfile(cost_raw_path, output / 'cost-source.html')
        shutil.copyfile(cost_source_manifest_path, output / 'cost-source-manifest.json')
    write(output / 'numerical-transformation.json', numerical)
    engine = facility_network.identity()
    preserved = [source_path, context_path, CATALOG_PATH, Path(__file__),
        ROOT / 'scripts/build_facility_swmm.py', ROOT / 'scripts/build_live_swmm.py',
        ROOT / 'simulation/native/network_snapshot.inc', ROOT / 'simulation/native/connected_lid_snapshot.inc',
        ROOT / 'simulation/pyproject.toml', ROOT / 'simulation/uv.lock',
        *sorted((ROOT / 'simulation/waterleague_sim').rglob('*.py'))]
    if costing is not None:
        preserved.append(cistern.CATALOG_PATH)
    for path in preserved:
        target = output / 'source' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    (output / 'engine').mkdir()
    for path in (facility_network.library_path(), facility_network.library_path().parent / 'network-build.json',
                 ROOT / 'tmp/swmm/source.tar.gz'):
        shutil.copyfile(path, output / 'engine' / path.name)
    cases = []
    variants = [('baseline', [])] + [('single-' + p['id'].lower(), [p]) for p in design['placements']]
    for p in design['placements']:
        if p['facilityType'] == 'RAINWATER_CISTERN' and p['parameters']['drain']['delayHours'] > 0:
            opened = deepcopy(p)
            opened['parameters']['drain']['delayHours'] = 0
            variants.append(('open-' + p['id'].lower(), [opened]))
    variants.append(('combined', design['placements']))
    for name, placements in variants:
        directory = output / name
        directory.mkdir()
        case_design = {**design, 'placements': deepcopy(placements)}
        if placements and costing is not None:
            ids = {p['id'] for p in placements}
            case_costing = {**costing, 'items': [item for item in costing['items'] if item['placementId'] in ids]}
            raw, transformation = compile_priced_design(base, case_design, case_costing)
        else:
            raw, transformation = compile_design(base, case_design) if placements else (base, None)
        (directory / 'input.inp').write_bytes(raw)
        write(directory / 'transformation.json', transformation)
        summary = {'id': name, 'inputSha256': digest(raw), 'rankingEligible': False}
        if costing is not None:
            summary['costing'] = transformation['costing'] if transformation else None
        try:
            with EngineProcess('facility_network', raw.decode(), directory / 'calculation', native_duration=True) as process:
                result = process.call('run', 300)['result']
            summary.update({key: result[key] for key in ('numericalStatus', 'runoffContinuityPercent',
                'routingContinuityPercent', 'numericalQuality', 'convergence', 'facilityQuality')})
            summary['networkTotals'] = result['final']['totals']
            summary['facilities'] = result['final']['facilities']
        except FloodModelError as error:
            summary.update({'numericalStatus': 'FAILED', 'failureCode': str(error)})
        cases.append(summary)
        write(directory / 'summary.json', summary)
        print(json.dumps({'case': name, 'status': summary['numericalStatus']}), flush=True)
    effects = []
    if 'networkTotals' in cases[0]:
        for case in cases[1:]:
            if 'networkTotals' not in case:
                continue
            effects.append({'id': case['id'], 'bothNumericallyPassed':
                case['numericalStatus'] == cases[0]['numericalStatus'] == 'PASSED',
                'signedReductionM3': {key: cases[0]['networkTotals'][key] - case['networkTotals'][key]
                                     for key in ('outflowM3', 'floodingM3')},
                'meaning': '문헌 단면의 가상 배치에 따른 공개 연구 관망 변화이며 서울 설치 효과·점수 아님'})
    manifest = {'schemaVersion': 1, 'classification': 'PUBLIC_NETWORK_WITH_EXPLICIT_REFERENCE_DESIGNS',
        'sourceManifestSha256': source_hash, 'sourceMember': row['member'],
        'catalogSha256': CATALOG_SHA256, 'attribution': source['attribution'], 'licence': source['licence'],
        'engine': engine, 'numericalProfile': PROFILE, 'cases': cases, 'effects': effects,
        'rankingEligible': False, 'historicalReconstructionEligible': False,
        'limitations': context['limitations'] + ['새 시설 위치·대체 면적·집수 연결·단면·4mm/h 하부 침투는 명시적 설계 가정',
            '기존 관망의 시간 강우·외부 유입·침투법·경계를 보존한 설계 비교, 실제 현재/2010년 시설 아님',
            '시설 초기 포화도 0은 수치 시작 조건이며 선행 관측으로 계산한 현장 초기 상태가 아님',
            '수두 역압을 받는 LID 배수·지표 결합·구간별 점수·비용/입지/현장 검증 미완료'],
        'files': {str(p.relative_to(output)): digest(p.read_bytes()) for p in sorted(output.rglob('*')) if p.is_file()}}
    if costing is not None:
        manifest['costCatalogSha256'] = cistern.CATALOG_SHA256
        manifest['costScope'] = '추가 설계의 용량 일치 문헌 견적·연간 가정 비용; 기존 자산·현재 총공사비·물리 전력량 제외'
    write(output / 'manifest.json', manifest)
    print(json.dumps({'cases': len(cases), 'manifestSha256': digest((output / 'manifest.json').read_bytes())}), flush=True)


if __name__ == '__main__':
    main()

"""고정 공개 관망·문헌 제원의 회원 설계 비교와 재현 파일 보존."""
import json
import os
import platform
from pathlib import Path
import resource
import shutil
import sys
from zipfile import ZipFile, ZIP_DEFLATED

from .engine import facility_network
from .engine.connected_facilities import compile_design, CATALOG_PATH, CATALOG_SHA256
from .engine.flood_errors import FloodModelError, require
from .engine.flood_process import EngineProcess
from .engine.swmm import ROOT
from .ingestion.network_variant import derive
from .ingestion.published_network import digest, load_archive, inspect_input
from .costing.watershed import verify as verify_costs

CATALOG = ROOT / 'backend/src/main/resources/watersheds/seocho-published-v1.json'
CATALOG_HASH = 'beaddba8868b6f1f6bbf35b1d53d4695a94db99498d8988f90d62013cf8f053c'


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n')


def inputs(request):
    raw = CATALOG.read_bytes()
    require(digest(raw) == request['modelHash'] == CATALOG_HASH
            and digest((request['modelHash']+'\n'+request['placements']).encode()) == request['inputHash'],
            'WATERSHED_INPUT_HASH_MISMATCH')
    catalog = json.loads(raw)
    design = json.loads(request['placements'])
    require(isinstance(design, dict) and isinstance(design.get('placements'), list)
            and 1 <= len(design['placements']) <= 20, 'WATERSHED_DESIGN_INVALID')
    for p in design['placements']:
        template = catalog['templates'].get(p['facilityType'])
        require(template is not None and p['parameters'] == template['parameters']
                and p['initialSaturationPercent'] == template['initialSaturationPercent']
                and p['replacedImperviousM2'] == p['areaM2'], 'WATERSHED_TEMPLATE_CHANGED')
    verify_costs(design)
    manifest = ROOT/'data/manifests/mendeley-seocho-network-v3.json'
    source, source_hash, entries = load_archive(ROOT, manifest)
    require(source_hash == catalog['sourceManifestSha256']
            and CATALOG_SHA256 == catalog['facilityCatalogSha256'], 'WATERSHED_SOURCE_CHANGED')
    original = next(v['raw'] for v in entries if v['member'] == catalog['sourceMember'])
    require(digest(original) == catalog['sourceOriginalSha256'], 'WATERSHED_SOURCE_CHANGED')
    audit=inspect_input(original)
    catchments=[{'id':v['id'], 'areaM2':v['areaDeclared']*10000,
                 'imperviousM2':v['areaDeclared']*10000*v['imperviousPercent']/100,
                 'outletNodeId':v['outlet']} for v in audit['catchments']]
    require(catchments==catalog['catchments'], 'WATERSHED_CATCHMENT_SOURCE_MISMATCH')
    base, numerical = derive(original, catalog['numericalProfile'])
    strategy, transformation = compile_design(base, {k: v for k, v in design.items() if k != 'costing'})
    return catalog, original, base, strategy, numerical, transformation, manifest


def calculate(request, directory):
    catalog, original, base, strategy, numerical, transformation, manifest = inputs(request)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    design = json.loads(request['placements'])
    cost_raw = verify_costs(design)
    if cost_raw is not None:
        (directory/'cost-catalog.json').write_bytes(cost_raw)
        write(directory/'cost-snapshot.json', design['costing'])
    (directory/'catalog.json').write_bytes(CATALOG.read_bytes())
    (directory/'original.inp').write_bytes(original)
    (directory/'source-manifest.json').write_bytes(manifest.read_bytes())
    (directory/'facility-catalog.json').write_bytes(CATALOG_PATH.read_bytes())
    write(directory/'numerical-transformation.json', numerical)
    write(directory/'design-transformation.json', transformation)
    (directory/'replay.py').write_bytes((Path(__file__).parent/'watershed_replay.py').read_bytes())
    engine = facility_network.identity() | {'platform': platform.platform()}
    require(digest((ROOT/'tmp/swmm/source.tar.gz').read_bytes()) == engine['sourceArchiveSha256'],
            'WATERSHED_ENGINE_SOURCE_CHANGED')
    for path, name in ((facility_network.library_path(), 'engine.bin'),
                       (facility_network.library_path().parent/'network-build.json', 'engine-build.json'),
                       (ROOT/'tmp/swmm/source.tar.gz', 'engine-source.tar.gz')):
        shutil.copyfile(path, directory/name)
    with ZipFile(directory/'implementation.zip', 'w', ZIP_DEFLATED) as archive:
        files = [*sorted((ROOT/'simulation/waterleague_sim').rglob('*.py')),
                 ROOT/'simulation/native/network_snapshot.inc', ROOT/'simulation/native/connected_lid_snapshot.inc',
                 ROOT/'scripts/build_facility_swmm.py', ROOT/'scripts/build_live_swmm.py',
                 ROOT/'simulation/pyproject.toml', ROOT/'simulation/uv.lock']
        for path in files:
            archive.write(path, str(path.relative_to(ROOT)))
    cases = []
    for name, raw in (('baseline', base), ('strategy', strategy)):
        target = directory/name
        case = {'id': name, 'inputSha256': digest(raw)}
        (directory/(name+'-input.inp')).write_bytes(raw)
        try:
            with EngineProcess('facility_network', raw.decode(), target, native_duration=True) as process:
                result = process.call('run', 300)['result']
            case.update({key: result[key] for key in ('numericalStatus', 'runoffContinuityPercent',
                'routingContinuityPercent', 'numericalQuality', 'convergence', 'facilityQuality')})
            case.update({key: result[key] for key in ('timeWindowPolicy', 'calendarShortfallSeconds', 'complete')})
            case['totals'] = result['final']['totals']
            case['facilities'] = result['final']['facilities']
            case['outfalls'] = {key: value for key, value in result['final']['nodes'].items() if value['type'] == 1}
        except FloodModelError as error:
            case.update(numericalStatus='FAILED', failureCode=str(error))
        cases.append(case)
    passed = all(v['numericalStatus'] == 'PASSED' for v in cases)
    result = {'schemaVersion': 1, 'catalogHash': CATALOG_HASH, 'inputHash': request['inputHash'],
        'classification': 'PUBLIC_NETWORK_REFERENCE_DESIGN_COMPARISON', 'engine': engine,
        'numericalProfile': catalog['numericalProfile'],
        'hydraulicApproximationChanged': numerical['hydraulicApproximationChanged'],
        'numericalStatus': 'PASSED' if passed else 'FAILED', 'cases': cases,
        'signedReductionM3': {key: cases[0]['totals'][key]-cases[1]['totals'][key]
                              for key in ('outflowM3', 'floodingM3')} if passed else None,
        'sourceUrl': catalog['sourceUrl'], 'attribution': catalog['attribution'], 'licence': catalog['licence'],
        'rankingEligible': False, 'historicalReconstructionEligible': False,
        'completeInstalledCostKrw': None, 'budgetChargedKrw': None,
        'limitations': catalog['limitations'] + transformation['limitations'] + ['월류 체적은 지표 침수 깊이·면적·지속시간의 대체 지표가 아님',
            '원본 EXTRAN 수치 실패를 보존하고 별도 SLOT 파생 입력으로 계산; 원본의 달력 종료보다 1초 짧은 엔진 평가 창',
            '방류 체적만으로 하류 첨두 개선을 판정하지 않으며 필수 침수 지표 미확보로 총점 없음']}
    if cost_raw is not None:
        result['costing'] = design['costing']
    return result


def main():
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CPU, (75,75))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64*1024*1024,64*1024*1024))
    if sys.platform.startswith('linux'):
        resource.setrlimit(resource.RLIMIT_AS, (1536*1024*1024,1536*1024*1024))
    directory=Path(sys.argv[1])
    result=calculate(json.loads((directory/'request.json').read_text()), directory)
    result['artifactFiles']={str(p.relative_to(directory)): digest(p.read_bytes())
        for p in sorted(directory.rglob('*')) if p.is_file()}
    write(directory/'result.json', result)
    write(directory/'manifest.json', {str(p.relative_to(directory)): digest(p.read_bytes())
        for p in sorted(directory.rglob('*')) if p.is_file() and p != directory/'manifest.json'})


if __name__ == '__main__':
    main()

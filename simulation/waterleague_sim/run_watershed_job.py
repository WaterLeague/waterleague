"""고정 공개 관망·문헌 제원의 회원 설계 비교와 재현 파일 보존."""
import json
import os
import platform
from pathlib import Path
import resource
import shutil
import sys
from zipfile import ZipFile, ZIP_DEFLATED

from .engine import facility_metrics as facility_network
from .engine.connected_facilities import compile_design, CATALOG_PATH, CATALOG_SHA256
from .engine.flood_errors import FloodModelError, require
from . import watershed_cache
from .engine.swmm import ROOT
from .ingestion.network_variant import derive
from .ingestion.published_network import digest, load_archive, inspect_input
from .costing.watershed import verify as verify_costs
from .engine.flow_connections import published_network, archive as archive_flow, encode

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
            and design.get('schemaVersion') == 1 and design.get('basis') == catalog['designBasis']
            and set(design) <= {'schemaVersion','basis','placements','costing','storage','conduits','cisternCosting','pumps','cistern'}, 'WATERSHED_DESIGN_INVALID')
    storage = design.get('storage', {})
    require(isinstance(storage, dict) and isinstance(storage.get('placements', []), list), 'WATERSHED_STORAGE_PLACEMENTS_INVALID')
    conduit_design=design.get('conduits', {})
    require(isinstance(conduit_design,dict) and isinstance(conduit_design.get('placements',[]),list),'WATERSHED_CONDUIT_PLACEMENTS_INVALID')
    pump_design = design.get('pumps', {})
    require(isinstance(pump_design, dict) and isinstance(pump_design.get('placements', []), list), 'WATERSHED_PUMP_PLACEMENTS_INVALID')
    storage_count = (1 if 'cistern' in design else 0) + len(pump_design.get('placements', [])) + len(storage.get('placements', [])) + len(conduit_design.get('placements',[]))
    require(1 <= len(design['placements'])+storage_count <= 20, 'WATERSHED_DESIGN_INVALID')
    for p in design['placements']:
        template = catalog['templates'].get(p['facilityType'])
        require(template is not None and p['parameters'] == template['parameters']
                and p['initialSaturationPercent'] == template['initialSaturationPercent']
                and p['replacedImperviousM2'] == p['areaM2'], 'WATERSHED_TEMPLATE_CHANGED')
    verify_costs({k: v for k, v in design.items() if k not in ('storage','conduits','cisternCosting','pumps','cistern')})
    from .costing.cistern_reference import verify as verify_cistern
    verify_cistern(design)
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
    strategy, storage_metadata = base, None
    if 'storage' in design:
        from .watershed_storage import compile as compile_storage
        strategy, storage_metadata = compile_storage(base, design['storage'], [p['id'] for p in design['placements']])
    conduit_metadata=None
    if 'conduits' in design:
        from .watershed_conduits import compile as compile_conduits
        strategy,conduit_metadata=compile_conduits(strategy,design['conduits'],base,[p['id'] for p in design['placements']+storage.get('placements',[])])
    pump_metadata = None
    if 'pumps' in design:
        from .watershed_pumps import compile as compile_pumps
        strategy, pump_metadata = compile_pumps(strategy, design['pumps'], base, [p['id'] for p in design['placements']+storage.get('placements',[])+conduit_design.get('placements',[])])
    cistern_metadata = None
    if 'cistern' in design:
        from .watershed_cistern import compile as compile_cistern
        all_ids = [p['id'] for group in (design['placements'], storage.get('placements', []),
            conduit_design.get('placements', []), pump_design.get('placements', [])) for p in group]
        strategy, cistern_metadata = compile_cistern(strategy, design['cistern'], base, design['placements'], all_ids)
    transformation = {'limitations': []}
    if design['placements']:
        from .watershed_cistern import prepare_lids
        original_design = {k: v for k, v in design.items() if k not in ('costing','storage','conduits','cisternCosting','pumps','cistern')}
        strategy, execution_design, assignments, width_binding = prepare_lids(strategy, original_design, cistern_metadata)
        strategy, transformation = compile_design(strategy, execution_design)
        if assignments:
            transformation['sourceDesign'] = original_design
            transformation['sourceCatchmentAssignments'] = assignments
            transformation['sharedCatchmentWidth'] = width_binding
    if cistern_metadata is not None:
        transformation['networkCistern'] = cistern_metadata
        transformation['limitations'] += cistern_metadata['limitations']
    if storage_metadata is not None:
        transformation['connectedStorage'] = storage_metadata
        transformation['limitations'] += storage_metadata['limitations']
    if conduit_metadata is not None:
        transformation['conduitRetrofits']=conduit_metadata
        transformation['limitations']+=conduit_metadata['limitations']
    if pump_metadata is not None:
        transformation['connectedPumps'] = pump_metadata
        transformation['limitations'] += pump_metadata['limitations']
    return catalog, original, base, strategy, numerical, transformation, manifest


def calculate(request, directory, cache_root=None):
    implementation_hash = watershed_cache.implementation_hash()
    catalog, original, base, strategy, numerical, transformation, manifest = inputs(request)
    from .presentation.node_flooding import load_layout, summarize as node_flooding
    layout_raw, layout_snapshot = load_layout(catalog['sourceOriginalSha256'])
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory/'network-layout.json').write_bytes(layout_raw)
    design = json.loads(request['placements'])
    (directory/'design.json').write_bytes(encode(design))
    cost_raw = verify_costs({k: v for k, v in design.items() if k not in ('storage','conduits','cisternCosting','pumps','cistern')})
    from .costing.cistern_reference import verify as verify_cistern
    cistern_raw = verify_cistern(design)
    if cistern_raw is not None:
        (directory/'cistern-cost-catalog.json').write_bytes(cistern_raw)
        write(directory/'cistern-cost-snapshot.json', design['cisternCosting'])
        from .costing.life_cycle import archive_cistern
        cistern_life_cycle = archive_cistern(design['cisternCosting'], directory)
        from .costing.cistern_reference import source_artifacts
        for name, raw in source_artifacts().items():
            (directory/name).write_bytes(raw)
    if cost_raw is not None:
        (directory/'cost-catalog.json').write_bytes(cost_raw)
        write(directory/'cost-snapshot.json', design['costing'])
    if 'storage' in design or 'cistern' in design:
        from .watershed_storage import CATALOG as STORAGE_CATALOG
        (directory/'storage-connections.json').write_bytes(STORAGE_CATALOG.read_bytes())
    if 'conduits' in design:
        from .watershed_conduits import CATALOG as CONDUIT_CATALOG
        (directory/'conduit-catalog.json').write_bytes(CONDUIT_CATALOG.read_bytes())
    (directory/'catalog.json').write_bytes(CATALOG.read_bytes())
    (directory/'original.inp').write_bytes(original)
    (directory/'source-manifest.json').write_bytes(manifest.read_bytes())
    (directory/'facility-catalog.json').write_bytes(CATALOG_PATH.read_bytes())
    write(directory/'numerical-transformation.json', numerical)
    write(directory/'design-transformation.json', transformation)
    (directory/'replay.py').write_bytes((Path(__file__).parent/'watershed_replay.py').read_bytes())
    engine_module = facility_network
    engine_kind = 'facility_metrics'
    if 'pumps' in design:
        from .engine import pump_network
        from .engine.connected_pumps import CATALOG as PUMP_CATALOG
        engine_module, engine_kind = pump_network, 'pump_network'
        (directory/'pump-curve.json').write_bytes(PUMP_CATALOG.read_bytes())
    engine_identity = engine_module.identity()
    engine = engine_identity | {'platform': platform.platform()}
    require(digest((ROOT/'tmp/swmm/source.tar.gz').read_bytes()) == engine['sourceArchiveSha256'],
            'WATERSHED_ENGINE_SOURCE_CHANGED')
    for path, name in ((engine_module.library_path(), 'engine.bin'),
                       (engine_module.library_path().parent/'network-build.json', 'engine-build.json'),
                       (ROOT/'tmp/swmm/source.tar.gz', 'engine-source.tar.gz')):
        shutil.copyfile(path, directory/name)
    with ZipFile(directory/'implementation.zip', 'w', ZIP_DEFLATED) as archive:
        files = [*sorted((ROOT/'simulation/waterleague_sim').rglob('*.py')),
                 ROOT/'simulation/native/network_snapshot.inc', ROOT/'simulation/native/connected_lid_snapshot.inc',
                 ROOT/'simulation/native/network_metrics.inc',
                 ROOT/'simulation/native/node_flood_duration.inc', ROOT/'scripts/attach_node_flood_duration.py',
                 ROOT/'scripts/build_facility_metrics_swmm.py', ROOT/'scripts/build_pump_network_swmm.py', ROOT/'simulation/native/pump_snapshot.inc', ROOT/'scripts/build_live_swmm.py',
                 ROOT/'simulation/pyproject.toml', ROOT/'simulation/uv.lock']
        for path in files:
            archive.write(path, str(path.relative_to(ROOT)))
    cases = []
    for name, raw in (('baseline', base), ('strategy', strategy)):
        target = directory/name
        case = {'id': name, 'inputSha256': digest(raw)}
        (directory/(name+'-input.inp')).write_bytes(raw)
        try:
            result, execution = watershed_cache.run(
                request, raw, engine_kind, engine_identity, target, cache_root)
            case['execution'] = execution
            case.update({key: result[key] for key in ('numericalStatus', 'runoffContinuityPercent',
                'routingContinuityPercent', 'numericalQuality', 'convergence', 'facilityQuality')})
            case.update({key: result[key] for key in ('timeWindowPolicy', 'calendarShortfallSeconds', 'complete')})
            case['totals'] = result['final']['totals']
            case['facilities'] = result['final']['facilities']
            case['outfalls'] = {key: value for key, value in result['final']['nodes'].items() if value['type'] == 1}
            case['evaluationMetrics'] = result['evaluationMetrics']
            if 'pumpOperation' in result:
                case['pumpOperation'] = result['pumpOperation']
            deliveries = [p['deliveryNodeId'] for p in transformation.get('connectedPumps', {}).get('facilities', [])] if name == 'strategy' else []
            inlet = transformation.get('networkCistern', {}).get('inletPipe') if name == 'strategy' else None
            case['nodeFlooding'] = node_flooding(result['initial'], result['final'], layout_snapshot['layout'],
                deliveries, [inlet['nodeId']] if inlet else [])
            if 'conduits' in design:
                case['conduits']=[{'id':p['id'],'conduitId':p['conduitId'],**result['final']['links'][p['conduitId']]} for p in design['conduits']['placements']]
                case['conduitStateTimeSeconds']=result['final']['totals']['timeSeconds']
            if name == 'strategy' and 'connectedStorage' in transformation:
                from .engine.connected_storage import result_summary
                case['connectedStorage'] = result_summary(transformation['connectedStorage'], result['initial'], result['final'])
                if case['connectedStorage']['numericalStatus'] != 'PASSED':
                    case['numericalStatus'] = 'FAILED'
            if name == 'strategy' and 'networkCistern' in transformation:
                from .engine.connected_storage import result_summary
                case['networkCistern'] = result_summary(transformation['networkCistern'], result['initial'], result['final'])
                if case['networkCistern']['numericalStatus'] != 'PASSED':
                    case['numericalStatus'] = 'FAILED'
        except FloodModelError as error:
            case.update(numericalStatus='FAILED', failureCode=str(error))
        cases.append(case)
    passed = all(v['numericalStatus'] == 'PASSED' for v in cases)
    if passed:
        passed = (cases[0]['evaluationMetrics']['specificationSha256']
                  == cases[1]['evaluationMetrics']['specificationSha256'])
    result = {'schemaVersion': 2, 'catalogHash': CATALOG_HASH, 'inputHash': request['inputHash'],
        'classification': 'PUBLIC_NETWORK_REFERENCE_DESIGN_COMPARISON', 'engine': engine,
        'numericalProfile': catalog['numericalProfile'],
        'networkLayout': layout_snapshot,
        'hydraulicApproximationChanged': numerical['hydraulicApproximationChanged'],
        'numericalStatus': 'PASSED' if passed else 'FAILED', 'cases': cases,
        'signedReductionM3': {key: cases[0]['totals'][key]-cases[1]['totals'][key]
                              for key in ('outflowM3', 'floodingM3')} if passed else None,
        'signedPeakReductionM3s': (cases[0]['evaluationMetrics']['combined']['peakOutwardM3s']
                                  - cases[1]['evaluationMetrics']['combined']['peakOutwardM3s']) if passed else None,
        'sourceUrl': catalog['sourceUrl'], 'attribution': catalog['attribution'], 'licence': catalog['licence'],
        'rankingEligible': False, 'historicalReconstructionEligible': False,
        'completeInstalledCostKrw': None, 'budgetChargedKrw': None,
        'limitations': catalog['limitations'] + transformation['limitations'] + ['월류 체적은 지표 침수 깊이·면적·지속시간의 대체 지표가 아님',
            '원본 EXTRAN 수치 실패를 보존하고 별도 SLOT 파생 입력으로 계산; 원본의 달력 종료보다 1초 짧은 엔진 평가 창',
            '첨두는 같은 시각의 모든 외부 출구 유량 합의 최댓값이며 출구별 최댓값의 합이 아님',
            '외부 출구 첨두는 공개 연구 관망의 계산값이며 실제 하류 침수 위험도·현장 효과 확정값이 아님; 필수 지표 침수 미확보로 총점 없음']}
    if cost_raw is not None:
        result['costing'] = design['costing']
    if cistern_raw is not None:
        result['cisternCosting'] = design['cisternCosting']
        result['cisternLifeCycleCosts'] = cistern_life_cycle
    names = ('original.inp', 'baseline-input.inp', 'strategy-input.inp', 'design.json',
             'catalog.json', 'source-manifest.json', 'design-transformation.json',
             'numerical-transformation.json', 'facility-catalog.json')
    result['flowGraph'] = published_network(original, base, strategy, design, transformation,
        {name: digest((directory/name).read_bytes()) for name in names}, cases)
    archive_flow(result['flowGraph'], directory)
    from .evaluation.raw_metrics import network
    result['metricComparison'] = network(result)
    if any(m['status'] == 'WITHHELD' for m in result['metricComparison']['metrics']):
        result['signedReductionM3'] = result['signedPeakReductionM3s'] = None
    (directory/'raw_metrics.py').write_bytes((Path(__file__).parent/'evaluation/raw_metrics.py').read_bytes())
    require(watershed_cache.implementation_hash() == implementation_hash, 'WATERSHED_IMPLEMENTATION_CHANGED')
    return result


def main():
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CPU, (75,75))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64*1024*1024,64*1024*1024))
    if sys.platform.startswith('linux'):
        resource.setrlimit(resource.RLIMIT_AS, (1536*1024*1024,1536*1024*1024))
    directory=Path(sys.argv[1])
    result=calculate(json.loads((directory/'request.json').read_text()), directory,
                     watershed_cache.configured_root())
    result['artifactFiles']={str(p.relative_to(directory)): digest(p.read_bytes())
        for p in sorted(directory.rglob('*')) if p.is_file()}
    write(directory/'result.json', result)
    write(directory/'manifest.json', {str(p.relative_to(directory)): digest(p.read_bytes())
        for p in sorted(directory.rglob('*')) if p.is_file() and p != directory/'manifest.json'})


if __name__ == '__main__':
    main()

"""회원의 고정 시설 설계를 공개 지형·관망의 동일 조건 전후 계산에 연결."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

from .engine.swmm import ROOT
from .engine.flood_errors import require
from .engine.published_surface_connection import compile_connection, FACILITY_OBSERVER
from .engine.coupled_flood import run_coupled
from .evaluation.coupled_adapter import file_digest, engine_signature, read_coupled_record
from .evaluation.values import digest

PROFILE = ROOT/'backend/src/main/resources/watersheds/seocho-surface-design-v2.json'
PROFILE_SHA256 = '94fca7deba98583792d05806c1f768047ffe4034b110894f09246dc9e2a7e6da'
PROFILES = {
    PROFILE_SHA256: PROFILE,
    '017a325234f482695cf8bcf4b9cd0eece772cf58dacdafdb389bd37159a2b0e7':
        ROOT/'backend/src/main/resources/watersheds/seocho-surface-design-v1.json',
}


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n')


def verify(design):
    sha = design.get('surfaceConnection', {}).get('profileSha256')
    require(isinstance(sha, str) and sha in PROFILES, 'WATERSHED_SURFACE_PROFILE_UNKNOWN')
    raw = PROFILES[sha].read_bytes()
    require(hashlib.sha256(raw).hexdigest() == sha, 'WATERSHED_SURFACE_PROFILE_CHANGED')
    profile = json.loads(raw)
    require(design.get('surfaceConnection') == {'id': profile['id'], 'profileSha256': sha}
            and design.get('locationReference', {}).get('profileSha256') == profile['sourceFiles']['georeference.json']
            and not any(k in design for k in ('storage', 'conduits', 'pumps', 'cistern'))
            and 1 <= len(design.get('placements', [])) <= 20
            and all(p.get('facilityType') in profile['allowedFacilityTypes'] for p in design['placements']),
            'WATERSHED_SURFACE_DESIGN_INVALID')
    return profile


def models(design):
    profile = verify(design)
    source = ROOT/profile['sourceDirectory']
    data = {}
    for name, sha in profile['sourceFiles'].items():
        path = source/name
        require(path.is_file() and path.resolve() == path and not path.is_symlink()
                and path.stat().st_size <= 64*1024**2 and file_digest(path) == sha,
                'WATERSHED_SURFACE_SOURCE_CHANGED')
        data[name] = path.read_bytes()
    require(file_digest(ROOT/profile['reference']) == profile['referenceSha256'],
            'WATERSHED_SURFACE_REFERENCE_CHANGED')
    request = {'schemaVersion': 1, 'method': profile['method'], 'evidence': profile['evidence'],
        'sourceNetworkText': data['terrain/original-network.inp'].decode(),
        'sourceSurface': json.loads(data['surface-20m.json']),
        'sourceCoverage': json.loads(data['coverage-20m.json']),
        'sourceLocation': json.loads(data['georeference.json']), 'parameters': profile['parameters']}
    baseline = compile_connection(request) | {'networkObserverPolicy': FACILITY_OBSERVER}
    strategy = deepcopy(baseline)
    strategy['connectedFacilityDesign'] = {k: deepcopy(design[k]) for k in ('schemaVersion', 'basis', 'placements')}
    return profile, baseline, strategy


def summarize_case(name, model, target, result):
    network = json.loads((target/'network/network-result.json').read_bytes())
    surface = json.loads((target/'surface/surface-result.json').read_bytes())
    binding = model['publishedSurfaceConnection']
    context = {'scopeId': 'seocho-published-v3-public-terrain-window', 'modelGrade': 'EXPLORATORY',
        'evidenceClass': 'PUBLIC_DATA', 'comparisonKind': 'PAST_RAINFALL_STRESS_TEST',
        'effectAreaId': 'published-303ha-rectangle-not-damage-map',
        'scenarioSnapshotSha256': digest(binding['request']),
        'forcingSha256': digest({'originalNetworkSha256': binding['summary']['originalNetworkSha256'],
                                'surfaceRainfall': model['surfaceRainfall']}),
        'engineSha256': engine_signature(network, surface, result),
        'metricSpecificationSha256': digest(model['evaluationMetrics'])}
    record = read_coupled_record(target, file_digest(target/'coupled-result.json'), context)
    metrics = surface['evaluationMetrics']
    raw = record['raw'] | {k: metrics[k] for k in ('maximumDepthM', 'maximumWetAreaM2')}
    raw['maximumWetDurationSeconds'] = max(metrics['wetDurationSeconds'])
    return {'id': name, 'resultSha256': file_digest(target/'coupled-result.json'),
        'numericalStatus': record['numericalStatus'], 'complete': record['complete'],
        'durationSeconds': result['durationSeconds'], 'context': context, 'raw': raw,
        'balance': result['balance'], 'networkConvergence': result['networkConvergence'],
        'networkRoutingContinuityPercent': result['networkRoutingContinuityPercent'],
        'networkNumericalStatus': result['networkNumericalStatus'],
        'surfaceNumericalStatus': result['surfaceNumericalStatus'],
        'calendarDurationSeconds': network['calendarDurationSeconds'],
        'calendarShortfallSeconds': network['calendarShortfallSeconds'],
        'finalMaximumDepthM': max(surface['final']['depthM'])}


def calculate(design, directory):
    profile, baseline, strategy = models(design)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    require(shutil.disk_usage(directory).free >= 6*1024**3, 'WATERSHED_SURFACE_DISK_LIMIT')
    (directory/'profile.json').write_bytes(PROFILES[design['surfaceConnection']['profileSha256']].read_bytes())
    (directory/'reference.json').write_bytes((ROOT/profile['reference']).read_bytes())
    from .engine.coupled_facility_network import library_path
    shutil.copyfile(library_path(), directory/'coupled-engine.bin')
    shutil.copyfile(library_path().parent/'network-build.json', directory/'coupled-engine-build.json')
    write(directory/'design.json', design)
    cases = []
    for name, model in (('baseline', baseline), ('strategy', strategy)):
        target = directory/name
        result = run_coupled(model, target)
        case = summarize_case(name, model, target, result)
        cases.append(case)
        write(directory/(name+'-summary.json'), case)
    require(cases[0]['context'] == cases[1]['context'], 'WATERSHED_SURFACE_CONTEXT_MISMATCH')
    passed = all(c['complete'] and c['numericalStatus'] == 'PASSED' for c in cases)
    result = {'schemaVersion': 1, 'classification': 'PUBLIC_COUPLED_DESIGN_COMPARISON',
        'profileSha256': design['surfaceConnection']['profileSha256'], 'designSha256': digest(design),
        'numericalStatus': 'PASSED' if passed else 'FAILED', 'cases': cases,
        'signedReduction': {key: cases[0]['raw'][key]-cases[1]['raw'][key]
                            for key in cases[0]['raw']} if passed else None,
        'parameters': profile['parameters'], 'sourceFiles': profile['sourceFiles'],
        'rankingEligible': False, 'historicalReconstructionEligible': False,
        'totalScore': None, 'limitations': profile['limitations']}
    write(directory/'comparison.json', result)
    return result


def replay(bundle, output):
    from zipfile import ZipFile
    bundle, output = Path(bundle).resolve(), Path(output).resolve()
    source = json.loads((bundle/'result.json').read_bytes())
    require('surfaceComparison' in source and not output.exists(), 'WATERSHED_SURFACE_REPLAY_INVALID')
    for name, expected in source['artifactFiles'].items():
        path = bundle/name
        require(not Path(name).is_absolute() and '..' not in Path(name).parts
                and path.resolve() == path and path.is_relative_to(bundle)
                and path.is_file() and file_digest(path) == expected, 'WATERSHED_SURFACE_REPLAY_SOURCE_CHANGED')
    # 재생은 같은 고정 저장소·의존성 환경에서 수행하며 다른 구현으로 조용히 대체하지 않는다.
    with ZipFile(bundle/'implementation.zip') as archive:
        for item in archive.infolist():
            path = ROOT/item.filename
            require(not Path(item.filename).is_absolute() and '..' not in Path(item.filename).parts
                    and path.is_file() and item.file_size <= 16*1024**2
                    and hashlib.sha256(archive.read(item)).hexdigest() == file_digest(path),
                    'WATERSHED_SURFACE_REPLAY_IMPLEMENTATION_CHANGED')
    design = json.loads((bundle/'design.json').read_bytes())
    result = calculate(design, output)
    def physical(value):
        return value | {'cases': [{k: v for k, v in case.items() if k != 'resultSha256'}
                                  for case in value['cases']]}
    require(physical(result) == physical(source['surfaceComparison']), 'WATERSHED_SURFACE_REPLAY_RESULT_CHANGED')
    write(output/'replay-audit.json', {'physicalSummaryEqual': True,
        'sourceResultSha256': file_digest(bundle/'result.json'),
        'reportClockExcluded': True, 'rankingEligible': False})
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--replay', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    arguments = parser.parse_args()
    replay(arguments.replay, arguments.output)

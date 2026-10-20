"""공개 관측·원형 후보 7종의 지연 평가와 원 누적 물수지에 의한 독립 적분."""
import argparse
import ctypes as C
from datetime import datetime, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))
from waterleague_sim import admission
from waterleague_sim.engine import continuous
from waterleague_sim.run_historical_job import calculate
from waterleague_sim.spatial import game_catalog


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n')


def independent_moment(directory, name, run, seconds):
    lib = C.CDLL(str(continuous.library_path()))
    lib.wl_hydrologySnapshot.argtypes = [C.POINTER(C.c_double), C.c_int]
    lib.wl_hydrologySnapshot.restype = C.c_int
    raw = (C.c_double * len(continuous.FIELDS))()
    offset = seconds - run['runoffMetrics']['observedSeconds']
    terms, volumes, previous = [], [], 0.
    try:
        assert lib.swmm_open(os.fsencode(directory / f'{name}.inp'),
            os.fsencode(directory / f'{name}-independent.rpt'),
            os.fsencode(directory / f'{name}-independent.out')) == 0
        assert lib.swmm_start(1) == 0
        elapsed = C.c_double()
        for second in range(1, seconds + 1):
            assert lib.swmm_step(C.byref(elapsed)) == 0
            assert lib.wl_hydrologySnapshot(raw, len(raw)) >= 0
            cumulative = raw[4] + raw[5]
            if second > offset:
                # 순간 유량 관측기와 독립적으로 엔진 누적 물수지의 구간 차를 적분한다.
                volume = cumulative - previous
                volumes.append(volume)
                terms.append(volume * (second - .5 - offset))
            previous = cumulative
        assert lib.swmm_end() == 0
        assert lib.swmm_report() == 0
    finally:
        lib.swmm_close()
    assert (directory / f'{name}.out').read_bytes() == (directory / f'{name}-independent.out').read_bytes()
    moment, volume = math.fsum(terms), math.fsum(volumes)
    native = run['runoffMetrics']
    assert math.isclose(volume, native['dischargeIntegralM3'], abs_tol=1e-8, rel_tol=1e-7)
    assert math.isclose(moment, native['timing']['firstMomentM3Seconds'], abs_tol=1e-6, rel_tol=1e-7)
    return {'id': name, 'independentVolumeM3': volume, 'independentFirstMomentM3Seconds': moment,
        'firstMomentDifferenceM3Seconds': moment - native['timing']['firstMomentM3Seconds'],
        'outBytesIdentical': True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--fixture', required=True, type=Path)
    args = parser.parse_args()
    directory = args.output.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    catalog = game_catalog.catalog()
    cases = json.loads((ROOT / 'data/manifests/seoul-native-play-v1.json').read_bytes())[
        'validation']['engineValidation']['cases']
    roof = next(c for c in cases if c['facilityType'] == 'GREEN_ROOF')
    cases.append(roof | {'facilityType': 'RAINWATER_CISTERN'})
    policy = json.loads((ROOT / 'backend/src/main/resources/infrastructure/native-v1/associations.json').read_bytes())
    policy = {key: policy[key] for key in ('version', 'sourceSha256', 'siteCatalogSha256',
                                          'scope', 'historicalExistenceVerified')}
    policy['sha256'] = admission.NATIVE_SHA256
    results = []
    for case in cases:
        region = next(row for row in catalog['models'] if row['districtId'] == case['districtId']
                      and '-seoul-20220808-' in row['id'])
        observed = json.loads(game_catalog.forcing(region['sha256']))
        at = datetime.fromisoformat(observed['rainfall']['start']) + timedelta(seconds=137)
        placement = {'districtId': case['districtId'], 'cellId': case['candidateId'],
            'facilityType': case['facilityType'], 'areaM2': case['areaM2'],
            'siteModelHash': catalog['siteCatalogSha256'], 'publicAssetPolicy': policy,
            'installedAt': at.isoformat(), 'temporalPolicy': 'INSTALLATION_TIME_EXPERIMENT_V1'}
        placements = json.dumps([placement], ensure_ascii=False)
        request = {'modelHash': region['sha256'], 'placements': placements,
            'inputHash': continuous.digest((region['sha256'] + '\n' + placements).encode())}
        target = directory / case['facilityType']
        value = calculate(request, target)
        write(target / 'request.json', request)
        write(target / 'historical-result.json', value)
        result = json.loads((target / '0/result.json').read_bytes())
        model = json.loads((target / '0/model.json').read_bytes())
        seconds = len(model['rainfall']['depthsMm']) * 60
        checks = [independent_moment(target / '0', name, result[name], seconds)
                  for name in ('baseline', 'strategy')]
        row = value['facilities'][0]
        assert row['runoffComparison']['schemaVersion'] == 3
        assert row['runoffComparison']['cases'][0]['metrics']['start'] == at.isoformat()
        results.append({'facilityType': case['facilityType'], 'candidateId': case['candidateId'],
            'districtId': case['districtId'], 'forcingSha256': region['sha256'],
            'comparison': row['runoffComparison'], 'contract': row['designContract'],
            'independentIntegralChecks': checks})
        print(case['facilityType'], row['runoffComparison']['detention'], flush=True)
    shutil.copyfile(__file__, directory / Path(__file__).name)
    report = {'schemaVersion': 1,
        'classification': 'PUBLIC_OBSERVED_NATIVE_SURFACES_NOT_FIELD_VALIDATION',
        'warmupDays': 7, 'activationOffsetSeconds': 137,
        'cases': results, 'rankingEligible': False}
    write(args.fixture, report)
    write(directory / 'report.json', report)
    files = {str(path.relative_to(directory)): continuous.digest(path.read_bytes())
             for path in sorted(directory.rglob('*')) if path.is_file()}
    write(directory / 'manifest.json', {'files': files})
    write(ROOT / 'data/benchmarks/runoff-timing-v1.json', {
        'classification': report['classification'], 'warmupDays': 7, 'activationOffsetSeconds': 137,
        'facilities': [{key: c[key] for key in ('facilityType', 'candidateId', 'districtId',
                        'forcingSha256', 'independentIntegralChecks')} |
                      {'detention': c['comparison']['detention']} for c in results],
        'archive': str(directory.relative_to(ROOT)),
        'manifestSha256': continuous.digest((directory / 'manifest.json').read_bytes()),
        'fixtureSha256': continuous.digest(args.fixture.read_bytes()), 'fileCount': len(files)})


if __name__ == '__main__':
    main()

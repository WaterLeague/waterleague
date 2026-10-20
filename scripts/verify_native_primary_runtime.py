"""로컬 API·실제 워커의 원형 후보 6종·관측·비용·게스트 결과 잠금 대조."""
import argparse
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import http.cookiejar
import json
import math
import os
from pathlib import Path, PurePosixPath
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
SPATIAL_SHA256 = 'd2d9ea2a888ee01d59f253b3848c3c30fdf4b6b3f03662b1202dc9b7a48b88b9'
FORCING_SHA256 = 'f08b92fa00db08126e86b379583299a831764b958a4f131de4647ebde95e6fdb'
RUNTIME_SOURCES = (
    'scripts/verify_native_primary_runtime.py',
    'backend/src/main/java/io/waterleague/installation/repository/SiteCatalogRepository.java',
    'backend/src/main/java/io/waterleague/installation/service/InstallationService.java',
    'backend/src/main/java/io/waterleague/historical/service/HistoricalService.java',
    'backend/src/main/java/io/waterleague/historical/service/HistoricalArtifactService.java',
    'backend/src/main/resources/db/migration/V30__native_game_spatial_version.sql',
    'simulation/waterleague_sim/historical.py',
    'simulation/waterleague_sim/run_historical_job.py',
    'simulation/waterleague_sim/installation_model.py',
    'simulation/waterleague_sim/forcing/game_climate.py',
    'simulation/waterleague_sim/forcing/archived_game_weather.py',
    'simulation/waterleague_sim/spatial/play_bundle.py',
    'simulation/waterleague_sim/spatial/game_catalog.py',
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class Client:
    def __init__(self, base):
        parts = urllib.parse.urlsplit(base)
        if (parts.scheme != 'http' or parts.hostname not in ('127.0.0.1', 'localhost', '::1')
                or parts.username or parts.password or parts.path not in ('', '/') or parts.query or parts.fragment):
            raise ValueError('로컬 시험 API 주소만 허용')
        self.base = base.rstrip('/') + '/api/v1'
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf = self.api('/auth/csrf')

    def api(self, path, body=None, expected=200):
        headers = {'Accept': 'application/json'}
        if body is not None:
            headers.update({'Content-Type': 'application/json', self.csrf['headerName']: self.csrf['token']})
        request = urllib.request.Request(self.base + path,
            data=None if body is None else json.dumps(body).encode(), headers=headers)
        try:
            with self.opener.open(request, timeout=30) as response:
                if response.status != expected:
                    raise ValueError('시험 API 상태 불일치')
                raw = response.read(16 * 1024**2 + 1)
                if len(raw) > 16 * 1024**2:
                    raise ValueError('시험 API 응답 크기 초과')
                return json.loads(raw)
        except urllib.error.HTTPError as error:
            if error.code != expected:
                raise ValueError('시험 API 오류 상태 ' + str(error.code)) from None
            return json.loads(error.read(65536))


def verify(base, artifacts):
    client = Client(base)
    registry = client.api('/spatial/play/forcings')
    if registry['catalogSha256'] != FORCING_SHA256:
        raise ValueError('현재 관측 목록 불일치')
    event = next(row for row in client.api('/disasters')['events'] if row['id'] == 'seoul-20220808')
    regions = {row['districtId']: row for row in event['regions']}
    cases = json.loads((ROOT / 'data/manifests/seoul-native-play-v1.json').read_bytes())['validation']['engineValidation']['cases']
    results = []
    for case in cases:
        district, candidate = case['districtId'], case['candidateId']
        site = client.api('/installations/sites/' + district + '/' + candidate)
        if site['modelHash'] != SPATIAL_SHA256 or case['facilityType'] not in site['allowedTypes']:
            raise ValueError('API 후보의 원형·시설 불일치')
        at = (datetime.fromisoformat(regions[district]['start']) + timedelta(seconds=137)).isoformat()
        placement = {'districtId': district, 'placement': {'cellId': candidate, 'facilityType': case['facilityType'],
            'areaM2': case['areaM2'], 'siteModelHash': SPATIAL_SHA256, 'installedAt': at}}
        request = {'requestKey': str(uuid.uuid4()), 'eventId': event['id'], 'districtId': district, 'placements': [placement]}
        job = client.api('/guest-historical', request, expected=202)
        if client.api('/guest-historical', request, expected=202)['id'] != job['id']:
            raise ValueError('게스트 요청 멱등 불일치')
        deadline = time.monotonic() + 180
        while job['state'] in ('QUEUED', 'RUNNING') and time.monotonic() < deadline:
            time.sleep(1)
            job = client.api('/guest-historical/' + job['id'])
        if job['state'] != 'SUCCEEDED':
            raise ValueError('실제 워커 계산 실패: ' + case['facilityType'])
        guest = job['result']
        if any(key in guest for key in ('differenceM3', 'baselineAccountedM3', 'designAccountedM3')):
            raise ValueError('게스트 최종 결과 잠금 누락')
        folders = list((artifacts / 'historical' / str(uuid.UUID(job['id']))).iterdir())
        if len(folders) != 1 or folders[0].is_symlink():
            raise ValueError('시험 재현 묶음 경로 불일치')
        folder = folders[0]
        uuid.UUID(folder.name)
        manifest_raw = (folder / 'manifest.json').read_bytes()
        manifest = json.loads(manifest_raw)
        for relative, expected in manifest.items():
            path = PurePosixPath(relative)
            source = folder / relative
            if (path.is_absolute() or '..' in path.parts or path.as_posix() != relative
                    or source.is_symlink() or not source.is_file() or source.stat().st_size > 64 * 1024**2
                    or sha(source.read_bytes()) != expected):
                raise ValueError('시험 재현 원문 해시·경로 불일치')
        raw = (folder / 'result.json').read_bytes()
        result = json.loads(raw)
        frozen = json.loads(json.loads((folder / 'request.json').read_bytes())['placements'])[0]
        cost = json.loads(frozen['costSnapshotRaw'])
        expected_cost = Decimal(str(case['areaM2'])) * Decimal(str(site['unitCosts'][case['facilityType']]))
        if (sha(frozen['costSnapshotRaw'].encode()) != frozen['costSnapshotSha256']
                or Decimal(str(cost['budgetChargeKrw'])) != expected_cost
                or cost['siteModelHash'] != SPATIAL_SHA256
                or sha((folder / 'rainfall-model.json').read_bytes()) != regions[district]['modelHash']
                or result['facilities'][0]['initialization']['warmupMinutes'] != 10080
                or datetime.fromisoformat(result['facilities'][0]['frames'][0]['at']) != datetime.fromisoformat(at)
                or any(any(frame[key] != 0 for key in ('baselineM3s', 'designM3s', 'differenceM3'))
                       for frame in result['frames'] if datetime.fromisoformat(frame['at']) < datetime.fromisoformat(at))
                or datetime.fromisoformat(guest['frames'][-1]['at']) >= datetime.fromisoformat(result['end'])
                or not math.isclose(result['differenceM3'], result['baselineAccountedM3'] - result['designAccountedM3'], abs_tol=1e-9)):
            raise ValueError('비용·관측·선행 상태·시간·원 지표 결속 불일치')
        other = Client(base)
        other.api('/guest-historical/' + job['id'], expected=404)
        results.append({'facilityType': case['facilityType'], 'districtId': district, 'candidateId': candidate,
            'areaM2': case['areaM2'], 'budgetChargeKrw': str(expected_cost), 'installedAt': at,
            'warmupMinutes': 10080, 'frameCount': len(result['frames']), 'guestFrameCount': len(guest['frames']),
            'differenceM3': result['differenceM3'], 'baselineAccountedM3': result['baselineAccountedM3'],
            'designAccountedM3': result['designAccountedM3'], 'resultSha256': sha(raw),
            'manifestSha256': sha(manifest_raw), 'forcingHash': regions[district]['modelHash'],
            'serverCostSnapshotVerified': True, 'guestFinalResultLocked': True, 'foreignSessionRejected': True})
        print(json.dumps({'facilityType': case['facilityType'], 'state': 'SUCCEEDED',
            'differenceM3': result['differenceM3']}, ensure_ascii=False), flush=True)
    return {'schemaVersion': 1, 'status': 'PASS', 'spatialSha256': SPATIAL_SHA256,
        'forcingCatalogSha256': FORCING_SHA256, 'eventId': event['id'], 'facilityCount': len(results),
        'actualApiWorkerStorageVerified': True, 'fieldValidation': False,
        'independentDirectRainfallOnly': True, 'cases': results}


def stored_evidence(report, artifacts):
    if (report['status'] != 'PASS' or report['spatialSha256'] != SPATIAL_SHA256
            or report['forcingCatalogSha256'] != FORCING_SHA256 or report['facilityCount'] != 6
            or not report['actualApiWorkerStorageVerified']
            or len({case['facilityType'] for case in report['cases']}) != 6):
        raise ValueError('기존 실제 실행 증거의 범위 불일치')
    pending = {case['manifestSha256']: case for case in report['cases']}
    for manifest_path in (artifacts / 'historical').glob('*/*/manifest.json'):
        if manifest_path.is_symlink() or manifest_path.stat().st_size > 1024**2:
            continue
        manifest_raw = manifest_path.read_bytes()
        case = pending.get(sha(manifest_raw))
        if case is None:
            continue
        folder = manifest_path.parent
        for relative, expected in json.loads(manifest_raw).items():
            path = PurePosixPath(relative)
            item = folder / relative
            if (path.is_absolute() or '..' in path.parts or path.as_posix() != relative
                    or any(part.is_symlink() for part in (item, *item.parents))
                    or not item.is_file() or item.stat().st_size > 64 * 1024**2
                    or sha(item.read_bytes()) != expected):
                raise ValueError('보관 실제 실행의 파일 경로·해시 불일치')
        if sha((folder / 'result.json').read_bytes()) != case['resultSha256']:
            raise ValueError('보관 결과 원문 불일치')
        calculation = json.loads((folder / '0/result.json').read_bytes())
        engine = calculation['strategy']['engine']
        if engine != calculation['baseline']['engine'] or engine['engineVersion'] != '5.2.4':
            raise ValueError('기준·설계 엔진 불일치')
        case['engine'] = engine
        pending.pop(sha(manifest_raw))
    if pending:
        raise ValueError('보관 실제 실행 증거 누락')
    report['storedArtifactsRevalidated'] = True
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8080')
    parser.add_argument('--artifacts', type=Path, default=ROOT / 'data/runs')
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--stored-report', type=Path)
    args = parser.parse_args()
    if os.path.lexists(args.report):
        parser.error('기존 실행 증거 덮어쓰기 금지')
    hashes = {name: sha((ROOT / name).read_bytes()) for name in RUNTIME_SOURCES}
    if args.stored_report is not None:
        if args.stored_report.is_symlink() or not 1 <= args.stored_report.stat().st_size <= 1024**2:
            parser.error('보관 실행 증거 경로·크기 제한')
        report = json.loads(args.stored_report.read_bytes())
    else:
        report = verify(args.base_url, args.artifacts.resolve())
    report = stored_evidence(report, args.artifacts.resolve())
    if hashes != {name: sha((ROOT / name).read_bytes()) for name in RUNTIME_SOURCES}:
        parser.error('검사 중 현재 런타임 코드 변경')
    report['runtimeSources'] = hashes
    report['apiRequestsReplayedInThisRun'] = args.stored_report is None
    with args.report.open('x', encoding='utf-8') as target:
        target.write(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n')
    print(json.dumps({'status': report['status'], 'facilities': report['facilityCount']}))


if __name__ == '__main__':
    main()

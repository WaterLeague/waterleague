"""공개 행정코드·원형 후보와 보관 관측 강우의 현재 게임 결속 생성."""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import re
import gzip
import io
import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pyproj

import prepare_seoul_topography as source
import prepare_seoul_spatial as spatial
from waterleague_sim.ingestion.kma import normalize

OUTPUT = source.ROOT / 'backend/src/main/resources/native-game/v1'
EVENTS = source.ROOT / 'backend/src/main/resources/native-game/events-source-v1.json'
BOUNDARIES = source.ROOT / 'data/derived/seoul-district-boundaries-v1.json'
BOUNDARY_SHA256 = 'ff49da7030e1abcea4190aa3e3375714889fc537c2759cb4d220c04e764cf4c4'
PLAY_SHA256 = '4ec7535e7cbaf41dc73f73519d77ba11f956f4c75c1a574fffa08f16625919b7'
DEFAULT_DAY = '2024-07-18'
SELECTION = 'NEAREST_ARCHIVED_QUALITY_CHECKED_AWS_WITHIN_10KM'
INPUTS = {
    'backend/src/main/resources/native-game/events-source-v1.json':
        '35ff542617feacd819d9cb0222bebfc703412505d5fb1ee3b9161d2c68443d68',
    'data/derived/evaporation/disaster-catalog-v1.json':
        'a99694bec44a395df435516306c4f8293f94b001d8391873d6a4f004b93f3e04',
    'data/derived/antecedent/catalog-v1.json':
        '5dc164c212778a60a8add9cc1dfc828d471edd0d4347b50fb94df28b1fb56b3c',
}


def read(path, expected=None):
    with source.source_stream(path, expected_sha256=expected) as (stream, _):
        return json.load(stream)


def record_file(relative, hashes, expected=None):
    path = source.project_path(source.ROOT, relative)
    with source.source_stream(path, expected_sha256=expected, limit=32 * 1024**2) as (stream, checksum):
        body = stream.read()
    if relative in hashes and hashes[relative] != checksum:
        raise source.TopographyDataError('생성 중 원자료 변경')
    hashes[relative] = checksum
    return body


def verify_rain(rain, hashes):
    name = rain['sourceManifest']
    if (not re.fullmatch(r'kma-\d{1,5}-\d{12}-\d{12}\.json', name)
            or rain['quality'] not in ('BASIC_CHECKED', 'BASIC_CHECKED_NO_PROVIDER_QC_FLAGS')
            or rain['intervalSeconds'] != 60):
        raise source.TopographyDataError('관측 강우 품질·출처 오류')
    manifest = json.loads(record_file('data/manifests/' + name, hashes))
    raw = record_file('data/raw/' + name.removesuffix('.json') + '.txt', hashes, rain['sourceHash'])
    rows, total = normalize(raw.decode('utf-8'))
    if (manifest['sha256'] != rain['sourceHash'] or manifest['bytes'] != len(raw)
            or manifest['parameters']['stn'] != rain['stationId']
            or rows[0].station_id != rain['stationId']
            or rows[0].start != datetime.fromisoformat(rain['start'])
            or rows[-1].end != datetime.fromisoformat(rain['end'])
            or rain['depthsMm'] != [float(row.depth_mm) for row in rows]
            or rain['totalDepthMm'] != float(total)):
        raise source.TopographyDataError('원문 재정규화 강우 불일치')
    station = rain['stationMetadata']
    if (station['stationId'] != rain['stationId'] or station['crs'] != 'EPSG:4326'
            or not -90 <= station['latitude'] <= 90 or not -180 <= station['longitude'] <= 180):
        raise source.TopographyDataError('관측소 좌표·식별 오류')
    for key, checksum_key in [('sourceManifest', 'sourceSha256'), ('endSourceManifest', 'endSourceSha256')]:
        if key not in station:
            continue
        name = station[key]
        if not re.fullmatch(r'kma-stations-aws-\d{12}\.json', name):
            raise source.TopographyDataError('관측소 원자료 경로 오류')
        manifest = json.loads(record_file('data/manifests/' + name, hashes))
        raw = record_file('data/raw/' + name.removesuffix('.json') + '.txt', hashes, station[checksum_key])
        if manifest['sha256'] != station[checksum_key] or manifest['bytes'] != len(raw):
            raise source.TopographyDataError('관측소 원자료 불일치')
        rows = [line.split() for line in raw.decode('cp949').splitlines()
            if line.strip() and not line.startswith('#')]
        matched = [row for row in rows if row[0] == rain['stationId']]
        if (len(matched) != 1 or float(matched[0][1]) != station['longitude']
                or float(matched[0][2]) != station['latitude']):
            raise source.TopographyDataError('관측소 원문 좌표 불일치')


def observed_sources(events, antecedent):
    pools, hashes = {}, {}
    supported = {(row['eventId'], row['stationId']) for row in antecedent['entries']}
    for path in sorted((source.ROOT / 'data/derived/rainfall').glob('*.json')):
        if not re.fullmatch(r'kma-\d{1,5}-\d{12}-\d{12}-(historical|disaster)-v1.json', path.name):
            continue
        rain = read(path)
        station = rain.get('stationMetadata')
        event = next((event for event in events['events']
            if event['startKst'] in path.name and event['endKst'] in path.name), None)
        if not station or not rain.get('sourceHash') or not rain.get('sourceManifest'):
            continue
        if event is not None:
            key = event['id']
            if (key, str(rain['stationId'])) not in supported:
                continue
        elif (path.name.endswith('-historical-v1.json')
              and datetime.fromisoformat(rain['start']).astimezone(ZoneInfo('Asia/Seoul')).date().isoformat() == DEFAULT_DAY):
            key = 'default'
        else:
            continue
        verify_rain(rain, hashes)
        identifier = str(rain['stationId'])
        original = pools.setdefault(key, {}).get(identifier)
        # 같은 관측 창·지점의 원 강우가 다르면 물리 모델 차이로 숨기지 않는다.
        observed = {k: v for k, v in rain.items() if k not in ('stationDistanceKm', 'stationDistanceEvidence')}
        if original and original['rainfall'] != observed:
            raise source.TopographyDataError('같은 지점·시간의 관측 입력 충돌')
        relative = str(path.relative_to(source.ROOT))
        candidate = {'rainfall': observed, 'disasterEvent': event,
            'sourceRainfallFile': relative, 'sourceRainfallSha256': spatial.file_sha256(path)}
        if original is None or relative < original['sourceRainfallFile']:
            pools[key][identifier] = candidate
        hashes[str(path.relative_to(source.ROOT))] = candidate['sourceRainfallSha256']
    return pools, hashes


def verify_climate(bindings, pet, antecedent, hashes):
    for checksum, body in bindings.items():
        if 'disasterEvent' not in body:
            continue
        rain = body['rainfall']
        p = [row for row in pet['entries'] if checksum in row['modelHashes']]
        a = [row for row in antecedent['entries'] if checksum in row['modelHashes']]
        if len(p) != 1 or len(a) != 1:
            raise source.TopographyDataError('재해별 증발산·선행 관측 결속 누락')
        p, a = p[0], a[0]
        if p['eventId'] != body['disasterEvent']['id'] or a['eventId'] != p['eventId'] or a['stationId'] != rain['stationId']:
            raise source.TopographyDataError('재해별 증발산·선행 관측 결속 불일치')
        if not re.fullmatch(r'seoul-\d{8}-fao56-v1\.json', p['file']):
            raise source.TopographyDataError('증발산 파일 경로 오류')
        evaporation = json.loads(record_file('data/derived/evaporation/' + p['file'], hashes, p['sha256']))
        if (any(datetime.fromisoformat(evaporation[key]) != datetime.fromisoformat(rain[key]) for key in ('start', 'end'))
                or len(evaporation['ratesMmDay']) != len(rain['depthsMm'])
                or any(not math.isfinite(value) or value < 0 for value in evaporation['ratesMmDay'])):
            raise source.TopographyDataError('사건 증발산 시간·값 불일치')
        values = [evaporation]
        antecedent_values = {}
        for kind in ('rainfall', 'evaporation'):
            ref = a[kind]
            if not re.fullmatch(r'seoul-\d{8}-(\d{1,5}-rain|pet)-v1\.json\.gz', ref['file']):
                raise source.TopographyDataError('선행 관측 파일 경로 오류')
            raw = record_file('data/derived/antecedent/' + ref['file'], hashes, ref['sha256'])
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
                decoded = compressed.read(16 * 1024**2 + 1)
            if len(decoded) > 16 * 1024**2:
                raise source.TopographyDataError('선행 관측 압축 해제 크기 초과')
            antecedent_values[kind] = json.loads(decoded)
            values.append(antecedent_values[kind])
        start = datetime.fromisoformat(rain['start'])
        prior = antecedent_values['rainfall']
        rates = antecedent_values['evaporation']['ratesMmDay']
        if (antecedent['warmupMinutes'] != 10080 or prior['intervalSeconds'] != 60
                or prior['stationId'] != rain['stationId'] or len(prior['depthsMm']) != 10080 or len(rates) != 10080
                or datetime.fromisoformat(prior['end']) != start
                or datetime.fromisoformat(prior['start']) != start - timedelta(days=7)
                or any(not math.isfinite(value) or value < 0 for value in prior['depthsMm'] + rates)):
            raise source.TopographyDataError('7일 선행 관측 시간·값 불일치')
        for value in values:
            for request in value['sourceRequests']:
                if not re.fullmatch(r'data/raw/kma-disaster-pet-[a-f0-9]{24}\.txt', request['rawFile']):
                    raise source.TopographyDataError('기상 원문 경로 오류')
                raw = record_file(request['rawFile'], hashes, request['sha256'])
                if len(raw) != request['bytes']:
                    raise source.TopographyDataError('기상 원문 크기 불일치')


def nearest(center, candidates):
    transform = pyproj.Transformer.from_crs(5186, 4326, always_xy=True)
    lon, lat = transform.transform(*center)
    geod = pyproj.Geod(ellps='WGS84')
    choices = []
    for station_id, value in candidates.items():
        station = value['rainfall']['stationMetadata']
        distance = geod.inv(lon, lat, station['longitude'], station['latitude'])[2] / 1000
        if distance <= 10:
            choices.append((distance, station_id, value))
    if not choices:
        raise source.TopographyDataError('10km 안에 보관 관측 창이 있는 지점 없음')
    distance, _, value = min(choices, key=lambda row: (row[0], row[1]))
    return value, distance


def build(output):
    if os.path.lexists(output) or output.parent.resolve() != output.parent.absolute():
        raise source.TopographyDataError('기존 게임 결속·출력 링크 덮어쓰기 금지')
    boundaries = read(BOUNDARIES, BOUNDARY_SHA256)
    play = read(source.ROOT / 'data/manifests/seoul-native-play-v1.json')
    if play['playSha256'] != PLAY_SHA256:
        raise source.TopographyDataError('원형 후보 버전 불일치')
    old_pet = read(source.ROOT / 'data/derived/evaporation/disaster-catalog-v1.json',
        INPUTS['data/derived/evaporation/disaster-catalog-v1.json'])
    old_antecedent = read(source.ROOT / 'data/derived/antecedent/catalog-v1.json',
        INPUTS['data/derived/antecedent/catalog-v1.json'])
    original_events = read(EVENTS, INPUTS[str(EVENTS.relative_to(source.ROOT))])
    pools, input_hashes = observed_sources(original_events, old_antecedent)
    if len(pools) != 4 or 'default' not in pools:
        raise source.TopographyDataError('기본·재해 관측 창 누락')
    input_hashes.update(INPUTS)
    input_hashes[str(BOUNDARIES.relative_to(source.ROOT))] = BOUNDARY_SHA256
    input_hashes['data/manifests/seoul-native-play-v1.json'] = spatial.file_sha256(
        source.ROOT / 'data/manifests/seoul-native-play-v1.json')
    implementations = {str(Path(module.__file__).resolve().relative_to(source.ROOT)): spatial.file_sha256(module.__file__)
        for module in (source, spatial)}
    implementations.update({path: spatial.file_sha256(source.ROOT / path) for path in (
        'simulation/waterleague_sim/ingestion/kma.py', 'simulation/waterleague_sim/ingestion/rainfall.py')})
    code_sha = spatial.file_sha256(__file__)
    output.mkdir(mode=0o755)
    (output / 'models').mkdir()
    regions, entries, bindings = [], [], {}
    try:
        for district in sorted(boundaries['districts'], key=lambda row: row['id']):
            identifier = district['id']
            map_id = 'seoul-ngii-v1-' + identifier
            refs = {}
            for key, candidates in sorted(pools.items()):
                selected, distance = nearest(district['centerProjected'], candidates)
                rain = copy.deepcopy(selected['rainfall'])
                rain.update(stationDistanceKm=distance,
                    stationDistanceEvidence='공개 자치구 대표점에서 보관·검사 통과 관측 창이 있는 지점 중 거리; 현장 강우 대표성 미검증')
                model_id = f'ngii-{identifier}-{key}-{rain["stationId"]}'
                body = {'schemaVersion': 1, 'kind': 'OBSERVED_FORCING_BINDING', 'id': model_id,
                    'districtId': identifier, 'mapId': map_id, 'siteCatalogSha256': PLAY_SHA256,
                    'rainfall': rain, 'selectionMethod': SELECTION,
                    'sourceRainfallFile': selected['sourceRainfallFile'],
                    'sourceRainfallSha256': selected['sourceRainfallSha256'],
                    'stationPoolIds': sorted(candidates), 'districtBoundarySha256': BOUNDARY_SHA256,
                    'centerProjected': district['centerProjected'],
                    'limitations': ['관측 창 보관 지점의 집합에서 선택; 모든 AWS 중 최근접 지점 판정 아님',
                        '2026-03-07 공개 형상에 과거 관측 적용; 사건 당시 자산·침수 복원 아님',
                        '관측소 거리와 자치구 소속은 현장 강우 대표성·배수 연결의 증거 아님']}
                if selected['disasterEvent'] is not None:
                    body['disasterEvent'] = selected['disasterEvent']
                raw = (source.canonical(body) + '\n').encode()
                checksum = source.digest(raw)
                filename = f'models/{model_id}.json'
                with (output / filename).open('xb') as target:
                    target.write(raw)
                entries.append({'id': model_id, 'file': filename, 'sha256': checksum,
                    'bytes': len(raw), 'districtId': identifier, 'eventId': key})
                refs[key] = checksum
                bindings[checksum] = body
            origin = [198128, 551989]
            station = bindings[refs['default']]['rainfall']
            regions.append({'districtId': identifier, 'districtName': district['name'], 'mapId': map_id,
                'center': [district['centerProjected'][i] - origin[i] for i in (0, 1)],
                'centerProjected': district['centerProjected'], 'defaultModelHash': refs['default'],
                'modelHashes': list(refs.values()), 'eventModelHashes': {k: v for k, v in refs.items() if k != 'default'},
                'roofCount': play['districtKindCounts'][identifier + ':ROOF'],
                'groundCount': play['districtKindCounts'][identifier + ':GROUND'],
                'siteCatalogSha256': PLAY_SHA256, 'defaultRainfall': {
                    'stationId': station['stationId'], 'stationName': station['stationName'],
                    'distanceKm': station['stationDistanceKm'], 'use': SELECTION}})
        events = copy.deepcopy(original_events)
        for event in events['events']:
            event['models'] = []
            for region in regions:
                checksum = region['eventModelHashes'][event['id']]
                rain = bindings[checksum]['rainfall']
                event['models'].append({'districtId': region['districtId'], 'modelHash': checksum,
                    'stationId': rain['stationId'], 'stationName': rain['stationName'], 'totalDepthMm': rain['totalDepthMm']})
        pet = copy.deepcopy(old_pet)
        for row in pet['entries']:
            row['modelHashes'] = sorted(sha for sha, body in bindings.items()
                if body.get('disasterEvent', {}).get('id') == row['eventId'])
        antecedent = copy.deepcopy(old_antecedent)
        for row in antecedent['entries']:
            row['modelHashes'] = sorted(sha for sha, body in bindings.items()
                if body.get('disasterEvent', {}).get('id') == row['eventId']
                and body['rainfall']['stationId'] == row['stationId'])
        antecedent['entries'] = [row for row in antecedent['entries'] if row['modelHashes']]
        verify_climate(bindings, pet, antecedent, input_hashes)
        registry = {'schemaVersion': 1, 'id': 'SEOUL_NGII_GAME_V1', 'generatorSha256': code_sha,
            'coordinateSystem': 'EPSG:5186', 'originProjected': [198128, 551989],
            'districtBoundarySha256': BOUNDARY_SHA256, 'siteCatalogSha256': PLAY_SHA256,
            'sceneCatalogSha256': '7af763a751b8d697ab0f0c7d09aaab3efe724c89bebc46f7ddaf9c565a48910a',
            'selectionMethod': SELECTION, 'regions': regions, 'models': entries,
            'implementationHashes': implementations,
            'versions': {'pyproj': pyproj.__version__, 'proj': pyproj.proj_version_str},
            'rainfallUse': 'ARCHIVED_OBSERVATIONS_ON_CURRENT_PUBLIC_GEOMETRY',
            'events': {'file': 'events.json', 'sha256': source.digest((source.canonical(events) + '\n').encode())},
            'climateBindings': {key: {'file': key + '.json', 'sha256': source.digest((source.canonical(value) + '\n').encode())}
                for key, value in [('evaporation', pet), ('antecedent', antecedent)]},
            'sourceHashes': dict(sorted(input_hashes.items())),
            'climateSourceHashes': {path: spatial.file_sha256(source.ROOT / path) for path in (
                'data/derived/evaporation/disaster-catalog-v1.json', 'data/derived/antecedent/catalog-v1.json')},
            'policy': {'observedDepthsChanged': False, 'fieldRepresentativenessConfirmed': False}}
        for filename, value in [('catalog.json', registry), ('events.json', events),
                                ('evaporation.json', pet), ('antecedent.json', antecedent)]:
            with (output / filename).open('x', encoding='utf-8') as target:
                target.write(source.canonical(value) + '\n')
        if (spatial.file_sha256(__file__) != code_sha
                or any(spatial.file_sha256(source.ROOT / path) != sha for path, sha in (input_hashes | implementations).items())):
            raise source.TopographyDataError('게임 결속 생성 중 코드·관측 변경')
        return registry
    except BaseException:
        shutil.rmtree(output)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    args.output.parent.mkdir(exist_ok=True)
    try:
        registry = build(args.output.absolute())
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(1, '원형 게임 결속 생성 실패: 관측·경계·출력 확인 필요\n')
    print(source.canonical({'districts': len(registry['regions']), 'models': len(registry['models']),
        'catalogSha256': spatial.file_sha256(args.output / 'catalog.json')}))


if __name__ == '__main__':
    main()

"""기존 지역 모델을 보존하며 인근 AWS 관측 강우 버전 추가."""
import copy
import json
from pathlib import Path

from prepare_seoul_play_models import ROOT, payload, sha, write


def read(path):
    return json.loads((ROOT/path).read_text())


def main():
    source = ROOT/'data/manifests/seoul-regional-rainfall-v1.json'
    report = json.loads(source.read_text())
    original = ROOT/'data/manifests/seoul-play-v1.json'
    if sha(original.read_bytes()) != report['geometryRegistrySha256']:
        raise ValueError('구역 원본 목록 해시 불일치')
    if report['collectorSha256'] != sha((ROOT/'scripts/fetch_seoul_regional_rainfall.py').read_bytes()):
        raise ValueError('강우 수집 코드 해시 불일치')
    registry = read('data/manifests/seoul-play-v1.json')
    catalog = read('data/models/catalog.json')
    by_hash = {e['sha256']: e for e in catalog['models']}
    maps = read('frontend/public/data/maps.json')
    map_entries = {e['id']: e for e in maps['maps']}
    generator = sha(Path(__file__).read_bytes())
    added = []
    for region in registry['regions']:
        selections = [s for s in report['selections'] if s['mapId'] == region['mapId'] and s['status'] == 'ACCEPTED']
        entries = []
        for selection in sorted(selections, key=lambda s: s['startKst']):
            date = selection['startKst'][:8]
            base = read('data/models/'+region['mapId']+'-421-'+date+'.json')
            event_file = ROOT/'data/derived/rainfall'/f"{selection['rainfallId']}.json"
            if sha(event_file.read_bytes()) != selection['rainfallSha256']:
                raise ValueError('강우 파생자료 해시 불일치')
            rain = json.loads(event_file.read_text())
            rain['stationDistanceKm'] = selection['stationDistanceKm']
            rain['stationDistanceEvidence'] = '관측 창 양 끝 시점 API 좌표에서 대표 블록 중심까지 WGS84 지오데식 거리; 부지 강우 대표성 미검증'
            identifier = region['mapId']+'-near-'+rain['stationId']+'-'+date
            model = copy.deepcopy(base)
            model.update({'id': identifier, 'title': region['districtName']+' · 인근 관측 강우 '+date,
                          'rainfall': rain, 'rainfallSource': f"기상청 {rain['stationName']} {rain['stationId']} 관측소 · {date}",
                          'regionalRainfallUse': 'NEAREST_AWS_OBSERVED_REPLAY',
                          'rainfallModelGeneratorSha256': generator,
                          'rainfallSelectionManifestSha256': sha(source.read_bytes())})
            model['assumptions'] = [a for a in base['assumptions']
                                    if '성동 관측 강우 공통 재생' not in a and not a.startswith('관측된 후행 무강우')]
            model['assumptions'] += [
                '2026 공개 형상에서 2024 인근 AWS 관측 강우 재생; 해당 블록 실측 강우·동일 시점 지형 아님',
                f"관측된 후행 무강우 {rain['windowStatistics']['observedDryTailMinutes']}분; 장기 배수·저류 회복 효과 미검증"]
            raw = payload(model)
            entry = {'id': identifier, 'file': identifier+'.json', 'sha256': sha(raw)}
            for folder in ('data/models', 'backend/src/main/resources/models'):
                write(ROOT/folder/entry['file'], raw)
            entries.append(entry)
            if entry['sha256'] not in by_hash:
                if any(e['id'] == entry['id'] for e in catalog['models']):
                    raise ValueError('등록된 모델 ID의 원문 변경 거부')
                catalog['models'].append(entry)
            binding = map_entries[region['mapId']]['modelHashes']
            if entry['sha256'] not in binding:
                binding.append(entry['sha256'])
        if entries:
            last = sorted(selections, key=lambda s: s['startKst'])[-1]
            region['defaultModelHash'] = entries[-1]['sha256']
            region['defaultRainfall'] = {'stationName': last['stationName'], 'stationId': last['stationId'],
                                        'distanceKm': last['stationDistanceKm'], 'use': 'NEAREST_AWS_OBSERVED_REPLAY'}
            region['modelHashes'] += [e['sha256'] for e in entries]
        added += entries
    if not added:
        raise ValueError('연결 가능한 인근 관측 강우 없음')
    registry.update({'rainfallUse': 'COMMON_AND_NEAREST_AWS_OBSERVED_REPLAY',
                     'rainfallGeneratorSha256': generator, 'rainfallSelectionManifestSha256': sha(source.read_bytes())})
    for folder in ('data/models', 'backend/src/main/resources/models'):
        write(ROOT/folder/'catalog.json', payload(catalog), mutable=True)
    write(ROOT/'frontend/public/data/maps.json', payload(maps), mutable=True)
    raw = payload(registry)
    write(ROOT/'frontend/public/data/seoul-play-v2.json', raw)
    write(ROOT/'data/manifests/seoul-play-v2.json', raw)
    print('인근 강우 모델', len(added), '전체 모델', len(catalog['models']), '지역 목록 SHA256', sha(raw))


if __name__ == '__main__':
    main()

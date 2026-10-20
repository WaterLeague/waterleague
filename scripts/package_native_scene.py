"""검증한 원형 장면의 게임 표시 묶음. 계산은 원형 후보 DB에서만 수행."""
import argparse
import gzip
import heapq
import json
import os
from pathlib import Path
import shutil
import platform
import zlib
from contextlib import closing

import shapely
from shapely.geometry import shape, mapping

import prepare_seoul_topography as source
import prepare_seoul_spatial as spatial
from waterleague_sim.spatial import play_bundle, game_catalog

SCENE = source.ROOT / 'data/private/vworld-seoul-topography-20260307/scene-v1'
SCENE_SHA256 = '7af763a751b8d697ab0f0c7d09aaab3efe724c89bebc46f7ddaf9c565a48910a'
OUTPUT = source.ROOT / 'frontend/public/data/seoul-native-v1'


def polygons(geometry):
    if geometry['type'] == 'Polygon':
        return [geometry['coordinates']]
    if geometry['type'] == 'MultiPolygon':
        return geometry['coordinates']
    raise ValueError('표시 면 도형 형식 오류')


def write(path, value, compressed=False):
    raw = (source.canonical(value) + '\n').encode()
    if len(raw) > 16 * 1024**2:
        raise ValueError('표시 파일 크기 상한 초과')
    encoded = gzip.compress(raw, compresslevel=9, mtime=0) if compressed else raw
    with path.open('xb') as target:
        target.write(encoded)
    return dict(sha256=source.digest(raw), bytes=len(raw), storedSha256=source.digest(encoded), storedBytes=len(encoded))


def package(output, progress=None):
    if os.path.lexists(output) or output.parent.resolve() != output.parent.absolute():
        raise ValueError('기존 장면 묶음·링크 덮어쓰기 금지')
    with source.source_stream(SCENE / 'catalog.json', expected_sha256=SCENE_SHA256) as (stream, _):
        scene = json.load(stream)
    reader = play_bundle.open_catalog()
    with closing(reader.connection()) as db:
        candidates = {identifier: (candidate, mask, kind) for identifier, candidate, mask, kind in
            db.execute('SELECT object_id,id,allowed_mask,kind FROM sites WHERE allowed_mask<>0')}
    output.mkdir()
    (output / 'tiles').mkdir()
    entries, overview, waters = [], [], []
    code_sha = spatial.file_sha256(__file__)
    count = 0
    try:
        for index, entry in enumerate(scene['tiles']):
            with source.source_stream(SCENE / entry['file'], expected_bytes=entry['bytes'], expected_sha256=entry['sha256'],
                                      limit=16 * 1024**2) as (stream, _):
                tile = json.load(stream)
            buildings, features = [], []
            for feature in tile['features']:
                identifier, role = feature['id'], feature['role']
                match = candidates.get(identifier)
                if role == 'BUILDING_FOOTPRINT':
                    value = dict(id=identifier, districtId=feature['districtId'], polygons=polygons(feature['geometry']),
                        center=feature['center'], heightM=feature['heightM'], heightSource=feature['heightBasis'],
                        areaM2=feature['sourceAreaM2'], candidateId=match[0] if match and match[2] == 'ROOF' else None,
                        geometryEligibility=feature['geometryEligibility'])
                    buildings.append(value)
                    score = (value['areaM2'], identifier, value)
                    if len(overview) < 200:
                        heapq.heappush(overview, score)
                    elif score[:2] > overview[0][:2]:
                        heapq.heapreplace(overview, score)
                else:
                    value = {key: feature[key] for key in ('id', 'role', 'districtId', 'geometry', 'center', 'sourceAreaM2', 'sourceLengthM', 'geometryEligibility')}
                    value.update(candidateId=match[0] if match and match[2] == 'GROUND' else None,
                                 allowedMask=match[1] if match and match[2] == 'GROUND' else 0)
                    if role == 'ROAD_CENTERLINE':
                        value.update({key: feature[key] for key in ('roadClass', 'oneWayObservation', 'trafficDirection', 'reportedWidthRaw', 'reportedWidthUnit')})
                    features.append(value)
                    if role in ('RIVER_WATER_AREA', 'LAKE_RESERVOIR_AREA'):
                        simplified = shapely.simplify(shape(feature['geometry']), 5, preserve_topology=True)
                        if simplified.is_empty or not simplified.is_valid:
                            raise ValueError('전체 보기 수면 표시 도형 오류')
                        waters.append(dict(kind='water', sourceObjectId=identifier, displayToleranceM=5,
                                           polygons=polygons(mapping(simplified))))
            filename = 'tiles/' + entry['id'] + '.json.gz'
            reference = write(output / filename, dict(schemaVersion=2, id=entry['id'], buildings=buildings, nativeFeatures=features), True)
            entries.append(dict(id=entry['id'], file=filename, bounds=entry['bounds'], buildingCount=len(buildings),
                                featureCount=len(features), **reference))
            count += len(buildings)
            if progress and (index + 1) % 100 == 0:
                progress(index + 1, len(scene['tiles']))
        districts = [dict(id=row['id'], name=row['name'], center=row['center'],
            polygons=polygons(row['geometry']), areaKm2=row['areaM2'] / 1e6) for row in scene['districts']]
        boundary = shapely.union_all([shape(row['geometry']) for row in scene['districts']])
        if boundary.is_empty or not boundary.is_valid:
            raise ValueError('공개 행정경계의 표시 합집합 오류')
        district_bounds = boundary.bounds
        bounds = [min(district_bounds[0], *(row['bounds'][0] for row in entries)),
                  min(district_bounds[1], *(row['bounds'][1] for row in entries)),
                  max(district_bounds[2], *(row['bounds'][2] for row in entries)),
                  max(district_bounds[3], *(row['bounds'][3] for row in entries))]
        city = dict(schemaVersion=2, id=scene['id'], sourceSha256=scene['sourceSpatialSha256'],
            sourceObjectsSha256=scene['sourceObjectsSha256'], siteCatalogSha256=reader.sha256, sourceDate='2026-03-07',
            attribution=scene['attribution'], licenseUrl=scene['licenseEvidenceUrl'], coordinateSystem='EPSG:5186',
            originProjected=scene['originProjected'], tileSizeM=1000, bounds=bounds,
            boundary=polygons(mapping(boundary)), districts=districts,
            surfaces=waters, roads=[], overviewBuildings=[row[2] for row in sorted(overview, reverse=True)],
            buildingCount=count, tiles=entries, playAreas=[],
            limitations=['2026-03-07 갱신 수치지형도; 원 도엽 제작연도와 구분',
                '높이는 확인된 층수×3.2m 표시 가정 또는 미확인 0.3m 평면 표시; 현장 높이 아님',
                '도로면·보도·건물은 원 도형 보존; 폭 단위·미확인 일방 방향·주차 칸 추정 없음',
                '전체 보기 수면만 5m 표시 단순화; 면적·설치·수문 계산은 원형 후보 DB 사용',
                '배경 높이는 별도 Copernicus DSM의 90m 표시 격자이며 수문·관망 입력이나 현장 지반고가 아님'])
        reference = write(output / 'city.json', city)
        game_raw = game_catalog._read('catalog.json')
        with (output / 'game.json').open('xb') as target:
            target.write(game_raw)
        if (count != scene['counts']['BUILDING_FOOTPRINT'] or spatial.file_sha256(__file__) != code_sha
                or spatial.file_sha256(SCENE / 'catalog.json') != SCENE_SHA256):
            raise ValueError('장면 묶음 생성 중 코드·입력 변경')
        summary = dict(schemaVersion=1, generatorSha256=code_sha, sourceSceneSha256=SCENE_SHA256,
            sourceObjectsSha256=scene['sourceObjectsSha256'], siteCatalogSha256=reader.sha256,
            forcingCatalogSha256=game_catalog.SHA256, city=reference, tileCount=len(entries), buildingCount=count,
            storedTileBytes=sum(row['storedBytes'] for row in entries), rawTileBytes=sum(row['bytes'] for row in entries),
            versions={'python': platform.python_version(), 'zlib': zlib.ZLIB_RUNTIME_VERSION,
                      'shapely': shapely.__version__, 'geos': shapely.geos_version_string},
            geometryClippedToTile=False, detailGeometrySimplified=False, modelCalculationsFromDisplayGeometry=False)
        (output / 'summary.json').write_text(source.canonical(summary) + '\n')
        return summary
    except BaseException:
        shutil.rmtree(output)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    summary = package(args.output.absolute(), lambda done, total: print(source.canonical(dict(tiles=done, total=total)), flush=True))
    print(source.canonical(summary))


if __name__ == '__main__':
    main()

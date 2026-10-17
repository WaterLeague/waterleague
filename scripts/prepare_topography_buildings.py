"""보관한 수치지형도에서 서비스용 건물 스냅샷 생성. 외부 API 호출 없음."""
import argparse
import hashlib
import json
import math
import re
import tempfile
import zipfile
from pathlib import Path

import pyproj
import shapely
from shapely.geometry import shape, mapping
from pyproj.enums import TransformDirection

import audit_spatial_sources as audit

LAYER = 'N1A_B0010000'


def normalize(features, boundary, transformer, tile):
    buildings = []
    for feature in features:
        geometry = shape(feature['geometry'])
        if (geometry.geom_type not in ('Polygon', 'MultiPolygon') or geometry.is_empty
                or shapely.get_coordinate_dimension(geometry) != 2 or not geometry.is_valid
                or not all(math.isfinite(v) for p in shapely.get_coordinates(geometry) for v in p)):
            raise audit.SpatialDataError('유효한 2차원 건물 경계 필요')
        if geometry.intersection(boundary).area <= 0:
            continue
        props = feature['properties']
        identifier, name, floors = props.get('UFID'), props.get('명칭') or '', props.get('층수')
        if (not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', identifier)
                or not isinstance(name, str) or len(name) > 200 or '\ufffd' in name
                or floors is not None and (type(floors) != int or not 0 <= floors <= 200)):
            raise audit.SpatialDataError('건물 속성 형식 오류')
        geographic = shapely.transform(geometry, lambda x, y: transformer.transform(
            x, y, direction=TransformDirection.INVERSE, errcheck=True), interleaved=False)
        if (not geographic.is_valid or any(not (127.04 <= x <= 127.07 and 37.53 <= y <= 37.56)
                                          for x, y in shapely.get_coordinates(geographic))):
            raise audit.SpatialDataError('변환된 건물 경계 오류')
        coordinates = mapping(geographic)['coordinates']
        buildings.append({'id': f'{tile}:{identifier}', 'name': name,
                          'aboveGroundFloors': floors if floors else None,
                          'polygons': [coordinates] if geographic.geom_type == 'Polygon' else coordinates})
    if len({b['id'] for b in buildings}) != len(buildings):
        raise audit.SpatialDataError('중복 건물 식별자')
    return sorted(buildings, key=lambda b: b['id'])


def prepare(registry):
    sources = audit.ROOT/registry['sourceDirectory']
    buildings, details = [], []
    for source in registry['files']:
        path = sources/source['file']
        if path.is_symlink() or audit.digest(path) != source['sha256'] or path.stat().st_size != source['bytes']:
            raise audit.SpatialDataError('수치지도 원본 무결성 오류')
        if path.suffix != '.zip':
            continue
        tile = source['file'].split('_')[1]
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or archive.testzip() is not None:
                raise audit.SpatialDataError('수치지도 압축 중복·CRC 오류')
            prj = archive.read(LAYER+'.prj').decode('utf-8')
        boundary, crs = audit.study_boundary(prj)
        transformer = pyproj.Transformer.from_pipeline(crs['pipeline'])
        with tempfile.TemporaryDirectory(prefix='waterleague-topography-') as directory:
            output = Path(directory)/'native.json'
            audit.command('ogr2ogr', '-f', 'GeoJSON', '-oo', 'ENCODING=CP949', output,
                          '/vsizip/'+str(path), LAYER)
            if output.stat().st_size > 32*1024**2:
                raise audit.SpatialDataError('건물 변환 출력 크기 초과')
            features = json.loads(output.read_text())['features']
        selected = normalize(features, boundary, transformer, tile)
        buildings.extend(selected)
        details.append({'tile': tile, 'sourceSha256': source['sha256'],
                        'totalFeatureCount': len(features), 'selectedCount': len(selected), 'crs': crs})
    if not 1 <= len(buildings) <= 1000 or len({b['id'] for b in buildings}) != len(buildings):
        raise audit.SpatialDataError('스냅샷 건물 수·식별자 오류')
    return {'schemaVersion': 1, 'provider': registry['provider'], 'layer': LAYER,
            'requestedCrs': 'EPSG:4326', 'sourceUrl': registry['sourceUrl'],
            'retrievedAt': registry['acquiredAt'], 'dataYear': registry['editionYear'],
            'use': 'DISPLAY_COMPARISON_ONLY', 'rawRetained': True,
            'bounds': registry['boundsWgs84'], 'buildings': sorted(buildings, key=lambda b: b['id'])}, details


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    registry_path = audit.ROOT/'data/manifests/seongsu-topography-sources.json'
    registry = json.loads(registry_path.read_text())
    snapshot, details = prepare(registry)
    data = (json.dumps(snapshot, ensure_ascii=False, separators=(',', ':'), allow_nan=False)+'\n').encode()
    digest = hashlib.sha256(data).hexdigest()
    resource = audit.ROOT/'backend/src/main/resources/spatial/seongsu-buildings.json'
    checksum = resource.with_suffix('.sha256')
    metadata = audit.ROOT/'data/manifests/seongsu-topography-buildings.json'
    summary = {'schemaVersion': 1, 'snapshotSha256': digest, 'registrySha256': audit.digest(registry_path),
               'generatorSha256': audit.digest(Path(__file__)), 'buildings': len(snapshot['buildings']),
               'selection': 'POSITIVE_AREA_INTERSECTION_WITH_STUDY_BOUNDS_FULL_FEATURE_PRESERVED',
               'tileFragmentsMerged': False, 'tiles': details,
               'versions': {'gdal': audit.command('ogrinfo', '--version').strip(),
                            'pyproj': pyproj.__version__, 'proj': pyproj.proj_version_str,
                            'shapely': shapely.__version__, 'geos': shapely.geos_version_string},
               'limitations': ['2025 제작 자료이며 2024 강우 당시 형상 일치 미검증',
                               '도엽별 건물 도형이며 건수 차이를 누락 건물 수로 해석하지 않음',
                               '층수는 실측 높이·표고가 아님', '화면 대조 자료; 수문 모델 변경 없음']}
    outputs = {resource: data, checksum: (digest+'\n').encode(),
               metadata: (json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode()}
    for path, payload in outputs.items():
        if path.exists():
            if path.read_bytes() != payload:
                raise audit.SpatialDataError('기존 스냅샷과 불일치; 자료 버전 검토 필요')
        elif args.check:
            raise audit.SpatialDataError('스냅샷 누락')
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(payload)
    print(json.dumps({'buildings': len(snapshot['buildings']), 'sha256': digest, 'checked': args.check}))


if __name__ == '__main__':
    main()

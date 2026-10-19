"""서울시 공개 자치구 영역의 소속·집계용 경계 정규화."""
import argparse
import json
import os
from pathlib import Path
import re
import struct
import zipfile

import pyproj
import shapely
from shapely.geometry import mapping

import prepare_seoul_topography as source
import topography_catalog as native

ARCHIVE = source.ROOT / 'data/raw/seoul-district-boundaries-20231031.zip'
ARCHIVE_SHA256 = 'abd34d82897f0c2191fe4095df55a4aacfe8fce815fa4dacf730cc34c6dd962c'
OUTPUT = source.ROOT / 'data/derived/seoul-district-boundaries-v1.json'
SOURCE_URL = 'https://data.seoul.go.kr/dataList/OA-22161/A/1/datasetView.do'


def prepare(path=ARCHIVE):
    with source.source_stream(path, 488551, ARCHIVE_SHA256) as (stream, _):
        with zipfile.ZipFile(stream) as archive:
            entries = source.archive_members(archive)
            components = {}
            stems = set()
            for name, entry in entries:
                stem, extension = name.rsplit('.', 1)
                if extension not in ('shp', 'shx', 'dbf', 'prj', 'cpg') or extension in components:
                    raise source.TopographyDataError('자치구 경계 구성 오류')
                stems.add(stem)
                components[extension] = source.read_member(archive, entry)
    if len(stems) != 1 or set(components) != {'shp', 'shx', 'dbf', 'prj', 'cpg'}:
        raise source.TopographyDataError('자치구 SHP/SHX/DBF/PRJ/CPG 구성 누락')
    if components['cpg'].decode('ascii').strip() != 'UTF-8':
        raise source.TopographyDataError('자치구 문자셋 불일치')
    wkt = components['prj'].decode('utf-8-sig')
    crs = pyproj.CRS.from_wkt(wkt)
    if crs.to_epsg() != 5181 or not crs.is_projected or any(a.unit_conversion_factor != 1 for a in crs.axis_info):
        raise source.TopographyDataError('자치구 원 좌표계 불일치')
    pyproj.network.set_network_enabled(False)
    transformer = pyproj.Transformer.from_crs(crs, 5186, always_xy=True, allow_ballpark=False)
    schema = source.dbf_schema(components['dbf'], 'utf-8')
    shp, shx, dbf = components['shp'], components['shx'], components['dbf']
    if (source.shape_header(shp)[0] != 5 or source.shape_header(shx) != source.shape_header(shp)
            or len(shx) != 100 + 8 * schema['recordCount'] or schema['recordCount'] != 25
            or schema['deletedRecordCount']):
        raise source.TopographyDataError('자치구 경계 행·도형 수 불일치')
    expected_names = {f['district'] for f in native.read_json(source.ROOT / source.MANIFEST)['files']
                      if f['role'] == 'DISTRICT_TILE_PACKAGE'}
    features, geometries, cursor = [], [], 100
    for index in range(schema['recordCount']):
        offset, length = struct.unpack_from('>II', shx, 100 + index * 8)
        if cursor != offset * 2:
            raise source.TopographyDataError('자치구 SHX 오프셋 불일치')
        number, actual_length = struct.unpack_from('>II', shp, cursor)
        if number != index + 1 or length != actual_length:
            raise source.TopographyDataError('자치구 원 레코드 번호·길이 불일치')
        content = shp[cursor + 8:cursor + 8 + length * 2]
        source.verify_shape_content(content, 5)
        original = native.native_geometry(content)
        if original['status'] != 'VALID':
            raise source.TopographyDataError('유효하지 않은 자치구 원 도형')
        start = schema['headerBytes'] + schema['recordBytes'] * index
        row = dbf[start:start + schema['recordBytes']]
        props = {f['name']: row[f['offset']:f['offset'] + f['width']].decode('utf-8').strip(' \0')
                 for f in schema['fields']}
        code, name = props['SIGNGU_CD'], props['SIGNGU_NM']
        if not re.fullmatch(r'11\d{3}', code) or name not in expected_names:
            raise source.TopographyDataError('서울 자치구 코드·명칭 불일치')
        geometry = shapely.transform(original['geometry'], transformer.transform, interleaved=False)
        if geometry.is_empty or not geometry.is_valid or abs(geometry.area - original['geometry'].area) > .001:
            raise source.TopographyDataError('자치구 변환 도형·면적 보존 실패')
        representative = geometry.representative_point()
        features.append({'id': code, 'name': name, 'recordNumber': index + 1,
            'sourceRecordId': f'seoul:OA-22161:{index + 1}:{ARCHIVE_SHA256}',
            'rawShapeSha256': source.digest(content), 'rawDbfSha256': source.digest(row),
            'nativeGeometry': mapping(geometry), 'areaM2': geometry.area,
            'centerProjected': [representative.x, representative.y], 'originalAttributes': props})
        geometries.append(geometry)
        cursor += 8 + length * 2
    if (cursor != len(shp) or len({f['id'] for f in features}) != 25
            or {f['name'] for f in features} != expected_names):
        raise source.TopographyDataError('서울 자치구 중복·누락')
    union = shapely.union_all(geometries)
    return {'schemaVersion': 1, 'provider': '서울특별시 · 서울신용보증재단', 'sourceUrl': SOURCE_URL,
        'sourceSha256': ARCHIVE_SHA256, 'license': 'KOGL-TYPE1', 'fileModifiedAt': '2023-10-31',
        'geometryReferenceDate': None, 'coordinateSystem': 'EPSG:5186', 'originalWkt': wkt,
        'transform': {'pipeline': transformer.definition, 'alwaysXY': True, 'ballparkAllowed': False,
                      'statedOperationAccuracyM': transformer.accuracy},
        'generatorSha256': source.digest(Path(__file__).read_bytes()),
        'decoderSha256': source.digest(Path(native.__file__).read_bytes()),
        'versions': {'pyproj': pyproj.__version__, 'proj': pyproj.proj_version_str,
                     'shapely': shapely.__version__, 'geos': shapely.geos_version_string},
        'use': 'DISTRICT_MEMBERSHIP_AGGREGATION_AND_SPATIAL_COVERAGE_AUDIT_ONLY',
        'clipsHydrologicDomain': False, 'geometryRepair': False,
        'districts': sorted(features, key=lambda f: f['id']), 'boundary': mapping(union),
        'areaM2': union.area, 'districtOverlapM2': sum(g.area for g in geometries) - union.area}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    try:
        if os.path.lexists(args.output):
            raise source.TopographyDataError('기존 자치구 경계 덮어쓰기 금지')
        value = prepare()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(source.canonical(value) + '\n')
    except source.TopographyDataError as exc:
        parser.exit(1, f'자치구 경계 생성 실패: {exc}\n')
    except (OSError, ValueError, KeyError, struct.error, zipfile.BadZipFile, shapely.errors.ShapelyError):
        parser.exit(1, '자치구 경계 생성 실패: 원본·좌표계·구성 확인 필요\n')
    print(source.canonical({'districts': len(value['districts']), 'areaKm2': value['areaM2'] / 1e6,
                            'sha256': source.digest(args.output.read_bytes())}))


if __name__ == '__main__':
    main()

"""공개 시설 원본의 해시·삭제 표시·좌표를 보존하는 참고 카탈로그 생성."""
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import urllib.parse
import urllib.request
import zipfile

from pyproj import Transformer
from shapely.geometry import Point, MultiPolygon, Polygon

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'seoul-public-20261018-v1'
ORIGIN = [198128.0, 551989.0]
SOURCES = [
    ('seoul-pump-assets-20261018', '빗물펌프장', 'STORM_PUMP'),
    ('seoul-lid-assets-20261018', '빗물관리시설', 'RAINWATER_FACILITY'),
    ('seoul-assets-OA-21193-20261018', '기타 침투시설', 'INFILTRATION_OTHER'),
    ('seoul-assets-OA-21194-20261018', '침투측구', 'INFILTRATION_GUTTER'),
    ('seoul-assets-OA-21195-20261018', '원형침투통', 'INFILTRATION_PIT'),
    ('seoul-assets-OA-21196-20261018', '침투 트렌치', 'INFILTRATION_TRENCH'),
    ('seoul-assets-OA-21197-20261018', '빗물이용시설', 'RAINWATER_REUSE'),
    ('seoul-assets-OA-21199-20261018', '정방형침투통', 'INFILTRATION_PIT'),
    ('gangseo-pumps-20261018', '강서구 빗물펌프장 제원', 'STORM_PUMP'),
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def payload(value):
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)+'\n').encode()


def raw_source(manifest, fetch):
    path = (ROOT / manifest['path']).resolve()
    if not path.is_relative_to(ROOT / 'data/raw'):
        raise ValueError('원본 저장 경로 오류')
    if not path.exists() and fetch:
        url = manifest['downloadUrl']
        if urllib.parse.urlsplit(url).hostname not in ('datafile.seoul.go.kr', 'www.data.go.kr'):
            raise ValueError('허용되지 않은 공개자료 서버')
        form = manifest.get('downloadForm')
        request = urllib.request.Request(url, data=urllib.parse.urlencode(form).encode() if form else None)
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read(16_000_001)
        if len(data) > 16_000_000 or digest(data) != manifest['sha256']:
            raise ValueError('재취득 원본 변경: 새 버전 필요')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    data = path.read_bytes()
    if digest(data) != manifest['sha256'] or len(data) != manifest['bytes']:
        raise ValueError('공개 시설 원본 무결성 오류')
    return path, data


def read_shape(path):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if (sum(v.file_size for v in entries) > 100_000_000 or
                sum(v.filename.lower().endswith('.shp') for v in entries) != 1 or
                any(Path(v.filename).is_absolute() or '..' in Path(v.filename).parts or
                    Path(v.filename).suffix.lower() not in ('.shp', '.shx', '.dbf', '.cpg', '.prj')
                    for v in entries)):
            raise ValueError('공간 원본 구성 오류')
    result = subprocess.run(['ogr2ogr', '--config', 'SHAPE_ENCODING', 'CP949', '-f', 'GeoJSON',
                             '/vsistdout/', '/vsizip/'+str(path), '-a_srs', 'EPSG:5186'],
                            check=True, capture_output=True, timeout=30)
    return json.loads(result.stdout)['features']


def grouped_pumps(data):
    rows = list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
    groups = {}
    shared_keys = ['펌프장 주소', '위도', '경도', '유역면적(ha)', '유수지 용량(세제곱미터)', '데이터기준일자']
    for row in rows:
        name = row['펌프장명']
        group = groups.setdefault(name, {'row': row, 'units': []})
        if any(group['row'][k] != row[k] for k in shared_keys):
            raise ValueError('동명 펌프장의 공통 제원 불일치')
        unit = int(row['펌프(호기)'])
        if any(v['unit'] == unit for v in group['units']):
            raise ValueError('펌프 호기 중복')
        group['units'].append(dict(unit=unit, powerHp=float(row['펌프 마력(HP)']),
                                   capacityM3Min=float(row['펌프 양수량(세제곱미터_min)'])))
    return groups


def display_status(deletion, district_id, deletion_field=True):
    if deletion == 'Y':
        return 'SOURCE_DELETED'
    if deletion_field and deletion != 'N':
        return 'DELETE_FLAG_UNKNOWN'
    return 'REFERENCE' if district_id else 'OUTSIDE_SEOUL'


def build(fetch=False):
    city_path = ROOT / 'frontend/public/data/seoul-v1/city.json'
    city_raw = city_path.read_bytes()
    city = json.loads(city_raw)
    districts = [(d['id'], MultiPolygon([Polygon(p[0], p[1:]) for p in d['polygons']]))
                 for d in city['districts']]
    def record(source_id, record_id, kind, name, xy, deletion, properties, deletion_field=True):
        center = [round(xy[0]-ORIGIN[0], 3), round(xy[1]-ORIGIN[1], 3)]
        if not all(math.isfinite(v) and abs(v) < 60000 for v in center):
            raise ValueError('시설 좌표 범위 오류')
        hits = [id for id, geometry in districts if geometry.covers(Point(center))]
        district_id = hits[0] if len(hits) == 1 else None
        return dict(id=f'{source_id}:{record_id}', sourceId=source_id, name=name, kind=kind,
                    center=center, districtId=district_id,
                    displayStatus=display_status(deletion, district_id, deletion_field),
                    geometryEvidence='LOCATION_POINT', verticalLayer='UNKNOWN',
                    validFrom=None, validTo=None, operationStatus='UNKNOWN',
                    hydraulicStatus='UNCONNECTED', sourceProperties=properties, pumpSpecs=None)
    assets, sources, lineage = [], [], []
    for manifest_name, title, kind in SOURCES:
        manifest_path = ROOT / f'data/manifests/{manifest_name}.json'
        m = json.loads(manifest_path.read_bytes())
        path, raw = raw_source(m, fetch)
        source = dict(id=m['datasetId'], title=title, publisher='서울특별시 강서구' if path.suffix == '.csv' else '서울특별시',
                      url=m['sourceUrl'], sha256=m['sha256'], license='KOGL_TYPE_1',
                      fileModifiedAt=m.get('fileModifiedAt'), portalUpdatedAt=m.get('portalUpdatedAt'),
                      referenceDate='2025-09-08' if path.suffix == '.csv' else None,
                      crs='EPSG:4326' if path.suffix == '.csv' else 'EPSG:5186',
                      retrievedAt=m['retrievedAt'])
        start = len(assets)
        if path.suffix == '.csv':
            transform = Transformer.from_crs(4326, 5186, always_xy=True, allow_ballpark=False)
            for name, group in sorted(grouped_pumps(raw).items()):
                row = group['row']
                xy = transform.transform(float(row['경도']), float(row['위도']))
                item = record(m['datasetId'], name, kind, name+' 빗물펌프장', xy, None, row, False)
                item['pumpSpecs'] = dict(asOf=row['데이터기준일자'], address=row['펌프장 주소'],
                                        basinAreaHa=float(row['유역면적(ha)']),
                                        storageCapacityM3=float(row['유수지 용량(세제곱미터)']),
                                        units=sorted(group['units'], key=lambda u: u['unit']))
                assets.append(item)
            source['inputRows'] = len(list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))))
        else:
            for feature in read_shape(path):
                geometry, p = feature['geometry'], feature['properties']
                if geometry['type'] != 'MultiPoint' or len(geometry['coordinates']) != 1:
                    raise ValueError('지원하지 않는 시설 형상: 별도 해석 필요')
                name = (p.get('PUMP_NM')+' 빗물펌프장' if p.get('PUMP_NM') else
                        title+' · 등록 '+str(p.get('REGSTR_NO', p['OBJECTID'])))
                assets.append(record(m['datasetId'], str(p['OBJECTID']), kind, name,
                                     geometry['coordinates'][0], p.get('DEL_YN'), p, kind != 'STORM_PUMP'))
        source['records'] = len(assets)-start
        sources.append(source)
        lineage.append(dict(manifest=str(manifest_path.relative_to(ROOT)), sha256=digest(manifest_path.read_bytes())))
    if len({a['id'] for a in assets}) != len(assets):
        raise ValueError('공개 시설 식별자 중복')
    value = dict(version=VERSION, origin=ORIGIN, coordinateSystem='EPSG:5186_LOCAL',
                 sources=sources, assets=sorted(assets, key=lambda a: a['id']))
    meta = dict(version=VERSION, sources=lineage, citySha256=digest(city_raw),
                generatorSha256=digest(Path(__file__).read_bytes()),
                gdal=subprocess.check_output(['ogr2ogr', '--version'], text=True).strip(),
                recordCount=len(assets), statusCounts={s: sum(a['displayStatus'] == s for a in assets)
                    for s in ['REFERENCE', 'SOURCE_DELETED', 'DELETE_FLAG_UNKNOWN', 'OUTSIDE_SEOUL']})
    return value, meta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--fetch', action='store_true')
    args = parser.parse_args()
    catalog, meta = build(args.fetch)
    output = ROOT / f'backend/src/main/resources/infrastructure/{VERSION}.json'
    raw = payload(catalog)
    meta.update(catalogPath=str(output.relative_to(ROOT)), sha256=digest(raw), bytes=len(raw))
    for path, data in [(output, raw), (ROOT/f'data/manifests/{VERSION}.json', payload(meta))]:
        if path.exists():
            if path.read_bytes() != data:
                raise ValueError(f'불변 자료 불일치: {path.name}')
        elif args.check:
            raise ValueError('파생 자료 미생성')
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    print(json.dumps(meta, ensure_ascii=False))


if __name__ == '__main__':
    main()

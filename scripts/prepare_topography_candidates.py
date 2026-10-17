"""공개 수치지도 경계에서 다음 모델용 배치 후보 생성. 운영 모델 변경 없음."""
import argparse
import hashlib
import json
import math
import re
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

import pyproj
import shapely
from shapely.geometry import Polygon, box, mapping, shape
from shapely.ops import unary_union
from pyproj.enums import TransformDirection

import audit_spatial_sources as audit

LAYERS = {'buildings': 'N1A_B0010000', 'roads': 'N1A_A0010000',
          'railways': 'N1A_A0160024', 'bridges': 'N1A_A0070000'}
POLICY = {'minimumRoofAreaM2': 100, 'roofCount': 8, 'groundCount': 5, 'gridSizeM': 5,
          'roofOrdering': 'AREA_DESCENDING_THEN_SOURCE_ID',
          'groundOrdering': 'NEAREST_STUDY_CENTER_THEN_FARTHEST_MINIMUM_DISTANCE_THEN_GRID_ID',
          'groundBoundaryContactAllowed': False, 'siteEligibility': 'UNKNOWN'}


def validate_geometry(geometry):
    if (geometry.geom_type not in ('Polygon', 'MultiPolygon') or geometry.is_empty
            or not geometry.is_valid or geometry.area <= 0
            or shapely.get_coordinate_dimension(geometry) != 2
            or any(not math.isfinite(v) for p in shapely.get_coordinates(geometry) for v in p)):
        raise audit.SpatialDataError('수치지도 유효 2차원 면적 도형 필요')
    return geometry


def read_sources(registry):
    records = {kind: [] for kind in LAYERS}
    source_root = audit.ROOT/registry['sourceDirectory']
    metadata, reference_wkt, study, crs = [], None, None, None
    for source in registry['files']:
        path = source_root/source['file']
        if path.is_symlink() or path.stat().st_size != source['bytes'] or audit.digest(path) != source['sha256']:
            raise audit.SpatialDataError('등록 수치지도 원본 불일치')
        if path.suffix != '.zip':
            continue
        tile = source['file'].split('_')[1]
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or archive.testzip() is not None:
                raise audit.SpatialDataError('원본 압축 중복·CRC 오류')
            for layer in LAYERS.values():
                wkt = archive.read(layer+'.prj').decode('utf-8')
                if reference_wkt is None:
                    reference_wkt = wkt
                    study, crs = audit.study_boundary(wkt)
                if wkt != reference_wkt:
                    raise audit.SpatialDataError('레이어 간 원문 좌표계 불일치; 개별 변환 필요')
        with tempfile.TemporaryDirectory(prefix='waterleague-candidates-') as directory:
            for kind, layer in LAYERS.items():
                output = Path(directory)/(layer+'.json')
                audit.command('ogr2ogr', '-f', 'GeoJSON', '-oo', 'ENCODING=CP949', output,
                              '/vsizip/'+str(path), layer)
                if output.stat().st_size > 32*1024**2:
                    raise audit.SpatialDataError('레이어 변환 출력 크기 초과')
                features = json.loads(output.read_text())['features']
                ids, selected = set(), 0
                for feature in features:
                    geometry = validate_geometry(shape(feature['geometry']))
                    identifier = feature['properties'].get('UFID')
                    if (not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', identifier)
                            or identifier in ids):
                        raise audit.SpatialDataError('수치지도 식별자 누락·중복')
                    ids.add(identifier)
                    if geometry.intersection(study).area <= 0:
                        continue
                    attributes = {}
                    if kind == 'buildings':
                        floors = feature['properties'].get('층수')
                        if floors is not None and (type(floors) != int or not 0 <= floors <= 200):
                            raise audit.SpatialDataError('수치지도 층수 형식 오류')
                        attributes = {'aboveGroundFloors': floors or None}
                    records[kind].append({'id': f'{tile}:{identifier}', 'geometry': geometry,
                                          'attributes': attributes})
                    selected += 1
                metadata.append({'tile': tile, 'layer': layer, 'sourceSha256': source['sha256'],
                                 'totalCount': len(features), 'selectedCount': selected})
        if audit.digest(path) != source['sha256']:
            raise audit.SpatialDataError('검사 중 원본 변경')
    if study is None:
        raise audit.SpatialDataError('수치지도 원본 없음')
    for values in records.values():
        values.sort(key=lambda r: r['id'])
        if len({r['id'] for r in values}) != len(values):
            raise audit.SpatialDataError('도엽 간 식별자 충돌')
    return records, study, crs, metadata


def select_candidates(records, study):
    validate_geometry(study)
    unions = {kind: unary_union([validate_geometry(r['geometry']) for r in records[kind]]) for kind in LAYERS}
    forbidden_roof = unary_union([unions[k] for k in ('roads', 'railways', 'bridges')])
    forbidden_ground = unary_union([unions[k] for k in ('buildings', 'railways', 'bridges')])
    excluded = Counter()
    roof_pool = []
    for item in records['buildings']:
        g = item['geometry']
        if g.geom_type != 'Polygon' or g.interiors:
            excluded['UNSUPPORTED_HOLES_OR_MULTIPART'] += 1
        elif not study.covers(g):
            excluded['OUTSIDE_STUDY'] += 1
        elif g.area < POLICY['minimumRoofAreaM2']:
            excluded['BELOW_ROOF_AREA_THRESHOLD'] += 1
        elif g.intersection(forbidden_roof).area > 0:
            excluded['TRANSPORT_AREA_OVERLAP'] += 1
        else:
            roof_pool.append(item)
    roof_pool.sort(key=lambda r: (-r['geometry'].area, r['id']))
    selected = [{'id': f'R{i+1}', 'kind': 'ROOF', 'sourceIds': [item['id']],
                 'geometry': item['geometry'], 'attributes': item['attributes']}
                for i, item in enumerate(roof_pool[:POLICY['roofCount']])]
    minx, miny, maxx, maxy = study.bounds
    size = POLICY['gridSizeM']
    ground_pool = []
    for x in range(math.floor(minx/size)*size, math.ceil(maxx), size):
        for y in range(math.floor(miny/size)*size, math.ceil(maxy), size):
            g = box(x, y, x+size, y+size)
            if not study.covers(g):
                continue
            if not unions['roads'].covers(g):
                continue
            if g.intersects(forbidden_ground):
                continue
            sources = sorted(r['id'] for r in records['roads'] if r['geometry'].intersection(g).area > 0)
            ground_pool.append({'gridId': f'{x}:{y}', 'kind': 'GROUND', 'geometry': g,
                                'sourceIds': sources, 'attributes': {}})
    original_pool_count = len(ground_pool)
    picked = []
    while ground_pool and len(picked) < POLICY['groundCount']:
        if not picked:
            ground_pool.sort(key=lambda r: (r['geometry'].centroid.distance(study.centroid), r['gridId']))
        else:
            ground_pool.sort(key=lambda r: (-min(r['geometry'].centroid.distance(
                p['geometry'].centroid) for p in picked), r['gridId']))
        picked.append(ground_pool.pop(0))
    selected += [{'id': f'G{i+1}', **item} for i, item in enumerate(picked)]
    selected_union = unary_union([c['geometry'] for c in selected])
    summed = math.fsum(c['geometry'].area for c in selected)
    if abs(summed-selected_union.area) > 1e-7:
        raise audit.SpatialDataError('후보 간 면적 중첩')
    return selected, {'roofEligibleCount': len(roof_pool), 'roofExcludedCounts': dict(sorted(excluded.items())),
                      'groundEligibleCount': original_pool_count,
                      'selectedAreaSumM2': summed, 'selectedAreaUnionM2': selected_union.area}


def serialize(candidates, transformer, origin):
    output = []
    for c in candidates:
        g = c['geometry']
        geographic = shapely.transform(g, lambda x, y: transformer.transform(
            x, y, direction=TransformDirection.INVERSE, errcheck=True), interleaved=False)
        if any(not (127.04 <= x <= 127.07 and 37.53 <= y <= 37.56) for x,y in shapely.get_coordinates(geographic)):
            raise audit.SpatialDataError('후보 역변환 범위 오류')
        center = g.representative_point()
        output.append({k: v for k, v in c.items() if k != 'geometry'} | {
            'nativeGeometry': mapping(g), 'geographicGeometry': mapping(geographic),
            'coordinates': [[x-origin[0], y-origin[1]] for x,y in g.exterior.coords],
            'center': [center.x-origin[0], center.y-origin[1]], 'areaM2': g.area,
            'areaEvidence': 'NGII_PROJECTED_FOOTPRINT' if c['kind'] == 'ROOF' else 'DESIGN_GRID_WITHIN_NGII_ROAD',
            'siteEligibility': 'UNKNOWN'})
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    registry_path = audit.ROOT/'data/manifests/seongsu-topography-sources.json'
    registry = json.loads(registry_path.read_text())
    records, study, crs, metadata = read_sources(registry)
    selected, selection = select_candidates(records, study)
    transformer = pyproj.Transformer.from_pipeline(crs['pipeline'])
    west,south,east,north = registry['boundsWgs84']
    origin = transformer.transform((west+east)/2, (south+north)/2, errcheck=True)
    data = {'schemaVersion': 1, 'status': 'CANDIDATE_SET_NOT_ACTIVE',
            'provider': registry['provider'], 'sourceUrl': registry['sourceUrl'],
            'license': registry['license'], 'dataYear': registry['editionYear'],
            'registrySha256': audit.digest(registry_path), 'generatorSha256': audit.digest(Path(__file__)),
            'auditHelperSha256': audit.digest(Path(audit.__file__)), 'policy': POLICY,
            'boundsWgs84': registry['boundsWgs84'], 'originProjected': origin,
            'crs': crs, 'sources': metadata, 'selection': selection,
            'versions': {'gdal': audit.command('ogrinfo','--version').strip(), 'pyproj': pyproj.__version__,
                         'proj': pyproj.proj_version_str, 'shapely': shapely.__version__, 'geos': shapely.geos_version_string},
            'cells': serialize(selected, transformer, origin),
            'limitations': ['2025 지도 형상이며 과거 강우 당시 지표면 일치 미검증',
                            '건물 footprint는 실측 지붕 경계·높이·하중 검증이 아님',
                            '도로 격자는 실험 설계 단위이며 시공 허가·기존 투수성·배수 연결 미확인',
                            '시설 설치가능 면적 비율·표고·경사·토양·수문계수 미부여',
                            '운영 모델·기존 기록 변경 없음']}
    payload = (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode()
    output = audit.ROOT/'data/derived/seongsu-topography-candidates-v2.json'
    if output.is_symlink() or output.exists() and output.read_bytes() != payload:
        raise audit.SpatialDataError('기존 후보 자료와 불일치; 새 버전 검토 필요')
    if not output.exists():
        if args.check:
            raise audit.SpatialDataError('후보 자료 누락')
        with output.open('xb') as stream:
            stream.write(payload)
    print(json.dumps({'cells': len(selected), 'selection': selection,
                      'sha256': hashlib.sha256(payload).hexdigest(), 'checked': args.check}))


if __name__ == '__main__':
    main()

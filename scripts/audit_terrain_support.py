"""보관된 표고점·등고선·DEM의 공간 지지 범위 진단. 모델 입력 변경 없음."""
import argparse
import hashlib
import json
import math
import os
import re
import stat
import tempfile
import zipfile
from pathlib import Path

import pyproj
import shapely
from pyproj.aoi import AreaOfInterest
from pyproj.transformer import TransformerGroup
from shapely.geometry import MultiPoint, Point, Polygon, mapping, shape

import audit_spatial_sources as audit

LAYERS = {'points': 'N1P_F0020000', 'contours': 'N1L_F0010000'}
CANDIDATE_SHA = 'd879febb289cd101caaec9758a2e5df078ed903f1f1b8983b37fa1a7b0d485ec'
LIMITATIONS = [
    '표고점·DEM의 해상도·제작 시점·수직 기준이 통일되지 않은 수치 대조',
    'DEM 밴드 단위·수직 기준·취득일 미확인; 값 차이를 미터 단위 정확도나 보정량으로 해석하지 않음',
    '점 사이의 삼각망 선형 보간은 추정이며 실측 지면·도로 경사·배수경계가 아님',
    '차이가 큰 원본 점도 보존; 표고점의 현장 대상·높이 기준 확인 필요',
    '90m DEM 격자 값을 개별 시설 위치의 실측값으로 취급하지 않음',
    '옥상 구역 중심의 지형 자료 대조이며 지붕 높이·하중·시공 적합성 검증이 아님',
    '수문 모델·3D 지면·과거 기록·순위에 미반영',
]


def finite(values):
    return all(type(v) in (int, float) and math.isfinite(v) for v in values)


def feature_records(features, kind, tile):
    if kind not in LAYERS:
        raise audit.SpatialDataError('지원하지 않는 표고 레이어')
    records, ids = [], set()
    for feature in features:
        geometry = shape(feature['geometry'])
        props = feature['properties']
        value_field = '수치' if kind == 'points' else '등고수치'
        identifier, value = props.get('UFID'), props.get(value_field)
        allowed = ('Point',) if kind == 'points' else ('LineString', 'MultiLineString')
        if (geometry.geom_type not in allowed or geometry.is_empty or not geometry.is_valid
                or shapely.get_coordinate_dimension(geometry) != 2
                or not finite(shapely.get_coordinates(geometry).ravel().tolist())
                or not finite([value])):
            raise audit.SpatialDataError('표고 도형·수치 형식 오류')
        if (not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', identifier)
                or identifier in ids):
            raise audit.SpatialDataError('표고 식별자 누락·중복')
        ids.add(identifier)
        records.append({'id': f'{tile}:{identifier}', 'value': value, 'valueField': value_field,
                        'properties': props, 'geometry': mapping(geometry)})
    return sorted(records, key=lambda r: r['id'])


class LinearTin:
    def __init__(self, records):
        if not 3 <= len(records) <= 10000:
            raise audit.SpatialDataError('삼각망 점 개수 오류')
        self.points, ids = {}, set()
        for record in sorted(records, key=lambda r: r['id']):
            xy, value, identifier = tuple(record['coordinates']), record['value'], record['id']
            if (len(xy) != 2 or not finite([*xy, value]) or xy in self.points or identifier in ids
                    or not isinstance(identifier, str) or not identifier):
                raise audit.SpatialDataError('삼각망 중복·비유한 입력 거부')
            self.points[xy] = {'id': identifier, 'value': value}
            ids.add(identifier)
        cloud = MultiPoint(list(self.points))
        self.hull = cloud.convex_hull
        if self.hull.geom_type != 'Polygon' or self.hull.area <= 0:
            raise audit.SpatialDataError('삼각망 면적 없는 점 배열')
        self.triangles = []
        for triangle in shapely.delaunay_triangles(cloud, tolerance=0).geoms:
            coordinates = sorted(tuple(xy) for xy in list(triangle.exterior.coords)[:-1])
            if len(coordinates) != 3 or any(xy not in self.points for xy in coordinates):
                raise audit.SpatialDataError('삼각망 꼭짓점과 원본 연결 오류')
            self.triangles.append({'geometry': Polygon(coordinates), 'coordinates': coordinates,
                                   'pointIds': [self.points[xy]['id'] for xy in coordinates]})
        self.triangles.sort(key=lambda t: t['coordinates'])
        covered = shapely.union_all([t['geometry'] for t in self.triangles])
        if not covered.equals(self.hull):
            raise audit.SpatialDataError('삼각망 볼록껍질 피복 오류')

    def sample(self, xy):
        if len(xy) != 2 or not finite(xy):
            raise audit.SpatialDataError('보간 조회 좌표 오류')
        point = Point(xy)
        # 외삽을 막기 위해 수치 여유로 경계를 확장하지 않음.
        if not self.hull.covers(point):
            return None
        for index, triangle in enumerate(self.triangles):
            if not triangle['geometry'].covers(point):
                continue
            (ax, ay), (bx, by), (cx, cy) = triangle['coordinates']
            x, y = xy
            determinant = (by-cy)*(ax-cx)+(cx-bx)*(ay-cy)
            if determinant == 0:
                raise audit.SpatialDataError('퇴화 삼각형 거부')
            a = ((by-cy)*(x-cx)+(cx-bx)*(y-cy))/determinant
            b = ((cy-ay)*(x-cx)+(ax-cx)*(y-cy))/determinant
            weights = [a, b, 1-a-b]
            values = [self.points[p]['value'] for p in triangle['coordinates']]
            value = math.fsum(w*z for w, z in zip(weights, values))
            if not finite([*weights, value]) or min(weights) < -1e-12 or max(weights) > 1+1e-12:
                raise audit.SpatialDataError('삼각망 가중치 오류')
            return {'triangleIndex': index, 'pointIds': triangle['pointIds'],
                    'weights': weights, 'rawValue': value}
        raise audit.SpatialDataError('삼각망 내부 조회 누락')

    def describe(self):
        return {'method': 'POINT_ONLY_DELAUNAY_LINEAR', 'snapToleranceM': 0,
                'extrapolationAllowed': False, 'hull': mapping(self.hull),
                'triangles': [{k: v for k, v in t.items() if k != 'geometry'} for t in self.triangles]}


def sample_grid(report, rows, xy):
    gt, size = report['geoTransform'], report['size']
    if (len(xy) != 2 or not finite(xy) or len(gt) != 6 or not finite(gt)
            or gt[1] <= 0 or gt[5] >= 0 or gt[2] != 0 or gt[4] != 0
            or len(size) != 2 or any(type(v) != int or v <= 0 for v in size)
            or len(rows) != math.prod(size)):
        raise audit.SpatialDataError('DEM 조회 격자·좌표 오류')
    column = math.floor((xy[0]-gt[0])/gt[1])
    row = math.floor((xy[1]-gt[3])/gt[5])
    if not (0 <= column < size[0] and 0 <= row < size[1]):
        return {'status': 'OUTSIDE_GRID', 'rawValue': None}
    x, y, value = rows[row*size[0]+column]
    if not finite([x, y]) or abs(x-(gt[0]+(column+.5)*gt[1])) > 1e-6 or abs(
            y-(gt[3]+(row+.5)*gt[5])) > 1e-6:
        raise audit.SpatialDataError('DEM 원본 격자 순서 오류')
    valid = finite([value]) and value != report['noDataValue']
    return {'status': 'VALID_RAW_CELL' if valid else 'NODATA', 'row': row, 'column': column,
            'cellCenter': [x, y], 'rawValue': value if valid else None}


def read_sources(registry):
    records, metadata, reference_wkt = {k: [] for k in LAYERS}, [], None
    for source in registry['files']:
        path = audit.ROOT/registry['sourceDirectory']/source['file']
        if path.is_symlink() or path.stat().st_size != source['bytes'] or audit.digest(path) != source['sha256']:
            raise audit.SpatialDataError('등록 수치지도 원본 불일치')
        if path.suffix != '.zip':
            continue
        tile = source['file'].split('_')[1]
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if (len(names) > 512 or len(set(names)) != len(names)
                    or sum(i.file_size for i in archive.infolist()) > 64*1024**2
                    or any(not re.fullmatch(r'[A-Za-z0-9_]+\.[A-Za-z0-9]+', i.filename)
                           or i.flag_bits & 1 or stat.S_IFMT(i.external_attr >> 16)
                           not in (0, stat.S_IFREG) for i in archive.infolist())
                    or archive.testzip() is not None):
                raise audit.SpatialDataError('수치지도 압축 구조·CRC 오류')
            for kind, layer in LAYERS.items():
                files = [layer+suffix for suffix in ('.shp', '.shx', '.dbf', '.prj')]
                available = [name in names for name in files]
                if not all(available):
                    if any(available) or kind == 'points':
                        raise audit.SpatialDataError('표고 레이어 구성 누락')
                    metadata.append({'tile': tile, 'layer': layer, 'present': False,
                                     'count': 0, 'sourceSha256': source['sha256']})
                    continue
                wkt = archive.read(layer+'.prj').decode('utf-8')
                if reference_wkt is None:
                    reference_wkt = wkt
                if wkt != reference_wkt:
                    raise audit.SpatialDataError('표고 레이어 원문 좌표계 불일치')
                with tempfile.TemporaryDirectory(prefix='waterleague-terrain-layer-') as directory:
                    target = Path(directory)/'native.json'
                    audit.command('ogr2ogr', '-f', 'GeoJSON', '-oo', 'ENCODING=CP949', target,
                                  '/vsizip/'+str(path), layer)
                    if target.stat().st_size > 32*1024**2:
                        raise audit.SpatialDataError('표고 레이어 변환 크기 초과')
                    selected = feature_records(json.loads(target.read_text())['features'], kind, tile)
                records[kind].extend(selected)
                metadata.append({'tile': tile, 'layer': layer, 'present': True,
                                 'count': len(selected), 'sourceSha256': source['sha256']})
        if audit.digest(path) != source['sha256']:
            raise audit.SpatialDataError('검사 중 원본 변경')
    if reference_wkt is None:
        raise audit.SpatialDataError('표고 원본 없음')
    for kind in records:
        records[kind].sort(key=lambda r: r['id'])
        if len({r['id'] for r in records[kind]}) != len(records[kind]):
            raise audit.SpatialDataError('도엽 간 표고 식별자 중복')
    return records, metadata, reference_wkt


def comparison_stats(samples):
    values = [s['demMinusReferenceRawValue'] for s in samples if s['demMinusReferenceRawValue'] is not None]
    return {'comparedCount': len(values), 'missingCount': len(samples)-len(values),
            'demMinusReferenceRawValue': audit.stats(values),
            'absoluteRawDifference': audit.stats([abs(v) for v in values]),
            'unitCompatibility': 'UNVERIFIED', 'accuracyMetric': False}


def bytes_for(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode()


def build_report():
    registry_path = audit.ROOT/'data/manifests/seongsu-topography-sources.json'
    candidate_path = audit.ROOT/'data/derived/seongsu-topography-candidates-v2.json'
    if audit.digest(candidate_path) != CANDIDATE_SHA:
        raise audit.SpatialDataError('고정 배치 후보 해시 불일치')
    registry = json.loads(registry_path.read_text())
    candidates = json.loads(candidate_path.read_text())
    if candidates['registrySha256'] != audit.digest(registry_path):
        raise audit.SpatialDataError('후보와 원본 목록 연결 불일치')
    records, sources, wkt = read_sources(registry)
    study, crs = audit.study_boundary(wkt)
    if candidates['crs']['originalWkt'] != wkt:
        raise audit.SpatialDataError('후보와 표고 원문 좌표계 불일치')
    points = [{'id': r['id'], 'coordinates': r['geometry']['coordinates'], 'value': r['value']}
              for r in records['points']]
    tin = LinearTin(points)
    targets = []
    for cell in candidates['cells']:
        center = [a+b for a, b in zip(cell['center'], candidates['originProjected'])]
        geometry = shape(cell['nativeGeometry'])
        if not geometry.covers(Point(center)):
            raise audit.SpatialDataError('배치 중심과 원본 도형 불일치')
        targets.append({'id': cell['id'], 'kind': cell['kind'], 'coordinates': center,
                        'samplingLocation': 'STORED_REPRESENTATIVE_POINT', 'tin': tin.sample(center)})
    point_geometries = [Point(r['coordinates']) for r in points]
    contours = [shape(r['geometry']) for r in records['contours']]
    summary = {'sourcePointCount': len(points),
               'pointsWithinStudy': sum(study.covers(p) for p in point_geometries),
               'sourceContourCount': len(contours),
               'contoursIntersectingStudy': sum(study.intersects(g) for g in contours),
               'nearestContourDistanceM': min((study.distance(g) for g in contours), default=None),
               'studyAreaM2': study.area, 'tinCoveredStudyFraction': study.intersection(tin.hull).area/study.area,
               'candidateCount': len(targets), 'interpolatedCandidateCount': sum(t['tin'] is not None for t in targets)}
    datasets = []
    for year in (2024, 2025):
        source = audit.ROOT/f'data/private/seongsu-official-20261017/dem-{year}.zip'
        with tempfile.TemporaryDirectory(prefix='waterleague-terrain-dem-') as directory:
            work = Path(directory)
            archive = audit.extract_checked(source, work/'dem', audit.EXPECTED[f'dem-{year}'])
            dem, rows = audit.dem(work/'dem/37705/37705.img')
        group = TransformerGroup(wkt, dem['crs']['originalWkt'], always_xy=True,
                                 area_of_interest=AreaOfInterest(*audit.BOUNDS), allow_ballpark=True)
        if not group.transformers:
            raise audit.SpatialDataError('DEM 좌표 변환 없음')
        transform = group.transformers[0]
        sampled = {'points': [], 'candidates': []}
        for kind, locations in (('points', points), ('candidates', targets)):
            for location in locations:
                xy = transform.transform(*location['coordinates'], errcheck=True)
                sample = sample_grid(dem, rows, xy)
                reference = location['value'] if kind == 'points' else (
                    location['tin']['rawValue'] if location['tin'] else None)
                sampled[kind].append({'id': location['id'], 'demCoordinates': xy, 'sample': sample,
                                     'referenceRawValue': reference,
                                     'demMinusReferenceRawValue': sample['rawValue']-reference
                                     if reference is not None and sample['rawValue'] is not None else None})
        if audit.digest(source) != archive['sha256']:
            raise audit.SpatialDataError('검사 중 DEM 원본 변경')
        datasets.append({'year': year, 'archive': archive, 'dem': dem,
                         'coordinateTransform': {'pipeline': transform.definition, 'description': transform.description,
                             'bestOperationAvailable': group.best_available, 'statedAccuracyM': transform.accuracy,
                             'usesBallpark': any(o.has_ballpark_transformation for o in transform.operations),
                             'verticalTransformation': False},
                         'samples': sampled, 'comparison': {kind: comparison_stats(values)
                                                           for kind, values in sampled.items()}})
    if audit.digest(candidate_path) != CANDIDATE_SHA or audit.digest(registry_path) != candidates['registrySha256']:
        raise audit.SpatialDataError('검사 중 후보·원본 목록 변경')
    return {'schemaVersion': 1, 'status': 'DIAGNOSTIC_ONLY', 'modelEligible': False,
            'mapId': 'seongsu-ngii-2025-v2', 'provider': registry['provider'], 'sourceUrl': registry['sourceUrl'],
            'inputHashes': {'registry': audit.digest(registry_path), 'candidates': CANDIDATE_SHA},
            'codeHashes': {Path(p).name: audit.digest(Path(p)) for p in (__file__, audit.__file__)},
            'versions': {'gdal': audit.command('gdalinfo', '--version').strip(), 'pyproj': pyproj.__version__,
                         'proj': pyproj.proj_version_str, 'shapely': shapely.__version__, 'geos': shapely.geos_version_string},
            'crs': crs, 'sources': sources, 'summary': summary, 'pointValues': points,
            'pointFeatures': records['points'],
            'contourValues': records['contours'], 'tin': tin.describe(), 'candidates': targets,
            'datasets': datasets, 'limitations': LIMITATIONS}


def public_summary(report):
    return {k: report[k] for k in ('schemaVersion', 'status', 'modelEligible', 'mapId', 'provider', 'sourceUrl',
                                  'inputHashes', 'codeHashes', 'versions', 'sources', 'summary', 'limitations')} | {
        'reportSha256': hashlib.sha256(bytes_for(report)).hexdigest(),
        'datasets': [{'year': d['year'], 'sourceSha256': d['archive']['sha256'],
                      'resolutionM': [d['dem']['geoTransform'][1], -d['dem']['geoTransform'][5]],
                      'bandUnit': d['dem']['bandUnit'], 'verticalDatum': d['dem']['verticalDatum'],
                      'acquisitionDate': d['dem']['acquisitionDate'],
                      'studyIntersectingCellCount': d['dem']['study']['intersectingCellCount'],
                      'comparison': d['comparison']} for d in report['datasets']]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--publish-summary', action='store_true')
    args = parser.parse_args()
    destination = Path(os.path.abspath(args.output))
    private = audit.ROOT/'data/private'
    if (destination == private or not destination.is_relative_to(private)
            or any(p.is_symlink() for p in (destination, *destination.parents))):
        raise audit.SpatialDataError('상세 보고서는 링크 없는 data/private 내부 경로 필요')
    report = build_report()
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with os.fdopen(os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as output:
        output.write(bytes_for(report))
    if args.publish_summary:
        payload = bytes_for(public_summary(report))
        for path in (audit.ROOT/'data/manifests/seongsu-terrain-support.json',
                     audit.ROOT/'frontend/public/data/seongsu-terrain-support.json'):
            if path.is_symlink() or path.exists() and path.read_bytes() != payload:
                raise audit.SpatialDataError('기존 공개 요약 변경 거부; 별도 버전 필요')
            if not path.exists():
                with path.open('xb') as stream:
                    stream.write(payload)
    print(json.dumps({'status': report['status'], 'reportSha256': audit.digest(destination),
                      'summary': report['summary']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
